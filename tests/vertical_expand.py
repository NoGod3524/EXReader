"""Reproducible A5 EPUBs and public-SDK vertical geometry/pixel checks.

No downloaded text or images: all prose and the asymmetric corner chart are
original fixtures. Normal tests use the repository's existing synthetic fonts.
"""
# SPDX-License-Identifier: MIT
import argparse
import ctypes as c
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import zipfile
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/regress'))
from run_realbooks import SDK, Options, Bitmap, Error, pixel_hash

P, N = c.c_void_p, c.c_size_t
VERTICAL, SIDEWAYS, COMBINED = 128, 256, 16384


class Glyph(c.Structure):
    _fields_ = [(k, N) for k in ('start', 'end')] + [
        ('codepoint', c.c_uint32), ('glyph', c.c_uint32)] + [
        (k, c.c_float) for k in ('x', 'baseline', 'advance', 'size')] + [
        ('page', N), ('node', N), ('color', c.c_uint32), ('flags', c.c_uint),
        ('clip_left', c.c_float), ('clip_right', c.c_float), ('line_height', c.c_float),
        ('cluster_start', N), ('cluster_end', N), ('boundaries', c.c_uint),
        ('font_index', N), ('offset_x', c.c_float), ('offset_y', c.c_float), ('bidi_level', c.c_uint)]


class Line(c.Structure):
    _fields_ = [(k, N) for k in ('start', 'end', 'glyph_start', 'glyph_count')] + [
        ('y', c.c_float), ('page', N)] + [(k, c.c_float) for k in ('x', 'width', 'height')]


class Box(c.Structure):
    _fields_ = [('kind', c.c_int)] + [(k, N) for k in ('node', 'page', 'resource', 'start', 'end')] + [
        (k, c.c_float) for k in ('x', 'y', 'width', 'height', 'border_width')] + [
        (k, c.c_uint32) for k in ('background', 'border_color', 'flags')]


class Point(c.Structure):
    _fields_ = [('x', c.c_double), ('y', c.c_double)]


class Segment(c.Structure):
    _fields_ = [('verb', c.c_int), ('points', Point*3)]


def bind(path):
    sdk = SDK(path)
    for name, result, args in [
        ('layout_create_ex', c.c_int, [P, P, c.POINTER(type(sdk.layout_config_defaults())), c.POINTER(P), c.POINTER(Error)]),
        ('layout_lines', c.POINTER(Line), [P, c.POINTER(N)]),
        ('layout_glyphs', c.POINTER(Glyph), [P, c.POINTER(N)]),
        ('layout_boxes', c.POINTER(Box), [P, c.POINTER(N)]),
        ('layout_writing_mode', c.c_int, [P]),
        ('bitmap_write_png', c.c_int, [c.POINTER(Bitmap), c.c_char_p, c.POINTER(Error)]),
        ('glyph_matrix', c.c_int, [c.POINTER(Glyph), c.POINTER(c.c_double), c.POINTER(Error)]),
        ('font_glyph_outline', c.c_int, [P, N, c.c_uint32, c.POINTER(c.POINTER(Segment)), c.POINTER(N), P, c.POINTER(Error)]),
        ('free', None, [P]),
    ]:
        fn = getattr(sdk.dll, 'exr_' + name)
        fn.restype, fn.argtypes = result, args
        setattr(sdk, name, fn)
    return sdk


def ink_bounds(sdk, font, glyph):
    """Conservative transformed outline bounds, including Bezier control points."""
    path=c.POINTER(Segment)(); n=N(); matrix=(c.c_double*6)()
    sdk.check('glyph_matrix', c.byref(glyph), matrix)
    sdk.check('font_glyph_outline', font, glyph.font_index, glyph.glyph, c.byref(path), c.byref(n), None)
    points=[]
    try:
        for s in path[:n.value]:
            for p in s.points[:(1,1,2,3,0)[s.verb]]:
                points.append((matrix[0]*p.x+matrix[2]*p.y+matrix[4], matrix[1]*p.x+matrix[3]*p.y+matrix[5]))
    finally:
        sdk.free(path)
    return [min(p[0] for p in points),min(p[1] for p in points),max(p[0] for p in points),max(p[1] for p in points)] if points else None


def chart():
    """120x180 PNG: red/green/blue/yellow corners, white central up-arrow."""
    rows = bytearray()
    for y in range(180):
        rows.append(0)
        for x in range(120):
            color = ((220, 30, 40), (20, 180, 60), (30, 70, 220), (240, 200, 20))[(y >= 90)*2 + (x >= 60)]
            if (55 <= x <= 65 and 40 <= y <= 145) or (20 <= y < 60 and abs(x-60) <= (y-20)):
                color = (255, 255, 255)
            rows.extend(color)
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind+data))
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 120, 180, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(rows)) + chunk(b'IEND', b'')


CSS = '''body{writing-mode:vertical-rl} p{margin:0;text-indent:0;text-align:start}
.new{page-break-before:always} .two{text-combine-upright:digits 2}
.four{text-combine-upright:digits 4} .all{text-combine-upright:all}
rt{ruby-position:over}'''


def epub(path, body, title='竖排验证', language='zh-Hans', css=CSS):
    files = {
        'mimetype': 'application/epub+zip',
        'META-INF/container.xml': '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0"><rootfiles><rootfile full-path="book.opf" media-type="application/oebps-package+xml"/></rootfiles></container>',
        'book.opf': f'''<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="id" version="3.0"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="id">exr-a5-{path.stem}</dc:identifier><dc:title>{title}</dc:title><dc:language>{language}</dc:language><meta property="dcterms:modified">2026-11-10T00:00:00Z</meta></metadata><manifest><item id="main" href="main.xhtml" media-type="application/xhtml+xml"/><item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/><item id="chart" href="chart.png" media-type="image/png"/></manifest><spine page-progression-direction="rtl"><itemref idref="main"/></spine></package>''',
        'nav.xhtml': '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><head><title>目录</title></head><body><nav epub:type="toc"><ol><li><a href="main.xhtml">正文</a></li></ol></nav></body></html>',
        'main.xhtml': f'<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="{language}"><head><title>{title}</title><style>{css}</style></head><body>{body}</body></html>',
        'chart.png': chart(),
    }
    with zipfile.ZipFile(path, 'w') as z:
        for name, data in files.items():
            info = zipfile.ZipInfo(name, (2026, 11, 10, 0, 0, 0))
            z.writestr(info, data.encode() if isinstance(data, str) else data)


def corpus(directory):
    directory.mkdir(parents=True, exist_ok=True)
    stories = [
        ('zh-lake', '湖上晨读', 'zh-Hans', '清晨，湖面有一层薄雾。小船从东岸驶来，船头的灯还亮着。岸边的人翻开书，把昨天读过的一句又读了一遍。「慢慢看，别着急。」风吹过树叶，湖水轻轻拍岸。'),
        ('zh-hill', '山城夜记', 'zh-Hant', '夜色漸深，山路上的燈一盞盞亮起。茶館門前，有人收起雨傘，笑著說：「雨停了，走吧！」石階還留著水光。遠處的鐘聲傳來，街角的小店也準備關門。'),
        ('ja-stars', '星の観察日記', 'ja', '<ruby>夜空<rt>よぞら</rt></ruby>を見上げると、雲の間に星が見えた。<ruby>友達<rt>ともだち</rt></ruby>は小さな手帳を開き、「今日はよく見えるね。」と言った。風が止まり、<ruby>静<rt>しず</rt></ruby>かな時間が流れていた。'),
        ('vertical-images', '图与文字的方向', 'zh-Hans', '先看图的四角，再读旁边的文字。红色在左上，绿色在右上，蓝色在左下，黄色在右下。白色箭头始终向上。图片保持直立，文字从右向左逐列排列。'),
    ]
    result = []
    for key, title, language, prose in stories:
        # The same diagnostic appendix makes all seven checks applicable to each book.
        body = f'<p>{title}。</p>' + ''.join(f'<p>{prose}</p>' for _ in range(5))
        body += '<p><ruby>東京<rt>とうきょう</rt></ruby>。<ruby>星空<rt>ほしぞら</rt></ruby>、<ruby>山<rt>やま</rt></ruby>。</p>'
        body += '<p class="new">边界检查。</p><p>甲<span class="two">12</span>乙<span class="all">……</span>丙。</p>'
        for digits in ('2026', '1234', '0000'):
            body += f'<p>甲<span class="two">{digits}</span>乙<span class="four">{digits}</span>丙。</p>'
        for marks in ('。，', '！？', '」』'):
            body += f'<p>甲{marks}乙。</p>'
        body += '<p class="new"><img src="chart.png" style="width:432px;height:648px" alt="四角方向图"/></p>'
        body += f'<p class="new">图文混排。</p><p>{prose}</p><p><img src="chart.png" style="width:80px;height:120px" alt="小方向图"/></p><p>{prose}</p><p><ruby>東京<rt>とうきょう</rt></ruby>。甲<span class="two">12</span>乙。</p>'
        path = directory / (key + '.epub')
        epub(path, body, title, language)
        result.append(dict(id=key, title=title, language=language, filename=path.name,
                           sha256=hashlib.sha256(path.read_bytes()).hexdigest(), provenance='original MIT fixture'))
    (directory / 'manifest.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return result


def config(sdk, height=720, css=None):
    value = sdk.layout_config_defaults()
    value.page = Options(504, height, 36, 28, 1.5, 10)
    value.user_css = css.encode() if css else None
    return value


def render(sdk, font, path, cfg, output=None, measure_ink=False):
    doc, pager, page = P(), P(), P()
    records = []
    try:
        sdk.check('document_open', str(path).encode(), c.byref(doc))
        sdk.check('pager_create', doc, font, c.byref(cfg), c.byref(pager))
        while True:
            sdk.check('pager_next', pager, c.byref(page))
            if not page: break
            try:
                n = N()
                # Copy borrowed records before releasing the page layout.
                def copy(fn):
                    ptr = fn(page, c.byref(n))
                    return [{name: getattr(v, name) for name, _ in v._fields_} for v in ptr[:n.value]]
                glyphs, lines, boxes = copy(sdk.layout_glyphs), copy(sdk.layout_lines), copy(sdk.layout_boxes)
                if output or measure_ink:
                    for g in glyphs:
                        g['ink_bounds']=ink_bounds(sdk,sdk.layout_font(page),Glyph(**g))
                bitmap = Bitmap()
                sdk.check('render_page_color', page, sdk.layout_font(page), 0, c.byref(bitmap))
                try:
                    raw = c.string_at(bitmap.pixels, bitmap.stride*bitmap.height)
                    assert raw != b'\xff'*len(raw), 'blank page'
                    image_checks = []
                    for b in boxes:
                        if b['kind'] != 2: continue
                        assert not b['flags'] & 1, 'image placeholder'
                        assert abs(b['width']/b['height']-2/3) < .002, b
                        samples = []
                        for x, y in ((.1,.1),(.9,.1),(.1,.9),(.9,.9)):
                            at = int(b['y']+y*b['height'])*bitmap.stride + int(b['x']+x*b['width'])*4
                            samples.append(list(raw[at:at+3]))
                        assert samples == [[220,30,40],[20,180,60],[30,70,220],[240,200,20]], samples
                        image_checks.append(dict(box=b, corner_rgb=samples))
                    filename = f'{path.stem}-{len(records)+1:02d}.png'
                    if output:
                        sdk.check('bitmap_write_png', c.byref(bitmap), str(output/filename).encode())
                    records.append(dict(page=len(records)+1, mode=sdk.layout_writing_mode(page),
                                        pixel_sha256=pixel_hash(bitmap), screenshot=filename,
                                        glyphs=glyphs, lines=lines, images=image_checks))
                finally:
                    sdk.bitmap_free(c.byref(bitmap))
            finally:
                sdk.layout_free(page); page = P()
    finally:
        sdk.pager_free(pager); sdk.document_free(doc)
    return records


def test_group(sdk, font, directory, group):
    if group == 'boundaries':
        # Opening marks have leading blank space; treating it as trailing
        # space changes existing vertical books even when no ink collides.
        path=directory/'opening.epub'; epub(path,'<p>「甲</p>')
        pages=render(sdk,font,path,config(sdk),measure_ink=True)
        opening=pages[0]['glyphs'][0]
        assert opening['codepoint']==0x300c and abs(opening['advance']-14)<.02,opening
        assert opening['ink_bounds'][1]>=36-.02,opening
        for digits in ('2026','1234','0000'):
            for limit in (2,4):
                path=directory/'boundary.epub'
                epub(path, f'<p>甲<span style="text-combine-upright:digits {limit}">{digits}</span>甲</p>')
                pages=render(sdk,font,path,config(sdk,180))
                gs=[g for p in pages for g in p['glyphs'] if 48<=g['codepoint']<=57]
                assert len(gs)==4
                assert sum(bool(g['flags']&COMBINED) for g in gs)==(4 if limit==4 else 0), gs
                if limit==4:
                    assert len({(g['x'],g['baseline'],g['cluster_start'],g['cluster_end']) for g in gs})==1
        for width in (504,114):
            for content in ('2026','1234','0000','……'):
                path=directory/'wrap.epub'
                epub(path,'<p>'+'甲'*5+'<span class="all">'+content+'</span>甲</p>')
                cfg=config(sdk,226); cfg.page.width=width
                pages=render(sdk,font,path,cfg)
                groups=[(p['page'],g) for p in pages for g in p['glyphs'] if g['flags']&COMBINED]
                assert len(groups)==len(content)
                assert len({(p,g['x'],g['baseline'],g['cluster_start'],g['cluster_end']) for p,g in groups})==1
                assert abs(sum(g['advance'] for _,g in groups)-28)<.02
                assert groups[0][0]==(2 if width==114 else 1)
                # Ellipsis cannot start a column: kinsoku moves the preceding
                # ideograph with it, then the intact block begins one em down.
                assert abs(groups[0][1]['baseline']-(64 if content=='……' else 36))<.02
        for marks in ('。。','。。。','。。。。'):
            path=directory/'punctuation.epub'; epub(path, '<p>甲'+marks+'甲</p>')
            pages=render(sdk,font,path,config(sdk))
            gs=[g for p in pages for g in p['glyphs'] if g['codepoint']==0x3002]
            assert len(gs)==len(marks) and all(g['flags']&VERTICAL for g in gs)
            assert abs(sum(g['advance'] for g in gs)-28*(1+(len(marks)-1)/2))<.05,gs
            # A terminal run must also preserve each mark's safe advance;
            # fitting the entire run into one em stacks vertical outlines.
            epub(path, '<p>甲'+marks+'</p>')
            pages=render(sdk,font,path,config(sdk))
            gs=[g for p in pages for g in p['glyphs'] if g['codepoint']==0x3002]
            assert abs(sum(g['advance'] for g in gs)-28*(1+(len(marks)-1)/2))<.05,gs
        for marks in ('！？','！！？','！？！？'):
            for suffix in ('甲',''):
                path=directory/'tall.epub'; epub(path,'<p>甲'+marks+suffix+'</p>')
                pages=render(sdk,font,path,config(sdk),measure_ink=True)
                gs=[g for p in pages for g in p['glyphs'] if g['codepoint'] in (0xff01,0xff1f)]
                assert len(gs)==len(marks)
                for a,b in zip(gs,gs[1:]):
                    assert a['ink_bounds'][3]<=b['ink_bounds'][1]+.02,(a,b)
    elif group == 'ruby':
        path=directory/'ruby.epub'
        epub(path, ''.join('<p>甲<ruby>甲<rt>甲甲</rt></ruby>甲。</p>' for _ in range(20)))
        pages=render(sdk,font,path,config(sdk,240))
        assert len(pages)>2
        notes=0
        for p in pages:
            for g in p['glyphs']:
                assert g['flags']&VERTICAL
                if g['size']<20:
                    notes+=1
                    bases=[b for b in p['glyphs'] if b['size']==28 and b['x']<g['x'] and abs(b['baseline']-g['baseline'])<28]
                    assert bases, g
            for l in p['lines']:
                assert l['x']>=35.98 and l['y']>=35.98 and l['x']+l['width']<=468.02 and l['y']+l['height']<=204.02,l
        assert notes==40,notes  # 20 groups, each containing two annotation glyphs.
    elif group == 'images':
        path=directory/'images.epub'
        epub(path, '<p><img src="chart.png" style="width:80px;height:120px"/></p><p>甲甲甲甲甲甲。</p>'*6)
        pages=render(sdk,font,path,config(sdk,240))
        assert len(pages)>1 and sum(len(p['images']) for p in pages)==6
        assert all(p['mode']==1 for p in pages)
    else:
        raise ValueError(group)


def assess(pages):
    """Check all book pages, retaining measurements for the six SDK criteria.

    The seventh criterion is exercised separately in the actual Windows host:
    a left-gutter click must advance its visible page footer.
    """
    notes=[]; punctuation=[]; pairs=[]; blocks={}; digits={}
    for p in pages:
        assert p['mode']==1
        gs=p['glyphs']; base_lines=[]
        for l in p['lines']:
            assert l['x']>=35.98 and l['y']>=35.98
            assert l['x']+l['width']<=468.02 and l['y']+l['height']<=684.02,l
            run=gs[l['glyph_start']:l['glyph_start']+l['glyph_count']]
            assert all(a['baseline']<=b['baseline']+.02 for a,b in zip(run,run[1:])),run
            if any(g['size']>=28 for g in run): base_lines.append(l)
            for a,b in zip(run,run[1:]):
                pair=chr(a['codepoint'])+chr(b['codepoint'])
                if pair in ('。，','！？','」』'):
                    gap=b['ink_bounds'][1]-a['ink_bounds'][3]
                    assert gap>=-.05,(pair,gap)
                    pairs.append(dict(text=pair,page=p['page'],advances=[a['advance'],b['advance']],ink_gap=gap))
        assert all(a['x']>=b['x']-.02 for a,b in zip(base_lines,base_lines[1:])),base_lines
        for g in gs:
            assert g['flags']&VERTICAL and not g['flags']&8 and g['glyph'],g
            if g['flags']&COMBINED:
                blocks.setdefault((g['cluster_start'],g['cluster_end']),[]).append(g)
            if 48<=g['codepoint']<=57:
                digits.setdefault(g['node'],[]).append(g)
            if g['size']>=28 and g['codepoint'] in (0x3002,0x3001,0xff0c):
                box=g['ink_bounds']
                assert box[0]>=g['x']-.05 and box[1]>=g['baseline']-.05 and box[3]<=g['baseline']+14.05,g
                punctuation.append(dict(character=chr(g['codepoint']),page=p['page'],
                                        ink_from_column_centre=[box[0]-g['x'],box[1]-g['baseline'],box[2]-g['x'],box[3]-g['baseline']]))
            if g['size']==14 and not g['flags']&COMBINED:
                candidates=[b for b in gs if b['size']==28 and b['x']<g['x'] and abs(b['baseline']-g['baseline'])<56]
                assert candidates,g
                notes.append(dict(page=p['page'],size=g['size'],x=g['x'],nearest_base_dx=min(g['x']-b['x'] for b in candidates)))
    block_rows=[]
    for group in blocks.values():
        assert len({(g['x'],g['baseline'],g['page']) for g in group})==1
        assert abs(sum(g['advance'] for g in group)-28)<.02
        assert all(not g['flags']&SIDEWAYS for g in group)
        block_rows.append(dict(text=''.join(chr(g['codepoint']) for g in group),advance=sum(g['advance'] for g in group),cluster=[group[0]['cluster_start'],group[0]['cluster_end']]))
    assert {'12','……','2026','1234','0000'}<={r['text'] for r in block_rows},block_rows
    digit_rows=[]
    for group in digits.values():
        value=''.join(chr(g['codepoint']) for g in group)
        if len(value)==4:
            combined=sum(bool(g['flags']&COMBINED) for g in group)
            assert combined in (0,4)
            digit_rows.append(dict(text=value,combined_glyphs=combined,advance=sum(g['advance'] for g in group)))
    assert len(digit_rows)==6 and all(sum(r['text']==d for r in digit_rows)==2 for d in ('2026','1234','0000'))
    assert len(pairs)==3 and notes
    images=[dict(page=p['page'],**im) for p in pages for im in p['images']]
    assert len(images)==2 and any(p['images'] and p['glyphs'] for p in pages)
    return dict(sdk_passed=6,criteria=dict(columns='PASS',punctuation_position='PASS',
                punctuation_compression='PASS',combine='PASS',ruby='PASS',images='PASS'),
                punctuation=punctuation,adjacent_pairs=pairs,combined_blocks=block_rows,
                four_digit_cases=digit_rows,ruby_glyphs=len(notes),ruby=notes,images=images)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library', type=Path)
    parser.add_argument('--font', type=Path)
    parser.add_argument('--group', choices=['boundaries','ruby','images'])
    parser.add_argument('--output', type=Path)
    args=parser.parse_args()
    sdk=bind(args.library.resolve()); font=P()
    sdk.check('font_open', str(args.font.resolve()).encode(), c.byref(font))
    try:
        if args.group:
            with tempfile.TemporaryDirectory() as d:
                test_group(sdk,font,Path(d),args.group)
            print('PASS vertical-expand '+args.group)
        else:
            args.output.mkdir(parents=True,exist_ok=True)
            books=corpus(args.output/'corpus')
            result=dict(font_sha256=hashlib.sha256(args.font.read_bytes()).hexdigest(),
                        library_sha256=hashlib.sha256(args.library.read_bytes()).hexdigest(), books=[])
            for book in books:
                pages=render(sdk,font,args.output/'corpus'/book['filename'],config(sdk),args.output)
                result['books'].append(dict(**book,page_count=len(pages),analysis=assess(pages),pages=pages))
                print(book['id'],len(pages),'pages',flush=True)
            (args.output/'measurements.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    finally:
        sdk.font_free(font)


if __name__=='__main__': main()
