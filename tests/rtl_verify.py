#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Deterministic RTL EPUB fixtures and public-SDK paragraph/pixel evidence.

generate: three ORIGINAL test books, never represented as published real books.
render: paginates every supplied EPUB; saves two pages and all line/glyph evidence.
"""
import argparse
import ctypes as c
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/regress'))
import run_realbooks as reg
sys.path.insert(0, str(ROOT / 'tests'))
from font_coverage import Glyph

AR = 'نقرأ الكتب كل يوم ونتعلم كلمات جديدة في رحلة جميلة إلى عالم المعرفة'
HE = 'אנחנו קוראים ספרים בכל יום ולומדים מילים חדשות במסע אל עולם הידע'


def generate(directory):
    directory.mkdir(parents=True, exist_ok=True)
    for name, lang, text in [('arabic-journey', 'ar', AR),
                             ('arabic-library', 'ar', 'في المكتبة نلتقي بأصدقاء جدد ونبحث عن قصة مفيدة وعن كتاب جميل للقراءة'),
                             ('hebrew-journey', 'he', HE)]:
        # Each scenario has its own source paragraph; explicit LTR is also tested
        # inside an RTL book so book progression cannot stand in for paragraph bidi.
        scenes = [f'<p id="direction">{text}.</p>',
                  f'<p id="digits">{text} 0123456789 {text} 2026 {text} 12.34.</p>',
                  f'<p id="punctuation">{text} ({text}) [{text}] «{text}» “{text}” \"{text}\".</p>',
                  f'<p id="mixed">{text} OpenAI Reader ABC xyz {text}.</p>',
                  f'<p id="justify" style="text-align:justify">{(text + " ") * 12}{text}.</p>',
                  '<p id="ltr" dir="ltr">Reader ABC 0123456789 (English paragraph).</p>']
        # Two chapters, multiple pages, no manually inserted page breaks.
        entries = {'mimetype': 'application/epub+zip', 'META-INF/container.xml':
                   '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0"><rootfiles><rootfile full-path="book.opf" media-type="application/oebps-package+xml"/></rootfiles></container>'}
        manifest, spine = [], []
        for part in range(2):
            path = f'part{part}.xhtml'
            manifest.append(f'<item id="p{part}" href="{path}" media-type="application/xhtml+xml"/>')
            spine.append(f'<itemref idref="p{part}"/>')
            entries[path] = f'<html xmlns="http://www.w3.org/1999/xhtml" lang="{lang}" dir="rtl"><head><title>{name} {part}</title><style>body{{margin:0}} p{{margin:0 0 12px 0}} #justify{{text-indent:24px}}</style></head><body>{"".join(scenes)}</body></html>'
        entries['nav.xhtml'] = '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><head><title>Contents</title></head><body><nav epub:type="toc"><ol><li><a href="part0.xhtml">1</a></li><li><a href="part1.xhtml">2</a></li></ol></nav></body></html>'
        entries['book.opf'] = f'<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="id">urn:exreader:rtl:{name}</dc:identifier><dc:title>{name} (original test book)</dc:title><dc:language>{lang}</dc:language><meta property="dcterms:modified">2026-11-09T00:00:00Z</meta></metadata><manifest>{"".join(manifest)}<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/></manifest><spine page-progression-direction="rtl">{"".join(spine)}</spine></package>'
        with zipfile.ZipFile(directory / (name + '.epub'), 'w') as z:
            for path, value in entries.items():
                z.writestr(zipfile.ZipInfo(path, (2026, 11, 9, 0, 0, 0)), value.encode())
        if lang == 'he':
            for suffix, attr, language in [('ltr', 'ltr', 'he'), ('default', 'default', 'he-IL'),
                                            ('absent', None, 'en'), ('invalid', 'bogus', 'HE-il')]:
                opf = entries['book.opf'].replace('page-progression-direction="rtl"',
                    f'page-progression-direction="{attr}"' if attr else '')
                opf = opf.replace('<dc:language>he</dc:language>', f'<dc:language>{language}</dc:language>')
                with zipfile.ZipFile(directory / f'progression-{suffix}.epub', 'w') as z:
                    for path, value in entries.items():
                        z.writestr(zipfile.ZipInfo(path, (2026, 11, 9, 0, 0, 0)),
                                   (opf if path == 'book.opf' else value).encode())
    cases = {
        'numbers-he': "<p dir='rtl'>אבג 0123456789 דהו</p>",
        'numbers-ar': "<p dir='rtl'>نقرأ 0123456789 الكتب</p>",
        'decimal': "<p dir='rtl'>אבג 12.34 דהו</p>",
        'mixed-he': "<p dir='rtl'>אבג Reader ABC xyz דהו</p>",
        'mixed-ar': "<p dir='rtl'>نقرأ Reader ABC xyz الكتب</p>",
        'ltr': "<div dir='rtl'><p dir='ltr'>Reader ABC xyz</p></div>",
        'punctuation': '<p dir="rtl">אבג (דהו) [זחט] «יכל» "מנס" “עפצ”</p>',
        'break': "<div dir='rtl' style='text-align:justify'><p>אבג<br/>דהו</p><h2>זחט</h2></div>"}
    for lang, words in [('he', 'אבג דהו זחט יכל מנס עפצ קרש תאב'),
                         ('ar', 'نقرأ الكتب كل يوم ونتعلم كلمات جديدة')]:
        cases['paragraph-' + lang] = f'<p dir="rtl" style="text-align:justify;text-indent:24px">{(words + " ") * 15}{words}.</p>'
    for name, body in cases.items():
        with zipfile.ZipFile(directory / f'native-{name}.epub', 'w') as z:
            for path, value in entries.items():
                if path == 'part0.xhtml':
                    value = '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Native RTL test</title><style>body{margin:0}p{margin:0}</style></head><body>' + body + '</body></html>'
                z.writestr(zipfile.ZipInfo(path, (2026, 11, 9, 0, 0, 0)), value.encode())


class Line(c.Structure):
    _fields_ = [(n, c.c_size_t) for n in ('start', 'end', 'glyph_start', 'glyph_count')] + [
        ('y', c.c_float), ('page', c.c_size_t)] + [(n, c.c_float) for n in ('x', 'width', 'height')]


class Node(c.Structure):
    _fields_ = [('kind', c.c_int)] + [(n, c.c_size_t) for n in
        ('parent', 'first_child', 'next_sibling', 'chapter', 'start', 'end')] + [
        ('name', c.c_char_p), ('text', c.c_char_p), ('attributes', c.c_void_p), ('attribute_count', c.c_size_t)]


class Part(c.Structure):
    _fields_ = [('id', c.c_char_p), ('path', c.c_char_p), ('title', c.c_char_p), ('in_reading_order', c.c_int)]


def bind(sdk):
    ptr, out, err = c.c_void_p, c.POINTER(c.c_void_p), c.POINTER(reg.Error)
    specs = {'layout_lines': (c.POINTER(Line), [ptr, c.POINTER(c.c_size_t)]),
             'bitmap_write_png': (c.c_int, [c.POINTER(reg.Bitmap), c.c_char_p, err]),
             'document_text': (c.c_char_p, [ptr, c.POINTER(c.c_size_t)]),
             'document_nodes': (c.POINTER(Node), [ptr, c.POINTER(c.c_size_t)]),
             'node_attribute': (c.c_char_p, [c.POINTER(Node), c.c_char_p]),
             'document_page_progression': (c.c_int, [ptr]),
             'publication_page_progression': (c.c_int, [ptr])}
    for name, (ret, args) in specs.items():
        if hasattr(sdk.dll, 'exr_' + name):
            fn = getattr(sdk.dll, 'exr_' + name)
            fn.restype, fn.argtypes = ret, args
            setattr(sdk, name, fn)


def probe(source, fixture, output):
    """Append a clearly labelled controlled chapter; leave original content members intact."""
    ns = {'o': 'http://www.idpf.org/2007/opf'}
    with zipfile.ZipFile(source) as z:
        entries = {n: z.read(n) for n in z.namelist()}
    container = ET.fromstring(entries['META-INF/container.xml'])
    opf_path = next(e.attrib['full-path'] for e in container.iter() if e.tag.endswith('rootfile'))
    opf = ET.fromstring(entries[opf_path])
    ET.SubElement(opf.find('o:manifest', ns), '{' + ns['o'] + '}item',
                  id='exr-rtl-probe', href='exr-rtl-probe.xhtml', **{'media-type': 'application/xhtml+xml'})
    ET.SubElement(opf.find('o:spine', ns), '{' + ns['o'] + '}itemref', idref='exr-rtl-probe')
    entries[opf_path] = ET.tostring(opf, encoding='utf-8', xml_declaration=True)
    with zipfile.ZipFile(fixture) as z:
        appendix = z.read('part0.xhtml').replace(b'<body>', b'<body><h1 dir="ltr">EXReader ORIGINAL CONTROLLED TEST APPENDIX</h1>')
    entries[str(Path(opf_path).parent / 'exr-rtl-probe.xhtml').replace('\\', '/')] = appendix
    with zipfile.ZipFile(output, 'w') as z:
        for name, value in entries.items():
            z.writestr(zipfile.ZipInfo(name, (2026, 11, 9, 0, 0, 0)), value)
    reg.write_json(output.with_suffix('.provenance.json'), dict(
        original_sha256=reg.file_hash(source), derivative_sha256=reg.file_hash(output),
        original_content_members_unchanged=True, changed_original_members=[opf_path],
        added_member='exr-rtl-probe.xhtml', fixture_sha256=reg.file_hash(fixture)))


def render(args):
    sdk = reg.SDK(args.dll.resolve())
    bind(sdk)
    args.output.mkdir(parents=True, exist_ok=True)
    font = c.c_void_p()
    sdk.check('font_open', str(args.font.resolve()).encode(), c.byref(font))
    result = dict(dll_sha256=reg.file_hash(args.dll), font_sha256=reg.file_hash(args.font),
                  source_revision=args.source_revision, books=[])
    for path in args.books:
        pub = c.c_void_p()
        sdk.check('publication_open', str(path.resolve()).encode(), c.byref(pub))
        n = c.c_size_t()
        parts = c.cast(sdk.publication_parts(pub, c.byref(n)), c.POINTER(Part))[:n.value]
        book = dict(name=path.stem, kind=('real book' if path.stem == 'hunger' else
                    'real book + original controlled appendix' if path.stem == 'hunger-probed' else 'original test book'),
                    epub_sha256=reg.file_hash(path), parts=n.value, pages=[],
                    excluded_nonreading_parts=[i for i,p in enumerate(parts) if not p.in_reading_order],
                    progression=sdk.publication_page_progression(pub) if hasattr(sdk, 'publication_page_progression') else None)
        config = sdk.layout_config_defaults()
        config.page = reg.Options(720, 720, 36, 26, 1.3, 10)
        config.embedded_fonts = 0
        for part in range(n.value):
            if not parts[part].in_reading_order:
                continue
            doc, pager = c.c_void_p(), c.c_void_p()
            sdk.check('publication_load', pub, part, c.byref(doc))
            text = sdk.document_text(doc, None)
            nodes = sdk.document_nodes(doc, c.byref(count := c.c_size_t()))
            scenes = []
            for node in nodes[:count.value]:
                name = sdk.node_attribute(c.byref(node), b'id')
                if name and name.decode() in ('direction', 'digits', 'punctuation', 'mixed', 'justify', 'ltr'):
                    scenes.append((node.start, node.end, name.decode()))
            sdk.check('pager_create', doc, font, c.byref(config), c.byref(pager))
            while True:
                page = c.c_void_p()
                sdk.check('pager_next', pager, c.byref(page))
                if not page:
                    break
                count = c.c_size_t()
                gs = c.cast(sdk.layout_glyphs(page, c.byref(count)), c.POINTER(Glyph))[:count.value]
                lines = sdk.layout_lines(page, c.byref(count))[:count.value]
                record = dict(part=part, glyph_count=len(gs), lines=[])
                for line in lines:
                    row = gs[line.glyph_start:line.glyph_start + line.glyph_count]
                    record['lines'].append(dict(start=line.start, end=line.end, x=line.x,
                        width=line.width, logical=text[line.start:line.end].decode('utf-8'),
                        scene=next((name for start, end, name in scenes if start <= line.start < end), None),
                        glyphs=[dict(cp=g.codepoint, gid=g.glyph, start=g.start, end=g.end,
                                     x=g.x, advance=g.advance, level=g.bidi_level, flags=g.flags)
                                for g in row]))
                bitmap = reg.Bitmap()
                sdk.check('render_page_color', page, None, 0, c.byref(bitmap))
                record['pixel_sha256'] = reg.pixel_hash(bitmap)
                # Keep first two pages with RTL-script body text (skip PG English header).
                rtl = sum(bool(g.bidi_level & 1) for g in gs if 0x590 <= g.codepoint <= 0x6ff)
                minimum_rtl = 300 if path.stem.startswith('hunger') else 30
                if rtl > minimum_rtl and sum('screenshot' in p for p in book['pages']) < 2:
                    png = args.output / f'{path.stem}-{len(book["pages"]):03}.png'
                    sdk.check('bitmap_write_png', c.byref(bitmap), str(png).encode())
                    record['screenshot'] = png.name
                if scenes and path.stem == 'hunger-probed' and not any('probe_screenshot' in p for p in book['pages']):
                    png = args.output / f'{path.stem}-appendix.png'
                    sdk.check('bitmap_write_png', c.byref(bitmap), str(png).encode())
                    record['probe_screenshot'] = png.name
                sdk.bitmap_free(c.byref(bitmap))
                sdk.layout_free(page)
                book['pages'].append(record)
            sdk.pager_free(pager)
            sdk.document_free(doc)
        sdk.publication_free(pub)
        book['page_count'] = len(book['pages'])
        result['books'].append(book)
        print(path.stem, book['page_count'], 'pages', 'progression', book['progression'], flush=True)
        reg.write_json(args.output / 'render.json', result)
    sdk.font_free(font)


def assess(render_path, font_path, output):
    """Assertions on measured source offsets, physical coordinates and independent cmap IDs."""
    import uharfbuzz as hb
    font = hb.Font(hb.Face(font_path.read_bytes()))
    mirror = {ord(a): ord(b) for a, b in zip('()[]«»', ')(][»«')}
    quotes = set(map(ord, '\"“”'))
    data = reg.read_json(render_path)
    results = []
    for book in data['books']:
        groups = {}
        for pi, page in enumerate(book['pages']):
            for li, line in enumerate(page['lines']):
                if line['scene']:
                    groups.setdefault((page['part'], line['scene']), []).append((pi, li, line))
        if not groups:
            results.append(dict(book=book['name'], controlled_scenarios=False,
                                note='Unmodified real book: no invented six-scenario score; see controlled appendix.'))
            continue
        failures, evidence = [], dict(direction=[], numbers=[], punctuation=[], mixed=[], alignment=[], progression=[])

        def check(item, condition, value):
            evidence[item].append(value)
            if not condition:
                failures.append(dict(item=item, evidence=value))

        for (part, scene), rows in groups.items():
            if scene == 'direction':
                for pi, li, line in rows:
                    gs = [g for g in line['glyphs'] if not g['flags'] & 4 and chr(g['cp']).isalpha()]
                    check('direction', len(gs)>1 and all(g['level']&1 for g in gs) and
                          all(a['start']>=b['start'] and a['x']<b['x'] for a,b in zip(gs,gs[1:])) and
                          abs(line['x']+line['width']-684)<.1,
                          dict(page=pi, line=li, source_offsets=[g['start'] for g in gs],
                               x=[g['x'] for g in gs], right=line['x']+line['width']))
            elif scene in ('digits', 'mixed', 'ltr'):
                for pi, li, line in rows:
                    # One ASCII scalar maps to one glyph in these fixtures.
                    for m in re.finditer(r'[0-9]+(?:\.[0-9]+)?' if scene=='digits' else r'[A-Za-z]+(?: [A-Za-z]+)*', line['logical']):
                        start=line['start']+len(line['logical'][:m.start()].encode())
                        end=start+len(m.group().encode())
                        gs=[g for g in line['glyphs'] if start<=g['start']<end and not g['flags']&4]
                        item='numbers' if scene=='digits' else 'mixed'
                        check(item, ''.join(chr(g['cp']) for g in gs)==m.group() and
                              all(not g['level']&1 for g in gs) and all(a['x']<b['x'] for a,b in zip(gs,gs[1:])),
                              dict(page=pi,line=li,token=m.group(),x=[g['x'] for g in gs],scene=scene))
            elif scene == 'punctuation':
                for pi, li, line in rows:
                    for g in line['glyphs']:
                        cp=g['cp']
                        if cp in mirror or cp in quotes:
                            expected=mirror.get(cp,cp) if g['level']&1 else cp
                            gid=font.get_nominal_glyph(expected)
                            check('punctuation', g['gid']==gid and gid!=0,
                                  dict(page=pi,line=li,source=f'U+{cp:04X}', expected=f'U+{expected:04X}',
                                       level=g['level'],actual_gid=g['gid'],harfbuzz_cmap_gid=gid))
            elif scene == 'justify':
                for index, (pi,li,line) in enumerate(rows):
                    right=660 if index==0 else 684
                    final=index==len(rows)-1
                    check('alignment', abs(line['x']+line['width']-right)<.1 and
                          (line['x']>36 if final else abs(line['x']-36)<.1),
                          dict(page=pi,line=li,x=line['x'],width=line['width'],expected_right=right,final=final))
        check('progression',book['progression']==2,dict(direction=book['progression'],next_side='left' if book['progression']==2 else 'unknown'))
        scores = {key: bool(value) and not any(f['item']==key for f in failures) for key,value in evidence.items()}
        results.append(dict(book=book['name'],page_count=book['page_count'],passed=sum(scores.values()),
                            results=scores,failures=failures,evidence=evidence))
    reg.write_json(output, dict(oracle='HarfBuzz nominal cmap (independent of engine mirror mapping)',
                                harfbuzz_version=hb.version_string(),font_sha256=reg.file_hash(font_path),books=results))
    for b in results:
        print(b['book'], b.get('passed', 'no controlled scenarios'), flush=True)
    return 0 if all(b.get('passed',6)==6 for b in results) else 1


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    g = sub.add_parser('generate')
    g.add_argument('directory', type=Path)
    r = sub.add_parser('render')
    r.add_argument('--dll', type=Path, required=True)
    r.add_argument('--font', type=Path, required=True)
    r.add_argument('--output', type=Path, required=True)
    r.add_argument('--source-revision', required=True)
    r.add_argument('books', type=Path, nargs='+')
    b = sub.add_parser('probe')
    b.add_argument('source', type=Path)
    b.add_argument('fixture', type=Path)
    b.add_argument('output', type=Path)
    v = sub.add_parser('assess')
    v.add_argument('render', type=Path)
    v.add_argument('font', type=Path)
    v.add_argument('output', type=Path)
    a = p.parse_args()
    if a.command == 'generate': generate(a.directory)
    elif a.command == 'probe': probe(a.source, a.fixture, a.output)
    elif a.command == 'assess': sys.exit(assess(a.render, a.font, a.output))
    else: render(a)
