#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Real-font acceptance: 640 scalar picks, an independent FreeType oracle and EPUB pixels.

Run --help. Generated EPUBs belong in build/, never in the repository.
The FreeType bridge uses the same pinned library but never the manager's index.
"""
import argparse
import collections
import ctypes as c
import hashlib
import json
import os
from pathlib import Path
import sys
import unicodedata as ud
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/regress'))
import run_realbooks as reg

SIZE_MAX = c.c_size_t(-1).value


class Pick(c.Structure):
    _fields_ = [('struct_size', c.c_size_t), ('face', c.c_size_t),
                ('step', c.c_uint), ('chain_position', c.c_size_t)]


class Face(c.Structure):
    _fields_ = [('struct_size', c.c_size_t), ('family', c.c_char_p),
                ('style_name', c.c_char_p), ('path', c.c_char_p),
                ('face_index', c.c_uint), ('style', c.c_uint), ('weight', c.c_uint),
                ('scripts', c.c_uint), ('location', c.c_size_t), ('codepoints', c.c_size_t)]


class Glyph(c.Structure):
    _fields_ = [('start', c.c_size_t), ('end', c.c_size_t), ('codepoint', c.c_uint32),
                ('glyph', c.c_uint32), ('x', c.c_float), ('baseline', c.c_float),
                ('advance', c.c_float), ('size', c.c_float), ('page', c.c_size_t),
                ('node', c.c_size_t), ('color', c.c_uint32), ('flags', c.c_uint),
                ('clip_left', c.c_float), ('clip_right', c.c_float), ('line_height', c.c_float),
                ('cluster_start', c.c_size_t), ('cluster_end', c.c_size_t),
                ('boundaries', c.c_uint), ('font_index', c.c_size_t),
                ('offset_x', c.c_float), ('offset_y', c.c_float), ('bidi_level', c.c_uint)]


def sample():
    def spread(values, count, first=()):
        result = list(dict.fromkeys(first))
        values = [cp for cp in values if cp not in result]
        n = count - len(result)
        return result + [values[i * (len(values) - 1) // (n - 1)] for i in range(n)]
    gb = [ord(bytes([a, b]).decode('gb2312')) for a in range(0xb0, 0xd8)
          for b in range(0xa1, 0xff) if a < 0xd7 or b <= 0xf9]
    assigned = lambda a, b: [cp for cp in range(a, b) if ud.category(chr(cp)) != 'Cn']
    emoji = [0x200d, 0xfe0f, 0x1f600, 0x1f468, 0x1f469, 0x1f467, 0x1f466,
             0x1f3f3, 0x1f308, 0x1f4bb, 0x1f680, 0x2764, 0x1f48b, 0x1f3fb, 0x1f3ff]
    groups = {
        'cjk_gb2312_level1': spread(gb, 200, map(ord, '的一是不了人我在有他')),
        'cjk_extension_ab': spread(range(0x3400, 0x4dc0), 50, [0x3400, 0x3401]) +
                            spread(range(0x20000, 0x2a6e0), 50, [0x20000, 0x20001]),
        'cjk_compatibility': spread(assigned(0xf900, 0xfb00), 25, [0xfa0e, 0xfa0f]) +
                             spread(assigned(0x2f800, 0x2fa20), 25),
        'kana_halfwidth': spread(range(0x3041, 0x3097), 20, [0x3042]) +
                          spread(range(0x30a1, 0x30fb), 20, [0x30a2]) +
                          spread(range(0xff66, 0xff9e), 20, [0xff71]),
        'hangul': spread(range(0xac00, 0xd7a4), 50, [0xac00, 0xac01, 0xac02]),
        'emoji': spread(range(0x1f600, 0x1f650), 60, emoji),
        'math_symbols': spread(assigned(0x2200, 0x2300), 50, [0x2211, 0x222b, 0x221a, 0x21d2]),
        'arabic_hebrew': spread(range(0x0627, 0x064b), 20, [0x627, 0x628, 0x62a]) +
                         spread(range(0x05d0, 0x05eb), 20, [0x5d0, 0x5d1, 0x5d2]),
        'fullwidth_halfwidth': list(map(ord, 'ＡAａaＢBｂbＣCｃcＤDｄdＥEｅeＦFｆf０0１1２2')),
    }
    rows = [dict(group=group, cp=cp, codepoint=f'U+{cp:04X}', character=chr(cp),
                 name=ud.name(chr(cp), '<unnamed>')) for group, cps in groups.items() for cp in cps]
    assert [len(v) for v in groups.values()] == [200, 100, 50, 60, 50, 60, 50, 40, 30]
    assert len(rows) == len({r['cp'] for r in rows}) == 640
    return rows


SEQUENCES = ['👨‍👩‍👧', '🏳️‍🌈', '👩‍💻', '👨‍🚀', '👩‍❤️‍👨', '👨‍👩‍👧‍👦', '👩🏻‍💻', '👨🏿‍🚀']
SCENES = [
    ('chinese_emoji', 'zh', '中文阅读与表情混排。今天一家人👨‍👩‍👧来到公园，看见彩虹🏳️‍🌈，开心地说😀：世界有许多美好的故事！全角Ａ与半角A共同出现。' * 5 + ' '.join(SEQUENCES)),
    ('japanese', 'ja', '日本語の文章を読みます。ひらがなの「あいうえお」とカタカナの「アイウエオ」、半角の「ｱｲｳｴｵ」を漢字と一緒に表示します。春の空には美しい雲があります。' * 5),
    ('arabic_rtl', 'ar', 'القراءة رحلة جميلة في عالم المعرفة. نقرأ الكتب ونتعلم كل يوم كلمات جديدة. اللغة العربية تجمع بين جمال الحروف ووضوح المعنى. ' * 10),
    ('math_symbols', 'en', '∑ ∫ √ ⇒ ∀ ∂ ∃ ∅ ∇ ∈ ∉ ∋ − ∓ ∗ ∘ ∝ ∞ ∠ ∧ ∨ ∩ ∪ ≈ ≠ ≡ ≤ ≥ ⊂ ⊃ ⊆ ⊇ ⊕ ⊗ ⊥ ⋅  ∑ x = 10; ∫ x dx = x²/2; √4 = 2 ⇒ 2² = 4. ' * 6),
]


class FreeType:
    def __init__(self, path):
        self.dll = c.CDLL(str(path.resolve()))
        specs = {'init': (c.c_void_p, []), 'done': (None, [c.c_void_p]),
                 'open': (c.c_void_p, [c.c_void_p, c.c_void_p, c.c_long, c.c_long]),
                 'close': (None, [c.c_void_p]), 'count': (c.c_long, [c.c_void_p]),
                 'family': (c.c_char_p, [c.c_void_p]),
                 'index': (c.c_uint, [c.c_void_p, c.c_uint]),
                 'load': (c.c_int, [c.c_void_p, c.c_uint])}
        for name, (ret, args) in specs.items():
            fn = getattr(self.dll, 'fc_' + name)
            fn.restype, fn.argtypes = ret, args
            setattr(self, name, fn)
        self.library = self.init()
        assert self.library
        self.loaded = {}

    def face(self, path, index):
        key = (path, index)
        if key not in self.loaded:
            data = Path(path).read_bytes()
            face = self.open(self.library, data, len(data), index)
            assert face, key
            self.loaded[key] = (data, face)
        return self.loaded[key][1]

    def free(self):
        for _, face in self.loaded.values():
            self.close(face)
        self.done(self.library)


def bind(sdk):
    ptr, out, err = c.c_void_p, c.POINTER(c.c_void_p), c.POINTER(reg.Error)
    specs = {'font_manager_open': (c.c_int, [c.c_char_p, out, err]),
             'font_manager_free': (None, [ptr]),
             'font_manager_face_count': (c.c_size_t, [ptr]),
             'font_manager_face': (c.c_int, [ptr, c.c_size_t, c.POINTER(Face), err]),
             'font_manager_pick': (c.c_int, [ptr, c.c_char_p, c.c_uint, c.c_uint32, c.POINTER(Pick), err]),
             'font_manager_create_font': (c.c_int, [ptr, c.c_char_p, c.c_uint, out,
                                                  c.POINTER(c.POINTER(c.c_size_t)), c.POINTER(c.c_size_t), err]),
             'bitmap_write_png': (c.c_int, [c.POINTER(reg.Bitmap), c.c_char_p, err]),
             'document_open_memory': (c.c_int, [c.c_int, c.c_void_p, c.c_size_t, out, err]),
             'free': (None, [ptr])}
    for name, (ret, args) in specs.items():
        fn = getattr(sdk.dll, 'exr_' + name)
        fn.restype, fn.argtypes = ret, args
        setattr(sdk, name, fn)


def inventory(ft, output, rows):
    directories = [Path(os.environ['WINDIR']) / 'Fonts',
                   Path(os.environ['LOCALAPPDATA']) / 'Microsoft/Windows/Fonts']
    paths = {p.resolve() for d in directories for p in d.rglob('*') if p.suffix.lower() in ('.ttf', '.otf', '.ttc', '.otc')}
    # Also audit registered fonts outside the standard directories.
    import winreg
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        with winreg.OpenKey(hive, r'SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts') as key:
            for i in range(winreg.QueryInfoKey(key)[1]):
                _, value, _ = winreg.EnumValue(key, i)
                if not isinstance(value, str):
                    continue
                p = Path(os.path.expandvars(value))
                if not p.is_absolute():
                    p = directories[0] / p
                if p.is_file() and p.suffix.lower() in ('.ttf', '.otf', '.ttc', '.otc'):
                    paths.add(p.resolve())
    witnesses = {str(r['cp']): [] for r in rows}
    files, errors = [], []
    for path in sorted(paths):
        try:
            data = path.read_bytes()
        except OSError as exc:
            errors.append(dict(path=str(path), error=str(exc)))
            continue
        header = ft.open(ft.library, data, len(data), -1)
        if not header:
            errors.append(dict(path=str(path), error='FreeType cannot open container'))
            continue
        count = ft.count(header)
        ft.close(header)
        files.append(dict(path=str(path), sha256=hashlib.sha256(data).hexdigest(), faces=count))
        for index in range(count):
            face = ft.open(ft.library, data, len(data), index)
            if not face:  # Non-Unicode symbol faces cannot cover a Unicode scalar.
                continue
            family = (ft.family(face) or b'').decode('utf-8', 'replace')
            for row in rows:
                glyph = ft.index(face, row['cp'])
                if glyph:
                    load = ft.load(face, glyph)
                    assert load == 0, (path, index, row, glyph, load)
                    witnesses[str(row['cp'])].append(dict(path=str(path), face_index=index, family=family, glyph=glyph))
            ft.close(face)
    result = dict(files=files, errors=errors, witnesses=witnesses)
    reg.write_json(output, result)
    assert not errors, errors
    return result


def faces(sdk, manager):
    result = []
    for i in range(sdk.font_manager_face_count(manager)):
        face = Face(struct_size=c.sizeof(Face))
        sdk.check('font_manager_face', manager, i, c.byref(face))
        result.append({name: (getattr(face, name).decode('utf-8') if name in ('family', 'style_name', 'path')
                              else getattr(face, name)) for name, _ in Face._fields_ if name != 'struct_size'})
    return result


def matrix(sdk, ft, manager, info, args):
    rows = sample()
    extra = [dict(group='tibetan_supplement', cp=cp, codepoint=f'U+{cp:04X}', character=chr(cp),
                  name=ud.name(chr(cp))) for cp in range(0x0f40, 0x0f60) if cp != 0x0f48]
    oracle_path = args.output / 'oracle.json'
    oracle = reg.read_json(args.oracle) if args.oracle else inventory(ft, oracle_path, rows + extra)
    if args.oracle:
        assert all(reg.file_hash(f['path']) == f['sha256'] for f in oracle['files'])
    font, mapping, count = c.c_void_p(), c.POINTER(c.c_size_t)(), c.c_size_t()
    sdk.check('font_manager_create_font', manager, b'serif', 0, c.byref(font), c.byref(mapping), c.byref(count))
    loaded = set(mapping[:count.value])
    for row in rows + extra:
        pick = Pick(struct_size=c.sizeof(Pick))
        sdk.check('font_manager_pick', manager, b'serif', 0, row['cp'], c.byref(pick))
        row.update(face=None if pick.face == SIZE_MAX else pick.face, step=pick.step,
                   chain_position=None if pick.chain_position == SIZE_MAX else pick.chain_position)
        available = oracle['witnesses'][str(row['cp'])]
        row['local_face_count'] = len(available)
        if pick.face == SIZE_MAX:
            row.update(verdict='manager_miss' if available else 'font_absent', ft_index=0,
                       witness=available[0] if available else None)
        else:
            face = info[pick.face]
            actual = ft.face(face['path'], face['face_index'])
            glyph = ft.index(actual, row['cp'])
            row.update(selected=face, ft_index=glyph, ft_load_error=ft.load(actual, glyph) if glyph else None,
                       loaded_by_create_font=pick.face in loaded,
                       verdict='hit' if glyph else 'false_coverage')
            assert glyph and row['ft_load_error'] == 0, row
            assert row['loaded_by_create_font'], row
    sdk.font_free(font)
    sdk.free(mapping)
    summary = dict(total=len(rows), counts=dict(collections.Counter(r['verdict'] for r in rows)),
                   groups={g: dict(collections.Counter(r['verdict'] for r in rows if r['group'] == g))
                           for g in dict.fromkeys(r['group'] for r in rows)},
                   selected_ft_zero=sum(r['face'] is not None and r['ft_index'] == 0 for r in rows))
    result = dict(dll_sha256=reg.file_hash(args.dll), summary=summary, rows=rows,
                  tibetan_supplement=extra, manager_faces=info, oracle_sha256=reg.file_hash(args.oracle or oracle_path))
    if args.recommend_font:
        recommended = ft.face(str(args.recommend_font.resolve()), 0)
        checks = []
        for row in rows:
            if row['verdict'] == 'font_absent':
                glyph = ft.index(recommended, row['cp'])
                assert glyph and ft.load(recommended, glyph) == 0
                checks.append(dict(codepoint=row['codepoint'], ft_index=glyph))
        result['recommendation'] = dict(family=(ft.family(recommended) or b'').decode(),
                                       sha256=reg.file_hash(args.recommend_font), checked=checks)
    reg.write_json(args.output / 'matrix.json', result)
    gaps = [r for r in rows if r['verdict'] != 'hit']
    (args.output / 'gaps.txt').write_text('\n'.join(f"{r['codepoint']} {r['character']} {r['name']}: {r['verdict']}" for r in gaps) + '\n', encoding='utf-8')
    print(json.dumps(summary), flush=True)
    if args.require_complete:
        assert all(r['verdict'] in ('hit', 'font_absent') for r in rows + extra)


def make_epub(path):
    manifest, spine = [], []
    entries = {'mimetype': 'application/epub+zip', 'META-INF/container.xml':
               '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0"><rootfiles><rootfile full-path="book.opf" media-type="application/oebps-package+xml"/></rootfiles></container>'}
    for i, (name, lang, text) in enumerate(SCENES):
        manifest.append(f'<item id="p{i}" href="{name}.xhtml" media-type="application/xhtml+xml"/>')
        spine.append(f'<itemref idref="p{i}"/>')
        direction = 'rtl' if lang == 'ar' else 'ltr'
        entries[name + '.xhtml'] = f'<html xmlns="http://www.w3.org/1999/xhtml" lang="{lang}" dir="{direction}"><head><title>{name}</title><style>body{{margin:0;font-family:serif}} p{{margin:0;direction:{direction};text-align:justify}}</style></head><body><p>{text}</p></body></html>'
    entries['book.opf'] = '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="id">urn:exreader:fontcov:1</dc:identifier><dc:title>Multilingual font coverage</dc:title><dc:language>mul</dc:language><meta property="dcterms:modified">2026-11-09T00:00:00Z</meta></metadata><manifest>' + ''.join(manifest) + '</manifest><spine>' + ''.join(spine) + '</spine></package>'
    with zipfile.ZipFile(path, 'w') as archive:
        for name, value in entries.items():
            archive.writestr(zipfile.ZipInfo(name, (2026, 11, 9, 0, 0, 0)), value.encode('utf-8'))


def render(sdk, ft, manager, info, args):
    epub = args.output / 'multilingual.epub'
    make_epub(epub)
    font, pub, mapping, count = c.c_void_p(), c.c_void_p(), c.POINTER(c.c_size_t)(), c.c_size_t()
    sdk.check('font_manager_create_font', manager, b'serif', 0, c.byref(font), c.byref(mapping), c.byref(count))
    loaded = [info[mapping[i]] for i in range(count.value)]
    sdk.check('publication_open', str(epub).encode(), c.byref(pub))
    n = c.c_size_t()
    sdk.publication_parts(pub, c.byref(n))
    assert n.value == 4
    config = sdk.layout_config_defaults()
    config.page = reg.Options(720, 720, 24, 28, 1.12, 0)
    config.embedded_fonts = 0
    result = dict(epub_sha256=reg.file_hash(epub), dll_sha256=reg.file_hash(args.dll),
                  loaded_faces=loaded, scenes=[])
    for i, (name, lang, text) in enumerate(SCENES):
        doc, pager = c.c_void_p(), c.c_void_p()
        sdk.check('publication_load', pub, i, c.byref(doc))
        sdk.check('pager_create', doc, font, c.byref(config), c.byref(pager))
        pages = []
        while True:
            page = c.c_void_p()
            sdk.check('pager_next', pager, c.byref(page))
            if not page:
                break
            ng = c.c_size_t()
            glyphs = c.cast(sdk.layout_glyphs(page, c.byref(ng)), c.POINTER(Glyph))
            visible, zero, missing, details, rtl, usage = 0, 0, 0, [], 0, collections.Counter()
            for g in glyphs[:ng.value]:
                if g.flags & 4:
                    continue
                visible += 1
                face = loaded[g.font_index]
                raw = ft.index(ft.face(face['path'], face['face_index']), g.codepoint)
                zero += raw == 0
                missing += bool(g.flags & 8) or g.glyph == 0
                rtl += bool(g.bidi_level & 1)
                usage[face['family']] += 1
                if raw == 0 or g.glyph == 0 or g.flags & 8:
                    details.append(dict(cp=f'U+{g.codepoint:04X}', glyph=g.glyph, face=face))
            bitmap = reg.Bitmap()
            sdk.check('render_page_color', page, None, 0, c.byref(bitmap))
            pixels = c.string_at(bitmap.pixels, bitmap.stride * bitmap.height)
            nonwhite = sum(any(pixels[y * bitmap.stride + x * 4 + k] < 250 for k in range(3))
                           for y in range(bitmap.height) for x in range(bitmap.width))
            png = args.output / f'{name}-{len(pages)}.png'
            sdk.check('bitmap_write_png', c.byref(bitmap), str(png).encode())
            pages.append(dict(screenshot=png.name, sha256=reg.file_hash(png), width=bitmap.width,
                              height=bitmap.height, nonblank_ratio=nonwhite / (bitmap.width * bitmap.height),
                              visible_glyphs=visible, ft_zero=zero, notdef=missing, missing=details,
                              rtl_glyphs=rtl, font_usage=dict(usage)))
            sdk.bitmap_free(c.byref(bitmap))
            sdk.layout_free(page)
        sdk.pager_free(pager)
        sdk.document_free(doc)
        result['scenes'].append(dict(name=name, language=lang, pages=pages))
    sdk.publication_free(pub)
    # A scalar cmap hit alone does not demonstrate a ZWJ sequence. Compare with
    # independent HarfBuzz shaping: Segoe's families use several positioned
    # component glyphs, so "one glyph per sequence" would be an invalid oracle.
    import uharfbuzz as hb
    reference_path = Path(os.environ['WINDIR']) / 'Fonts/seguiemj.ttf'
    reference_face = hb.Face(reference_path.read_bytes())
    reference_font = hb.Font(reference_face)
    hb.ot_font_set_funcs(reference_font)
    result['zwj_reference'] = dict(engine='HarfBuzz', version=hb.version_string(),
                                   font_sha256=reg.file_hash(reference_path))
    result['zwj_sequences'] = []
    for sequence in SEQUENCES:
        html = ('<p>' + sequence + '</p>').encode('utf-8')
        doc, pager, page = c.c_void_p(), c.c_void_p(), c.c_void_p()
        sdk.check('document_open_memory', 2, html, len(html), c.byref(doc))
        sdk.check('pager_create', doc, font, c.byref(config), c.byref(pager))
        sdk.check('pager_next', pager, c.byref(page))
        ng = c.c_size_t()
        glyphs = c.cast(sdk.layout_glyphs(page, c.byref(ng)), c.POINTER(Glyph))
        visible = [g for g in glyphs[:ng.value] if not g.flags & 4]
        buffer = hb.Buffer()
        buffer.add_str(sequence)
        buffer.guess_segment_properties()
        buffer.flags = hb.BufferFlags.REMOVE_DEFAULT_IGNORABLES
        hb.shape(reference_font, buffer)
        expected = [g.codepoint for g in buffer.glyph_infos]
        reference_positions = [[p.x_advance, p.x_offset, p.y_offset] for p in buffer.glyph_positions]
        positions = [[g.advance * reference_face.upem / g.size,
                      g.offset_x * reference_face.upem / g.size,
                      g.offset_y * reference_face.upem / g.size] for g in visible]
        matches = expected == [g.glyph for g in visible]
        item = dict(sequence=sequence, scalars=[f'U+{ord(ch):04X}' for ch in sequence],
                    visible_glyphs=len(visible), glyphs=[g.glyph for g in visible],
                    reference_glyphs=expected, positions=positions, reference_positions=reference_positions,
                    matches_reference_glyphs=matches,
                    families=[loaded[g.font_index]['family'] for g in visible],
                    ft_zero=sum(ft.index(ft.face(loaded[g.font_index]['path'], loaded[g.font_index]['face_index']),
                                         g.codepoint) == 0 for g in visible),
                    notdef=sum(g.glyph == 0 or bool(g.flags & 8) for g in visible))
        result['zwj_sequences'].append(item)
        sdk.layout_free(page)
        sdk.pager_free(pager)
        sdk.document_free(doc)
    sdk.font_free(font)
    sdk.free(mapping)
    reg.write_json(args.output / 'render.json', result)
    for scene in result['scenes']:
        print(json.dumps(scene, ensure_ascii=True), flush=True)
    if args.require_complete:
        assert all(s['matches_reference_glyphs'] and s['ft_zero'] == s['notdef'] == 0
                   for s in result['zwj_sequences']), result['zwj_sequences']
        for scene in result['scenes']:
            assert len(scene['pages']) == 1, scene
            for page in scene['pages']:
                assert page['nonblank_ratio'] > .05 and page['ft_zero'] == page['notdef'] == 0, page
            if scene['language'] == 'ar':
                assert scene['pages'][0]['rtl_glyphs'] > 0


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=['matrix', 'render'])
    p.add_argument('--dll', type=Path, required=True)
    p.add_argument('--freetype', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--config', type=Path)
    p.add_argument('--oracle', type=Path)
    p.add_argument('--require-complete', action='store_true')
    p.add_argument('--recommend-font', type=Path, help='Verify every locally absent scalar in this uninstalled font')
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    config = args.config or args.output / 'fonts.conf'
    if not args.config:
        config.write_text('version = 1\nplatform_dirs = yes\n', encoding='utf-8')
    sdk = reg.SDK(args.dll.resolve())
    bind(sdk)
    ft = FreeType(args.freetype)
    manager = c.c_void_p()
    sdk.check('font_manager_open', str(config.resolve()).encode(), c.byref(manager))
    try:
        globals()[args.mode](sdk, ft, manager, faces(sdk, manager), args)
    finally:
        sdk.font_manager_free(manager)
        ft.free()


if __name__ == '__main__':
    main()
