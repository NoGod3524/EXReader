"""Render the vertical sample book with a before and an after SDK and measure every
text-combine-upright block: cell width, scale, vertical centring and pixel ink extents.

usage: probe_combine.py BEFORE_DLL AFTER_DLL BOOK FONT OUT_DIR
"""
import ctypes as c
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools' / 'regress'))
import run_realbooks as rb  # noqa: E402
from PIL import Image  # noqa: E402

COMBINED = 16384


class Glyph(c.Structure):
    _fields_ = [('start', c.c_size_t), ('end', c.c_size_t), ('codepoint', c.c_uint32), ('glyph', c.c_uint32),
                ('x', c.c_float), ('baseline', c.c_float), ('advance', c.c_float), ('size', c.c_float),
                ('page', c.c_size_t), ('node', c.c_size_t), ('color', c.c_uint32), ('flags', c.c_uint),
                ('clip_left', c.c_float), ('clip_right', c.c_float), ('line_height', c.c_float),
                ('cluster_start', c.c_size_t), ('cluster_end', c.c_size_t), ('boundaries', c.c_uint),
                ('font_index', c.c_size_t), ('offset_x', c.c_float), ('offset_y', c.c_float),
                ('bidi_level', c.c_uint)]


def render(dll, book, font_path, layout, keep):
    """Yield (part, page_index, glyph list, Image) for pages selected by keep(glyphs)."""
    sdk = rb.SDK(dll)
    sdk.dll.exr_layout_glyphs.restype = c.POINTER(Glyph)
    font, publication, document, pager, page = [c.c_void_p() for _ in range(5)]
    sdk.check('font_open', str(font_path).encode(), c.byref(font))
    sdk.check('publication_open', str(book).encode(), c.byref(publication))
    parts = c.c_size_t()
    sdk.publication_parts(publication, c.byref(parts))
    config = sdk.layout_config_defaults()
    config.page = rb.Options(**{k: layout[k] for k, _ in rb.Options._fields_})
    config.document_css, config.embedded_fonts, config.direction = layout['document_css'], layout['embedded_fonts'], layout['direction']
    pages_total = 0
    out = []
    for part in range(parts.value):
        sdk.check('publication_load', publication, part, c.byref(document))
        sdk.check('pager_create', document, font, c.byref(config), c.byref(pager))
        local = 0
        while True:
            sdk.check('pager_next', pager, c.byref(page))
            if not page:
                break
            n = c.c_size_t()
            gp = sdk.dll.exr_layout_glyphs(page, c.byref(n))
            glyphs = [Glyph.from_buffer_copy(gp[i]) for i in range(n.value)]
            image = None
            if keep(part, glyphs):
                bitmap = rb.Bitmap()
                sdk.check('render_page_color', page, sdk.layout_font(page), 0, c.byref(bitmap))
                raw = c.string_at(bitmap.pixels, bitmap.stride * bitmap.height)
                image = Image.frombuffer('RGBA', (bitmap.width, bitmap.height), raw, 'raw', 'RGBA', bitmap.stride, 1).convert('RGB')
                sdk.bitmap_free(c.byref(bitmap))
            out.append((part, local, pages_total, glyphs, image))
            sdk.layout_free(page)
            page = c.c_void_p()
            local += 1
            pages_total += 1
        sdk.pager_free(pager); pager = c.c_void_p()
        sdk.document_free(document); document = c.c_void_p()
    sdk.publication_free(publication); sdk.font_free(font)
    return out


def blocks(glyphs):
    """Group consecutive COMBINED glyphs: the last member of a block carries the em advance."""
    result, current = [], []
    for g in glyphs:
        if g.flags & COMBINED:
            current.append(g)
            if g.advance > 0:
                result.append(current); current = []
        elif current:
            result.append(current); current = []
    return result


def ink(image, box):
    x0, y0, x1, y1 = [int(round(v)) for v in box]
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(image.width, x1), min(image.height, y1)
    xs, ys = [], []
    px = image.load()
    for y in range(y0, y1):
        for x in range(x0, x1):
            if sum(px[x, y]) < 3 * 128:
                xs.append(x); ys.append(y)
    if not xs:
        return None
    return {'left': min(xs), 'right': max(xs) + 1, 'top': min(ys), 'bottom': max(ys) + 1,
            'width': max(xs) + 1 - min(xs), 'height': max(ys) + 1 - min(ys)}


def main():
    before_dll, after_dll, book, font, out = [Path(a) for a in sys.argv[1:6]]
    out.mkdir(parents=True, exist_ok=True)
    layout = json.loads((Path(__file__).resolve().parents[2] / 'tools/regress/layout.json').read_text())
    keep_all = lambda part, glyphs: any(g.flags & COMBINED for g in glyphs)  # noqa: E731
    after = render(after_dll, book, font, layout, keep_all)
    spans = {(part, g.start) for part, _, _, glyphs, _ in after for g in glyphs if g.flags & COMBINED}
    before = render(before_dll, book, font, layout,
                    lambda part, glyphs: any((part, g.start) in spans for g in glyphs))
    report = {'book': book.name, 'before_pages': len(before), 'after_pages': len(after),
              'before_layout_pages_per_part': {}, 'after_layout_pages_per_part': {}, 'blocks': []}
    for tag, data in (('before', before), ('after', after)):
        for part, *_ in data:
            report[tag + '_layout_pages_per_part'][str(part)] = report[tag + '_layout_pages_per_part'].get(str(part), 0) + 1
    index = 0
    for part, local, total, glyphs, image in after:
        if image is None:
            continue
        for block in blocks(glyphs):
            first, last = block[0], block[-1]
            size = last.advance
            cell = (first.x - size / 2, first.baseline, first.x + size / 2, first.baseline + size)
            measured = ink(image, cell)
            ring = ink(image, (cell[0] - 3, cell[1] - 3, cell[2] + 3, cell[3] + 3))
            text = ''.join(chr(g.codepoint) for g in block)
            # Page in the before render that contains the same source span.
            match = next(((p, lp, t, gl, im) for p, lp, t, gl, im in before
                          if p == part and any(g.start == first.start for g in gl)), None)
            entry = {'index': index, 'text': text, 'part': part, 'part_page': local + 1, 'page': total + 1,
                     'font_size': size, 'cell_advance': size, 'members': len(block),
                     'member_size': first.size, 'scale': round(first.size / size, 5),
                     'offset_x_first': first.offset_x, 'offset_y': first.offset_y,
                     'ink_cell_px': measured, 'ink_ring_px': ring,
                     'centre_y_error_px': None if not measured else
                     round((measured['top'] + measured['bottom']) / 2 - (cell[1] + size / 2), 3),
                     'centre_x_error_px': None if not measured else
                     round((measured['left'] + measured['right']) / 2 - first.x, 3)}
            if match:
                p, lp, t, gl, im = match
                bg = next(g for g in gl if g.start == first.start)
                members = [g for g in gl if first.start <= g.start < last.end]
                entry['before'] = {'page': t + 1, 'orientation': 'sideways' if bg.flags & 256 else 'upright',
                                   'column_extent_px': round(sum(g.advance for g in members), 3)}
                crop = lambda image_, x, y: image_.crop((int(x - 70), int(y - 80), int(x + 70), int(y + 140))).resize((420, 660), Image.NEAREST)  # noqa: E731
                a, b = crop(im, bg.x, bg.baseline), crop(image, first.x, first.baseline)
                sheet = Image.new('RGB', (420 * 2 + 20, 660), 'white')
                sheet.paste(a, (0, 0)); sheet.paste(b, (440, 0))
                sheet.save(out / f'block-{index:02d}-{text}.png')
            report['blocks'].append(entry)
            index += 1
        image.save(out / f'page-after-{total + 1}.png')
        for p, lp, t, gl, im in before:
            if p == part and im is not None and any((part, g.start) in {(part, b[0].start) for b in blocks(glyphs)} for g in gl):
                im.save(out / f'page-before-{t + 1}.png')
    (out / 'blocks.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'blocks'}, ensure_ascii=False))
    for b in report['blocks']:
        print(b['text'], b['part'], b['page'], b['cell_advance'], b['scale'], b['ink_cell_px'], b['centre_y_error_px'], b.get('before'))


if __name__ == '__main__':
    main()
