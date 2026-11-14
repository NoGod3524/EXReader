#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""PPTX M3 image, gradient, theme and alpha acceptance through the public ABI."""
import argparse
import colorsys
import copy
import ctypes as C
from io import BytesIO
import json
from pathlib import Path
import runpy
import xml.etree.ElementTree as ET
from zipfile import ZipFile, ZIP_DEFLATED

from test_pptx_skeleton import Engine, Bitmap, Error
from test_pptx_shapes import A, NS, P, SLIDE, Raster, changed, opened, sp, tree, xf

HERE = Path(__file__).resolve().parent / 'fixtures/pptx-fills'
THEME = json.loads((HERE / 'theme.json').read_text())
GENERATE = runpy.run_path(str(HERE / 'generate.py'))
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
RELS = 'ppt/slides/_rels/slide1.xml.rels'
MEDIA = 'ppt/media/image1.png'


def fixture(name):
    return (HERE / f'{name}.pptx').read_bytes()


def repack(data, changes):
    """Like the M1 helper, also permits adding/relocating OPC members."""
    output = BytesIO()
    with ZipFile(BytesIO(data)) as src, ZipFile(output, 'w', ZIP_DEFLATED) as dst:
        parts = {name: src.read(name) for name in src.namelist()}
        parts.update(changes)
        for name, value in parts.items():
            if value is not None:
                dst.writestr(name, value)
    return output.getvalue()


def render(engine, data, warning=''):
    doc, error = C.c_void_p(), Error()
    status = engine.lib.exr_fixed_open_memory(11, data, len(data), None, C.byref(doc), C.byref(error))
    message = error.message.decode('utf-8')
    assert status == error.code == 0 and doc.value, (status, error.code, message)
    # These fill fixtures contain no text, so every unrequested warning fails.
    assert warning.lower() in message.lower() if warning else not message, message
    try:
        return Raster(engine, doc)
    finally:
        engine.lib.exr_fixed_free(doc)


def slide_replace(data, old, new):
    with ZipFile(BytesIO(data)) as src:
        xml = src.read(SLIDE)
    assert old in xml, old
    return repack(data, {SLIDE: xml.replace(old, new)})


def near(actual, expected, tolerance=2):
    delta = max(abs(a - b) for a, b in zip(actual, expected))
    assert delta <= tolerance, (actual, expected, delta)
    return delta


def set_fill(root, xml):
    properties = sp(root).find('p:spPr', NS)
    for item in list(properties):
        if item.tag in [f'{{{A}}}{name}' for name in ('solidFill', 'gradFill', 'blipFill', 'noFill')]:
            properties.remove(item)
    fill = ET.fromstring(f'<root xmlns:a="{A}" xmlns:r="{R}">{xml}</root>')[0]
    line = properties.find('a:ln', NS)
    properties.insert(list(properties).index(line) if line is not None else len(properties), fill)


def fill_changed(data, xml):
    return changed(data, lambda root: set_fill(root, xml))


def check_sink(engine):
    image_type = C.CFUNCTYPE(C.c_int, C.c_void_p, C.c_void_p, C.POINTER(C.c_double), C.c_double, C.POINTER(Error))
    clip_type = C.CFUNCTYPE(C.c_int, C.c_void_p, C.c_void_p, C.c_size_t, C.POINTER(C.c_double), C.c_int, C.c_uint, C.POINTER(Error))
    state_type = C.CFUNCTYPE(C.c_int, C.c_void_p, C.c_int, C.POINTER(Error))
    cancel_type = C.CFUNCTYPE(C.c_int, C.c_void_p)

    class Sink(C.Structure):
        _fields_ = [(name, C.c_void_p) for name in ('path', 'image', 'clip', 'state', 'context')]

    class Control(C.Structure):
        _fields_ = [('cancelled', cancel_type), ('progress', C.c_void_p), ('context', C.c_void_p)]

    events, records = [], []
    failure = ''

    def result(stage, error):
        if stage == failure:
            error.contents.code, error.contents.message = 3, f'{stage} sink failure'.encode()
            return 3
        return 0

    @image_type
    def image(context, layer, matrix, alpha, error):
        events.append('image')
        bitmap = C.cast(layer, C.POINTER(Bitmap)).contents
        records.append(((bitmap.width, bitmap.height), tuple(matrix[i] for i in range(6)), alpha))
        return result('image', error)

    @clip_type
    def clip(context, path, count, matrix, rule, accumulate, error):
        events.append('clip')
        return result('clip', error)

    @state_type
    def state(context, value, error):
        stage = 'save' if value == 0 else 'restore'
        events.append(stage)
        return result(stage, error)

    sink = Sink(None, C.cast(image, C.c_void_p), C.cast(clip, C.c_void_p), C.cast(state, C.c_void_p))
    draw = engine.lib.exr_fixed_draw
    draw.argtypes = [C.c_void_p, C.c_size_t, C.POINTER(C.c_double), C.POINTER(Sink), C.c_void_p, C.POINTER(Error)]
    draw.restype = C.c_int
    caller, error = (C.c_double * 6)(2, 0, 0, 3, 11, 13), Error()
    with opened(engine, fixture('stretch')) as doc:
        assert draw(doc, 0, caller, C.byref(sink), None, C.byref(error)) == 0
        assert events == ['save', 'clip', 'image', 'restore'], events
        assert records == [((100, 50), (800, 0, 0, 150, 91, 133), 1)], records
        print(f'image sink: events={events}, image dimensions/matrix/alpha={records[0]}')
        for failure in ('save', 'clip', 'image', 'restore'):
            events.clear()
            records.clear()
            assert draw(doc, 0, caller, C.byref(sink), None, C.byref(error)) == 3
            assert error.code == 3 and error.message == f'{failure} sink failure'.encode()
            assert events[-1] == ('save' if failure == 'save' else 'restore'), events
            print(f'{failure} sink failure: propagated, events={events}')
    failure = ''
    events.clear()
    records.clear()
    cancelled = cancel_type(lambda context: int(bool(records)))
    control = Control(cancelled)
    with opened(engine, fixture('tile')) as doc:
        assert draw(doc, 0, caller, C.byref(sink), C.byref(control), C.byref(error)) == 9
        assert len(records) == 1 and error.code == 9
        assert events == ['save', 'clip', 'image', 'restore'], events
        print(f'tile cancellation after first image: status=9, events={events}')


def run(engine, group):
    if group == 'image':
        image = render(engine, fixture('image'))
        maximum = max(near(image.pixel(x, y), (0, 255, 0)) for y in range(42, 118) for x in range(42, 158))
        assert image.pixel(39, 60) == image.pixel(161, 60) == (255, 255, 255)
        print(f'PNG 120x80: interior RGB={image.pixel(100, 80)}, max channel error={maximum}')
        # Image fill follows the same shape silhouette, group matrix and flips as solid fill.
        def ellipse(root):
            sp(root).find('p:spPr/a:prstGeom', NS).set('prst', 'ellipse')
        image = render(engine, changed(fixture('image'), ellipse))
        assert image.pixel(41, 41) == (255, 255, 255)
        near(image.pixel(100, 80), (0, 255, 0))
        print('image ellipse: clipped white corner, green center')
        image = render(engine, slide_replace(fixture('image'), b'<a:stretch><a:fillRect/></a:stretch>', b''))
        near(image.pixel(100, 80), (0, 255, 0))
        print('absent stretch/tile: default stretch')
    elif group == 'stretch':
        image = render(engine, fixture('stretch'))
        samples = [(x, image.pixel(x, 65)) for x in (41, 139, 239, 339, 438)]
        for _, value in samples:
            near(value, (0, 255, 0))
        print(f'PNG 100x50 -> 400x50: five samples={samples}')
        stripes = GENERATE['png'](100, 50, lambda x, y: (255, 0, 0) if x < 50 else (0, 0, 255))
        image = render(engine, repack(fixture('stretch'), {MEDIA: stripes}))
        assert image.pixel(139, 65) == (255, 0, 0) and image.pixel(339, 65) == (0, 0, 255)
        def flip(root):
            xf(root).set('flipH', '1')
        flipped = render(engine, changed(repack(fixture('stretch'), {MEDIA: stripes}), flip))
        assert flipped.pixel(139, 65) == (0, 0, 255) and flipped.pixel(339, 65) == (255, 0, 0)
        print('stretch stripe landmarks and horizontal flip: pass')
    elif group == 'tile':
        image = render(engine, fixture('tile'))
        # No DPI metadata: 40px at 96dpi is a 30pt tile, with two 15pt stripes.
        xs = (45, 60, 75, 90, 105, 120, 255, 270)
        samples = [(x, image.pixel(x, 65)) for x in xs]
        for i, (_, value) in enumerate(samples):
            near(value, (255, 0, 0) if i % 2 == 0 else (0, 0, 255))
        assert image.pixel(281, 65) == (255, 255, 255)
        print(f'40px tile at 96dpi, period=30pt: {samples}')
        for attrs in ('tx="12700"', 'sx="50000"', 'flip="x"', 'algn="ctr"'):
            altered = slide_replace(fixture('tile'), b'<a:tile/>', f'<a:tile {attrs}/>'.encode())
            image = render(engine, altered, 'tile')
            near(image.pixel(80, 65), (255, 0, 0))
            near(image.pixel(240, 65), (0, 0, 255))
            print(f'unsupported tile {attrs}: stretch fallback')
    elif group == 'image-fallback':
        with ZipFile(BytesIO(fixture('image'))) as src:
            rels = src.read(RELS)
        cases = [('missing part', {MEDIA: None}), ('decode failure', {MEDIA: b'not an image'}),
                 ('missing relationship', {RELS: rels.replace(b'Id="img1"', b'Id="other"')}),
                 ('external target', {RELS: rels.replace(b'Target="../media/image1.png"',
                                          b'Target="https://invalid.example/image.png" TargetMode="External"')}),
                 ('unsafe path', {RELS: rels.replace(b'../media/image1.png', b'../../../escape.png')})]
        for label, changes in cases:
            image = render(engine, repack(fixture('image'), changes), 'image')
            assert image.pixel(100, 80) == (204, 204, 204)
            print(f'{label}: status=0, fill RGB={image.pixel(100, 80)}, warning present')
    elif group == 'relative-path':
        data = fixture('image')
        with ZipFile(BytesIO(data)) as src:
            slide, rels, media = src.read(SLIDE), src.read(RELS), src.read(MEDIA)
            presentation_rels = src.read('ppt/_rels/presentation.xml.rels')
        for target, path in ((b'../../../assets/green.png', 'assets/green.png'),
                             (b'/assets/green.png', 'assets/green.png')):
            moved = repack(data, {SLIDE: None, RELS: None, MEDIA: None,
                'ppt/custom/slides/page.xml': slide,
                'ppt/custom/slides/_rels/page.xml.rels': rels.replace(b'../media/image1.png', target),
                path: media,
                'ppt/_rels/presentation.xml.rels': presentation_rels.replace(b'slides/slide1.xml', b'custom/slides/page.xml')})
            image = render(engine, moved)
            near(image.pixel(100, 80), (0, 255, 0))
            print(f'part ppt/custom/slides/page.xml, target={target.decode()}: RGB={image.pixel(100, 80)}')
    elif group == 'formats':
        fixture_root = HERE.parent
        cases = [('BMP', fixture_root / 'images/bmp/solid.bmp', (220, 30, 40)),
                 ('GIF', fixture_root / 'images/gif/solid.gif', (220, 30, 40)),
                 ('JPEG', fixture_root / 'pdf-images/gray.jpg', (64, 64, 64))]
        for name, path, expected in cases:
            # The deliberately unchanged .png extension also checks signature-based decoding.
            image = render(engine, repack(fixture('image'), {MEDIA: path.read_bytes()}))
            near(image.pixel(100, 80), expected)
            print(f'{name} through shared decoder: RGB={image.pixel(100, 80)}')
        image = render(engine, repack(fixture('image'), {MEDIA: (fixture_root / 'pdf-images/baseline.jpg').read_bytes()}))
        for point, expected in (((60, 55), (255, 0, 0)), ((140, 55), (0, 255, 0)), ((60, 105), (0, 0, 255))):
            near(image.pixel(*point), expected, 5)
        print('JPEG quadrant orientation: red/green top, blue bottom-left')
    elif group == 'picture':
        def picture(root):
            item = sp(root)
            item.tag = f'{{{P}}}pic'
            item.find('p:nvSpPr/p:cNvSpPr', NS).tag = f'{{{P}}}cNvPicPr'
            item.find('p:nvSpPr', NS).tag = f'{{{P}}}nvPicPr'
            properties = item.find('p:spPr', NS)
            fill = properties.find('a:blipFill', NS)
            properties.remove(fill)
            fill.tag = f'{{{P}}}blipFill'
            item.insert(1, fill)
        image = render(engine, changed(fixture('image'), picture))
        near(image.pixel(100, 80), (0, 255, 0))
        assert image.pixel(39, 60) == (255, 255, 255)
        print(f'p:pic/p:blipFill: RGB={image.pixel(100, 80)}')
    elif group == 'fill-transforms':
        stripes = GENERATE['png'](100, 50, lambda x, y: (255, 0, 0) if x < 50 else (0, 0, 255))
        def rotate(root):
            xf(root).set('rot', '5400000')
            xf(root).find('a:off', NS).set('y', str(215 * 12700))
        image = render(engine, changed(repack(fixture('stretch'), {MEDIA: stripes}), rotate))
        assert image.pixel(240, 100) == (255, 0, 0) and image.pixel(240, 380) == (0, 0, 255)
        assert image.pixel(200, 240) == (255, 255, 255)
        print('image rotate90: red top, blue bottom; width=50 height=400')
        def wrap(root):
            parent, original = tree(root), sp(root)
            parent.remove(original)
            group = ET.SubElement(parent, f'{{{P}}}grpSp')
            transform = ET.SubElement(ET.SubElement(group, f'{{{P}}}grpSpPr'), f'{{{A}}}xfrm')
            for tag, attrs in [('off', dict(x=str(100 * 12700), y=str(80 * 12700))),
                               ('ext', dict(cx=str(360 * 12700), cy=str(270 * 12700))),
                               ('chOff', dict(x='0', y='0')), ('chExt', dict(cx=str(720 * 12700), cy=str(540 * 12700)))]:
                ET.SubElement(transform, f'{{{A}}}{tag}', attrs)
            group.append(original)
        for name, expected in (('image', (0, 255, 0)), ('gradient', (127, 0, 128))):
            image = render(engine, changed(fixture(name), wrap))
            point = (150, 120) if name == 'image' else (220, 120)
            near(image.pixel(*point), expected, 3)
            assert image.pixel(110, 110) == (255, 255, 255)
            print(f'{name} nested group scale0.5 + offset100,80: point={point}, RGB={image.pixel(*point)}')
    elif group == 'sink':
        check_sink(engine)
    elif group == 'gradient':
        image = render(engine, fixture('gradient'))
        xs = (40, 90, 140, 190, 240, 290, 340, 390, 439)
        samples = [image.pixel(x, 80) for x in xs]
        near(samples[0], (255, 0, 0))
        near(samples[-1], (0, 0, 255))
        assert all(a[0] >= b[0] and a[2] <= b[2] for a, b in zip(samples, samples[1:]))
        for x, rgb in zip(xs, samples):
            t = (x + .5 - 40) / 400
            near(rgb, (round(255 * (1 - t)), 0, round(255 * t)))
        print(f'red -> blue angle=0, nine x={xs}: RGB={samples}; monotone=True')
    elif group == 'gradient-angles':
        checks = {90: ((240, 40), (240, 119)), 180: ((439, 80), (40, 80)),
                  270: ((240, 119), (240, 40)), 45: ((40, 40), (439, 119))}
        for angle, points in checks.items():
            data = slide_replace(fixture('gradient'), b'ang="0"', f'ang="{angle * 60000}"'.encode())
            image = render(engine, data)
            values = [image.pixel(*p) for p in points]
            near(values[0], (255, 0, 0), 3)
            near(values[1], (0, 0, 255), 3)
            print(f'gradient angle={angle}: points={points}, RGB={values}')
        def rotate(root):
            xf(root).set('rot', '5400000')
            xf(root).find('a:off', NS).set('y', str(160 * 12700))
        image = render(engine, changed(fixture('gradient'), rotate))
        near(image.pixel(240, 1), (255, 0, 0), 3)
        near(image.pixel(240, 398), (0, 0, 255), 3)
        print('gradient rotated shape: top red, bottom blue')
    elif group == 'gradient-stops':
        xml = GENERATE['gradient'](((0, 'FF0000'), (25000, '00FF00'), (100000, '0000FF')))
        image = render(engine, fill_changed(fixture('gradient'), xml))
        samples = [(x, image.pixel(x, 80)) for x in (40, 90, 140, 290, 439)]
        for (_, actual), expected in zip(samples, ((255, 0, 0), (128, 128, 0), (0, 255, 0), (0, 128, 128), (0, 0, 255))):
            near(actual, expected, 3)
        print(f'nonuniform stops 0/25000/100000: {samples}')
        xml = '<a:gradFill><a:gsLst><a:gs pos="0"><a:srgbClr val="FF0000"><a:alpha val="50000"/></a:srgbClr></a:gs><a:gs pos="100000"><a:srgbClr val="0000FF"><a:alpha val="50000"/></a:srgbClr></a:gs></a:gsLst><a:lin ang="0"/></a:gradFill>'
        image = render(engine, fill_changed(fixture('gradient'), xml))
        near(image.pixel(40, 80), (255, 128, 128), 3)
        near(image.pixel(439, 80), (128, 128, 255), 3)
        print(f'gradient alpha=50% endpoints: {image.pixel(40, 80)}, {image.pixel(439, 80)}')
    elif group == 'gradient-fallback':
        for stops in (((0, '37A25C'),), ()):
            data = fill_changed(fixture('gradient'), GENERATE['gradient'](stops))
            image = render(engine, data, 'gradient')
            expected = tuple(bytes.fromhex('37A25C')) if stops else (0, 0, 0)
            near(image.pixel(240, 80), expected)
            print(f'gradient stops={len(stops)}: solid RGB={image.pixel(240, 80)}, warning present')
    elif group == 'theme':
        image = render(engine, fixture('theme'))
        for i, (name, text) in enumerate(THEME.items()):
            actual = image.pixel(80 + i % 4 * 150, 50 + i // 4 * 100)
            assert actual == tuple(bytes.fromhex(text)), (name, actual, text)
            print(f'schemeClr {name:8} -> #{text} -> RGB={actual}')
        with ZipFile(BytesIO(fixture('theme'))) as src:
            theme = src.read('ppt/theme/theme1.xml')
        theme = theme.replace(b'<a:srgbClr val="102030"/>', b'<a:sysClr val="windowText" lastClr="102030"/>')
        image = render(engine, repack(fixture('theme'), {'ppt/theme/theme1.xml': theme}))
        assert image.pixel(80, 50) == (16, 32, 48)
        print('theme sysClr lastClr: RGB=(16, 32, 48)')
    elif group == 'theme-default':
        xml = '<a:solidFill><a:schemeClr val="accent1"/></a:solidFill>'
        data = repack(fill_changed(fixture('alpha'), xml), {'ppt/theme/theme1.xml': None})
        image = render(engine, data, 'theme')
        assert image.pixel(100, 80) == (79, 129, 189)
        print(f'theme1.xml missing: builtin accent1 RGB={image.pixel(100, 80)}, warning present')
    elif group == 'color-transforms':
        orders = [[('lumMod', 50000), ('lumOff', 20000), ('tint', 25000), ('shade', 80000)],
                  [('shade', 80000), ('tint', 25000), ('lumOff', 20000), ('lumMod', 50000)]]
        for order in orders:
            h, l, s = colorsys.rgb_to_hls(*(x / 255 for x in bytes.fromhex(THEME['accent1'])))
            for tag, value in order:
                factor = value / 100000
                if tag in ('lumMod', 'shade'):
                    l *= factor
                elif tag == 'lumOff':
                    l += factor
                else:
                    l = 1 - (1 - l) * factor
                l = min(1, max(0, l))
            expected = tuple(round(x * 255) for x in colorsys.hls_to_rgb(h, l, s))
            transforms = ''.join(f'<a:{tag} val="{value}"/>' for tag, value in order)
            xml = f'<a:solidFill><a:schemeClr val="accent1">{transforms}</a:schemeClr></a:solidFill>'
            image = render(engine, fill_changed(fixture('alpha'), xml))
            near(image.pixel(100, 80), expected, 1)
            print(f'HSL transforms {order}: RGB={image.pixel(100, 80)}, oracle={expected}')
        for value, expected in ((0, (255, 255, 255)), (100000, tuple(bytes.fromhex(THEME['accent1'])))):
            xml = f'<a:solidFill><a:schemeClr val="accent1"><a:tint val="{value}"/></a:schemeClr></a:solidFill>'
            image = render(engine, fill_changed(fixture('alpha'), xml))
            near(image.pixel(100, 80), expected, 1)
            print(f'tint={value}: RGB={image.pixel(100, 80)}')
    elif group == 'alpha':
        image = render(engine, fixture('alpha'))
        near(image.pixel(100, 80), (255, 128, 128), 3)
        print(f'alpha=50000 red over white: RGB={image.pixel(100, 80)}')
        def background(root):
            front = sp(root)
            back = copy.deepcopy(front)
            fill = back.find('p:spPr/a:solidFill', NS)
            fill.clear()
            ET.SubElement(fill, f'{{{A}}}srgbClr', val='0000FF')
            parent = tree(root)
            parent.insert(list(parent).index(front), back)
        image = render(engine, changed(fixture('alpha'), background))
        near(image.pixel(100, 80), (128, 0, 127), 3)
        print(f'alpha=50000 red over blue: RGB={image.pixel(100, 80)}')
        image = render(engine, slide_replace(fixture('alpha'), b'val="50000"', b'val="0"'))
        assert image.pixel(100, 80) == (255, 255, 255)
        print('alpha=0: white background visible')
    elif group == 'alpha-invalid':
        for value in ('100001', '200000', '-1', 'bad'):
            image = render(engine, slide_replace(fixture('alpha'), b'val="50000"', f'val="{value}"'.encode()), 'alpha')
            assert image.pixel(100, 80) == (255, 0, 0)
            print(f'alpha={value}: RGB={image.pixel(100, 80)}, opaque fallback + warning')
    elif group == 'background-solid':
        image = render(engine, fixture(group))
        points = ((0, 0), (719, 0), (0, 539), (719, 539), (360, 270))
        samples = [(point, image.pixel(*point)) for point in points]
        assert all(rgb == (18, 52, 86) for _, rgb in samples), samples
        assert image.pixel(100, 80) == (0, 255, 0)
        print(f'p:bg solid #123456: {samples}; foreground (100,80)={image.pixel(100, 80)}')
    elif group == 'background-gradient':
        data = fixture(group)
        image = render(engine, data)
        xs = (0, 180, 360, 540, 719)
        samples = [(x, image.pixel(x, 270)) for x in xs]
        for x, actual in samples:
            t = (x + .5) / 720
            near(actual, (round(255 * (1 - t)), 0, round(255 * t)))
        print(f'p:bg gradient red -> blue angle=0: y=270, {samples}')
        for angle in (0, 45, 90, 180, 270):
            background = render(engine, slide_replace(data, b'ang="0"', f'ang="{angle * 60000}"'.encode()))
            shape = GENERATE['shape'](GENERATE['gradient'](angle=angle * 60000), (0, 0, 720, 540))
            reference = render(engine, GENERATE['package'](shape))
            assert background.data == reference.data, f'background/shape gradient angle={angle}'
            print(f'p:bg gradient angle={angle}: exact full-slide shape raster match')
    elif group == 'background-image':
        image = render(engine, fixture(group))
        points = ((0, 0), (180, 270), (539, 270), (719, 539))
        samples = [(point, image.pixel(*point)) for point in points]
        assert [rgb for _, rgb in samples] == [(255, 0, 0), (255, 0, 0), (0, 0, 255), (0, 0, 255)], samples
        print(f'p:bg blipFill 100x50 stretched to 720x540: {samples}')
    elif group == 'background-theme':
        image = render(engine, fixture(group))
        points = ((0, 0), (360, 270), (719, 539))
        samples = [(point, image.pixel(*point)) for point in points]
        assert all(rgb == (194, 58, 85) for _, rgb in samples), samples
        print(f'p:bgRef idx=1002 -> second bgFillStyleLst phClr -> accent2 #C23A55: {samples}')
        changed_ref = slide_replace(fixture(group), b'val="accent2"', b'val="accent3"')
        changed_image = render(engine, changed_ref)
        assert changed_image.pixel(360, 270) == (53, 121, 189)
        print(f'p:bgRef schemeClr accent3: RGB={changed_image.pixel(360, 270)}')
        first = render(engine, slide_replace(fixture(group), b'idx="1002"', b'idx="1001"'))
        assert first.pixel(360, 270) == (255, 0, 0)
        print(f'p:bgRef idx=1001 -> first bgFillStyleLst entry: RGB={first.pixel(360, 270)}')
        gradient = render(engine, slide_replace(fixture(group), b'idx="1002"', b'idx="1003"'))
        direct = GENERATE['background'](GENERATE['gradient'](((0, THEME['accent2']), (100000, '0000FF'))))
        assert gradient.data == render(engine, GENERATE['package']('', background=direct)).data
        print(f'p:bgRef idx=1003 -> gradient phClr=accent2: RGB(360,270)={gradient.pixel(360, 270)}, exact direct-gradient match')
        for index in (0, 1000):
            render(engine, slide_replace(fixture(group), b'idx="1002"', f'idx="{index}"'.encode())).blank()
            print(f'p:bgRef idx={index}: no background, all pixels white and no warning')
    elif group == 'background-inheritance':
        data = fixture('background-master')
        image = render(engine, data)
        points = ((0, 0), (360, 270), (719, 539))
        samples = [(point, image.pixel(*point)) for point in points]
        assert all(rgb == (91, 36, 109) for _, rgb in samples), samples
        print(f'absent slide p:bg -> master #5B246D: {samples}')
        white = GENERATE['background']('<a:solidFill><a:srgbClr val="FFFFFF"/></a:solidFill>')
        overridden = slide_replace(data, b'<p:cSld>', f'<p:cSld>{white}'.encode())
        render(engine, overridden).blank()
        print('explicit white slide p:bg overrides master background: all pixels white')
        layout = 'ppt/slideLayouts/slideLayout1.xml'
        with ZipFile(BytesIO(data)) as source:
            layout_xml = source.read(layout)
        layout_fill = GENERATE['background']('<a:solidFill><a:srgbClr val="00FFFF"/></a:solidFill>')
        layout_xml = layout_xml.replace(b'<p:cSld>', f'<p:cSld xmlns:a="{A}">{layout_fill}'.encode())
        image = render(engine, repack(data, {layout: layout_xml}))
        assert image.pixel(360, 270) == (0, 255, 255)
        render(engine, repack(overridden, {layout: layout_xml})).blank()
        print('layout cyan background overrides master; explicit slide white overrides layout')
        master = 'ppt/slideMasters/slideMaster1.xml'
        master_rels = 'ppt/slideMasters/_rels/slideMaster1.xml.rels'
        with ZipFile(BytesIO(data)) as source:
            xml, rels = source.read(master), source.read(master_rels)
        fill = GENERATE['background']('<a:blipFill><a:blip r:embed="masterImage"/><a:stretch><a:fillRect/></a:stretch></a:blipFill>')
        begin, end = xml.index(b'<p:bg>'), xml.index(b'</p:bg>') + len(b'</p:bg>')
        inherited = repack(data, {master: xml[:begin] + fill.encode() + xml[end:],
                                 master_rels: rels.replace(b'Id="img1"', b'Id="masterImage"'),
                                 MEDIA: GENERATE['png'](8, 8, lambda x, y: (37, 158, 213))})
        image = render(engine, inherited)
        assert all(image.pixel(*point) == (37, 158, 213) for point in points)
        print(f'master blipFill resolves relationship on master part: RGB={image.pixel(360, 270)}')
        render(engine, GENERATE['package']('')).blank()
        print('absent slide and master p:bg: all pixels white')
    else:
        raise AssertionError(group)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library', type=Path, required=True)
    parser.add_argument('group')
    args = parser.parse_args()
    run(Engine(args.library.resolve()), args.group)
