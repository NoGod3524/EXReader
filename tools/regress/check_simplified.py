"""Observe real SDK pagination, punctuation geometry and independent cmap identity.

Books/screenshots stay in the ignored corpus directory. JSON contains numbers,
hashes and source offsets only. Full run needs Pillow and fontTools; self-check
uses only the standard library and runs in ctest without downloaded books.
"""
import argparse
from collections import Counter
import ctypes as c
import hashlib
import json
from pathlib import Path
import sys
import tempfile

from run_realbooks import (SDK, Bitmap, Options, Control, file_hash, pixel_hash,
                           read_json, write_json, compare)

HEAD = set(map(ord, '”，。、．）」』！？：；'))
TAIL = set(map(ord, '“（「『'))
FULL = set(map(ord, '—―‘’“”‥…、。〈〉《》「」『』【】〔〕〖〗〘〙〚〛！（），．：；？［］｛｝｟｠'))
ASCII = set(map(ord, ',.!?:;()[]{}'))
PAIRS = ['发髮', '后後', '里裏', '台臺', '干乾', '云雲', '面麵', '只隻',
         '钟鐘', '国國', '汉漢', '书書', '门門', '风風', '东東', '车車',
         '马馬', '鱼魚', '龙龍', '鸟鳥']


class Glyph(c.Structure):
    _fields_ = [('start', c.c_size_t), ('end', c.c_size_t),
                ('codepoint', c.c_uint32), ('glyph', c.c_uint32),
                *[(k, c.c_float) for k in ('x', 'baseline', 'advance', 'size')],
                ('page', c.c_size_t), ('node', c.c_size_t),
                ('color', c.c_uint32), ('flags', c.c_uint),
                *[(k, c.c_float) for k in ('clip_left', 'clip_right', 'line_height')],
                ('cluster_start', c.c_size_t), ('cluster_end', c.c_size_t),
                ('boundaries', c.c_uint), ('font_index', c.c_size_t),
                ('offset_x', c.c_float), ('offset_y', c.c_float), ('bidi_level', c.c_uint)]


class Line(c.Structure):
    _fields_ = [(k, c.c_size_t) for k in ('start', 'end', 'glyph_start', 'glyph_count')] + [
        ('y', c.c_float), ('page', c.c_size_t)] + [(k, c.c_float) for k in ('x', 'width', 'height')]


class Node(c.Structure):
    _fields_ = [('kind', c.c_int)] + [(k, c.c_size_t) for k in
        ('parent', 'first_child', 'next_sibling', 'chapter', 'start', 'end')] + [
        ('name', c.c_char_p), ('text', c.c_char_p), ('attributes', c.c_void_p),
        ('attribute_count', c.c_size_t)]


class Box(c.Structure):
    _fields_ = [('kind', c.c_int)] + [(k, c.c_size_t) for k in
        ('node', 'page', 'resource', 'start', 'end')] + [(k, c.c_float) for k in
        ('x', 'y', 'width', 'height', 'border_width')] + [(k, c.c_uint32) for k in
        ('background', 'border_color', 'flags')]


class ShapeOptions(c.Structure):
    _fields_ = [('font_size', c.c_float), ('style_flags', c.c_uint), ('direction', c.c_int),
                ('script', c.c_uint32), ('language', c.c_uint32), ('features', c.c_void_p),
                ('feature_count', c.c_size_t), ('context_before', c.c_uint32),
                ('context_after', c.c_uint32), ('control', Control)]


class Shaped(c.Structure):
    _fields_ = [('start', c.c_size_t), ('end', c.c_size_t), ('glyph', c.c_uint32)] + [
        (k, c.c_float) for k in ('advance_x', 'advance_y', 'offset_x', 'offset_y')] + [('flags', c.c_uint)]


class Observer(SDK):
    def __init__(self, path):
        super().__init__(path)
        for name, kind in [('layout_glyphs', Glyph), ('layout_lines', Line),
                           ('layout_boxes', Box), ('document_nodes', Node)]:
            fn = getattr(self.dll, 'exr_' + name)
            fn.restype = c.POINTER(kind)
            fn.argtypes = [c.c_void_p, c.POINTER(c.c_size_t)]
            setattr(self, name, fn)
        self.document_text = self.dll.exr_document_text
        self.document_text.restype = c.c_void_p
        self.document_text.argtypes = [c.c_void_p, c.POINTER(c.c_size_t)]
        self.shape = self.dll.exr_shape
        self.shape.restype = c.c_int
        self.shape.argtypes = [c.c_void_p, c.c_size_t, c.c_char_p, c.c_size_t,
                              c.POINTER(ShapeOptions), c.POINTER(c.POINTER(Shaped)),
                              c.POINTER(c.c_size_t), c.c_void_p]
        self.shape_defaults = self.dll.exr_shape_defaults
        self.shape_defaults.restype = ShapeOptions
        self.dll.exr_free.argtypes = [c.c_void_p]
        self.metrics = {}

    def nominal(self, font, g):
        key = (g.codepoint, g.size, g.flags & 3)
        if key not in self.metrics:
            options = self.shape_defaults()
            options.font_size, options.style_flags = g.size, g.flags & 3
            raw = chr(g.codepoint).encode()
            out, count = c.POINTER(Shaped)(), c.c_size_t()
            self.check('shape', font, 0, raw, len(raw), c.byref(options), c.byref(out), c.byref(count))
            self.metrics[key] = (sum(out[i].advance_x for i in range(count.value)),
                                 out[0].glyph if count.value == 1 else None)
            self.dll.exr_free(out)
        width, gid = self.metrics[key]
        # Contextual GSUB may select a proportional ellipsis after Latin text.
        # Its actual glyph's hmtx, rather than the scalar's default cmap glyph,
        # decides whether it has em-wide metrics and can be compressed.
        if gid is not None and gid != g.glyph:
            metrics = self.glyph_advances
            width += round(metrics[g.glyph]*g.size)-round(metrics[gid]*g.size)
        return width


def visible(g):
    return not g.flags & 4 and not chr(g.codepoint).isspace() and g.codepoint not in (0x200b, 0xfeff)


def explicit_start(g, nodes, text):
    if g.boundaries & 4:
        return 'mandatory'
    if g.node < len(nodes) and not text[nodes[g.node].start:g.start].decode('utf-8').strip():
        # The public glyph map describes normalized text. A structural <br/>
        # can precede a new TEXT node without setting MANDATORY on that node's
        # first scalar. Inspect the retained document tree, as cjk_measure does.
        for previous in reversed(nodes[:g.node]):
            if previous.kind == 15:
                return 'source_br'
            if previous.kind == 4 and previous.end > previous.start:
                break
    node = g.node
    while node < len(nodes):
        n = nodes[node]
        if n.kind in (6, 7, 9, 14) and not text[n.start:g.start].decode('utf-8').strip():
            return 'block_start'
        if n.parent >= node:
            break
        node = n.parent
    return 'soft_wrap'


def compression_errors(gs, nominal):
    """Check eligible em punctuation, terminal-run ownership, and ASCII metrics."""
    errors, eligible, compressed, pairs, ascii_count = [], 0, 0, 0, 0
    tail = len(gs)
    while tail and gs[tail-1].codepoint in FULL and abs(nominal(gs[tail-1])-gs[tail-1].size) < .02:
        tail -= 1
    terminal = len(gs)-tail
    for i, g in enumerate(gs):
        if g.codepoint not in FULL | ASCII:
            continue
        natural = nominal(g)
        if g.codepoint in ASCII:
            ascii_count += 1
            # Raster metrics are grid fitted. Latin kerns are charged to the
            # previous glyph; compare isolated/CJK-adjacent ASCII only here.
            cjk_left = i == 0 or gs[i-1].codepoint >= 0x3000
            cjk_right = i+1 == len(gs) or gs[i+1].codepoint >= 0x3000
            if cjk_left and cjk_right and abs(g.advance-natural) > .025:
                errors.append(('ascii_advance', g.start))
        if g.codepoint not in FULL or abs(natural-g.size) > .02:
            continue
        eligible += 1
        compressed += g.advance < natural-.02
        floor = g.size/terminal if terminal > 1 and i >= tail else g.size*.5
        if not floor-.025 <= g.advance <= g.size+.025:
            errors.append(('punctuation_floor', g.start))
        if i+1 < len(gs):
            b = gs[i+1]
            if (b.codepoint in FULL and g.cluster_end == b.cluster_start
                    and g.font_index == b.font_index and abs(g.size-b.size) < .01
                    and abs(nominal(b)-b.size) < .02):
                pairs += 1
                if g.advance+b.advance > 1.5*g.size+.025:
                    errors.append(('uncompressed_pair', g.start))
    if terminal > 1 and abs(sum(g.advance for g in gs[tail:])-gs[-1].size) > .025:
        errors.append(('terminal_run', gs[tail].start))
    return errors, eligible, compressed, pairs, ascii_count


def font_oracle(path):
    from fontTools.ttLib import TTFont
    font = TTFont(path)
    cmap = font.getBestCmap()
    glyph_ids = {cp: font.getGlyphID(name) for cp, name in cmap.items()}
    advances = {font.getGlyphID(name): font['hmtx'][name][0]/font['head'].unitsPerEm
                for name in font.getGlyphOrder()}
    font.close()
    return glyph_ids, advances


def screenshot(bitmap, path):
    from PIL import Image
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.frombytes('RGBA', (bitmap.width, bitmap.height),
                    c.string_at(bitmap.pixels, bitmap.stride*bitmap.height),
                    'raw', 'RGBA', bitmap.stride).save(path)
    return {'path': str(path.resolve()), 'sha256': file_hash(path)}


def observe(sdk, font, source, config, advances, shots=None, capture=False):
    publication, document, pager, page = [c.c_void_p() for _ in range(4)]
    bitmap = Bitmap()
    result = dict(status='ok', pages=[], glyph_count=0, lines=0, violations=[],
                  counts=Counter(), screenshots={}, line_char_counts=[], punctuation_positions=[])
    if capture:
        result['glyph_identity'] = []
    layout_digest = hashlib.sha256()
    try:
        if source.suffix == '.epub':
            sdk.check('publication_open', str(source.resolve()).encode(), c.byref(publication))
            nparts = c.c_size_t()
            sdk.publication_parts(publication, c.byref(nparts))
        else:
            nparts = c.c_size_t(1)
        for part in range(nparts.value):
            if publication:
                sdk.check('publication_load', publication, part, c.byref(document))
            else:
                sdk.check('document_open', str(source.resolve()).encode(), c.byref(document))
            n = c.c_size_t()
            pnodes = sdk.document_nodes(document, c.byref(n))
            nodes = [pnodes[i] for i in range(n.value)]
            raw = sdk.document_text(document, c.byref(n))
            text = c.string_at(raw, n.value)
            sdk.check('pager_create', document, font, c.byref(config), c.byref(pager))
            local_page = 0
            while True:
                sdk.check('pager_next', pager, c.byref(page))
                if not page:
                    break
                ordinal = len(result['pages'])
                ptr = sdk.layout_glyphs(page, c.byref(n))
                glyphs = [ptr[i] for i in range(n.value)]
                line_ptr = sdk.layout_lines(page, c.byref(n))
                lines = [line_ptr[i] for i in range(n.value)]
                box_ptr = sdk.layout_boxes(page, c.byref(n))
                boxes = [box_ptr[i] for i in range(n.value)]
                result['counts'].update(table_cells=sum(b.kind == 3 for b in boxes),
                    image_boxes=sum(b.kind == 2 for b in boxes),
                    image_placeholders=sum(b.kind == 2 and bool(b.flags & 1) for b in boxes))
                result['glyph_count'] += len(glyphs)
                if capture:
                    result['glyph_identity'].extend(dict(codepoint=g.codepoint, glyph=g.glyph,
                        source_codepoint=ord(text[g.start:g.end].decode('utf-8')[0]), flags=g.flags)
                        for g in glyphs if visible(g) and g.end > g.start)
                for line in lines:
                    gs = [g for g in glyphs[line.glyph_start:line.glyph_start+line.glyph_count] if visible(g)]
                    if not gs:
                        continue
                    result['lines'] += 1
                    if capture:
                        result['line_char_counts'].append(len(gs))
                        result['punctuation_positions'].append([(i, g.codepoint, round(g.x, 4)) for i, g in enumerate(gs)
                                                               if g.codepoint in FULL | ASCII])
                    if gs[0].codepoint in HEAD:
                        reason = explicit_start(gs[0], nodes, text)
                        result['counts']['head_'+reason] += 1
                        if reason == 'soft_wrap':
                            result['violations'].append(('head', part, ordinal, gs[0].start))
                    if gs[-1].codepoint in TAIL:
                        result['violations'].append(('tail', part, ordinal, gs[-1].start))
                    # Whitespace affects terminal-run ownership. Strip it for
                    # edge checks only, retaining it for compression geometry.
                    raw_line = [g for g in glyphs[line.glyph_start:line.glyph_start+line.glyph_count]
                                if not g.flags & 4]
                    errs, eligible, compressed, pairs, ascii_count = compression_errors(
                        raw_line, lambda g: sdk.nominal(sdk.layout_font(page), g))
                    result['counts'].update(eligible_punctuation=eligible, compressed_glyphs=compressed,
                        adjacent_pairs=pairs, ascii_punctuation=ascii_count,
                        ascii_digits=sum(48 <= g.codepoint <= 57 for g in gs),
                        chinese_numerals=sum(chr(g.codepoint) in '零〇一二三四五六七八九十百千万亿两' for g in gs),
                        missing_glyphs=sum(bool(g.flags & 8) for g in gs))
                    result['violations'].extend((kind, part, ordinal, offset) for kind, offset in errs)
                # No allocator padding enters determinism hashes.
                for g in glyphs:
                    layout_digest.update(json.dumps([getattr(g, k) for k, _ in Glyph._fields_],
                                                     separators=(',', ':')).encode())
                for line in lines:
                    layout_digest.update(json.dumps([getattr(line, k) for k, _ in Line._fields_],
                                                     separators=(',', ':')).encode())
                sdk.check('render_page_color', page, sdk.layout_font(page), 0, c.byref(bitmap))
                result['pages'].append(dict(page=ordinal, part=part, part_page=local_page,
                    width=bitmap.width, height=bitmap.height, channels=bitmap.channels,
                    glyph_count=len(glyphs), pixel_sha256=pixel_hash(bitmap)))
                if shots:
                    kinds = ['first'] if ordinal == 0 else []
                    if sum(0x4e00 <= g.codepoint <= 0x9fff for g in glyphs) >= 20:
                        kinds.append('first-han')
                    if any(b.kind == 3 for b in boxes):
                        kinds.append('first-table')
                    if any(b.kind == 2 and not b.flags & 1 for b in boxes):
                        kinds.append('first-image')
                    for kind in kinds:
                        if kind not in result['screenshots']:
                            result['screenshots'][kind] = screenshot(bitmap, shots / (kind+'.png'))
                sdk.bitmap_free(c.byref(bitmap))
                sdk.layout_free(page)
                page = c.c_void_p()
                local_page += 1
            sdk.pager_free(pager)
            pager = c.c_void_p()
            sdk.document_free(document)
            document = c.c_void_p()
            if part % 50 == 0:
                print(source.stem, 'part', part, 'pages', len(result['pages']), flush=True)
        result['page_count'] = len(result['pages'])
        result['layout_sha256'] = layout_digest.hexdigest()
        return result
    finally:
        sdk.bitmap_free(c.byref(bitmap))
        for kind, handle in [('layout', page), ('pager', pager), ('document', document), ('publication', publication)]:
            getattr(sdk, kind+'_free')(handle)


def self_check():
    def glyph(cp, advance, start=0):
        return Glyph(codepoint=ord(cp), advance=advance, size=20, start=start,
                     cluster_start=start, cluster_end=start+3)
    good = [glyph('，', 10), glyph('。', 10, 3), glyph('字', 20, 6)]
    assert not compression_errors(good, lambda g: 20)[0]
    good[0].advance = 4
    assert compression_errors(good, lambda g: 20)[0][0][0] == 'punctuation_floor'
    good[0].advance = 20
    good[1].advance = 20
    assert any(e[0] == 'uncompressed_pair' for e in compression_errors(good, lambda g: 20)[0])
    terminal = [glyph('字', 20), glyph('。', 20/3, 3), glyph('”', 20/3, 6), glyph('！', 20/3, 9)]
    assert not compression_errors(terminal, lambda g: 20)[0]
    assert compression_errors([glyph(',', 3)], lambda g: 6)[0] == [('ascii_advance', 0)]
    g = glyph('，', 20)
    assert explicit_start(g, [], b'') == 'soft_wrap'
    g.boundaries = 4
    assert explicit_start(g, [], b'') == 'mandatory'
    g.boundaries = 0
    assert explicit_start(g, [Node(kind=6, parent=0, start=0)], b'') == 'block_start'
    g.node = 2
    assert explicit_start(g, [Node(kind=6), Node(kind=15), Node(kind=4)], b'') == 'source_br'
    assert len(PAIRS) == 20 and len(set(''.join(PAIRS))) == 40
    print('simplified observer: corruption, ASCII metrics, terminal runs and break reasons passed')


def probes(sdk, font, config, advances, gids, root):
    fixtures = read_json(Path(__file__).parents[2]/'tests/fixtures/simplified-comparison.json')
    output = {'pairs': [], 'comparisons': [], 'mixed_widths': []}
    root.mkdir(parents=True, exist_ok=True)
    def render(text, name, width=720):
        source = root/(name+'.html')
        source.write_text('<html><body><p>'+text+'</p></body></html>', encoding='utf-8')
        config.page.width = width
        return observe(sdk, font, source, config, advances, root/name, True)
    for pair in PAIRS:
        values = [render(cp, 'glyph-'+str(ord(cp))) for cp in pair]
        records = [r['glyph_identity'][0] for r in values]
        passed = all(r['codepoint'] == r['source_codepoint'] == ord(cp)
                     and r['glyph'] == gids[ord(cp)] and not r['flags'] & 8
                     for cp, r in zip(pair, records))
        distinct = records[0]['glyph'] != records[1]['glyph'] and values[0]['pages'][0]['pixel_sha256'] != values[1]['pages'][0]['pixel_sha256']
        output['pairs'].append(dict(pair=pair, records=records, passed=passed and distinct,
                                   pixel_sha256=[r['pages'][0]['pixel_sha256'] for r in values]))
    for sample in fixtures['samples']:
        for width in (360, 720):
            a, b = [render(sample[k], sample['id']+'-'+k+'-'+str(width), width)
                    for k in ('simplified', 'traditional')]
            ac, bc = a['line_char_counts'], b['line_char_counts']
            output['comparisons'].append(dict(id=sample['id'], width=width,
                simplified_lines=a['lines'], traditional_lines=b['lines'], line_delta=b['lines']-a['lines'],
                simplified_chars=sum(ac), traditional_chars=sum(bc), char_delta=sum(bc)-sum(ac),
                simplified_per_line=ac, traditional_per_line=bc,
                different_line_counts=sum(x != y for x, y in zip(ac, bc))+abs(len(ac)-len(bc)),
                punctuation_position_differences=sum(x != y for x, y in zip(a['punctuation_positions'], b['punctuation_positions']))+
                    abs(len(a['punctuation_positions'])-len(b['punctuation_positions'])),
                simplified_punctuation_positions=a['punctuation_positions'], traditional_punctuation_positions=b['punctuation_positions'],
                changed_pixel_pages=sum(x['pixel_sha256'] != y['pixel_sha256'] for x,y in zip(a['pages'],b['pages'])),
                violations=len(a['violations'])+len(b['violations'])))
    for width in (140, 220, 360, 720):
        r = render(fixtures['mixed'], 'mixed-'+str(width), width)
        output['mixed_widths'].append(dict(width=width, lines=r['lines'], counts=r['counts'],
                                         violations=r['violations'], layout_sha256=r['layout_sha256']))
    output['crossed_pairs'] = sum(not x['passed'] for x in output['pairs'])
    config.page.width = 720
    return output


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--self-check', action='store_true')
    p.add_argument('--dll', type=Path)
    p.add_argument('--font', type=Path)
    p.add_argument('--manifest', type=Path, default=Path(__file__).with_name('simplified.json'))
    p.add_argument('--output', type=Path)
    p.add_argument('--baseline', type=Path, help='compare two full independent observations')
    args = p.parse_args()
    if args.self_check:
        self_check()
        return 0
    sdk = Observer(args.dll.resolve())
    gids, advances = font_oracle(args.font)
    sdk.glyph_advances = advances
    font = c.c_void_p()
    sdk.check('font_open', str(args.font.resolve()).encode(), c.byref(font))
    result = dict(dll_sha256=file_hash(args.dll), font_sha256=file_hash(args.font),
                  observer_sha256=file_hash(__file__), books=[])
    config = sdk.layout_config_defaults()
    settings = read_json(Path(__file__).with_name('simplified-layout.json'))
    config.page = Options(**{k: settings[k] for k, _ in Options._fields_})
    config.document_css = settings['document_css']
    result['layout'] = settings
    try:
        result['probes'] = probes(sdk, font, config, advances, gids,
                                 args.manifest.parent.parent.parent/'tests/corpus/simplified/probes')
        write_json(args.output, result)
        for b in read_json(args.manifest)['books']:
            source = (args.manifest.parent / b['path']).resolve()
            if file_hash(source) != b['sha256']:
                raise ValueError('corpus hash mismatch: '+b['id'])
            r = observe(sdk, font, source, config, advances, source.parent/'screenshots'/b['id'])
            if file_hash(source) != b['sha256']:
                raise ValueError('source changed while reading')
            r.update(id=b['id'], sha256=b['sha256'])
            result['books'].append(r)
            write_json(args.output, result)
            print(b['id'], r['page_count'], 'pages', len(r['violations']), 'violations', flush=True)
    finally:
        sdk.font_free(font)
    failed = (any(b['violations'] for b in result['books']) or result['probes']['crossed_pairs']
              or any(x['violations'] for x in result['probes']['mixed_widths'])
              or any(x['violations'] for x in result['probes']['comparisons']))
    if args.baseline:
        before = read_json(args.baseline)
        diff = compare(before, result)
        diff['layout_hash_changed_books'] = [b['id'] for a, b in zip(before['books'], result['books'])
                                             if a['layout_sha256'] != b['layout_sha256']]
        diff['needs_review'] |= bool(diff['layout_hash_changed_books'])
        write_json(args.output.with_suffix('.diff.json'), diff)
        failed |= diff['needs_review']
    return int(failed)


if __name__ == '__main__':
    sys.exit(main())
