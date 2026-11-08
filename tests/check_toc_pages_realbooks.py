"""Acceptance audit of synthetic TOC pages on real EPUBs (books stay local).

Per book: build the labels from real body pagination, create the TOC pages,
render them, hash them, verify leader dots / right-aligned labels / indentation
from the layout geometry, click-test sampled entries through the ordinary
hit-test -> exr_publication_locate path, and prove full-text search skips them.
Run with --dll --manifest --font --layout --output [--png-dir DIR].
"""
import argparse
import ctypes as c
import hashlib
import json
from pathlib import Path
import struct
import sys
import xml.etree.ElementTree as ET
import zipfile
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools' / 'regress'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_realbooks import Bitmap, SDK, Error, file_hash, pixel_hash, read_json, write_json
from check_toc_realbooks import Toc, Target, Location, Line, bind, expected_offset, SIZE_MAX

SOURCES = ['host', 'nav', 'ncx', 'recovered']


class Page(c.Structure):
    _fields_ = [(k, c.c_size_t) for k in ('start', 'end', 'line_start', 'line_count', 'box_start', 'box_count')]


class Glyph(c.Structure):
    _fields_ = [('start', c.c_size_t), ('end', c.c_size_t), ('codepoint', c.c_uint32), ('glyph', c.c_uint32),
                ('x', c.c_float), ('baseline', c.c_float), ('advance', c.c_float), ('size', c.c_float),
                ('page', c.c_size_t), ('node', c.c_size_t), ('color', c.c_uint32), ('flags', c.c_uint),
                ('clip_left', c.c_float), ('clip_right', c.c_float), ('line_height', c.c_float),
                ('cluster_start', c.c_size_t), ('cluster_end', c.c_size_t), ('boundaries', c.c_uint),
                ('font_index', c.c_size_t), ('offset_x', c.c_float), ('offset_y', c.c_float), ('bidi_level', c.c_uint)]


class TocOptions(c.Structure):
    _fields_ = [('struct_size', c.c_size_t), ('labels', c.POINTER(c.c_char_p)), ('label_count', c.c_size_t),
                ('title', c.c_char_p), ('continued_title', c.c_char_p)]


GENERATED = 2048


def bind_toc(sdk):
    ptr, size = c.c_void_p, c.c_size_t
    err = c.POINTER(Error)
    table = {
        'toc_pages_create': (c.c_int, [ptr, ptr, c.POINTER(type(sdk.layout_config_defaults())), c.POINTER(TocOptions), c.POINTER(ptr), err]),
        'layout_page_kind': (c.c_int, [ptr, size]),
        'toc_pages_label': (c.c_char_p, [ptr, size]),
        'toc_pages_entries': (c.c_int, [ptr, size, c.POINTER(size), c.POINTER(size)]),
        'toc_pages_entry_at': (c.c_int, [ptr, size, c.c_float, c.c_float, c.POINTER(size)]),
        'toc_pages_entry_for_offset': (size, [ptr, size]),
        'layout_hit_test': (size, [ptr, size, c.c_float, c.c_float]),
        'layout_pages': (c.POINTER(Page), [ptr, c.POINTER(size)]),
        'layout_glyphs': (c.POINTER(Glyph), [ptr, c.POINTER(size)]),
        'publication_toc_insert_before': (c.c_int, [ptr, c.POINTER(size), err]),
        'document_find': (c.c_int, [ptr, c.c_char_p, size, c.POINTER(size), c.POINTER(size), err]),
        'pager_create': (c.c_int, [ptr, ptr, c.POINTER(type(sdk.layout_config_defaults())), c.POINTER(ptr), err]),
    }
    for name, (res, args) in table.items():
        fn = getattr(sdk.dll, 'exr_' + name)
        fn.restype, fn.argtypes = res, args
        setattr(sdk, name, fn)


def write_png(path, bitmap):
    w, h, ch = bitmap.width, bitmap.height, bitmap.channels
    raw = c.string_at(bitmap.pixels, bitmap.stride * h)
    rows = b''.join(b'\x00' + raw[y * bitmap.stride:y * bitmap.stride + w * ch] for y in range(h))
    kind = {3: 2, 4: 6}[ch]

    def chunk(tag, data):
        body = tag + data
        return struct.pack('>I', len(data)) + body + struct.pack('>I', zlib.crc32(body))
    Path(path).write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, kind, 0, 0, 0)) +
                           chunk(b'IDAT', zlib.compress(rows, 6)) + chunk(b'IEND', b''))


def paginate(sdk, document, font, config):
    """(lines [(start, end, page)], page_count) with the same pager as the body renderer."""
    pager, page = c.c_void_p(), c.c_void_p()
    lines, pages = [], 0
    sdk.check('pager_create', document, font, c.byref(config), c.byref(pager))
    try:
        while True:
            sdk.check('pager_next', pager, c.byref(page))
            if not page:
                break
            count = c.c_size_t()
            ls = sdk.layout_lines(page, c.byref(count))
            lines.extend((ls[i].start, ls[i].end, pages) for i in range(count.value))
            sdk.layout_free(page)
            page = c.c_void_p()
            pages += 1
    finally:
        sdk.pager_free(pager)
    return lines, pages


def page_of(lines, offset):
    for start, end, page in lines:
        if start <= offset < end or start == end == offset:
            return page
        if offset < start:
            return page
    return lines[-1][2] if lines else 0


def line_of(lines, offset):
    for i, (start, end, _) in enumerate(lines):
        if start <= offset < end or start == end == offset or offset < start:
            return i
    return len(lines) - 1


def audit(sdk, book, font, config, layout, png_dir, sample_xml, search_terms):
    publication = c.c_void_p()
    out = {'id': book['id'], 'sha256': file_hash(book['path'])}
    sdk.check('publication_open', book['path'].encode(), c.byref(publication))
    documents, toc_layout = {}, c.c_void_p()
    bitmap = Bitmap()
    try:
        count, toc = c.c_size_t(), c.POINTER(Toc)()
        sdk.check('publication_toc', publication, c.byref(toc), c.byref(count))
        n = count.value
        part_count = c.c_size_t()
        parts = sdk.publication_parts(publication, c.byref(part_count))

        def document(part):
            if part not in documents:
                doc = c.c_void_p()
                sdk.check('publication_load', publication, part, c.byref(doc))
                documents[part] = doc
            return documents[part]

        insert = c.c_size_t()
        sdk.check('publication_toc_insert_before', publication, c.byref(insert))
        out['parts'] = part_count.value
        out['insert_before_part'] = insert.value
        out['first_reading_part'] = parts[0].path.decode()
        out['toc_count'] = n
        out['sources'] = sorted({SOURCES[toc[i].source] for i in range(n)})
        out['max_toc_level'] = max((toc[i].level for i in range(n)), default=0)
        if not n:
            handle = c.c_void_p(1)
            options = TocOptions(c.sizeof(TocOptions))
            sdk.check('toc_pages_create', publication, font, c.byref(config), c.byref(options), c.byref(handle))
            out['toc_pages'] = 0 if not handle else -1
            out['generated_empty_page'] = bool(handle)
            return out

        # Body pagination fixes every label: global 1-based page number of the entry's location.
        part_lines, base, total = {}, {}, 0
        for part in range(part_count.value):
            if not parts[part].in_reading_order:
                continue
            part_lines[part], pages = paginate(sdk, document(part), font, config)
            base[part] = total
            total += pages
        out['body_pages'] = total
        labels, locations = [], []
        for i in range(n):
            location = Location()
            sdk.check('publication_locate', publication, c.byref(toc[i].target), c.byref(location))
            locations.append(location)
            if location.state == 0 and location.part in base:
                labels.append(str(base[location.part] + page_of(part_lines[location.part], location.offset) + 1).encode())
            else:
                labels.append(b'')
        array = (c.c_char_p * n)(*labels)
        options = TocOptions(c.sizeof(TocOptions), array, n, None, None)
        sdk.check('toc_pages_create', publication, font, c.byref(config), c.byref(options), c.byref(toc_layout))
        pcount = c.c_size_t()
        pages = sdk.layout_pages(toc_layout, c.byref(pcount))
        lcount, gcount = c.c_size_t(), c.c_size_t()
        lines = sdk.layout_lines(toc_layout, c.byref(lcount))
        glyphs = sdk.layout_glyphs(toc_layout, c.byref(gcount))
        out['toc_pages'] = pcount.value
        out['all_pages_toc_kind'] = all(sdk.layout_page_kind(toc_layout, i) == 1 for i in range(pcount.value))
        out['page_labels'] = [sdk.toc_pages_label(toc_layout, i).decode() for i in range(pcount.value)]
        per_page = []
        for i in range(pcount.value):
            first, cnt = c.c_size_t(), c.c_size_t()
            assert sdk.toc_pages_entries(toc_layout, i, c.byref(first), c.byref(cnt)) == 0
            per_page.append(cnt.value)
        out['entries_per_page'] = per_page
        out['pages_cover_all_entries'] = sum(per_page) == n

        # Geometry: row -> first glyph; indent; dot grid; label right edge.
        W, M = layout['width'], layout['margin']
        row_x, dots_ok, dots_rows, label_ok, labelled = {}, True, 0, True, 0
        entry_rows = {}
        for pg in range(pcount.value):
            for li in range(pages[pg].line_start, pages[pg].line_start + pages[pg].line_count):
                ln = lines[li]
                e = c.c_size_t()
                sdk.toc_pages_entry_at(toc_layout, pg, 0, ln.y + ln.height / 2, c.byref(e))
                if e.value == SIZE_MAX:
                    continue
                gl = [glyphs[k] for k in range(ln.glyph_start, ln.glyph_start + ln.glyph_count)]
                entry_rows.setdefault(e.value, []).append((pg, ln, gl))
        for e, rows in entry_rows.items():
            pg, ln, gl = rows[0]
            vis = [g for g in gl if not g.flags & 4]
            row_x[e] = vis[0].x if vis else ln.x
            _, ln2, gl2 = rows[-1]
            dots = [g for g in gl2 if g.flags & GENERATED]
            if labels[e]:
                labelled += 1
                nondot = [g for g in gl2 if not g.flags & GENERATED and not g.flags & 4]
                label_ok &= abs(nondot[-1].x + nondot[-1].advance - (W - M)) < 0.02
                if len(dots) >= 3:
                    dots_rows += 1
                    dots_ok &= all(abs((dots[k + 1].x - dots[k].x) - dots[k].advance) < 0.02 for k in range(len(dots) - 1))
                else:
                    dots_ok = False
        levels_x = {}
        for e in entry_rows:
            levels_x.setdefault(toc[e].level, []).append(row_x[e])
        base_x = min(levels_x[min(levels_x)])
        out['labelled_rows'] = labelled
        out['rows_with_leaders'] = dots_rows
        out['leader_dots_contiguous'] = bool(dots_ok)
        out['labels_right_aligned'] = bool(label_ok)
        out['indent_px_by_level'] = {str(k): round(min(v) - base_x, 3) for k, v in sorted(levels_x.items())}
        out['max_indent_px'] = max(out['indent_px_by_level'].values())
        out['indent_one_em_per_level'] = all(abs(round(v - (k - min(levels_x)) * layout['font_size'], 3)) < 0.02
                                             for k, v in ((int(k), v) for k, v in out['indent_px_by_level'].items()))
        out['max_row_lines'] = max(len(r) for r in entry_rows.values())

        # Render + hash every TOC page.
        hashes = []
        for pg in range(pcount.value):
            sdk.check('render_page_color', toc_layout, sdk.layout_font(toc_layout), pg, c.byref(bitmap))
            assert (bitmap.width, bitmap.height) == (layout['width'], layout['height'])
            hashes.append(pixel_hash(bitmap))
            if png_dir and book['id'] in png_dir[1] and pg in (0, pcount.value - 1, 1):
                write_png(png_dir[0] / f"{book['id']}-toc-{pg + 1}.png", bitmap)
            sdk.bitmap_free(c.byref(bitmap))
        out['toc_page_sha256'] = hashes

        # Click test: ten entries spread over the book, through ordinary hit-test.
        eligible = [i for i in range(n) if toc[i].source == 3 or toc[i].title.decode().startswith('Capítulo')]             if sample_xml(book) else list(range(n))
        picks = sorted({eligible[round(k * (len(eligible) - 1) / 9)] for k in range(10)})
        clicks = []
        for e in picks:
            pg, ln, gl = entry_rows[e][0]
            x, y = ln.x + 6, ln.y + ln.height / 2
            offset = sdk.layout_hit_test(toc_layout, pg, x, y)
            via_offset = sdk.toc_pages_entry_for_offset(toc_layout, offset)
            geo = c.c_size_t()
            sdk.toc_pages_entry_at(toc_layout, pg, x, y, c.byref(geo))
            loc = Location()
            sdk.check('publication_locate', publication, c.byref(toc[via_offset].target), c.byref(loc)) if via_offset < n else None
            item = {'entry': e, 'title': toc[e].title.decode(), 'toc_page': pg + 1, 'hit_entry': via_offset,
                    'geometry_entry': geo.value, 'located_part': loc.part, 'located_offset': loc.offset}
            item['hit_ok'] = via_offset == e and geo.value == e
            if sample_xml(book):
                with zipfile.ZipFile(book['path']) as archive:
                    paths = [parts[i].path.decode() for i in range(part_count.value)]
                    root = ET.fromstring(archive.read(paths[loc.part]))
                doc = document(loc.part)
                projected = sdk.document_text(doc, None).decode()
                expected = expected_offset(root, toc[e], projected)
                delta = line_of(part_lines[loc.part], loc.offset) - line_of(part_lines[loc.part], expected)
                item.update(expected_offset=expected, line_delta=delta, within_one_line=abs(delta) <= 1)
            else:
                item['within_one_line'] = None
            item['passed'] = item['hit_ok'] and loc.state == 0 and item['within_one_line'] is not False
            clicks.append(item)
        out['clicks'] = clicks
        out['clicks_passed'] = sum(1 for k in clicks if k['passed'])
        out['clicks_total'] = len(clicks)

        # Search/copy isolation: terms that exist only in the synthetic pages.
        wanted = {t for t in search_terms}
        found = {}
        for term in wanted:
            hits = 0
            for part in base:
                s, en = c.c_size_t(), c.c_size_t()
                sdk.check('document_find', document(part), term.encode(), 0, c.byref(s), c.byref(en))
                hits += s.value != SIZE_MAX
            in_toc = False
            text = ''.join(chr(glyphs[k].codepoint) for k in range(gcount.value))
            in_toc = term in text
            found[term] = {'publication_hit_parts': hits, 'present_in_toc_pages': in_toc}
        out['search'] = found
        return out
    finally:
        sdk.bitmap_free(c.byref(bitmap))
        for doc in documents.values():
            sdk.document_free(doc)
        if toc_layout:
            sdk.layout_free(toc_layout)
        sdk.publication_free(publication)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('dll', 'manifest', 'font', 'layout', 'output'):
        parser.add_argument('--' + key, type=Path, required=True)
    parser.add_argument('--png-dir', type=Path)
    parser.add_argument('--png-books', default='hongloumeng-24264,pachinko,xingshihengyan-24239')
    parser.add_argument('--only', default='')
    parser.add_argument('--extra-epub', action='append', default=[], help='id=path for additional fixtures')
    args = parser.parse_args()
    sdk = SDK(args.dll.resolve())
    bind(sdk)
    bind_toc(sdk)
    sdk.render_page_color.argtypes = [c.c_void_p, c.c_void_p, c.c_size_t, c.POINTER(Bitmap), c.POINTER(Error)]
    layout = read_json(args.layout)
    config = sdk.layout_config_defaults()
    for key in ('width', 'height', 'margin', 'font_size', 'line_height', 'paragraph_spacing'):
        setattr(config.page, key, layout[key])
    for key in ('document_css', 'embedded_fonts', 'direction'):
        setattr(config, key, layout[key])
    font = c.c_void_p()
    sdk.check('font_open', str(args.font.resolve()).encode(), c.byref(font))
    png = None
    if args.png_dir:
        args.png_dir.mkdir(parents=True, exist_ok=True)
        png = (args.png_dir, set(args.png_books.split(',')))
    books = [b for b in read_json(args.manifest)['books'] if b['path'].lower().endswith('.epub')]
    for item in args.extra_epub:
        ident, path = item.split('=', 1)
        books.append({'id': ident, 'path': path})
    if args.only:
        books = [b for b in books if b['id'] in args.only.split(',')]
    result = {'dll_sha256': file_hash(args.dll), 'layout': layout, 'books': []}
    sampled = ('pachinko', 'hongloumeng-24264', 'xingshihengyan-24239')
    terms = ['目录（续）', 'Contents (continued)', '目錄（續）']
    try:
        for book in books:
            entry = audit(sdk, book, font, config, layout, png, lambda b: b['id'] in sampled, terms)
            result['books'].append(entry)
            write_json(args.output, result)
            brief = {k: v for k, v in entry.items() if k not in ('clicks', 'toc_page_sha256', 'indent_px_by_level')}
            print(json.dumps(brief, ensure_ascii=False), flush=True)
    finally:
        sdk.font_free(font)


if __name__ == '__main__':
    main()
