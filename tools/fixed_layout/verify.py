"""Verify EPUB 3 Fixed Layout rendering through the public SDK.

Six items per book:
 1 size     page bitmap equals the requested viewport; one uniform scale
            min(W/vw, H/vh), centred; image boxes keep their aspect ratio
 2 image    a full-page image box equals the mapped viewport (no crop) and,
            for generated art, the red frame is visible on all four edges
 3 absolute positioned boxes sit at their declared CSS insets (box geometry
            and pixel colour inside the box)
 4 spread   exr_publication_spreads equals the expected left/right order
 5 mixed    fixed parts give one page at every viewport; reflowable parts
            give no fixed record and repaginate when the viewport changes
 6 zoom     viewport source (content meta / package rendition:viewport /
            image / page) and the fit scale at portrait and landscape targets
"""
import argparse
import ctypes as c
import json
import math
import os
from pathlib import Path
import re
import sys
import zipfile
import io

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'regress'))
from run_realbooks import Error, Bitmap, Options, Control, Config  # noqa: E402


class Part(c.Structure):
    _fields_ = [('id', c.c_char_p), ('path', c.c_char_p), ('title', c.c_char_p), ('in_reading_order', c.c_int)]


class Rendition(c.Structure):
    _fields_ = [('layout', c.c_int), ('spread', c.c_int), ('viewport_width', c.c_float), ('viewport_height', c.c_float)]


class Spread(c.Structure):
    _fields_ = [('left', c.c_size_t), ('right', c.c_size_t), ('flags', c.c_uint)]


class Fixed(c.Structure):
    _fields_ = [('fixed', c.c_int), ('source', c.c_int)] + [(k, c.c_float) for k in ('width', 'height', 'scale', 'x', 'y')]


class Box(c.Structure):
    _fields_ = [('kind', c.c_int), ('node', c.c_size_t), ('page', c.c_size_t), ('resource', c.c_size_t),
                ('start', c.c_size_t), ('end', c.c_size_t)] + \
               [(k, c.c_float) for k in ('x', 'y', 'width', 'height', 'border_width')] + \
               [('background', c.c_uint32), ('border_color', c.c_uint32), ('flags', c.c_uint)]


class Glyph(c.Structure):
    _fields_ = [('start', c.c_size_t), ('end', c.c_size_t), ('codepoint', c.c_uint32), ('glyph', c.c_uint32)] + \
               [(k, c.c_float) for k in ('x', 'baseline', 'advance', 'size')] + \
               [('page', c.c_size_t), ('node', c.c_size_t), ('color', c.c_uint32), ('flags', c.c_uint),
                ('clip_left', c.c_float), ('clip_right', c.c_float), ('line_height', c.c_float),
                ('cluster_start', c.c_size_t), ('cluster_end', c.c_size_t), ('boundaries', c.c_uint),
                ('font_index', c.c_size_t), ('offset_x', c.c_float), ('offset_y', c.c_float), ('bidi_level', c.c_uint)]


class Node(c.Structure):
    _fields_ = [('kind', c.c_int), ('parent', c.c_size_t), ('first_child', c.c_size_t), ('next_sibling', c.c_size_t),
                ('chapter', c.c_size_t), ('start', c.c_size_t), ('end', c.c_size_t), ('name', c.c_char_p),
                ('text', c.c_char_p), ('attributes', c.c_void_p), ('attribute_count', c.c_size_t)]


class Target(c.Structure):
    _fields_ = [('part', c.c_size_t), ('fragment', c.c_char_p), ('offset', c.c_size_t)]


class TocEntry(c.Structure):
    _fields_ = [('title', c.c_char_p), ('level', c.c_size_t), ('target', Target), ('source', c.c_int),
                ('play_order', c.c_size_t)]


SOURCES = {1: 'content', 2: 'package', 3: 'image', 4: 'page'}
NONE = c.c_size_t(-1).value
GLYPH_VERTICAL = 128  # EXR_GLYPH_VERTICAL


class SDK:
    def __init__(self, path):
        self.directory = os.add_dll_directory(str(Path(path).resolve().parent)) if os.name == 'nt' else None
        d = self.dll = c.CDLL(str(Path(path).resolve()))
        ptr, size, err = c.c_void_p, c.c_size_t, c.POINTER(Error)
        out, count = c.POINTER(ptr), c.POINTER(size)
        sig = {
            'layout_config_defaults': (Config, []),
            'font_open': (c.c_int, [c.c_char_p, out, err]), 'font_free': (None, [ptr]),
            'publication_open': (c.c_int, [c.c_char_p, out, err]), 'publication_free': (None, [ptr]),
            'publication_parts': (c.POINTER(Part), [ptr, count]),
            'publication_rendition': (c.c_int, [ptr, size, c.POINTER(Rendition), err]),
            'publication_page_progression': (c.c_int, [ptr]),
            'publication_spreads': (c.c_int, [ptr, c.POINTER(c.POINTER(Spread)), count, err]),
            'publication_toc': (c.c_int, [ptr, c.POINTER(c.POINTER(TocEntry)), count, err]),
            'publication_load': (c.c_int, [ptr, size, out, err]), 'document_free': (None, [ptr]),
            'document_nodes': (c.POINTER(Node), [ptr, count]),
            'node_attribute': (c.c_char_p, [c.POINTER(Node), c.c_char_p]),
            'pager_create': (c.c_int, [ptr, ptr, c.POINTER(Config), out, err]), 'pager_free': (None, [ptr]),
            'pager_next': (c.c_int, [ptr, out, err]), 'layout_free': (None, [ptr]),
            'layout_fixed_viewport': (Fixed, [ptr]),
            'layout_boxes': (c.POINTER(Box), [ptr, count]),
            'layout_glyphs': (c.POINTER(Glyph), [ptr, count]),
            'layout_font': (ptr, [ptr]),
            'render_page_color': (c.c_int, [ptr, ptr, size, c.POINTER(Bitmap), err]),
            'bitmap_free': (None, [c.POINTER(Bitmap)]), 'free': (None, [ptr]),
        }
        for name, (res, args) in sig.items():
            f = getattr(d, 'exr_' + name)
            f.restype, f.argtypes = res, args
            setattr(self, name, f)

    def ok(self, name, *args):
        e = Error()
        status = getattr(self, name)(*args, c.byref(e))
        if status:
            raise RuntimeError(f'exr_{name}: {status} {e.message.decode(errors="replace")}')


def to_image(bitmap):
    raw = c.string_at(bitmap.pixels, bitmap.stride * bitmap.height)
    return Image.frombuffer('RGBA', (bitmap.width, bitmap.height), raw, 'raw', 'RGBA', bitmap.stride, 1).convert('RGB')


def near(a, b, tol):
    return abs(a - b) <= tol


class Book:
    """One open publication; pages laid out per part at a given target size."""

    def __init__(self, sdk, font, path, layout):
        self.sdk, self.font, self.path, self.layout = sdk, font, Path(path), layout
        self.pub = c.c_void_p()
        sdk.ok('publication_open', str(path).encode('utf-8'), c.byref(self.pub))
        n = c.c_size_t()
        parts = sdk.publication_parts(self.pub, c.byref(n))
        self.parts = [(i, parts[i].path.decode(), bool(parts[i].in_reading_order)) for i in range(n.value)]
        self.zip = zipfile.ZipFile(path)

    def close(self):
        self.sdk.publication_free(self.pub)
        self.zip.close()

    def config(self, width, height):
        cfg = self.sdk.layout_config_defaults()
        lay = dict(self.layout, width=width, height=height)
        cfg.page = Options(**{k: lay[k] for k, _ in Options._fields_})
        cfg.document_css, cfg.embedded_fonts, cfg.direction = lay['document_css'], lay['embedded_fonts'], lay['direction']
        return cfg

    def rendition(self, part):
        r = Rendition()
        self.sdk.ok('publication_rendition', self.pub, part, c.byref(r))
        return r

    def spreads(self):
        out, n = c.POINTER(Spread)(), c.c_size_t()
        self.sdk.ok('publication_spreads', self.pub, c.byref(out), c.byref(n))
        result = [{'left': None if out[i].left == NONE else out[i].left,
                   'right': None if out[i].right == NONE else out[i].right,
                   'single': bool(out[i].flags & 1)} for i in range(n.value)]
        self.sdk.free(c.cast(out, c.c_void_p))
        return result

    def toc(self):
        out, n = c.POINTER(TocEntry)(), c.c_size_t()
        self.sdk.ok('publication_toc', self.pub, c.byref(out), c.byref(n))
        return [{'title': out[i].title.decode(), 'part': out[i].target.part} for i in range(n.value)]

    def pages(self, part, width, height, render=True, want_ids=()):
        """Lay out one part; return per-page records (and images when render)."""
        sdk = self.sdk
        doc, pager = c.c_void_p(), c.c_void_p()
        sdk.ok('publication_load', self.pub, part, c.byref(doc))
        cfg = self.config(width, height)
        records = []
        try:
            n = c.c_size_t()
            nodes = sdk.document_nodes(doc, c.byref(n))
            ids = {}
            for i in range(n.value):
                v = sdk.node_attribute(c.byref(nodes[i]), b'id')
                if v and v.decode() in want_ids:
                    ids[i] = v.decode()
            sdk.ok('pager_create', doc, self.font, c.byref(cfg), c.byref(pager))
            while True:
                page = c.c_void_p()
                sdk.ok('pager_next', pager, c.byref(page))
                if not page:
                    break
                fv = sdk.layout_fixed_viewport(page)
                nb = c.c_size_t()
                boxes = sdk.layout_boxes(page, c.byref(nb))
                rec = {'fixed': {k: getattr(fv, k) for k, _ in Fixed._fields_}, 'boxes': {}, 'image_boxes': []}
                for i in range(nb.value):
                    b = boxes[i]
                    geo = {'x': b.x, 'y': b.y, 'width': b.width, 'height': b.height, 'kind': b.kind,
                           'background': b.background, 'resource': b.resource}
                    if b.kind == 2 and not b.flags:
                        rec['image_boxes'].append(geo)
                    if b.node in ids and not (b.flags & 2) and ids[b.node] not in rec['boxes']:
                        rec['boxes'][ids[b.node]] = geo
                ng = c.c_size_t()
                glyphs = sdk.layout_glyphs(page, c.byref(ng))
                rec['glyphs'] = ng.value
                rec['max_right'] = max((glyphs[i].x + glyphs[i].advance for i in range(ng.value)), default=0)
                rec['vertical_glyphs'] = {}
                for i in range(ng.value):
                    g = glyphs[i]
                    node = g.node
                    # attribute glyphs to the nearest tagged ancestor
                    while node != NONE and node not in ids:
                        node = nodes[node].parent
                    if node != NONE and (g.flags & GLYPH_VERTICAL):
                        rec['vertical_glyphs'][ids[node]] = rec['vertical_glyphs'].get(ids[node], 0) + 1
                if render:
                    bmp = Bitmap()
                    sdk.ok('render_page_color', page, sdk.layout_font(page), 0, c.byref(bmp))
                    rec['size'] = [bmp.width, bmp.height]
                    rec['image'] = to_image(bmp)
                    sdk.bitmap_free(c.byref(bmp))
                records.append(rec)
                sdk.layout_free(page)
        finally:
            sdk.pager_free(pager)
            sdk.document_free(doc)
        return records


def real_oracle(book, part_path):
    """Oracle for a real book page read straight from its XHTML/OPF bytes."""
    html = book.zip.read(part_path).decode('utf-8', errors='replace')
    m = re.search(r'<meta\s+name="viewport"\s+content="([^"]+)"', html)
    viewport = None
    if m:
        w = re.search(r'width\s*=\s*([\d.]+)', m.group(1))
        h = re.search(r'height\s*=\s*([\d.]+)', m.group(1))
        viewport = [float(w.group(1)), float(h.group(1))]
    images = re.findall(r'<img[^>]+src="([^"]+)"', html)
    full = None
    if len(images) == 1:
        base = part_path.rsplit('/', 1)[0]
        parts = (base + '/' + images[0]).split('/')
        stack = []
        for p in parts:
            if p == '..':
                stack.pop()
            elif p and p != '.':
                stack.append(p)
        with Image.open(io.BytesIO(book.zip.read('/'.join(stack)))) as im:
            full = {'natural': list(im.size)}
    # Absolutely positioned image without insets (publisher CSS): static position.
    static = False
    for href in re.findall(r'<link[^>]+href="([^"]+\.css)"', html):
        base = part_path.rsplit('/', 1)[0].split('/')
        for p in href.split('/'):
            base = base[:-1] if p == '..' else base + [p]
        css = book.zip.read('/'.join(base)).decode('utf-8', errors='replace')
        rule = re.search(r'(?:^|})\s*img\s*{([^}]*)}', css)
        static |= bool(rule and re.search(r'position\s*:\s*absolute', rule.group(1)))
    return {'viewport': viewport, 'viewport_source': 'content' if viewport else None, 'fixed': True,
            'full_image_natural': full, 'static_absolute_image': static and full is not None}


def check_page(rec, oracle, W, H):
    """Items 1-3 for one fixed page at target W x H. Returns dict of results."""
    fv = rec['fixed']
    res = {}
    vw, vh = fv['width'], fv['height']
    s = min(W / vw, H / vh)
    ox, oy = (W - vw * s) / 2, (H - vh * s) / 2
    notes = []
    ok1 = fv['fixed'] == 1 and rec.get('size', [W, H]) == [W, H] and near(fv['scale'], s, 1e-4) and \
        near(fv['x'], ox, .01) and near(fv['y'], oy, .01)
    if oracle.get('viewport'):
        ok1 &= near(vw, oracle['viewport'][0], .01) and near(vh, oracle['viewport'][1], .01)
    elif oracle.get('viewport_source') == 'page':
        ok1 &= near(vw, W, .01) and near(vh, H, .01)
    for ib in rec['image_boxes']:
        if ib['width'] > 0 and ib['height'] > 0:
            ok1 &= ib['x'] >= ox - 1 and ib['y'] >= oy - 1 and ib['x'] + ib['width'] <= ox + vw * s + 1 and \
                ib['y'] + ib['height'] <= oy + vh * s + 1
    notes.append(f'vp={vw:g}x{vh:g} scale={fv["scale"]:.4f} offset=({fv["x"]:.1f},{fv["y"]:.1f})')
    res['1_size'] = ok1
    # 2 full page image
    full = oracle.get('full_image')
    natural = oracle.get('full_image_natural')
    if full or natural:
        if full:
            b = rec['boxes'].get(full['id'])
            ok2 = b is not None and near(b['x'], ox + full['left'] * s, 1) and near(b['y'], oy + full['top'] * s, 1) and \
                near(b['width'], full['width'] * s, 1) and near(b['height'], full['height'] * s, 1)
            img = rec.get('image')
            if ok2 and img is not None and full.get('frame'):
                t = max(1, full['frame_px'] * s / 2)
                probes = [(b['x'] + t, b['y'] + b['height'] / 2), (b['x'] + b['width'] - t, b['y'] + b['height'] / 2),
                          (b['x'] + b['width'] / 2, b['y'] + t), (b['x'] + b['width'] / 2, b['y'] + b['height'] - t)]
                reds = [img.getpixel((int(px), int(py))) for px, py in probes]
                ok2 &= all(r > 190 and g < 80 and bl < 80 for r, g, bl in reds)
                notes.append(f'frame4={sum(1 for r, g, bl in reds if r > 190 and g < 80 and bl < 80)}/4')
        else:
            nw, nh = natural['natural']
            big = max(rec['image_boxes'], key=lambda q: q['width'] * q['height'], default=None)
            ok2 = big is not None and near(big['width'] / big['height'], nw / nh, 0.005 * nw / nh) and \
                near(big['width'], min(nw, vw) * s, 1.5) and big['x'] >= ox - 1 and big['y'] >= oy - 1 and \
                big['x'] + big['width'] <= ox + vw * s + 1 and big['y'] + big['height'] <= oy + vh * s + 1
            if big:
                notes.append(f'img {nw}x{nh} -> {big["width"]:.1f}x{big["height"]:.1f} at ({big["x"]:.1f},{big["y"]:.1f})')
        res['2_image'] = bool(ok2)
    # 3 absolute
    checks = []
    for spec in oracle.get('boxes', []) + oracle.get('images', []):
        b = rec['boxes'].get(spec['id'])
        if b is None:
            checks.append(False)
            continue
        left = spec['left_pct'] * vw if 'left_pct' in spec else spec.get('left')
        top = spec['top_pct'] * vh if 'top_pct' in spec else spec.get('top')
        good = True
        if left is not None:
            good &= near(b['x'], ox + left * s, 1)
        if 'right' in spec:
            good &= near(b['x'] + b['width'], ox + (vw - spec['right']) * s, 1)
        if top is not None:
            good &= near(b['y'], oy + top * s, 1)
        if 'bottom' in spec:
            good &= near(b['y'] + b['height'], oy + (vh - spec['bottom']) * s, 1)
        if 'width_pct' in spec:
            good &= b['width'] >= spec['width_pct'] * vw * s - 1
        elif 'width' in spec:
            good &= b['width'] >= spec['width'] * s - 1
        if 'height' in spec:
            good &= near(b['height'], spec['height'] * s, 1)
        img = rec.get('image')
        if good and img is not None and 'color' in spec:
            px = img.getpixel((int(b['x'] + 3), int(b['y'] + 3)))
            good &= all(abs(px[i] - spec['color'][i]) <= 8 for i in range(3))
        checks.append(bool(good))
    if oracle.get('static_absolute_image'):
        big = max(rec['image_boxes'], key=lambda q: q['width'] * q['height'], default=None)
        checks.append(big is not None and near(big['x'], ox, 1) and near(big['y'], oy, 1))
    if oracle.get('vertical'):
        checks.append(rec['vertical_glyphs'].get(oracle['vertical'], 0) > 0)
    if checks:
        res['3_absolute'] = all(checks)
        notes.append(f'abs {sum(checks)}/{len(checks)}')
    return res, notes


def verify_book(sdk, font, entry, layout, shots):
    book = Book(sdk, font, entry['path'], layout)
    W, H = layout['width'], layout['height']
    out = {'id': entry['id'], 'path': entry['path'], 'kind': entry.get('kind'), 'pages': [], 'items': {}}
    try:
        oracle_pages = entry.get('pages')
        reading = [p for p in book.parts if p[2]]
        out['progression'] = sdk.publication_page_progression(book.pub)
        items = {k: [] for k in ('1_size', '2_image', '3_absolute', '4_spread', '5_mixed', '6_zoom')}
        total_pages = 0
        shot_count = 0
        rendered = {}
        for order, (part, path, _) in enumerate(reading):
            oracle = oracle_pages[order] if oracle_pages else (
                real_oracle(book, path) if book.rendition(part).layout else {'fixed': False})
            ids = [x['id'] for x in oracle.get('boxes', []) + oracle.get('images', [])]
            if oracle.get('full_image'):
                ids.append(oracle['full_image']['id'])
            if oracle.get('vertical'):
                ids.append(oracle['vertical'])
            r = book.rendition(part)
            portrait = book.pages(part, W, H, True, ids)
            landscape = book.pages(part, H, W, False, ids)
            small = book.pages(part, 480, 800, False, ids)
            total_pages += len(portrait)
            rec = {'part': part, 'path': path, 'layout': 'pre-paginated' if r.layout else 'reflowable',
                   'declared_spread': r.spread, 'pages': len(portrait), 'pages_landscape': len(landscape),
                   'pages_480x800': len(small)}
            fixed = bool(r.layout)
            ok5 = fixed == bool(oracle.get('fixed'))
            if fixed:
                ok5 &= len(portrait) == len(landscape) == len(small) == 1 and portrait[0]['fixed']['fixed'] == 1
                res, notes = check_page(portrait[0], oracle, W, H)
                res_l, notes_l = check_page(landscape[0], oracle, H, W)
                for k, v in res.items():
                    items[k].append(v and res_l.get(k, True))
                src = SOURCES.get(portrait[0]['fixed']['source'])
                want = oracle.get('viewport_source')
                ok6 = (want is None or src == want) and res['1_size'] and res_l['1_size']
                if want == 'page':
                    ok6 &= near(portrait[0]['fixed']['scale'], 1, 1e-4)
                items['6_zoom'].append(ok6)
                rec.update(boxes=portrait[0]['boxes'], fixed=portrait[0]['fixed'], fixed_landscape=landscape[0]['fixed'], viewport_source=src,
                           checks=res, checks_landscape=res_l, notes=notes + ['landscape ' + n for n in notes_l])
            else:
                # Reflow: no fixed record, text wraps inside each requested width,
                # and narrowing the viewport narrows the text measure.
                m = layout['margin']
                right_w = max(p['max_right'] for p in portrait)
                right_s = max(p['max_right'] for p in small)
                ok5 &= all(p['fixed']['fixed'] == 0 for p in portrait + small) and \
                    right_w <= W - m + 1 and right_s <= 480 - m + 1 and right_s < right_w - 50
                rec['text_right_720'], rec['text_right_480'] = round(right_w, 1), round(right_s, 1)
            items['5_mixed'].append(ok5)
            rec['mixed_ok'] = ok5
            rendered[part] = portrait[0].get('image')
            if shot_count < 2 or (fixed and shot_count < 3):
                name = f'{entry["id"]}-p{order + 1:02d}-{"fixed" if fixed else "reflow"}.png'
                portrait[0]['image'].save(shots / name)
                rec['screenshot'] = name
                shot_count += 1
            out['pages'].append(rec)
        spreads = book.spreads()
        out['spreads'] = spreads
        expected = entry.get('expected_spreads')
        if expected is not None:
            ok4 = len(expected) == len(spreads) and all(
                e.get('left') == g['left'] and e.get('right') == g['right'] and bool(e.get('single')) == g['single']
                for e, g in zip(expected, spreads))
            items['4_spread'].append(ok4)
            out['expected_spreads'] = expected
        # spread screenshot: first true two-page screen
        pair = next((s for s in spreads if s['left'] is not None and s['right'] is not None), None)
        if pair and rendered.get(pair['left']) and rendered.get(pair['right']):
            canvas = Image.new('RGB', (2 * W, H), (128, 128, 128))
            canvas.paste(rendered[pair['left']], (0, 0))
            canvas.paste(rendered[pair['right']], (W, 0))
            name = f'{entry["id"]}-spread-{pair["left"]}-{pair["right"]}.png'
            canvas.save(shots / name)
            out['spread_screenshot'] = name
        if entry.get('expected_toc_parts') is not None:
            toc = book.toc()
            out['toc'] = toc
            out['toc_ok'] = [t['part'] for t in toc] == entry['expected_toc_parts'] and \
                all(book.rendition(t['part']).layout == 1 for t in toc)
        out['page_count'] = total_pages
        for k, v in items.items():
            out['items'][k] = 'N/A' if not v else ('PASS' if all(v) else 'FAIL')
    finally:
        book.close()
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--dll', type=Path, required=True)
    ap.add_argument('--font', type=Path, required=True)
    ap.add_argument('--layout', type=Path, required=True)
    ap.add_argument('--corpus', type=Path, required=True, help='JSON list of books (oracle.json + real books)')
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    layout = json.loads(args.layout.read_text(encoding='utf-8-sig'))
    corpus = json.loads(args.corpus.read_text(encoding='utf-8'))
    shots = args.output / 'screenshots'
    shots.mkdir(parents=True, exist_ok=True)
    sdk = SDK(args.dll)
    font = c.c_void_p()
    sdk.ok('font_open', str(args.font).encode('utf-8'), c.byref(font))
    results = []
    for entry in corpus:
        try:
            results.append(verify_book(sdk, font, entry, layout, shots))
        except Exception as exc:  # report, keep going
            results.append({'id': entry['id'], 'error': repr(exc), 'items': {}})
        r = results[-1]
        print(r['id'], r.get('page_count'), r.get('error', ''), r['items'])
    sdk.font_free(font)
    (args.output / 'results.json').write_text(json.dumps(results, indent=2, ensure_ascii=False, default=str) + '\n',
                                              encoding='utf-8')


if __name__ == '__main__':
    main()
