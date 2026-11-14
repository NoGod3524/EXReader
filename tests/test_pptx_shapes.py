#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Pixel and malformed-input acceptance for the PPTX shape tree public ABI."""
import argparse
from contextlib import contextmanager
import copy
import ctypes as C
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from test_pptx_skeleton import Engine, Error, Bitmap, mutate

HERE = Path(__file__).resolve().parent / 'fixtures/pptx-shapes'
MANIFEST = json.loads((HERE / 'manifest.json').read_text())
P = 'http://schemas.openxmlformats.org/presentationml/2006/main'
A = 'http://schemas.openxmlformats.org/drawingml/2006/main'
NS = {'p': P, 'a': A}
SLIDE = 'ppt/slides/slide1.xml'


def fixture(name):
    return (HERE / f'{name}.pptx').read_bytes()


def changed(data, edit):
    from io import BytesIO
    from zipfile import ZipFile
    with ZipFile(BytesIO(data)) as archive:
        root = ET.fromstring(archive.read(SLIDE))
    edit(root)
    return mutate(data, {SLIDE: ET.tostring(root)})


def tree(root):
    return root.find('p:cSld/p:spTree', NS)


def sp(root):
    return tree(root).find('p:sp', NS)


def xf(root):
    return sp(root).find('p:spPr/a:xfrm', NS)


def group_xf(root):
    return tree(root).find('p:grpSp/p:grpSpPr/a:xfrm', NS)


@contextmanager
def opened(engine, data, code=0, warning=''):
    doc, error = C.c_void_p(), Error()
    status = engine.lib.exr_fixed_open_memory(11, data, len(data), None, C.byref(doc), C.byref(error))
    message = error.message.decode()
    assert status == error.code == code, (status, error.code, message)
    assert warning.lower() in message.lower(), (warning, message)
    if not code and not warning:
        assert message == '', message
    if warning or code:
        print(f'open status={status} message={message!r}')
    try:
        if code:
            assert not doc.value
        else:
            assert doc.value
        yield doc
    finally:
        if doc.value:
            engine.lib.exr_fixed_free(doc)


class Raster:
    def __init__(self, engine, doc, scale=1):
        bitmap, error = Bitmap(), Error()
        status = engine.lib.exr_fixed_render(doc, 0, scale, None, C.byref(bitmap), C.byref(error))
        assert status == 0, (status, error.message)
        try:
            assert bitmap.channels == 4
            self.width, self.height, self.stride = bitmap.width, bitmap.height, bitmap.stride
            self.data = C.string_at(bitmap.pixels, bitmap.stride * bitmap.height)
        finally:
            engine.lib.exr_bitmap_free(C.byref(bitmap))

    def pixel(self, x, y):
        at = int(y) * self.stride + int(x) * 4
        return tuple(self.data[at:at + 3])

    def bounds(self, rgb):
        target = bytes(rgb) + b'\xff' if rgb is not None else None
        xs, ys = [], []
        for y in range(self.height):
            row = self.data[y * self.stride:y * self.stride + self.width * 4]
            if target is None:
                # Curved fixture silhouettes include antialiased edge pixels;
                # exact RGB is checked independently in the opaque interior.
                if row.strip(b'\xff'):
                    xs.extend(((len(row) - len(row.lstrip(b'\xff'))) // 4,
                               (len(row.rstrip(b'\xff')) - 1) // 4))
                    ys.append(y)
                continue
            start = 0
            while True:
                x = row.find(target, start)
                if x < 0:
                    break
                if x % 4 == 0:
                    xs.append(x // 4)
                    ys.append(y)
                start = x + 1
        assert xs, ('color absent', rgb)
        return min(xs), min(ys), max(xs) + 1, max(ys) + 1

    def expect_bounds(self, rgb, box):
        actual = self.bounds(rgb)
        x, y, w, h = box
        expected = x, y, x + w, y + h
        delta = max(abs(a - b) for a, b in zip(actual, expected))
        assert delta < 2, (rgb, actual, expected, delta)
        return actual, delta

    def blank(self):
        assert self.data == b'\xff' * len(self.data)


def color(text):
    return tuple(bytes.fromhex(text))


def check_shape(raster, entry):
    rgb = color(entry['rgb'])
    x, y, w, h = entry['bounds_pt']
    count, maximum = 0, 0
    geometry = entry['geometry']
    for py in range(int(y + 4), int(y + h - 4)):
        for px in range(int(x + 4), int(x + w - 4)):
            u, v = (px + .5 - x) / w, (py + .5 - y) / h
            if geometry == 'ellipse' and (2 * u - 1) ** 2 + (2 * v - 1) ** 2 > .85 ** 2:
                continue
            if geometry == 'roundRect' and not (.2 < u < .8 or .35 < v < .65):
                continue
            if geometry == 'triangle' and not (v > .1 and abs(u - .5) < v / 2 - .05):
                continue
            maximum = max(maximum, *(abs(a - b) for a, b in zip(raster.pixel(px, py), rgb)))
            count += 1
    assert count > 100 and maximum <= 2, (entry, count, maximum)
    actual, delta = raster.expect_bounds(None if geometry in ('ellipse', 'roundRect', 'triangle') else rgb,
                                         entry['bounds_pt'])
    assert raster.pixel(x - 3, y + h / 2) == (255, 255, 255)
    assert raster.pixel(x + w + 3, y + h / 2) == (255, 255, 255)
    if geometry in ('ellipse', 'roundRect', 'triangle'):
        assert raster.pixel(x + 1, y + 1) == (255, 255, 255), geometry
    print(f"RGB={entry['rgb']} checked_pixels={count} max_channel_delta={maximum} "
          f"python-pptx_xywh={entry['bounds_pt']} render_bbox={actual} position_error={delta}px")


def render(engine, data):
    with opened(engine, data) as doc:
        return Raster(engine, doc)


def check_draw_contract(engine):
    class Point(C.Structure):
        _fields_ = [('x', C.c_double), ('y', C.c_double)]

    class Segment(C.Structure):
        _fields_ = [('verb', C.c_int), ('points', Point * 3)]

    callback_type = C.CFUNCTYPE(C.c_int, C.c_void_p, C.POINTER(Segment), C.c_size_t,
                               C.POINTER(C.c_double), C.c_void_p, C.POINTER(Error))

    class Sink(C.Structure):
        _fields_ = [('path', callback_type), ('image', C.c_void_p), ('clip', C.c_void_p),
                    ('state', C.c_void_p), ('context', C.c_void_p)]

    cancel_type = C.CFUNCTYPE(C.c_int, C.c_void_p)

    class Control(C.Structure):
        _fields_ = [('cancelled', cancel_type), ('progress', C.c_void_p), ('context', C.c_void_p)]

    records, failure = [], 0

    @callback_type
    def path(context, segments, count, matrix, style, error):
        m = tuple(matrix[i] for i in range(6))
        points = [(m[0] * segments[i].points[0].x + m[2] * segments[i].points[0].y + m[4],
                   m[1] * segments[i].points[0].x + m[3] * segments[i].points[0].y + m[5])
                  for i in range(count) if segments[i].verb != 4]
        records.append((points, C.cast(style, C.POINTER(C.c_uint32))[0]))
        if failure:
            error.contents.code, error.contents.message = failure, b'shape sink failure'
        return failure

    sink, error = Sink(path), Error()
    caller = (C.c_double * 6)(2, 0, 0, 3, 11, 13)
    draw = engine.lib.exr_fixed_draw
    draw.argtypes = [C.c_void_p, C.c_size_t, C.POINTER(C.c_double), C.POINTER(Sink),
                     C.c_void_p, C.POINTER(Error)]
    draw.restype = C.c_int
    with opened(engine, fixture('group')) as doc:
        assert draw(doc, 0, caller, C.byref(sink), None, C.byref(error)) == 0
        assert len(records) == 2
        for (points, rgba), box, expected_color in zip(records, ((371, 337, 288, 216), (803, 661, 432, 270)),
                                                       (0xFF0000FF, 0x0066FFFF)):
            x, y, w, h = box
            assert points == [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
            assert rgba == expected_color
        records.clear()
        failure = 3
        assert draw(doc, 0, caller, C.byref(sink), None, C.byref(error)) == 3
        assert len(records) == 1 and error.code == 3 and error.message == b'shape sink failure'
        records.clear()
        failure = 0
        cancelled = cancel_type(lambda context: int(bool(records)))
        control = Control(cancelled)
        assert draw(doc, 0, caller, C.byref(sink), C.byref(control), C.byref(error)) == 9
        assert len(records) == 1 and error.code == 9
    print('draw sink: caller matrix composed; sink failure propagated; cancellation between shapes honored')


def run(engine, group):
    case = next((e for e in MANIFEST if Path(e['file']).stem == group), None)
    if case:
        with opened(engine, fixture(group)) as doc:
            raster = Raster(engine, doc)
            assert (raster.width, raster.height) == tuple(case['size_pt'])
            for entry in case['shapes']:
                check_shape(raster, entry)
        return
    data = fixture('rect')
    if group == 'rotation':
        for degrees in (90, 180, 270, 450, -90):
            image = render(engine, changed(data, lambda r: xf(r).set('rot', str(degrees * 60000))))
            expected = (108, 36, 72, 144) if degrees % 180 else (72, 72, 144, 72)
            actual, delta = image.expect_bounds((255, 0, 0), expected)
            print(f'rotation={degrees} bbox={actual} expected_xywh={expected} error={delta}px')
        with opened(engine, changed(data, lambda r: xf(r).set('rot', '1800000')), warning='rot') as doc:
            Raster(engine, doc).expect_bounds((255, 0, 0), (72, 72, 144, 72))
    elif group == 'zero-extent':
        for axis in ('cx', 'cy'):
            damaged = changed(fixture('group'), lambda r: group_xf(r).find('a:chExt', NS).set(axis, '0'))
            with opened(engine, damaged, warning='chExt') as doc:
                raster = Raster(engine, doc)
                if axis == 'cx':
                    boxes = [(180, 108, 72, 72), (288, 216, 108, 90)]
                else:
                    boxes = [(180, 108, 144, 48), (396, 180, 216, 60)]
                for rgb, box in zip(((255, 0, 0), (0, 102, 255)), boxes):
                    actual, delta = raster.expect_bounds(rgb, box)
                    print(f'chExt {axis}=0: bbox={actual} expected_xywh={box} error={delta}px')
    elif group == 'group-transforms':
        data = fixture('group')
        for attribute, boxes in [('flipH', [(468, 108, 144, 72), (180, 216, 216, 90)]),
                                 ('flipV', [(180, 234, 144, 72), (396, 108, 216, 90)])]:
            image = render(engine, changed(data, lambda r: group_xf(r).set(attribute, '1')))
            for rgb, box in zip(((255, 0, 0), (0, 102, 255)), boxes):
                actual, delta = image.expect_bounds(rgb, box)
                print(f'group {attribute}: bbox={actual} expected_xywh={box} error={delta}px')
        def rotate(root):
            transform = group_xf(root)
            transform.find('a:off', NS).set('y', str(216 * 12700))
            transform.set('rot', str(90 * 60000))
        image = render(engine, changed(data, rotate))
        for rgb, box in zip(((255, 0, 0), (0, 102, 255)),
                            ((423, 99, 72, 144), (297, 315, 90, 216))):
            actual, delta = image.expect_bounds(rgb, box)
            print(f'group rotation90: bbox={actual} expected_xywh={box} error={delta}px')
        def wrap(root):
            parent = tree(root)
            original = parent.find('p:grpSp', NS)
            parent.remove(original)
            outer = ET.SubElement(parent, f'{{{P}}}grpSp')
            transform = ET.SubElement(ET.SubElement(outer, f'{{{P}}}grpSpPr'), f'{{{A}}}xfrm')
            for name, attrs in [('off', dict(x=str(36 * 12700), y=str(24 * 12700))),
                                ('ext', dict(cx=str(480 * 12700), cy=str(270 * 12700))),
                                ('chOff', dict(x='0', y='0')),
                                ('chExt', dict(cx=str(960 * 12700), cy=str(540 * 12700)))]:
                ET.SubElement(transform, f'{{{A}}}{name}', attrs)
            outer.append(original)
        image = render(engine, changed(data, wrap))
        for rgb, box in zip(((255, 0, 0), (0, 102, 255)), ((126, 78, 72, 36), (234, 132, 108, 45))):
            actual, delta = image.expect_bounds(rgb, box)
            print(f'nested groups: bbox={actual} expected_xywh={box} error={delta}px')
        check_draw_contract(engine)
    elif group == 'flips':
        def flip(root, horizontal=False, vertical=False):
            xf(root).set('flipH', 'true' if horizontal else 'false')
            xf(root).set('flipV', '1' if vertical else '0')
        triangle = fixture('triangle')
        for horizontal in (False, True):
            for vertical in (False, True):
                image = render(engine, changed(triangle, lambda r: flip(r, horizontal, vertical)))
                assert image.pixel(82, 82) == ((255, 153, 0) if vertical else (255, 255, 255))
                assert image.pixel(82, 169) == ((255, 255, 255) if vertical else (255, 153, 0))
                print(f'triangle flipH={horizontal} flipV={vertical}: orientation pixels pass')
        def flip_then_rotate(root):
            xf(root).set('flipH', '1')
            xf(root).set('rot', str(90 * 60000))
        image = render(engine, changed(triangle, flip_then_rotate))
        assert image.pixel(185, 80) == (255, 255, 255)
        assert image.pixel(185, 126) == (255, 153, 0)
        actual, delta = image.expect_bounds(None, (90, 54, 108, 144))
        print(f'triangle flipH then rotate90: bbox={actual} error={delta}px; orientation pixels pass')
        def diagonal(root, horizontal):
            properties = sp(root).find('p:spPr', NS)
            properties.find('a:prstGeom', NS).set('prst', 'line')
            line = properties.find('a:ln', NS)
            line.clear()
            line.set('w', str(6 * 12700))
            ET.SubElement(ET.SubElement(line, f'{{{A}}}solidFill'), f'{{{A}}}srgbClr', val='0000FF')
            xf(root).set('flipH', str(int(horizontal)))
        for horizontal in (False, True):
            image = render(engine, changed(data, lambda r: diagonal(r, horizontal)))
            assert image.pixel(108, 126 if horizontal else 90) == (0, 0, 255)
            assert image.pixel(108, 90 if horizontal else 126) == (255, 255, 255)
            print(f'line flipH={horizontal}: diagonal pixels pass')
        def connector(root):
            diagonal(root, False)
            xf(root).find('a:ext', NS).set('cy', '0')
            sp(root).tag = f'{{{P}}}cxnSp'
        image = render(engine, changed(data, connector))
        assert image.pixel(100, 72) == (0, 0, 255)
        assert image.pixel(100, 80) == (255, 255, 255)
        actual, delta = image.expect_bounds((0, 0, 255), (72, 69, 144, 6))
        print(f'zero-height connector: bbox={actual} error={delta}px')
    elif group == 'colors-lines':
        def recolor(root, tag, value):
            fill = sp(root).find('p:spPr/a:solidFill', NS)
            fill.clear()
            ET.SubElement(fill, f'{{{A}}}{tag}', val=value)
        for scheme, rgb in (('accent1', (79, 129, 189)), ('dk1', (0, 0, 0)),
                            ('lt1', (255, 255, 255)), ('accent6', (247, 150, 70))):
            image = render(engine, changed(data, lambda r: recolor(r, 'schemeClr', scheme)))
            assert image.pixel(100, 100) == rgb, (scheme, image.pixel(100, 100), rgb)
            print(f'schemeClr {scheme}: RGB={rgb}')
        for invalid in ('XYZ123', 'FF00', '1234567', ''):
            with opened(engine, changed(data, lambda r: recolor(r, 'srgbClr', invalid)), warning='color') as doc:
                assert Raster(engine, doc).pixel(100, 100) == (0, 0, 0)
        def border(root):
            properties = sp(root).find('p:spPr', NS)
            line = properties.find('a:ln', NS)
            line.clear()
            line.set('w', str(6 * 12700))
            ET.SubElement(ET.SubElement(line, f'{{{A}}}solidFill'), f'{{{A}}}srgbClr', val='0000FF')
        image = render(engine, changed(data, border))
        assert image.pixel(72, 100) == (0, 0, 255)
        assert image.pixel(100, 100) == (255, 0, 0)
        actual, _ = image.expect_bounds((0, 0, 255), (69, 69, 150, 78))
        print(f'6pt blue border: bbox={actual}, interior RGB=(255, 0, 0)')
    elif group == 'fallback':
        def unknown(root):
            parent = tree(root)
            original = sp(root)
            original.find('p:spPr/a:prstGeom', NS).set('prst', 'pentagon')
            duplicate = copy.deepcopy(original)
            duplicate.find('p:spPr/a:prstGeom', NS).set('prst', 'hexagon')
            duplicate.find('p:spPr/a:xfrm/a:off', NS).set('x', str(300 * 12700))
            parent.append(duplicate)
        with opened(engine, changed(data, unknown), warning='pentagon') as doc:
            image = Raster(engine, doc)
            assert image.pixel(73, 73) == image.pixel(301, 73) == (255, 0, 0)
        with opened(engine, changed(data, unknown), warning='hexagon'):
            pass
        print('fallback prstGeom values: pentagon, hexagon -> rectangles')
    elif group == 'missing':
        for element in ('off', 'ext'):
            def remove(root):
                transform = xf(root)
                transform.remove(transform.find(f'a:{element}', NS))
            with opened(engine, changed(data, remove), warning='off/ext') as doc:
                Raster(engine, doc).blank()
        def remove_tree(root):
            csld = root.find('p:cSld', NS)
            csld.remove(tree(root))
        with opened(engine, changed(data, remove_tree)) as doc:
            Raster(engine, doc).blank()
        def unsupported(root):
            parent = tree(root)
            parent.remove(sp(root))
            ET.SubElement(parent, f'{{{P}}}pic')
            ET.SubElement(parent, f'{{{P}}}graphicFrame')
        with opened(engine, changed(data, unsupported), warning='pic/graphicFrame') as doc:
            Raster(engine, doc).blank()
        print('missing off/ext: skipped; absent spTree: blank')
    elif group == 'limits':
        def repeat(root, count):
            parent, original = tree(root), sp(root)
            # Keep this below the shared XML node budget, so this assertion
            # isolates the PPTX object limit rather than the generic XML limit.
            properties = original.find('p:spPr', NS)
            properties[:] = [item for item in properties
                              if item.tag in (f'{{{A}}}xfrm', f'{{{A}}}solidFill')]
            original[:] = [properties]
            for _ in range(count - 1):
                parent.append(copy.deepcopy(original))
        with opened(engine, changed(data, lambda r: repeat(r, 10000))):
            pass
        with opened(engine, changed(data, lambda r: repeat(r, 10001)), code=6, warning='10000'):
            pass
        def nest(root, count):
            parent, original = tree(root), sp(root)
            parent.remove(original)
            for _ in range(count):
                group_node = ET.SubElement(parent, f'{{{P}}}grpSp')
                properties = ET.SubElement(group_node, f'{{{P}}}grpSpPr')
                transform = ET.SubElement(properties, f'{{{A}}}xfrm')
                for name, attrs in [('off', dict(x='0', y='0')), ('ext', dict(cx='12192000', cy='6858000')),
                                    ('chOff', dict(x='0', y='0')), ('chExt', dict(cx='12192000', cy='6858000'))]:
                    ET.SubElement(transform, f'{{{A}}}{name}', attrs)
                parent = group_node
            parent.append(original)
        with opened(engine, changed(data, lambda r: nest(r, 16))) as doc:
            Raster(engine, doc).expect_bounds((255, 0, 0), (72, 72, 144, 72))
        with opened(engine, changed(data, lambda r: nest(r, 17)), warning='depth') as doc:
            Raster(engine, doc).blank()
        print('10001 shapes: EXR_LIMIT; group depth 16: rendered; depth 17: warning + blank')
    else:
        raise AssertionError(group)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library', type=Path, required=True)
    parser.add_argument('group')
    args = parser.parse_args()
    run(Engine(args.library.resolve()), args.group)
