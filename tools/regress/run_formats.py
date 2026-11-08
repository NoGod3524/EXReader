"""Multi-format SDK regression: pixels for stable samples, observations for partial support.

Each sample runs in a disposable process with a timeout. Only metadata/hashes are
persisted. Count-only entries never participate in pixel comparison.
"""
import argparse
import ctypes as c
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import time
import zipfile

from run_realbooks import (SDK, Bitmap, Error, FixedOptions, Options, file_hash,
                           pixel_hash, read_json, write_json)

STATUS = ['EXR_OK', 'EXR_ARGUMENT', 'EXR_MEMORY', 'EXR_IO', 'EXR_ENCODING',
          'EXR_FORMAT', 'EXR_LIMIT', 'EXR_DATABASE', 'EXR_FONT', 'EXR_CANCELLED',
          'EXR_PASSWORD', 'EXR_UNSUPPORTED']


class Glyph(c.Structure):
    _fields_ = [('start', c.c_size_t), ('end', c.c_size_t), ('codepoint', c.c_uint32),
                ('glyph', c.c_uint32)] + [(k, c.c_float) for k in ('x', 'baseline', 'advance', 'size')] + [
                ('page', c.c_size_t), ('node', c.c_size_t), ('color', c.c_uint32), ('flags', c.c_uint)] + [
                (k, c.c_float) for k in ('clip_left', 'clip_right', 'line_height')] + [
                ('cluster_start', c.c_size_t), ('cluster_end', c.c_size_t),
                ('boundaries', c.c_uint), ('font_index', c.c_size_t),
                ('offset_x', c.c_float), ('offset_y', c.c_float), ('bidi_level', c.c_uint)]


class Box(c.Structure):
    _fields_ = [('kind', c.c_int)] + [(k, c.c_size_t) for k in
                ('node', 'page', 'resource', 'start', 'end')] + [(k, c.c_float) for k in
                ('x', 'y', 'width', 'height', 'border_width')] + [
                ('background', c.c_uint32), ('border_color', c.c_uint32), ('flags', c.c_uint)]


class ProbeSDK(SDK):
    def __init__(self, path):
        super().__init__(path)
        ptr, size, out, err = c.c_void_p, c.c_size_t, c.POINTER(c.c_void_p), c.POINTER(Error)
        count = c.POINTER(size)
        signatures = {
            'document_text': (ptr, [ptr, count]),
            'document_find': (c.c_int, [ptr, c.c_char_p, size, count, count, err]),
            'layout_hit_test': (size, [ptr, size, c.c_float, c.c_float]),
            'layout_boxes': (c.POINTER(Box), [ptr, count]),
            'layout_glyphs': (c.POINTER(Glyph), [ptr, count]),
            'fixed_text_string': (ptr, [ptr, count]),
            'fixed_text_find': (c.c_int, [ptr, c.c_char_p, size, size, ptr, count, count, err]),
            'fixed_text_select': (c.c_int, [ptr, size, size, ptr, out, count, err]),
            'pcm_open': (c.c_int, [c.c_char_p, ptr, out, err]),
            'pcm_free': (None, [ptr]),
            'free': (None, [ptr]),
            'bitmap_write_png': (c.c_int, [c.POINTER(Bitmap), c.c_char_p, err]),
            'pdf_crypto_available': (c.c_int, []),
        }
        for name, (result, arguments) in signatures.items():
            f = getattr(self.dll, 'exr_' + name)
            f.restype, f.argtypes = result, arguments
            setattr(self, name, f)


def status_call(sdk, name, *args):
    error = Error()
    code = getattr(sdk, name)(*args, c.byref(error))
    return {'code': code, 'name': STATUS[code] if 0 <= code < len(STATUS) else 'unknown'}


def measure(book, dll, font_path, layout, preview=None, checkpoint=None):
    sdk = ProbeSDK(dll)
    r = {k: v for k, v in book.items() if k != 'path'}
    r.update(status='error', pages=[], page_count=0, glyph_count=0, image_boxes=0,
             text_bytes=0, selection=None, first_screen=None, open=None)
    handles = {k: c.c_void_p() for k in ('font', 'publication', 'document', 'pager', 'layout', 'fixed', 'fixed_text')}
    bitmap = Bitmap()
    started = time.perf_counter()
    stage = 'source_hash'
    try:
        if file_hash(book['path']) != book['sha256']:
            raise ValueError('source SHA-256 mismatch')
        sdk.check('font_open', str(font_path).encode(), c.byref(handles['font']))

        def call(name, *args):
            nonlocal stage
            stage = name
            return sdk.check(name, *args)

        def save_progress():
            if checkpoint:
                write_json(checkpoint, r | {'stage': stage, 'rendered_page_count': len(r['pages'])})

        def record(part, local, glyphs):
            pixels = c.string_at(bitmap.pixels, bitmap.stride * bitmap.height)
            p = dict(page=len(r['pages']), part=part, part_page=local, width=bitmap.width,
                     height=bitmap.height, channels=bitmap.channels, glyph_count=glyphs)
            if book['regression'] == 'hash':
                p['pixel_sha256'] = pixel_hash(bitmap)
            if not r['pages']:
                r['first_screen'] = dict(width=bitmap.width, height=bitmap.height,
                                         nonwhite_components=len(pixels) - pixels.count(255), code=0)
                if preview:
                    call('bitmap_write_png', c.byref(bitmap), str(preview).encode())
            r['pages'].append(p)
            sdk.bitmap_free(c.byref(bitmap))

        fixed = Path(book['path']).suffix.lower() in ('.pdf', '.cbz')
        if fixed:
            options = FixedOptions()
            options.struct_size, options.fallback_font = c.sizeof(options), handles['font']
            # Deliberately try missing and incorrect passwords before the supplied password.
            if book.get('password_env'):
                r['without_password'] = status_call(sdk, 'fixed_open', book['path'].encode(), c.byref(options), c.byref(handles['fixed']))
                sdk.fixed_free(handles['fixed']); handles['fixed'] = c.c_void_p()
                wrong = c.create_string_buffer(b'intentionally-wrong')
                options.pdf_password, options.pdf_password_size = c.addressof(wrong), len(wrong.value)
                r['wrong_password'] = status_call(sdk, 'fixed_open', book['path'].encode(), c.byref(options), c.byref(handles['fixed']))
                sdk.fixed_free(handles['fixed']); handles['fixed'] = c.c_void_p()
                password = c.create_string_buffer(os.environ[book['password_env']].encode())
                options.pdf_password, options.pdf_password_size = c.addressof(password), len(password.value)
            stage = 'fixed_open'
            r['open'] = status_call(sdk, 'fixed_open', book['path'].encode(), c.byref(options), c.byref(handles['fixed']))
            if r['open']['code']:
                raise RuntimeError('open failed')
            n = c.c_size_t()
            directory = sdk.fixed_pages(handles['fixed'], c.byref(n))
            r['source_page_count'] = n.value
            r['page_count'] = n.value
            stage = 'fixed_render'
            save_progress()
            for index in range(min(n.value, book.get('max_render_pages', n.value))):
                r['active_page'] = index
                g = directory[index].geometry
                width, height = ((g.bounds[2] - g.bounds[0]) * g.unit_scale,
                                 (g.bounds[3] - g.bounds[1]) * g.unit_scale)
                scale = min(1, layout['fixed_max_dimension'] / max(width, height))
                if index == 0:
                    first_scale = scale
                call('fixed_render', handles['fixed'], index, scale, None, c.byref(bitmap))
                if index == 0:
                    r['native_page_size'] = [width, height]
                call('fixed_load_text', handles['fixed'], index, None, c.byref(handles['fixed_text']))
                count, length = c.c_size_t(), c.c_size_t()
                sdk.fixed_text_regions(handles['fixed_text'], c.byref(count))
                data = sdk.fixed_text_string(handles['fixed_text'], c.byref(length))
                r['text_bytes'] += length.value
                if not length.value and 'empty_text_probe' not in r:
                    a, b, selected, regions = c.c_size_t(), c.c_size_t(), c.c_void_p(), c.c_size_t()
                    found = status_call(sdk, 'fixed_text_find', handles['fixed_text'], b'probe', 5, 0, None, c.byref(a), c.byref(b))
                    selected_status = status_call(sdk, 'fixed_text_select', handles['fixed_text'], 0, 1, None, c.byref(selected), c.byref(regions))
                    r['empty_text_probe'] = dict(page=index, search=found, matched=a.value < b.value,
                                                 select=selected_status, regions=regions.value)
                    sdk.free(selected)
                if length.value and count.value and r['selection'] is None:
                    raw = c.string_at(data, length.value)
                    query = raw.decode('utf-8')[:1].encode('utf-8')
                    a, b, selected, regions = c.c_size_t(), c.c_size_t(), c.c_void_p(), c.c_size_t()
                    found = status_call(sdk, 'fixed_text_find', handles['fixed_text'], query, len(query), 0, None, c.byref(a), c.byref(b))
                    selected_status = status_call(sdk, 'fixed_text_select', handles['fixed_text'], a, b, None, c.byref(selected), c.byref(regions))
                    r['selection'] = dict(page=index, search=found, select=selected_status, regions=regions.value)
                    sdk.free(selected)
                sdk.fixed_text_free(handles['fixed_text']); handles['fixed_text'] = c.c_void_p()
                record(0, index, count.value)
            if n.value:
                call('fixed_render', handles['fixed'], 0, first_scale * 2, None, c.byref(bitmap))
                r['zoom_2x'] = dict(width=bitmap.width, height=bitmap.height, code=0)
                sdk.bitmap_free(c.byref(bitmap))
        else:
            config = sdk.layout_config_defaults()
            config.page = Options(**{key: layout[key] for key, _ in Options._fields_})
            for key in ('document_css', 'embedded_fonts', 'direction'):
                setattr(config, key, layout[key])
            parts = c.c_size_t(1)
            epub = Path(book['path']).suffix.lower() == '.epub'
            name = 'publication_open' if epub else 'document_open'
            stage = name
            r['open'] = status_call(sdk, name, book['path'].encode(), c.byref(handles['publication' if epub else 'document']))
            if r['open']['code']:
                raise RuntimeError('open failed')
            if epub:
                sdk.publication_parts(handles['publication'], c.byref(parts))
                probe = c.c_void_p()
                options = FixedOptions(); options.struct_size = c.sizeof(options)
                r['fixed_entry'] = status_call(sdk, 'fixed_open', book['path'].encode(), c.byref(options), c.byref(probe))
                sdk.fixed_free(probe)
                if 'audio' in book['category']:
                    r['epub_pcm_entry'] = status_call(sdk, 'pcm_open', book['path'].encode(), None, c.byref(probe))
                    sdk.pcm_free(probe)
                    r['audio_assets'] = []
                    with zipfile.ZipFile(book['path']) as archive, tempfile.TemporaryDirectory(prefix='exr-media-') as tmp:
                        for member in archive.namelist():
                            if member.lower().endswith(('.mp3', '.mp4', '.m4a', '.wav')) and '/video/' not in member:
                                asset = Path(tmp) / Path(member).name
                                asset.write_bytes(archive.read(member))
                                probe = c.c_void_p()
                                status = status_call(sdk, 'pcm_open', str(asset).encode(), None, c.byref(probe))
                                sdk.pcm_free(probe)
                                r['audio_assets'].append(dict(member=member, sha256=file_hash(asset), open=status))
            r['part_count'] = parts.value
            for part in range(parts.value):
                if epub:
                    call('publication_load', handles['publication'], part, c.byref(handles['document']))
                length = c.c_size_t()
                pointer = sdk.document_text(handles['document'], c.byref(length))
                raw = c.string_at(pointer, length.value) if length.value else b''
                r['text_bytes'] += length.value
                if not epub:
                    normalized = ' '.join(raw.decode('utf-8').split()).encode('utf-8')
                    r['normalized_text_sha256'] = hashlib.sha256(normalized).hexdigest()
                    r['text_matches_source'] = r['normalized_text_sha256'] == book.get('expected_text_sha256')
                    r['replacement_characters'] = raw.count(b'\xef\xbf\xbd')
                call('pager_create', handles['document'], handles['font'], c.byref(config), c.byref(handles['pager']))
                local = 0
                while True:
                    call('pager_next', handles['pager'], c.byref(handles['layout']))
                    page = handles['layout']
                    if not page:
                        break
                    count = c.c_size_t()
                    glyphs = sdk.layout_glyphs(page, c.byref(count))
                    if count.value and r['selection'] is None:
                        glyph = glyphs[0]
                        a, b = c.c_size_t(), c.c_size_t()
                        query = raw[glyph.start:glyph.end]
                        found = status_call(sdk, 'document_find', handles['document'], query, 0, c.byref(a), c.byref(b))
                        hit = sdk.layout_hit_test(page, 0, glyph.x + glyph.advance / 2, glyph.baseline - glyph.size / 2)
                        r['selection'] = dict(part=part, page=len(r['pages']), search=found,
                                              search_matched=a.value < b.value <= length.value,
                                              source_range=[glyph.start, glyph.end], hit=hit,
                                              hit_in_source=hit < length.value)
                    boxes = c.c_size_t()
                    array = sdk.layout_boxes(page, c.byref(boxes))
                    r['image_boxes'] += sum(array[i].kind == 2 and not array[i].flags & 1 for i in range(boxes.value))
                    call('render_page_color', page, sdk.layout_font(page), 0, c.byref(bitmap))
                    record(part, local, count.value)
                    sdk.layout_free(page); handles['layout'] = c.c_void_p()
                    local += 1
                sdk.pager_free(handles['pager']); handles['pager'] = c.c_void_p()
                sdk.document_free(handles['document']); handles['document'] = c.c_void_p()
        if file_hash(book['path']) != book['sha256']:
            raise ValueError('source changed while rendering')
        r['status'] = 'ok'
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        # SDK messages can contain publication text: retain stage and status only.
        message = str(exc)
        code = int(message.split('status=')[1]) if 'status=' in message else (r.get('open') or {}).get('code')
        r['error'] = dict(stage=stage, code=code, kind=type(exc).__name__)
        if 'active_page' in r:
            r['error']['page'] = r['active_page']
    finally:
        sdk.bitmap_free(c.byref(bitmap))
        for kind, handle in handles.items():
            getattr(sdk, kind + '_free')(handle)
    r['rendered_page_count'] = len(r['pages'])
    r.pop('active_page', None)
    r['page_count'] = r.get('source_page_count', len(r['pages']))
    r['glyph_count'] = sum(p['glyph_count'] for p in r['pages'])
    r['elapsed_seconds'] = round(time.perf_counter() - started, 6)
    return r


def compare(old, new):
    conditions = ('schema', 'pixel_contract', 'layout', 'alternate_layout', 'font_sha256', 'environment')
    incompatible = [k for k in conditions if old.get(k) != new.get(k)]
    before, after = ({b['id']: b for b in run['books']} for run in (old, new))
    report = dict(comparable=not incompatible, incompatible_conditions=incompatible,
                  added_books=sorted(after.keys() - before.keys()), removed_books=sorted(before.keys() - after.keys()), books=[])
    for id in sorted(before.keys() & after.keys()):
        a, b = before[id], after[id]
        fields = ['sha256', 'regression', 'status', 'open', 'error', 'page_count', 'glyph_count',
                  'first_screen', 'selection', 'image_boxes', 'text_bytes', 'normalized_text_sha256',
                  'text_matches_source', 'fixed_entry', 'epub_pcm_entry',
                  'without_password', 'wrong_password', 'zoom_2x', 'alternate', 'audio_assets',
                  'rendered_page_count', 'max_render_pages', 'empty_text_probe']
        changed = [k for k in fields if a.get(k) != b.get(k)]
        hashes = []
        if a['regression'] == b['regression'] == 'hash':
            ap, bp = a['pages'], b['pages']
            hashes = [i for i in range(max(len(ap), len(bp))) if
                      i >= len(ap) or i >= len(bp) or ap[i] != bp[i]]
        observations = []
        if a['regression'] == b['regression'] == 'count':
            observations = [k for k in changed if k not in ('sha256', 'regression', 'status', 'open', 'error')]
            changed = [k for k in changed if k not in observations]
        report['books'].append(dict(id=id, changed_fields=changed, observed_changes=observations, hash_changed_pages=hashes))
    report['hash_changed_pages'] = sum(len(b['hash_changed_pages']) for b in report['books'])
    report['needs_review'] = bool(incompatible or report['added_books'] or report['removed_books'] or
                                  any(b['changed_fields'] or b['hash_changed_pages'] for b in report['books']))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ('manifest', 'dll', 'font', 'layout', 'output', 'baseline', 'candidate', 'preview-dir'):
        parser.add_argument('--' + arg, type=Path)
    parser.add_argument('--source-revision')
    parser.add_argument('--timeout', type=int, default=240)
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--checkpoint', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not args.output:
        parser.error('--output is required')
    if args.candidate:
        if not args.baseline:
            parser.error('--candidate requires --baseline')
        diff = compare(read_json(args.baseline), read_json(args.candidate))
        write_json(args.output, diff)
        return 2 if not diff['comparable'] else int(diff['needs_review'])
    if not all((args.manifest, args.dll, args.font, args.layout, args.source_revision)):
        parser.error('render requires --manifest --dll --font --layout --source-revision')
    books, layout = read_json(args.manifest)['books'], read_json(args.layout)
    required = {key for key, _ in Options._fields_} | {'fixed_max_dimension', 'document_css', 'embedded_fonts', 'direction'}
    if set(layout) != required or any(not isinstance(layout[k], (float, int)) or not math.isfinite(layout[k]) for k in required):
        parser.error('layout must contain exactly the finite numeric layout fields')
    if args.timeout < 1 or any(layout[k] <= 0 for k in ('width', 'height', 'font_size', 'line_height', 'fixed_max_dimension')):
        parser.error('timeout, dimensions, font size and line height must be positive')
    if any(layout[k] != int(layout[k]) for k in ('width', 'height')) or layout['margin'] < 0:
        parser.error('width/height must be integers; margin must be nonnegative')
    if layout['document_css'] not in (0, 1) or layout['embedded_fonts'] not in (0, 1) or layout['direction'] not in (0, 1, 2):
        parser.error('invalid CSS/font/direction option')
    if not books or len({b['id'] for b in books}) != len(books):
        parser.error('nonempty manifest with unique IDs required')
    for b in books:
        if b['regression'] not in ('hash', 'count'):
            parser.error('regression must be hash or count')
        if b.get('max_render_pages') is not None and (b['regression'] != 'count' or b['max_render_pages'] < 1):
            parser.error('max_render_pages requires count policy and a positive limit')
        p = Path(b['path'])
        b['path'] = str((args.manifest.parent / p).resolve() if not p.is_absolute() else p)
    alternate = dict(layout, width=480, height=800, font_size=36)
    if args.preview_dir:
        if args.preview_dir.resolve().is_relative_to(Path(__file__).resolve().parents[2]):
            parser.error('previews must be outside repository')
        args.preview_dir.mkdir(parents=True, exist_ok=True)
    if args.worker:
        book = books[0]
        result = measure(book, args.dll, args.font, layout,
                         args.preview_dir / (book['id'] + '.png') if args.preview_dir else None, args.checkpoint)
        # Preserve the completed primary run even if the alternate layout times out.
        if args.checkpoint:
            write_json(args.checkpoint, result | {'stage': 'alternate'})
        alt = measure(dict(book, regression='count'), args.dll, args.font, alternate)
        result['alternate'] = {k: alt.get(k) for k in ('status', 'page_count', 'glyph_count', 'first_screen', 'error')}
        write_json(args.output, result)
        return 0
    sdk = ProbeSDK(args.dll.resolve())
    run = dict(schema=1, created_utc=datetime.now(timezone.utc).isoformat(), source_revision=args.source_revision,
               engine_version=sdk.version().decode(), abi_version=sdk.abi_version(), dll_sha256=file_hash(args.dll),
               driver_sha256=file_hash(__file__), shared_driver_sha256=file_hash(Path(__file__).with_name('run_realbooks.py')),
               font_sha256=file_hash(args.font), layout=layout, alternate_layout=alternate,
               pixel_contract='sha256/visible-row-major-RGBA8/white/v1',
               environment=dict(system=platform.system(), machine=platform.machine()),
               pdf_crypto_available=bool(sdk.pdf_crypto_available()), books=[])
    for book in books:
        with tempfile.TemporaryDirectory(prefix='exr-formats-') as temp:
            inp, out, checkpoint = Path(temp) / 'input.json', Path(temp) / 'result.json', Path(temp) / 'progress.json'
            write_json(inp, {'books': [book]})
            command = [sys.executable, __file__, '--worker', '--manifest', str(inp), '--output', str(out),
                       '--dll', str(args.dll.resolve()), '--font', str(args.font.resolve()),
                       '--layout', str(args.layout.resolve()), '--source-revision', args.source_revision]
            command += ['--checkpoint', str(checkpoint)]
            if args.preview_dir:
                command += ['--preview-dir', str(args.preview_dir.resolve())]
            try:
                process = subprocess.run(command, timeout=args.timeout, capture_output=True,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                if process.returncode:
                    raise RuntimeError(f'worker_exit={process.returncode}')
                value = read_json(out)
            except (subprocess.TimeoutExpired, RuntimeError) as exc:
                value = read_json(checkpoint) if checkpoint.exists() else {k: v for k, v in book.items() if k != 'path'}
                value.setdefault('page_count', 0)
                value.setdefault('glyph_count', 0)
                value.setdefault('pages', [])
                value.update(status='error', error=dict(stage=value.pop('stage', 'worker'),
                             code='RUNNER_TIMEOUT' if isinstance(exc, subprocess.TimeoutExpired) else 'RUNNER_EXIT',
                             exit_code=process.returncode if isinstance(exc, RuntimeError) else None,
                             kind=type(exc).__name__))
            run['books'].append(value)
            print(book['id'], value['status'], value['page_count'], value.get('error', ''), flush=True)
    run['summary'] = dict(samples=len(books), rendered=sum(b['status'] == 'ok' for b in run['books']),
                          hash_samples=sum(b['regression'] == 'hash' for b in books),
                          count_only_samples=sum(b['regression'] == 'count' for b in books),
                          total_pages=sum(b['page_count'] for b in run['books']))
    write_json(args.output, run)
    if args.baseline:
        diff = compare(read_json(args.baseline), run)
        write_json(args.output.with_suffix('.diff.json'), diff)
        return 2 if not diff['comparable'] else int(diff['needs_review'])
    return int(any(b['status'] != 'ok' for b in run['books'] if b['regression'] == 'hash'))


if __name__ == '__main__':
    sys.exit(main())
