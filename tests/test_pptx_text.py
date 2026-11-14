#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""PPTX M4 style inheritance and text layout through the public raster ABI."""
import argparse
import ctypes as C
from io import BytesIO
import sys
from pathlib import Path
import runpy
from zipfile import ZipFile

from test_pptx_skeleton import Engine, Error
from test_pptx_shapes import Raster

HERE = Path(__file__).resolve().parent / 'fixtures/pptx-text'
GEN = runpy.run_path(str(HERE / 'generate.py'))
run_text, paragraph, shape, package = (GEN[name] for name in ('run', 'paragraph', 'shape', 'package'))
GROUPS = ('hello', 'sizes', 'master', 'inheritance', 'master-types', 'bold', 'cjk', 'wrap', 'breaks',
          'alignment', 'line-spacing', 'paragraph-spacing', 'bullets', 'autofit', 'autofit-invalid',
          'level', 'body', 'run-properties', 'missing-font', 'invalid-utf8')


def fixture(name):
    return (HERE / f'{name}.pptx').read_bytes()


def replace(data, old, new, part=GEN['SLIDE']):
    with ZipFile(BytesIO(data)) as source:
        parts = {name: source.read(name) for name in source.namelist()}
    assert old in parts[part], old
    parts[part] = parts[part].replace(old, new)
    return GEN['archive'](parts)


def render(engine, data, scale=1, warning=''):
    document, error = C.c_void_p(), Error()
    status = engine.lib.exr_fixed_open_memory(11, data, len(data), None, C.byref(document), C.byref(error))
    message = error.message.decode('utf-8')
    assert status == error.code == 0, (status, message)
    assert warning.lower() in message.lower(), (warning, message)
    try:
        image = Raster(engine, document, scale)
    finally:
        engine.lib.exr_fixed_free(document)
    if message:
        print(f'open warning={message!r}')
    return image, message


def mask(image, box=None):
    left, top, right, bottom = box or (0, 0, image.width, image.height)
    left, right = max(0, left), min(right, image.width)
    pixels = set()
    for y in range(max(0, top), min(bottom, image.height)):
        row = image.data[y * image.stride + left * 4:y * image.stride + right * 4]
        if not row.strip(b'\xff'):
            continue
        first = (len(row) - len(row.lstrip(b'\xff'))) // 4
        last = (len(row.rstrip(b'\xff')) - 1) // 4 + 1
        pixels.update((left + x, y) for x in range(first, last) if min(row[x * 4:x * 4 + 3]) < 245)
    return pixels


def bounds(pixels):
    assert pixels, 'no glyph pixels'
    xs, ys = zip(*pixels)
    return min(xs), min(ys), max(xs) + 1, max(ys) + 1


try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass


def has_cjk_font():
    """True when this host actually has a CJK-covering font installed."""
    import glob, os, shutil, subprocess, sys
    if sys.platform == 'win32':
        return any(os.path.exists(os.path.join(os.environ.get('WINDIR', r'C:\Windows'), 'Fonts', name))
                   for name in ('simhei.ttf', 'msyh.ttc', 'simsun.ttc'))
    if shutil.which('fc-list'):
        try:
            out = subprocess.run(['fc-list', ':lang=zh', 'family'], capture_output=True, text=True, timeout=20)
            return bool(out.stdout.strip())
        except Exception:
            return False
    patterns = ('/usr/share/fonts/**/*CJK*', '/usr/share/fonts/**/*Han*', '/usr/share/fonts/**/*Noto*SC*',
                '/System/Library/Fonts/*Han*', '/Library/Fonts/*Han*')
    return any(glob.glob(pattern, recursive=True) for pattern in patterns)

def stats(image, box=None):
    pixels = mask(image, box)
    bbox = bounds(pixels)
    return dict(bbox=bbox, width=bbox[2] - bbox[0], height=bbox[3] - bbox[1], pixels=len(pixels))


def bands(image):
    rows = sorted({y for _, y in mask(image)})
    result = []
    for y in rows:
        if not result or y > result[-1][-1] + 1:
            result.append([y])
        else:
            result[-1].append(y)
    return [(min(row), max(row) + 1) for row in result]


def normalized(pixels):
    left, top, _, _ = bounds(pixels)
    return {(x - left, y - top) for x, y in pixels}


def text_data(text='Hello', attributes='sz="2400"', properties='', p_attributes='', p_properties='', **kwargs):
    return package(shape(paragraph(run_text(text, attributes, properties), p_attributes, p_properties), **kwargs))


def run(engine, group):
    if group == 'hello':
        image, _ = render(engine, fixture('hello'))
        result = stats(image)
        center = (result['bbox'][0] + result['bbox'][2]) / 2
        assert result['pixels'] > 0 and abs(center - 240) <= 2, (center, result)
        assert all(r == g == b for x, y in mask(image) for r, g, b in [image.pixel(x, y)])
        print(f'Hello 18pt black: {result}, shape_center=240, glyph_center={center}, delta={abs(center - 240)}px')
    elif group == 'sizes':
        values = [stats(render(engine, fixture(f'size{size}'), 4)[0]) for size in (12, 24, 48)]
        heights = [item['height'] for item in values]
        ratios = [value / heights[0] for value in heights]
        assert all(abs(actual / expected - 1) <= .10 for actual, expected in zip(ratios, (1, 2, 4))), ratios
        print(f'12/24/48pt at 4px/pt: heights={heights}px, normalized={ratios}, stats={values}')
    elif group == 'master':
        inherited, _ = render(engine, fixture('master28'), 4)
        explicit, _ = render(engine, text_data(attributes='sz="2800"'), 4)
        assert inherited.data == explicit.data
        print(f'ONLY slideMaster bodyStyle sz=2800; rPr/pPr/lstStyle/default have no sz: {stats(inherited)}, equals explicit28pt pixel-for-pixel')
    elif group == 'inheritance':
        expected, _ = render(engine, text_data(attributes='sz="2800" b="1" i="1" u="sng" spc="100"', properties='<a:solidFill><a:srgbClr val="007700"/></a:solidFill>'), 2)
        # All three attributes are inherited independently; absent attributes keep the lower layer.
        default = '<a:lvl1pPr><a:defRPr sz="1200" b="0" u="sng" spc="100"><a:solidFill><a:srgbClr val="FF0000"/></a:solidFill></a:defRPr></a:lvl1pPr>'
        master = '<p:bodyStyle><a:lvl1pPr><a:defRPr sz="2800" i="1"/></a:lvl1pPr></p:bodyStyle>'
        lst = '<a:lvl1pPr><a:defRPr><a:solidFill><a:srgbClr val="007700"/></a:solidFill></a:defRPr></a:lvl1pPr>'
        runs = run_text('Hello')
        pprops = '<a:defRPr b="1"/>'
        actual, _ = render(engine, package(shape(paragraph(runs, properties=pprops), placeholder='body', lst=lst), default=default, master=master), 2)
        assert actual.data == expected.data
        print('five layers merged per attribute: run absent; pPr bold=1; lstStyle green; master28pt+italic overrides default12pt; default underline+1pt tracking; exact flattened raster match')
        # Each priority boundary sets a different sz, then compare with a flattened run.
        size_default = '<a:lvl1pPr><a:defRPr sz="1200"/></a:lvl1pPr>'
        size_lst = '<a:lvl1pPr><a:defRPr sz="2400"/></a:lvl1pPr>'
        for source, data, size in (
            ('builtin', package(), 18),
            ('defaultTextStyle', package(default='<a:lvl1pPr><a:defRPr sz="2000"/></a:lvl1pPr>'), 20),
            ('lstStyle', package(shape(lst=size_lst), default=size_default), 24),
            ('pPr/defRPr', package(shape(paragraph(properties='<a:defRPr sz="2600"/>'), lst=size_lst), default=size_default), 26),
            ('rPr', package(shape(paragraph(run_text('Hello', 'sz="3000"'), properties='<a:defRPr sz="2600"/>'), lst=size_lst), default=size_default), 30),
        ):
            actual, _ = render(engine, data, 2)
            reference, _ = render(engine, text_data(attributes=f'sz="{size * 100}"'), 2)
            assert actual.data == reference.data, source
            print(f'{source}: resolved {size}pt, height={stats(actual)["height"]}px (2px/pt), exact reference match')
    elif group == 'master-types':
        styles = ''.join(f'<p:{tag}><a:lvl1pPr><a:defRPr sz="{size * 100}"/></a:lvl1pPr></p:{tag}>'
                         for tag, size in (('titleStyle', 36), ('bodyStyle', 28), ('otherStyle', 20)))
        for placeholder, size in (('title', 36), ('ctrTitle', 36), ('body', 28), ('', 20)):
            actual, _ = render(engine, package(shape(placeholder=placeholder), master=styles), 2)
            expected, _ = render(engine, text_data(attributes=f'sz="{size * 100}"'), 2)
            assert actual.data == expected.data, placeholder
            print(f'placeholder={placeholder!r}: master {size}pt, height={stats(actual)["height"]}px')
        actual, _ = render(engine, package(shape(placeholder='body'), master=styles, master_path='ppt/custom/deep/master.xml'), 2)
        expected, _ = render(engine, text_data(attributes='sz="2800"'), 2)
        assert actual.data == expected.data
        print('relationship-resolved relocated master: 28pt exact reference match')
    elif group == 'bold':
        images = [render(engine, fixture(name), 4)[0] for name in ('regular', 'bold')]
        values = [stats(image) for image in images]
        # Average horizontal dark stroke for eight vertical I stems, avoiding cap bars.
        widths = []
        for image, value in zip(images, values):
            left, top, right, bottom = value['bbox']
            y = (top + bottom) // 2
            widths.append(sum(min(image.pixel(x, y)) < 128 for x in range(left, right)) / 8)
        assert values[1]['pixels'] > values[0]['pixels'] * 1.1 and widths[1] > widths[0] * 1.1, (values, widths)
        print(f'b=0/b=1 48pt at 4px/pt: ink_pixels={[v["pixels"] for v in values]}, mean_stem_width={widths}px')
    elif group == 'cjk':
        if not has_cjk_font():
            image, warning = render(engine, fixture('cjk'), 2)
            assert 'font fallback=' in warning.lower(), warning
            print('no CJK font on this host: verified the fallback path and its warning only')
            return
        image, warning = render(engine, fixture('cjk'), 2)
        result = stats(image)
        assert result['pixels'] > 100
        # A host without SimHei may recover through a covering fallback font.
        # Only an unresolved character is a tofu failure.
        assert ' missing;' not in warning.lower(), warning
        # Four separate, nonidentical silhouettes rule out four repeated tofu boxes.
        cells = []
        left, top, right, bottom = result['bbox']
        for index in range(4):
            cell = mask(image, (100 + index * 56, top, 100 + (index + 1) * 56, bottom))
            assert cell
            cells.append(normalized(cell))
        assert len({frozenset(cell) for cell in cells}) == 4
        inherited_data = package(shape(paragraph(run_text('中文测试', 'sz="2800"', '<a:latin typeface="Segoe UI"/>'),
            properties='<a:defRPr><a:ea typeface="SimHei"/></a:defRPr>')))
        inherited, _ = render(engine, inherited_data, 2)
        assert inherited.data == image.data
        fallback, fallback_warning = render(engine, fixture('cjk-fallback'), 2, warning='fallback')
        assert ' missing;' not in fallback_warning.lower(), fallback_warning
        fallback_stats = stats(fallback)
        fallback_cells = [normalized(mask(fallback, (100 + index * 56, 0, 100 + (index + 1) * 56, fallback.height)))
                          for index in range(4)]
        assert len({frozenset(cell) for cell in fallback_cells}) == 4
        missing, missing_warning = render(engine, fixture('missing-glyph'), 2, warning='missing glyph')
        print(f'SimHei ea 中文测试: {result}, four distinct glyph masks; ea inherited independently of run latin exact match; fallback fixture warning={missing_warning!r}; missing mask pixels={len(mask(missing))}')
        print(f'Chinese requested ea=Segoe UI (no CJK): recovered four distinct glyphs, {fallback_stats}, warning={fallback_warning!r}')
    elif group == 'wrap':
        image, _ = render(engine, fixture('wrap'))
        lines = bands(image)
        assert len(lines) > 1, lines
        widths = [stats(image, (0, top, image.width, bottom))['width'] for top, bottom in lines]
        assert max(widths) <= 180, widths
        print(f'200 characters: lines={len(lines)}, line_widths={widths}px <= inner_width=180px, ink_pixels={stats(image)["pixels"]}')
        tracked = []
        for spacing in (0, 300):
            image, _ = render(engine, text_data('A' * 40, f'sz="1800" spc="{spacing}"', box=(40, 40, 100, 440)))
            lines = bands(image)
            line_widths = [stats(image, (0, top, image.width, bottom))['width'] for top, bottom in lines]
            assert max(line_widths) <= 80, (spacing, line_widths)
            tracked.append((len(lines), line_widths))
        assert tracked[1][0] > tracked[0][0], tracked
        print(f'narrow 80pt text width, spc=0/300 line counts+widths={tracked}; tracking participates in wrap')
    elif group == 'breaks':
        image, _ = render(engine, fixture('breaks'))
        lines = bands(image)
        assert len(lines) == 2, lines
        print(f'a:br: glyph row bands={lines}')
    elif group == 'alignment':
        boxes = {}
        for align in ('l', 'ctr', 'r'):
            image, _ = render(engine, text_data(p_attributes=f'algn="{align}"'))
            boxes[align] = stats(image)['bbox']
        assert boxes['l'][0] >= 50 and boxes['l'][0] <= 53, boxes
        assert abs((boxes['ctr'][0] + boxes['ctr'][2]) / 2 - 240) <= 2, boxes
        assert abs(boxes['r'][2] - 430) <= 2, boxes
        image, _ = render(engine, text_data('one two three four five six seven eight nine ten ', 'sz="1800"', p_attributes='algn="just"', box=(40, 40, 200, 300)))
        lines = bands(image)
        widths = [stats(image, (0, top, image.width, bottom))['width'] for top, bottom in lines]
        assert len(lines) > 1 and abs(widths[0] - 180) <= 3, widths
        print(f'l/ctr/r glyph bboxes={boxes}; just line widths={widths}px, inner_width=180px')
    elif group == 'line-spacing':
        gaps = {}
        for name, element in (('pct100', '<a:spcPct val="100000"/>'), ('pct200', '<a:spcPct val="200000"/>'), ('pts40', '<a:spcPts val="4000"/>')):
            runs = run_text('Hello', 'sz="1800"') + '<a:br/>' + run_text('Hello', 'sz="1800"')
            image, _ = render(engine, package(shape(paragraph(runs, properties=f'<a:lnSpc>{element}</a:lnSpc>'))))
            lines = bands(image)
            assert len(lines) == 2, lines
            gaps[name] = lines[1][0] - lines[0][0]
        assert abs(gaps['pct200'] / gaps['pct100'] - 2) < .1 and abs(gaps['pts40'] - 40) <= 1, gaps
        print(f'baseline-to-baseline pixel gaps: {gaps}')
    elif group == 'paragraph-spacing':
        gaps = []
        for spacing in ('', '<a:spcAft><a:spcPts val="1200"/></a:spcAft>'):
            paragraphs = paragraph(run_text('Hello', 'sz="1800"'), properties=spacing) + paragraph(run_text('Hello', 'sz="1800"'))
            image, _ = render(engine, package(shape(paragraphs)))
            lines = bands(image)
            gaps.append(lines[1][0] - lines[0][0])
        assert abs(gaps[1] - gaps[0] - 12) <= 1, gaps
        before, _ = render(engine, text_data(attributes='sz="1800"', p_properties='<a:spcBef><a:spcPts val="1000"/></a:spcBef>'))
        plain, _ = render(engine, text_data(attributes='sz="1800"'))
        assert abs(stats(before)['bbox'][1] - stats(plain)['bbox'][1] - 10) <= 1
        print(f'spcAft=12pt paragraph start gaps={gaps}px; spcBef=10pt top shift={stats(before)["bbox"][1] - stats(plain)["bbox"][1]}px')
        empty_gaps = []
        for properties in ('', '<a:spcBef><a:spcPts val="1000"/></a:spcBef><a:spcAft><a:spcPts val="1200"/></a:spcAft>'):
            paragraphs = paragraph(run_text('Hello', 'sz="1800"')) + paragraph('', properties=properties) + paragraph(run_text('Hello', 'sz="1800"'))
            image, _ = render(engine, package(shape(paragraphs)))
            lines = bands(image)
            assert len(lines) == 2, lines
            empty_gaps.append(lines[1][0] - lines[0][0])
        assert abs(empty_gaps[1] - empty_gaps[0] - 22) <= 1, empty_gaps
        print(f'empty paragraph preserves spcBef=10pt + spcAft=12pt: visible-line gaps={empty_gaps}px, delta={empty_gaps[1] - empty_gaps[0]}px')
    elif group == 'bullets':
        image, _ = render(engine, fixture('numbered'), 4)
        lines = bands(image)
        assert len(lines) == 3, lines
        records = []
        for index, (top, bottom) in enumerate(lines, 1):
            actual = normalized(mask(image, (0, top, 310, bottom)))
            reference_image, _ = render(engine, text_data(f'{index}.', 'sz="2400"'), 4)
            expected = normalized(mask(reference_image))
            score = max(len(actual & {(x + dx, y + dy) for x, y in expected}) /
                        len(actual | {(x + dx, y + dy) for x, y in expected})
                        for dx in (-1, 0, 1) for dy in (-1, 0, 1))
            assert score >= .80, (index, score, bounds(actual), bounds(expected))
            records.append((f'{index}.', len(actual), round(score, 4)))
        # buChar is independently rendered before the text.
        character, _ = render(engine, text_data('Item', p_attributes='marL="381000" indent="-381000"', p_properties='<a:buChar char="•"/>'), 2)
        assert mask(character, (90, 0, 155, character.height))
        print(f'buAutoNum prefixes vs independently rendered literal digits (label, ink_pixels, mask_IoU)={records}; buChar dot present')
        automatic = package(shape(''.join(paragraph(run_text('Item', 'sz="2400"'),
            properties='<a:buAutoNum type="arabicPeriod"/>') for _ in range(3))))
        image, _ = render(engine, automatic, 4)
        lines = bands(image)
        assert len(lines) == 3, lines
        records = []
        for index, (top, bottom) in enumerate(lines, 1):
            reference_image, _ = render(engine, text_data(f'{index}.', 'sz="2400"'), 4)
            expected_pixels = mask(reference_image)
            _, _, right, _ = bounds(expected_pixels)
            prefix_pixels = mask(image, (0, top, right + 2, bottom))
            actual, expected = normalized(prefix_pixels), normalized(expected_pixels)
            score = max(len(actual & {(x + dx, y + dy) for x, y in expected}) /
                        len(actual | {(x + dx, y + dy) for x, y in expected})
                        for dx in (-1, 0, 1) for dy in (-1, 0, 1))
            body_pixels = mask(image, (right + 2, top, image.width, bottom))
            gap = bounds(body_pixels)[0] - bounds(prefix_pixels)[2]
            assert score >= .80 and gap >= 8, (index, score, gap)
            records.append((f'{index}.', round(score, 4), gap))
        print(f'buAutoNum without marL/indent: prefix literal mask IoU and visible marker/body gap={records}; no overlap')
    elif group == 'autofit':
        normal, _ = render(engine, fixture('size48'), 4)
        shrunk, _ = render(engine, fixture('autofit'), 4)
        original, smaller = stats(normal), stats(shrunk)
        ratio = smaller['height'] / original['height']
        assert abs(ratio - .625) < .04, (original, smaller, ratio)
        explicit, _ = render(engine, text_data(attributes='sz="3000"'), 4)
        assert shrunk.data == explicit.data
        print(f'fontScale=62500: height {original["height"]}->{smaller["height"]}px, ratio={ratio:.6f}; exact explicit30pt match')
        runs = run_text('Hello', 'sz="1800"') + '<a:br/>' + run_text('Hello', 'sz="1800"')
        props = '<a:lnSpc><a:spcPts val="4000"/></a:lnSpc>'
        gaps = []
        for reduction in (0, 25000):
            image, _ = render(engine, package(shape(paragraph(runs, properties=props), autofit=f'<a:normAutofit fontScale="100000" lnSpcReduction="{reduction}"/>')))
            lines = bands(image)
            gaps.append(lines[1][0] - lines[0][0])
        assert abs(gaps[0] - 40) <= 1 and abs(gaps[1] - 30) <= 1, gaps
        print(f'lnSpcReduction=0/25000: 40pt line gaps={gaps}px')
    elif group == 'autofit-invalid':
        reference, _ = render(engine, fixture('size48'), 2)
        for value in ('0', '100001', '-1', 'bad'):
            data = replace(fixture('autofit'), b'fontScale="62500"', f'fontScale="{value}"'.encode())
            image, _ = render(engine, data, 2, 'fontScale')
            assert image.data == reference.data
            print(f'invalid fontScale={value}: 100% fallback, height={stats(image)["height"]}px')
    elif group == 'level':
        lst = '<a:lvl9pPr><a:defRPr sz="2800"/></a:lvl9pPr>'
        reference, _ = render(engine, text_data(attributes='sz="2800"'), 2)
        for value in (8, 9, 99):
            image, _ = render(engine, package(shape(paragraph(attributes=f'lvl="{value}"'), lst=lst)), 2, 'level' if value > 8 else '')
            assert image.data == reference.data
            print(f'lvl={value}: resolved lvl=8 / 28pt, height={stats(image)["height"]}px')
    elif group == 'body':
        positions = {}
        for anchor in ('t', 'ctr', 'b'):
            image, _ = render(engine, text_data(body=f'wrap="square" anchor="{anchor}" lIns="254000" rIns="127000" tIns="254000" bIns="381000"'))
            positions[anchor] = stats(image)['bbox']
        assert 60 <= positions['t'][0] <= 63 and positions['t'][1] < positions['ctr'][1] < positions['b'][1]
        overflow, _ = render(engine, text_data('Hello ' * 15, 'sz="4800"', box=(40, 40, 100, 20), body='wrap="none" lIns="0" rIns="0" tIns="0" bIns="0"'))
        result = stats(overflow)
        assert len(bands(overflow)) == 1 and result['bbox'][2] > 140 and result['bbox'][3] > 60, result
        print(f'bodyPr insets/anchors bboxes={positions}; wrap=none overflow allowed, {result}')
    elif group == 'run-properties':
        plain, _ = render(engine, text_data(attributes='sz="2800"'), 2)
        italic, _ = render(engine, text_data(attributes='sz="2800" i="1"'), 2)
        underline, _ = render(engine, text_data(attributes='sz="2800" u="sng"'), 2)
        spaced, _ = render(engine, text_data(attributes='sz="2800" spc="200"'), 2)
        assert italic.data != plain.data and len(mask(underline)) > len(mask(plain))
        assert stats(spaced)['width'] > stats(plain)['width'] + 10
        colored, _ = render(engine, text_data(properties='<a:solidFill><a:srgbClr val="FF0000"/></a:solidFill>'))
        assert all(r >= g and g == b for x, y in mask(colored) for r, g, b in [colored.pixel(x, y)])
        print(f'italic mask differs; underline ink={len(mask(plain))}->{len(mask(underline))}; spc=200 widths={stats(plain)["width"]}->{stats(spaced)["width"]}px; solidFill red verified')
        spaces = [render(engine, text_data(text), 2)[0] for text in ('A B', 'A  B')]
        widths = [stats(image)['width'] for image in spaces]
        assert widths[1] > widths[0] + 2, widths
        print(f'a:t internal whitespace preserved: A B/A  B glyph widths={widths}px')
    elif group == 'missing-font':
        image, warning = render(engine, fixture('missing-font'), 2, 'M4 Missing Font')
        assert stats(image)['pixels'] > 0
        assert 'font' in warning.lower()
        reference, _ = render(engine, text_data(attributes='sz="1800"'), 2)
        assert image.data == reference.data
        print(f'nonexistent font rendered via fallback: {stats(image)}, warning={warning!r}')
        # Each target slot is the generic installed family; the other five
        # slots deliberately name absent fonts so a wrong lookup cannot pass.
        def themed(data, selected_group, selected_script, family='sans-serif'):
            scheme = '<a:fontScheme name="M6b">'
            for role in ('majorFont', 'minorFont'):
                scheme += f'<a:{role}>'
                for script in ('latin', 'ea', 'cs'):
                    name = family if (role, script) == (selected_group, selected_script) else f'M6b Missing {role} {script}'
                    scheme += f'<a:{script} typeface="{name}"/>'
                scheme += f'</a:{role}>'
            scheme += '</a:fontScheme>'
            return replace(data, b'</a:clrScheme>', b'</a:clrScheme>'+scheme.encode(), 'ppt/theme/theme1.xml')
        explicit, explicit_warning = render(engine, text_data(properties='<a:latin typeface="sans-serif"/>'), 2)
        assert not explicit_warning, explicit_warning
        for prefix, role in (('mj', 'majorFont'), ('mn', 'minorFont')):
            for suffix, script in (('lt', 'latin'), ('ea', 'ea'), ('cs', 'cs')):
                symbol = f'+{prefix}-{suffix}'
                data = themed(text_data(properties=f'<a:latin typeface="{symbol}"/>'), role, script)
                actual, warning = render(engine, data, 2)
                assert actual.data == explicit.data and not warning, (symbol, warning)
                print(f'theme {symbol} -> {role}/{script}=sans-serif: exact explicit-family raster, no warning')
        for text, script, suffix in (('中文', 'ea', 'ea'), ('אב', 'cs', 'cs')):
            data = themed(text_data(text, properties=f'<a:{script} typeface="+mn-{suffix}"/>'), 'minorFont', script)
            actual, warning = render(engine, data, 2)
            expected, expected_warning = render(engine, text_data(text, properties=f'<a:{script} typeface="sans-serif"/>'), 2)
            assert actual.data == expected.data and warning == expected_warning, (script, warning, expected_warning)
            assert 'font fallback=+' not in warning, warning
            print(f'theme {script} script selection: exact explicit-family raster and diagnostics')
        data = themed(text_data(properties='<a:latin typeface="+mn-lt"/>'), 'minorFont', 'latin', 'M6b Missing Theme Font')
        actual, warning = render(engine, data, 2, 'M6b Missing Theme Font')
        assert actual.data == render(engine, text_data(), 2)[0].data
        assert '+mn-lt' not in warning, warning
        print('uninstalled resolved theme typeface retains the ordinary font-fallback warning')
        from pptx_real_matrix import font_warnings_only
        # Noncharacters fill the glyph diagnostic buffer on every host; a
        # LastResort face may report fallback instead of an unresolved glyph.
        text = ''.join(chr(cp) for cp in range(0xFDD0, 0xFDF0))
        data = text_data(text, properties='<a:latin typeface="sans-serif"/>')
        glyph_image, warning = render(engine, data, warning='missing glyph: sans-serif U+FDD0 ')
        assert font_warnings_only(warning) and '...' not in warning, warning
        assert warning.endswith((' missing; ', ' fallback; ')) and len(warning.encode('utf-8')) < 256, warning
        malformed = shape(number=2).replace('<a:off x="508000" y="508000"/>', '')
        data = replace(data, b'</p:spTree>', malformed.encode() + b'</p:spTree>')
        mixed_image, mixed_warning = render(engine, data, warning='missing off/ext=1;')
        assert mixed_image.data == glyph_image.data
        assert 'missing glyph: sans-serif U+FDD0 ' in mixed_warning, mixed_warning
        assert not font_warnings_only(mixed_warning), mixed_warning
        print('long glyph warnings end at complete records and retain non-font diagnostics')
    elif group == 'invalid-utf8':
        image, _ = render(engine, fixture('invalid-utf8'), 2, 'UTF-8')
        expected, _ = render(engine, text_data('Good'), 2)
        assert image.data == expected.data
        print(f'invalid a:t run skipped; sibling Good retained: {stats(image)}, exact valid-only reference match')
        variants = (
            ('arbitrary prefix', replace(replace(fixture('invalid-utf8'), b'xmlns:a=', b'xmlns:d='), b'a:', b'd:')),
            ('strict namespace', replace(fixture('invalid-utf8'), GEN['A'].encode(), b'http://purl.oclc.org/ooxml/drawingml/main')),
            ('CDATA', replace(fixture('invalid-utf8'), b'<a:t>bad\xfftext</a:t>', b'<a:t><![CDATA[bad\xfftext]]></a:t>')),
        )
        for name, data in variants:
            actual, _ = render(engine, data, 2, 'UTF-8')
            assert actual.data == expected.data, name
            print(f'UTF-8 recovery {name}: valid sibling raster retained')
        invalid = (
            ('attribute', replace(fixture('size24'), b'sz="2400"', b'sz="24\xff00"')),
            ('foreign namespace t', replace(fixture('invalid-utf8'), b'<a:t>bad\xfftext</a:t>', b'<x:t xmlns:x="urn:m4:foreign">bad\xfftext</x:t>')),
            ('mismatched XML after skipped run', replace(fixture('invalid-utf8'), b'</p:txBody>', b'</p:spPr>')),
        )
        for name, data in invalid:
            document, error = C.c_void_p(), Error()
            status = engine.lib.exr_fixed_open_memory(11, data, len(data), None, C.byref(document), C.byref(error))
            try:
                assert status == error.code == 5 and not document.value, (name, status, error.message)
            finally:
                if document.value:
                    engine.lib.exr_fixed_free(document)
            print(f'UTF-8 recovery boundary {name}: FORMAT, document=null')
    else:
        raise AssertionError(group)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library', type=Path, required=True)
    parser.add_argument('group', choices=GROUPS)
    arguments = parser.parse_args()
    run(Engine(arguments.library.resolve()), arguments.group)


