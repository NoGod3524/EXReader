#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""PPTX M5 table pixel and malformed-input acceptance through the public ABI."""
import argparse
import ctypes as C
from io import BytesIO
from pathlib import Path
import runpy
import sys
from zipfile import ZipFile

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from test_pptx_skeleton import Engine, Error
from test_pptx_shapes import Raster, opened
from test_pptx_text import bands, bounds, mask

HERE = Path(__file__).resolve().parent / 'fixtures/pptx-tables'
GEN = runpy.run_path(str(HERE / 'generate.py'))
cell, table, package, borders = (GEN[name] for name in ('cell', 'table', 'package', 'borders'))
COLORS = [tuple(bytes.fromhex(rgb)) for rgb in GEN['COLORS']]
PURPLE = tuple(bytes.fromhex(GEN['BORDER']))
GROUPS = ('fills', 'borders', 'columns', 'text', 'merges', 'anchor', 'malformed',
          'margins', 'overflow', 'transforms', 'limits', 'sink')


def fixture(name):
    return (HERE / f'{name}.pptx').read_bytes()


def render(engine, data, warning='', scale=1):
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
        print(f'open status={status} warning={message!r}')
    return image


def pixels(image, rgb, box=None):
    left, top, right, bottom = box or (0, 0, image.width, image.height)
    return {(x, y) for y in range(top, bottom) for x in range(left, right) if image.pixel(x, y) == rgb}


def inside(bbox, box):
    assert bbox[0] >= box[0] and bbox[1] >= box[1] and bbox[2] <= box[2] and bbox[3] <= box[3], (bbox, box)


def without_placeholder_text(data):
    with ZipFile(BytesIO(data)) as source:
        parts = {name: source.read(name) for name in source.namelist()}
    tx = GEN['body']('SHOULD NOT DRAW').encode()
    assert tx in parts[GEN['SLIDE']]
    parts[GEN['SLIDE']] = parts[GEN['SLIDE']].replace(tx, b'')
    return GEN['archive'](parts)


def check_sink(engine):
    class StyleHead(C.Structure):
        _fields_ = [('fill', C.c_uint32), ('stroke', C.c_uint32), ('flags', C.c_uint), ('rule', C.c_int)]

    path_type = C.CFUNCTYPE(C.c_int, C.c_void_p, C.c_void_p, C.c_size_t,
                           C.POINTER(C.c_double), C.POINTER(StyleHead), C.POINTER(Error))
    clip_type = C.CFUNCTYPE(C.c_int, C.c_void_p, C.c_void_p, C.c_size_t,
                           C.POINTER(C.c_double), C.c_int, C.c_uint, C.POINTER(Error))
    state_type = C.CFUNCTYPE(C.c_int, C.c_void_p, C.c_int, C.POINTER(Error))
    cancel_type = C.CFUNCTYPE(C.c_int, C.c_void_p)

    class Sink(C.Structure):
        _fields_ = [(name, C.c_void_p) for name in ('path', 'image', 'clip', 'state', 'context')]

    class Control(C.Structure):
        _fields_ = [('cancelled', cancel_type), ('progress', C.c_void_p), ('context', C.c_void_p)]

    events, clips = [], []
    failure = set()

    def result(stage, error):
        if stage in failure:
            error.contents.code, error.contents.message = 3, f'{stage} sink failure'.encode()
            return 3
        return 0

    @path_type
    def path(context, segments, count, matrix, style, error):
        stage = 'border' if style.contents.flags == 2 else ('fill' if style.contents.fill == 0xE84032FF else 'text')
        events.append(stage)
        return result(stage, error)

    @clip_type
    def clip(context, segments, count, matrix, rule, accumulate, error):
        events.append('clip')
        clips.append((count, tuple(matrix[i] for i in range(6)), rule, accumulate))
        return result('clip', error)

    @state_type
    def state(context, value, error):
        stage = 'save' if value == 0 else 'restore'
        events.append(stage)
        return result(stage, error)

    sink = Sink(C.cast(path, C.c_void_p), None, C.cast(clip, C.c_void_p), C.cast(state, C.c_void_p))
    draw = engine.lib.exr_fixed_draw
    draw.argtypes = [C.c_void_p, C.c_size_t, C.POINTER(C.c_double), C.POINTER(Sink), C.c_void_p, C.POINTER(Error)]
    draw.restype = C.c_int
    caller, error = (C.c_double * 6)(2, 0, 0, 3, 11, 13), Error()
    data = package(table([[cell('AB', fill=GEN['COLORS'][0], lines=borders())]], columns=(320,)))
    with opened(engine, data) as document:
        assert draw(document, 0, caller, C.byref(sink), None, C.byref(error)) == 0
        expected = ['fill'] + ['border'] * 4 + ['save', 'clip', 'text', 'text', 'restore']
        assert events == expected, events
        assert clips == [(5, (2, 0, 0, 3, 91, 133), 0, 0)], clips
        print(f'table sink success: events={events}, clip count/matrix/rule/accumulate={clips[0]}')
        for failed in ('fill', 'border', 'save', 'clip', 'text', 'restore'):
            events.clear()
            failure = {failed}
            assert draw(document, 0, caller, C.byref(sink), None, C.byref(error)) == 3
            assert error.code == 3 and error.message == f'{failed} sink failure'.encode(), error.message
            if failed in ('clip', 'text', 'restore'):
                assert events[-1] == 'restore', events
            else:
                assert 'restore' not in events, events
            print(f'{failed} callback failure: status=3 propagated, events={events}')
        failure = {'text', 'restore'}
        events.clear()
        assert draw(document, 0, caller, C.byref(sink), None, C.byref(error)) == 3
        assert error.message == b'text sink failure' and events[-1] == 'restore', (error.message, events)
        print('text + restore failure: original text error retained, restore attempted')
        failure = set()
        events.clear()
        cancelled = cancel_type(lambda context: int('text' in events))
        control = Control(cancelled)
        assert draw(document, 0, caller, C.byref(sink), C.byref(control), C.byref(error)) == 9
        assert error.code == 9 and events.count('text') == 1 and events[-1] == 'restore', events
        print(f'cancel after first text path: status=9, events={events}')
        for absent in ('path', 'clip', 'state', 'clip+state'):
            events.clear()
            partial = Sink(sink.path, None, sink.clip, sink.state)
            for field in absent.split('+'):
                setattr(partial, field, None)
            assert draw(document, 0, caller, C.byref(partial), None, C.byref(error)) == 0
            assert events == ([] if absent == 'path' else ['fill'] + ['border'] * 4 + ['text'] * 2), events
            print(f'missing {absent}: status=0, events={events}')


def run(engine, group):
    if group == 'fills':
        image = render(engine, fixture('fills'))
        for box, expected in zip(((40, 40, 200, 160), (200, 40, 360, 160),
                                  (40, 160, 200, 280), (200, 160, 360, 280)), COLORS):
            x, y, right, bottom = box
            actual = image.pixel((x + right) // 2, (y + bottom) // 2)
            maximum = max(abs(a - b) for a, b in zip(actual, expected))
            assert maximum <= 2, (actual, expected)
            print(f'cell={box} fill RGB={actual} expected={expected} max_channel_delta={maximum}')
    elif group == 'borders':
        image = render(engine, fixture('fills'))
        count = len(pixels(image, PURPLE))
        boundary = [(x, image.pixel(x, 100)) for x in range(194, 206)]
        width = sum(value == PURPLE for x, value in boundary)
        assert count > 0 and abs(width - 50800 / 12700) <= 1, (count, width)
        print(f'border RGB={PURPLE} exact_pixels={count}; @w=50800 EMU => 4px measured={width}px; boundary_samples={boundary}')
        doubled = render(engine, fixture('fills'), scale=2)
        doubled_width = sum(doubled.pixel(x, 200) == PURPLE for x in range(388, 412))
        assert abs(doubled_width - 8) <= 1, doubled_width
        print(f'border at scale=2: measured={doubled_width}px expected=8px')
        # Every side carries its own color and width; the second cell owns the shared edge.
        lines = ''.join(borders(rgb, width, side) for rgb, width, side in
                        [('FF0000', 2, 'L'), ('00AA00', 6, 'R'), ('0000FF', 8, 'T'), ('AA5500', 10, 'B')])
        image = render(engine, package(table([[cell(lines=lines), cell(lines=borders('FF8800', 4, 'L'))]])))
        for rgb, point in [((255, 0, 0), (40, 100)), ((0, 0, 255), (100, 40)),
                           ((170, 85, 0), (100, 160)), ((255, 136, 0), (200, 100))]:
            assert image.pixel(*point) == rgb, (point, image.pixel(*point), rgb)
        print('independent L/R/T/B and later-cell shared-edge color: pass; shared RGB=(255, 136, 0)')
    elif group == 'columns':
        image = render(engine, fixture('columns'))
        widths = [sum(image.pixel(x, 100) == rgb for x in range(image.width)) for rgb in COLORS[:2]]
        ratio = widths[1] / widths[0]
        assert abs(ratio / 3 - 1) <= .05, (widths, ratio)
        print(f'gridCol @w=(1270000,3810000) EMU: colored widths={widths}px ratio={ratio:.6f}')
        data = package(table([[cell(fill=GEN['COLORS'][0]), cell(fill=GEN['COLORS'][1])]],
                             columns=(100, 300), box=(40, 40, 200, 120)))
        image = render(engine, data, 'gridCol')
        assert image.pixel(439, 100) == COLORS[1] and image.pixel(440, 100) == (255, 255, 255)
        print('frame cx=200pt, grid sum=400pt: grid geometry ends at x=440px, warning present')
    elif group == 'text':
        image = render(engine, fixture('text'))
        boxes = ((40, 40, 200, 160), (200, 160, 360, 280))
        for text, box in zip(('A', 'B'), boxes):
            glyphs = mask(image, box)
            bbox = bounds(glyphs)
            inside(bbox, box)
            print(f'text={text!r} glyph_pixels={len(glyphs)} bbox={bbox} cell={box}')
        assert not mask(image, (200, 40, 360, 160)) and not mask(image, (40, 160, 200, 280))
    elif group == 'merges':
        image = render(engine, fixture('merged'))
        clean = render(engine, without_placeholder_text(fixture('merged')))
        assert image.data == clean.data
        separator = len(pixels(image, PURPLE, (200, 45, 201, 155)))
        ignored = len(pixels(image, (255, 0, 0), (40, 40, 360, 160)))
        assert separator == ignored == 0, (separator, ignored)
        assert len(pixels(image, PURPLE, (200, 165, 201, 275))) > 0
        print(f'gridSpan=2 + hMerge placeholder: divider x=200 y=45..154 border_pixels={separator}; ignored red fill pixels={ignored}; txBody vs empty placeholder pixel-identical=True')
        image = render(engine, fixture('rowspan'))
        clean = render(engine, without_placeholder_text(fixture('rowspan')))
        assert image.data == clean.data
        separator = len(pixels(image, PURPLE, (45, 160, 195, 161)))
        ignored = len(pixels(image, (255, 0, 0), (40, 40, 200, 280)))
        assert separator == ignored == 0, (separator, ignored)
        assert len(pixels(image, PURPLE, (205, 160, 355, 161))) > 0
        print(f'rowSpan=2 + vMerge placeholder: divider y=160 x=45..194 border_pixels={separator}; ignored red fill pixels={ignored}; txBody vs empty placeholder pixel-identical=True')
        combined = [[cell(fill='EFEFEF', lines=borders(), attrs='gridSpan="2" rowSpan="2"'), cell(attrs='hMerge="1"')],
                    [cell(attrs='vMerge="1"'), cell(attrs='hMerge="1" vMerge="1"')]]
        image = render(engine, package(table(combined)))
        assert not pixels(image, PURPLE, (200, 45, 201, 275)) and not pixels(image, PURPLE, (45, 160, 355, 161))
        print('simultaneous gridSpan=2 rowSpan=2: both interior separators absent')
    elif group == 'anchor':
        image = render(engine, fixture('anchor'))
        boxes = [bounds(mask(image, box)) for box in ((40, 40, 200, 280), (200, 40, 360, 280))]
        delta = boxes[1][1] - boxes[0][1]
        assert delta > 240 / 2, (boxes, delta)
        print(f'anchor=t bbox={boxes[0]}, anchor=b bbox={boxes[1]}, vertical_delta={delta}px > row_height/2=120px')
        centered = render(engine, package(table([[cell('Anchor', props='anchor="ctr"')]], columns=(160,), heights=[240])))
        center_box = bounds(mask(centered))
        assert abs(center_box[1] - (boxes[0][1] + boxes[1][1]) / 2) <= 1, (center_box, boxes)
        print(f'anchor=ctr bbox={center_box}, top coordinate halfway between t/b within 1px')
    elif group == 'malformed':
        image = render(engine, fixture('malformed'), 'gridCol')
        assert image.pixel(100, 100) == COLORS[0] and image.pixel(280, 100) == COLORS[1]
        assert not pixels(image, COLORS[2])
        print('2 gridCol / 3 tc: status=0, first two fills correct, third fill pixels=0, warning present')
        image = render(engine, fixture('empty-row'), 'missing tc')
        assert image.pixel(100, 100) == (255, 255, 255) and image.pixel(100, 220) == COLORS[0]
        print('row without tc: blank at y=100, following row retained at y=220, warning present')
        image = render(engine, fixture('clipped'), 'span')
        assert image.pixel(350, 150) == COLORS[0] and image.pixel(365, 150) == (255, 255, 255)
        print('gridSpan=20 rowSpan=20 clamped to 2x1 grid: rightmost interior RGB correct, warning present')
        image = render(engine, fixture('empty-cell'))
        count = len(mask(image))
        assert count > 0
        print(f'neither tcPr nor txBody: empty frame dark_pixels={count}')
        image = render(engine, fixture('no-border'))
        assert not pixels(image, (0, 0, 0)) and not pixels(image, PURPLE)
        print('ln without solidFill and ln/noFill: border pixels=0')
        image = render(engine, package(table([[cell(fill=GEN['COLORS'][0])]])), 'gridCol')
        assert image.pixel(100, 100) == COLORS[0] and image.pixel(280, 100) == (255, 255, 255)
        print('2 gridCol / 1 tc: smaller count=1 drawn, second slot blank')
        image = render(engine, package(table([[cell(fill=GEN['COLORS'][0]), cell(fill=GEN['COLORS'][1])]],
                             attrs='firstRow="1" bandRow="1"',
                             table_props='<a:tableStyleId>{5C22544A-7EE6-4342-B048-85BDC9FD1C3A}</a:tableStyleId>')), 'tableStyleId')
        assert image.pixel(100, 100) == COLORS[0] and image.pixel(280, 100) == COLORS[1]
        print('tableStyleId/firstRow/bandRow parsed: direct fills retained, unapplied style warning present')
    elif group == 'margins':
        default = render(engine, package(table([[cell('A')]], columns=(320,))))
        custom = render(engine, package(table([[cell('A', props='marL="472440" marR="12700" marT="345440" marB="12700"')]], columns=(320,))))
        first, second = bounds(mask(default)), bounds(mask(custom))
        dx, dy = second[0] - first[0], second[1] - first[1]
        assert abs(dx - 30) <= 1 and abs(dy - 20) <= 1, (first, second)
        print(f'default margins=91440 EMU (7.2pt): bbox={first}; custom L=37.2pt T=27.2pt bbox={second}; delta=({dx},{dy})px')
        # tcPr governs table anchor and margins even when a:bodyPr supplies contrary values.
        contrary = render(engine, package(table([[cell('A', body_attrs='anchor="b" lIns="0" tIns="0"')]], columns=(320,))))
        assert contrary.data == default.data
        print('table tcPr defaults override bodyPr anchor/inset values: identical pixels')
        wrapped = []
        for props in ('', 'marR="2032000"'):
            image = render(engine, package(table([[cell('word ' * 16, props=props, size=18)]], columns=(320,), heights=[400])))
            wrapped.append((len(bands(image)), bounds(mask(image))))
        assert wrapped[1][0] > wrapped[0][0] and wrapped[1][1][2] <= 201, wrapped
        print(f'marR default vs 160pt: (line_count,bbox)={wrapped}; right inset constrains wrapping')
        bottom = []
        for props in ('anchor="b"', 'anchor="b" marB="472440"'):
            image = render(engine, package(table([[cell('A', props=props)]], columns=(320,), heights=[240])))
            bottom.append(bounds(mask(image)))
        delta = bottom[1][1] - bottom[0][1]
        assert abs(delta + 30) <= 1, bottom
        print(f'marB default vs 37.2pt at anchor=b: bbox={bottom}, vertical_delta={delta}px')
    elif group == 'overflow':
        image = render(engine, fixture('overflow'), 'auto')
        assert image.pixel(280, 60) == COLORS[1] and image.pixel(280, 75) == (255, 255, 255)
        outside = {(x, y) for x, y in mask(image) if len(set(image.pixel(x, y))) == 1
                   and not (40 <= x < 200 and 40 <= y < 70)}
        assert not outside, bounds(outside)
        print('30pt minimum row with overflowing text: fill ends at y=70px, row not grown, auto-height warning present; dark glyph pixels outside cell=0')
    elif group == 'transforms':
        original = table([[cell(fill=GEN['COLORS'][0]), cell(fill=GEN['COLORS'][1])]], columns=(100, 300))
        group_xml = ('<p:grpSp><p:nvGrpSpPr/><p:grpSpPr><a:xfrm><a:off x="1270000" y="1016000"/>'
                     '<a:ext cx="4572000" cy="3429000"/><a:chOff x="0" y="0"/>'
                     '<a:chExt cx="9144000" cy="6858000"/></a:xfrm></p:grpSpPr>' + original + '</p:grpSp>')
        image = render(engine, package(group_xml))
        assert image.pixel(140, 120) == COLORS[0] and image.pixel(250, 120) == COLORS[1]
        assert image.pixel(119, 120) == image.pixel(320, 120) == (255, 255, 255)
        print('nested graphicFrame scale=0.5, offset=(100,80): table x=[120,320), fill landmarks=(140,120)/(250,120) pass')
    elif group == 'limits':
        for label, xml in [('201 columns', table([[cell()] * 201], columns=[1] * 201)),
                           ('201 rows', table([[cell()]] * 201, columns=[1], heights=[1] * 201)),
                           ('201 tc', table([[cell()] * 201], columns=[1, 1]))]:
            data = package(xml)
            document, error = C.c_void_p(), Error()
            status = engine.lib.exr_fixed_open_memory(11, data, len(data), None, C.byref(document), C.byref(error))
            assert status == error.code == 6 and not document.value, (label, status, error.message)
            print(f'{label}: status={status} EXR_LIMIT message={error.message.decode()!r}')
        image = render(engine, package(table([[cell(fill=GEN['COLORS'][0])] * 200] * 200,
                                            columns=[1] * 200, heights=[1] * 200)))
        assert image.pixel(100, 100) == COLORS[0]
        print('exact 200x200 table: status=0, 40000 cells within limit, interior fill correct')
    elif group == 'sink':
        check_sink(engine)
    else:
        raise AssertionError(group)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library', type=Path, required=True)
    parser.add_argument('group', choices=GROUPS)
    args = parser.parse_args()
    run(Engine(args.library.resolve()), args.group)
