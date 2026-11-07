"""Render every page through the public SDK; retain only counts and pixel hashes."""
import argparse
import concurrent.futures
import ctypes as c
from datetime import datetime, timezone
import hashlib
import json
import math
import multiprocessing
import os
from pathlib import Path
import platform
import sys
import time


class Error(c.Structure):
    _fields_ = [('code', c.c_int), ('message', c.c_char * 256)]


class Bitmap(c.Structure):
    _fields_ = [('width', c.c_uint32), ('height', c.c_uint32),
                ('stride', c.c_uint32), ('pixels', c.c_void_p), ('channels', c.c_uint32)]


class Options(c.Structure):
    _fields_ = [(k, c.c_float) for k in
                ('width', 'height', 'margin', 'font_size', 'line_height', 'paragraph_spacing')]


class Control(c.Structure):
    _fields_ = [('cancelled', c.c_void_p), ('progress', c.c_void_p), ('context', c.c_void_p)]


class Config(c.Structure):
    _fields_ = [('page', Options), ('user_css', c.c_char_p), ('document_css', c.c_int),
                ('decode_image', c.c_void_p), ('release_image', c.c_void_p),
                ('image_context', c.c_void_p), ('direction', c.c_int),
                ('embedded_fonts', c.c_int), ('control', Control)]


class FixedOptions(c.Structure):
    _fields_ = [('struct_size', c.c_size_t), ('fallback_font', c.c_void_p),
                ('control', Control), ('pdf_password', c.c_void_p),
                ('pdf_password_size', c.c_size_t), ('pdf_security', c.c_void_p)]


class Geometry(c.Structure):
    _fields_ = [('bounds', c.c_double * 4), ('unit_scale', c.c_double),
                ('rotation', c.c_uint), ('y_down', c.c_uint)]


class FixedPage(c.Structure):
    _fields_ = [('id', c.c_char_p), ('label', c.c_char_p), ('geometry', Geometry)]


def file_hash(path):
    with open(path, 'rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


class SDK:
    def __init__(self, path):
        # Keep the DLL directory handle alive for dependent DLL resolution on Windows.
        self.directory = os.add_dll_directory(str(Path(path).parent)) if os.name == 'nt' else None
        self.dll = c.CDLL(str(path))  # public API uses cdecl, including on Windows
        ptr, size, err = c.c_void_p, c.c_size_t, c.POINTER(Error)
        out, count = c.POINTER(ptr), c.POINTER(size)
        signatures = {
            'version': (c.c_char_p, []),
            'abi_version': (c.c_uint32, []),
            'layout_config_defaults': (Config, []),
            'font_open': (c.c_int, [c.c_char_p, out, err]),
            'document_open': (c.c_int, [c.c_char_p, out, err]),
            'publication_open': (c.c_int, [c.c_char_p, out, err]),
            'publication_parts': (ptr, [ptr, count]),
            'publication_load': (c.c_int, [ptr, size, out, err]),
            'pager_create': (c.c_int, [ptr, ptr, c.POINTER(Config), out, err]),
            'pager_next': (c.c_int, [ptr, out, err]),
            'layout_font': (ptr, [ptr]),
            'layout_glyphs': (ptr, [ptr, count]),
            'render_page_color': (c.c_int, [ptr, ptr, size, c.POINTER(Bitmap), err]),
            'bitmap_free': (None, [c.POINTER(Bitmap)]),
            'fixed_open': (c.c_int, [c.c_char_p, c.POINTER(FixedOptions), out, err]),
            'fixed_pages': (c.POINTER(FixedPage), [ptr, count]),
            'fixed_render': (c.c_int, [ptr, size, c.c_double, ptr, c.POINTER(Bitmap), err]),
            'fixed_load_text': (c.c_int, [ptr, size, ptr, out, err]),
            'fixed_text_regions': (ptr, [ptr, count]),
        }
        for kind in ('font', 'document', 'publication', 'pager', 'layout', 'fixed', 'fixed_text'):
            signatures[kind + '_free'] = (None, [ptr])
        for name, (result, arguments) in signatures.items():
            function = getattr(self.dll, 'exr_' + name)
            function.restype, function.argtypes = result, arguments
            setattr(self, name, function)

    def check(self, name, *arguments):
        error = Error()
        status = getattr(self, name)(*arguments, c.byref(error))
        if status:
            # Engine diagnostics can quote book contents; persist only stage/status.
            raise RuntimeError(f'exr_{name}: status={status}')


def pixel_hash(bitmap):
    if not bitmap.pixels or not bitmap.width or not bitmap.height or bitmap.channels != 4:
        raise ValueError('invalid RGBA bitmap')
    row_bytes = bitmap.width * bitmap.channels
    if bitmap.stride < row_bytes:
        raise ValueError('invalid bitmap stride')
    digest = hashlib.sha256()
    # Hash visible row bytes only: allocator padding is outside the image contract.
    if bitmap.stride == row_bytes:
        digest.update(c.string_at(bitmap.pixels, row_bytes * bitmap.height))
    else:
        for row in range(bitmap.height):
            digest.update(c.string_at(bitmap.pixels + row * bitmap.stride, row_bytes))
    return digest.hexdigest()


def render_book(book, dll, font_path, layout):
    started = time.perf_counter()
    result = {k: book[k] for k in ('id', 'filename', 'language', 'sha256') if k in book}
    result.update(status='error', pages=[], page_count=0, glyph_count=0)
    sdk = None
    font, publication, document, pager, page, fixed, text = [c.c_void_p() for _ in range(7)]
    bitmap = Bitmap()
    try:
        source = Path(book['path'])
        if not source.is_file():
            result['status'] = 'missing'
            result['error'] = 'corpus file not found'
            return result
        actual = file_hash(source)
        result['sha256'] = actual
        if book.get('sha256') and book['sha256'] != actual:
            raise ValueError('corpus SHA-256 differs from manifest')
        sdk = SDK(dll)
        sdk.check('font_open', str(font_path).encode('utf-8'), c.byref(font))

        def record(part, local_page, glyphs):
            result['pages'].append({
                'page': len(result['pages']), 'part': part, 'part_page': local_page,
                'width': bitmap.width, 'height': bitmap.height, 'channels': bitmap.channels,
                'glyph_count': glyphs, 'pixel_sha256': pixel_hash(bitmap),
                'elapsed_seconds': round(time.perf_counter() - page_started, 6),
            })
            sdk.bitmap_free(c.byref(bitmap))

        if source.suffix.lower() in ('.pdf', '.cbz'):
            options = FixedOptions()
            options.struct_size, options.fallback_font = c.sizeof(options), font
            sdk.check('fixed_open', str(source).encode('utf-8'), c.byref(options), c.byref(fixed))
            count = c.c_size_t()
            source_pages = sdk.fixed_pages(fixed, c.byref(count))
            if count.value and not source_pages:
                raise ValueError('missing fixed page directory')
            result['glyph_count_kind'] = 'mapped_pdf_text_regions'
            result['part_count'] = 1
            for index in range(count.value):
                page_started = time.perf_counter()
                geometry = source_pages[index].geometry
                width = (geometry.bounds[2] - geometry.bounds[0]) * geometry.unit_scale
                height = (geometry.bounds[3] - geometry.bounds[1]) * geometry.unit_scale
                if not all(math.isfinite(n) and n > 0 for n in (width, height)):
                    raise ValueError('invalid fixed page geometry')
                scale = min(1, layout['fixed_max_dimension'] / max(width, height))
                sdk.check('fixed_render', fixed, index, scale, None, c.byref(bitmap))
                sdk.check('fixed_load_text', fixed, index, None, c.byref(text))
                glyphs = c.c_size_t()
                sdk.fixed_text_regions(text, c.byref(glyphs))
                sdk.fixed_text_free(text)
                text = c.c_void_p()
                record(0, index, glyphs.value)
        else:
            config = sdk.layout_config_defaults()
            config.page = Options(**{key: layout[key] for key, _ in Options._fields_})
            config.document_css = layout['document_css']
            config.embedded_fonts = layout['embedded_fonts']
            config.direction = layout['direction']
            parts = c.c_size_t(1)
            if source.suffix.lower() == '.epub':
                sdk.check('publication_open', str(source).encode('utf-8'), c.byref(publication))
                sdk.publication_parts(publication, c.byref(parts))
            else:
                sdk.check('document_open', str(source).encode('utf-8'), c.byref(document))
            result['part_count'] = parts.value
            result['glyph_count_kind'] = 'layout_glyphs'
            for part in range(parts.value):
                if publication:
                    sdk.check('publication_load', publication, part, c.byref(document))
                sdk.check('pager_create', document, font, c.byref(config), c.byref(pager))
                local_page = 0
                while True:
                    page_started = time.perf_counter()
                    sdk.check('pager_next', pager, c.byref(page))
                    if not page:
                        break
                    glyphs = c.c_size_t()
                    sdk.layout_glyphs(page, c.byref(glyphs))
                    sdk.check('render_page_color', page, sdk.layout_font(page), 0, c.byref(bitmap))
                    if (bitmap.width, bitmap.height) != (layout['width'], layout['height']):
                        raise ValueError('unexpected reflow bitmap dimensions')
                    record(part, local_page, glyphs.value)
                    sdk.layout_free(page)
                    page = c.c_void_p()
                    local_page += 1
                sdk.pager_free(pager)
                pager = c.c_void_p()
                sdk.document_free(document)
                document = c.c_void_p()
        # Detect a source changed while it was being rendered.
        if file_hash(source) != actual:
            raise ValueError('corpus changed during rendering')
        result['status'] = 'ok'
    except (OSError, ValueError, RuntimeError) as exc:
        result['error'] = str(exc)
    finally:
        if sdk:
            sdk.bitmap_free(c.byref(bitmap))
            for kind, handle in [('layout', page), ('pager', pager), ('document', document),
                                 ('fixed_text', text), ('fixed', fixed),
                                 ('publication', publication), ('font', font)]:
                getattr(sdk, kind + '_free')(handle)
        result['page_count'] = len(result['pages'])
        result['glyph_count'] = sum(p['glyph_count'] for p in result['pages'])
        result['elapsed_seconds'] = round(time.perf_counter() - started, 6)
    return result


def compare(old, new):
    """Compare global zero-based page ordinals; counts alone are informational."""
    conditions = ('schema', 'pixel_contract', 'layout', 'font_sha256', 'environment')
    incompatible = [key for key in conditions if old.get(key) != new.get(key)]
    before = {b['id']: b for b in old['books']}
    after = {b['id']: b for b in new['books']}
    report = {'comparable': not incompatible, 'incompatible_conditions': incompatible,
              'added_books': sorted(after.keys() - before.keys()),
              'removed_books': sorted(before.keys() - after.keys()), 'books': []}
    for key in sorted(before.keys() & after.keys()):
        a, b = before[key], after[key]
        ap = {p['page']: p for p in a['pages']}
        bp = {p['page']: p for p in b['pages']}
        changed = [i for i in sorted(ap.keys() & bp.keys())
                   if any(ap[i][k] != bp[i][k] for k in
                          ('pixel_sha256', 'width', 'height', 'channels'))]
        report['books'].append({
            'id': key, 'old_status': a['status'], 'new_status': b['status'],
            'source_changed': a.get('sha256') != b.get('sha256'),
            'old_page_count': a['page_count'], 'new_page_count': b['page_count'],
            'page_count_changed': a['page_count'] != b['page_count'],
            'glyph_count_changed': a['glyph_count'] != b['glyph_count'],
            'added_pages': sorted(bp.keys() - ap.keys()),
            'removed_pages': sorted(ap.keys() - bp.keys()), 'hash_changed_pages': changed,
        })
    report['hash_changed_pages'] = sum(len(b['hash_changed_pages']) for b in report['books'])
    report['failed_books'] = [b['id'] for b in new['books'] if b['status'] != 'ok']
    report['needs_review'] = bool(incompatible or report['added_books'] or report['removed_books']
                                  or report['failed_books'] or any(
        b['source_changed'] or b['page_count_changed'] or b['glyph_count_changed']
        or b['added_pages'] or b['removed_pages'] or b['hash_changed_pages']
        for b in report['books']))
    return report


def fingerprint(books):
    # Timing and scheduling order are deliberately excluded from determinism checks.
    values = [{k: b[k] for k in ('id', 'sha256', 'status', 'page_count', 'glyph_count')} |
              {'pages': [{k: v for k, v in p.items() if k != 'elapsed_seconds'} for p in b['pages']]}
              for b in books]
    return hashlib.sha256(json.dumps(values, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--dll', type=Path, help='aggregate SDK DLL/shared library (cdecl)')
    parser.add_argument('--font', type=Path)
    parser.add_argument('--layout', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--baseline', type=Path, help='old baseline to compare')
    parser.add_argument('--candidate', type=Path, help='compare existing JSON without rendering')
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--source-revision', help='revision actually used to build the supplied DLL')
    args = parser.parse_args()
    if args.candidate:
        if not args.baseline:
            parser.error('--candidate requires --baseline')
        diff = compare(read_json(args.baseline), read_json(args.candidate))
        write_json(args.output, diff)
        print(json.dumps({k: v for k, v in diff.items() if k != 'books'}), flush=True)
        return 2 if not diff['comparable'] else int(diff['needs_review'])
    if not all((args.manifest, args.dll, args.font, args.layout, args.source_revision)):
        parser.error('render requires --manifest --dll --font --layout --source-revision')
    if args.workers < 1:
        parser.error('--workers must be positive')
    manifest, layout = read_json(args.manifest), read_json(args.layout)
    required = {k for k, _ in Options._fields_} | {'fixed_max_dimension', 'document_css', 'embedded_fonts', 'direction'}
    if set(layout) != required or any(not isinstance(layout[k], (int, float)) or
                                      not math.isfinite(layout[k]) for k in required):
        parser.error('layout must contain exactly the documented finite numeric fields')
    if any(layout[k] <= 0 for k in ('width', 'height', 'font_size', 'line_height', 'fixed_max_dimension')):
        parser.error('layout dimensions/font_size/line_height must be positive')
    if any(layout[k] != int(layout[k]) for k in ('width', 'height')) or layout['margin'] < 0:
        parser.error('width/height must be integers; margin must be nonnegative')
    if layout['document_css'] not in (0, 1) or layout['embedded_fonts'] not in (0, 1) or layout['direction'] not in (0, 1, 2):
        parser.error('invalid CSS/font/direction option')
    books = manifest['books']
    if not books or len({b['id'] for b in books}) != len(books):
        parser.error('manifest must have nonempty books with unique IDs')
    for book in books:
        path = Path(book['path'])
        book['path'] = str((args.manifest.parent / path).resolve()) if not path.is_absolute() else str(path)
        book.setdefault('filename', Path(book['path']).name)
    dll, font = args.dll.resolve(strict=True), args.font.resolve(strict=True)
    sdk = SDK(dll)
    started = time.perf_counter()
    baseline = {
        'schema': 1, 'created_utc': datetime.now(timezone.utc).isoformat(),
        'source_revision': args.source_revision, 'engine_version': sdk.version().decode(),
        'abi_version': sdk.abi_version(), 'dll_sha256': file_hash(dll),
        'driver_sha256': file_hash(__file__), 'font_sha256': file_hash(font),
        'layout': layout, 'pixel_contract': 'sha256/visible-row-major-RGBA8/white/v1',
        'environment': {'system': platform.system(), 'machine': platform.machine()},
        'python': platform.python_version(), 'workers': args.workers, 'books': [],
    }
    results = {}
    with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers,
            mp_context=multiprocessing.get_context('spawn')) as pool:
        pending = {pool.submit(render_book, b, dll, font, layout): b for b in books}
        for future in concurrent.futures.as_completed(pending):
            book = pending[future]
            try:
                value = future.result()
            except Exception as exc:
                value = {k: book[k] for k in ('id', 'filename', 'sha256') if k in book}
                value.update(status='error', error=type(exc).__name__, pages=[],
                             page_count=0, glyph_count=0, elapsed_seconds=0)
            results[book['id']] = value
            print(f"{value['status']}: {book['id']}: {value['page_count']} pages, "
                  f"{value['elapsed_seconds']:.3f}s", flush=True)
    baseline['books'] = [results[b['id']] for b in books]
    baseline['content_fingerprint'] = fingerprint(baseline['books'])
    successful = [b for b in baseline['books'] if b['status'] == 'ok']
    baseline['summary'] = {
        'requested_books': len(books), 'successful_books': len(successful),
        'failed_books': [b['id'] for b in baseline['books'] if b['status'] != 'ok'],
        'total_pages': sum(b['page_count'] for b in baseline['books']),
        'total_glyphs': sum(b['glyph_count'] for b in baseline['books']),
        'wall_seconds': round(time.perf_counter() - started, 6),
        'sum_book_seconds': round(sum(b['elapsed_seconds'] for b in baseline['books']), 6),
        'fastest_book': min(successful, key=lambda b: b['elapsed_seconds'])['id'] if successful else None,
        'slowest_book': max(successful, key=lambda b: b['elapsed_seconds'])['id'] if successful else None,
    }
    write_json(args.output, baseline)
    if args.baseline:
        diff = compare(read_json(args.baseline), baseline)
    else:
        diff = {'initial_baseline': True, 'needs_review': bool(baseline['summary']['failed_books']),
                'failed_books': baseline['summary']['failed_books'], 'hash_changed_pages': 0}
    write_json(args.output.with_name(args.output.stem + '.diff.json'), diff)
    print(json.dumps(baseline['summary']), flush=True)
    return 2 if diff.get('comparable') is False else int(diff['needs_review'])


if __name__ == '__main__':
    sys.exit(main())
