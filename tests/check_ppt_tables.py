"""PowerPoint COM table oracles and independent bounded binary corruptions."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile

from check_ppt import compound, record, OK, LIMIT
from check_ppt_fills import stream
from check_ppt_shapes import Pixels, document_header, prop_table, shape, slide_record
from check_ppt_text import bounds, cf, has_cjk_font, pf

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

COLORS = [(17, 34, 51), (68, 85, 102), (119, 136, 153), (170, 187, 204)]
BORDER = (160, 64, 32)
BOXES = [(60, 80, 240, 170), (240, 80, 420, 170),
         (60, 170, 240, 260), (240, 170, 420, 260)]


def records(data, at=0, end=None):
    end = len(data) if end is None else end
    while at < end:
        assert end - at >= 8
        header, kind, length = struct.unpack_from('<HHI', data, at)
        payload, next_at = at + 8, at + 8 + length
        assert next_at <= end
        yield at, header, kind, payload, next_at
        at = next_at


def table_groups(data, at=0, end=None):
    """Find the marker in a group header, independently of the C parser."""
    for entry in records(data, at, end):
        _, header, kind, payload, next_at = entry
        if kind == 0xF003:
            first = next(records(data, payload, next_at))
            for _, packed, rec_type, start, stop in records(data, first[3], first[4]):
                if rec_type in (0xF00B, 0xF121, 0xF122):
                    props = [struct.unpack_from('<HI', data, start + i * 6) for i in range(packed >> 4)]
                    if any(pid & 0x3FFF == 0x39F and value & 1 for pid, value in props):
                        yield entry
        if header & 15 == 15:
            yield from table_groups(data, payload, next_at)


def textbox(text='A', *, index=None, cjk=False, color=0xFE000000):
    if index is not None:
        content = record(0xF9E, struct.pack('<I', index))
    else:
        content = record(0xF9F, struct.pack('<I', 4)) + record(0xFA0, text.encode('utf-16le'))
        style = pf(len(text) + 1) + cf(len(text) + 1, size=24, color=color)
        if cjk:
            style = pf(len(text) + 1) + struct.pack('<IIHHHHI', len(text) + 1, 0x270001, 0, 0, 1, 24, 0xFE000000)
        content += record(0xFA1, style)
    return record(0xF00D, content, 15)


def cells(*, extra=b'', count=4):
    return b''.join(shape(rgb=COLORS[i], box=((i % 2) * 180, (i // 2) * 90, 180, 90),
                         child=True, extra=extra if i == 0 else b'') for i in range(count))


def table(children, *, declared_rows=2, row_values=None, rows=True, extent=(2880,1440)):
    if row_values is None:
        row_values = [720] * declared_rows
    props = [(0x39F, 1)]
    row_array = struct.pack('<HHH', declared_rows, declared_rows, 4)
    row_array += b''.join(struct.pack('<I', value) for value in row_values)
    if rows:
        props.append((0xC3A0, len(row_array)))
    options = record(0xF122, b''.join(struct.pack('<HI', *item) for item in props) + (row_array if rows else b''),
                     3, len(props))
    header = record(0xF009, struct.pack('<iiii', 0, 0, *extent), 1)
    header += record(0xF00A, struct.pack('<II', 1024, 0x201), 2)
    header += options + record(0xF010, struct.pack('<hhhh', 640, 480, 3360, 2080))
    return record(0xF003, record(0xF004, header, 15) + children, 15)


def presentation(drawing, *, outline=b''):
    environment = record(0x3F2, record(0x7D5, b''.join(
        record(0xFB7, (name + '\0').encode('utf-16le').ljust(64, b'\0') + bytes(4), instance=i)
        for i, name in enumerate(('Arial', 'SimHei'))), 15), 15)
    header = document_header(1)[8:]
    if outline:
        persist = record(0x3F3, struct.pack('<IIIII', 1, 0, 0, 256, 0))
        header = record(0x3E9, struct.pack('<II', 5760, 4320) + bytes(32)) + record(0xFF0, persist + outline, 15)
    return compound(record(0x3E8, header + environment, 15) + slide_record(drawing))


def color_pixels(image, color, box):
    left, top, right, bottom = map(int, box)
    return {(x, y) for y in range(max(0, top), min(image.height, bottom))
            for x in range(max(0, left), min(image.width, right))
            if all(abs(a - b) <= 2 for a, b in zip(image.at(x, y), color))}


def changed_pixels(image, color, box):
    left, top, right, bottom = map(int, box)
    return {(x, y) for y in range(top, bottom) for x in range(left, right)
            if max(abs(a - b) for a, b in zip(image.at(x, y), color)) > 5}


def font_warnings_only(message):
    """Font names and fallback glyph coverage are properties of the host."""
    if not message:
        return
    remaining = re.sub(r'^PPT warning: *', '', message)
    remaining = re.sub(r'(?:font fallback=[^;]*|glyph [^;]*); *', '', remaining)
    assert not remaining.strip(), message


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('probe', type=Path)
    parser.add_argument('fixtures', type=Path)
    parser.add_argument('group')
    args = parser.parse_args()
    manifest = json.loads((args.fixtures / 'manifest.json').read_text(encoding='utf-8-sig'))
    fixtures = {item['case']: item for item in manifest['fixtures']}
    checks = 0
    with tempfile.TemporaryDirectory(prefix='exr-ppt-table-') as directory:
        source, output = Path(directory) / 'input.ppt', Path(directory) / 'output.ppm'

        def render(case=None, *, data=None, scale=1, status=OK, warning=None, memory=False, metadata=False, timeout=30):
            nonlocal checks
            if case:
                entry = fixtures[case]
                path = args.fixtures / entry['file']
                assert hashlib.sha256(path.read_bytes()).hexdigest() == entry['sha256']
            else:
                source.write_bytes(data)
                path = source
            output.unlink(missing_ok=True)
            command = [str(args.probe.resolve()), str(path), str(output), '0', str(scale)]
            if metadata:
                command.append('tables')
            elif memory:
                command.append('memory')
            result = subprocess.run(command, capture_output=True, encoding='utf-8', check=True, timeout=timeout)
            values = dict(line.split('=', 1) for line in result.stdout.splitlines())
            assert int(values['status']) == status, result.stdout
            if warning:
                assert 'warning' in values['message'].lower() and warning in values['message'], result.stdout
            elif status == OK:
                font_warnings_only(values['message'])
            checks += 1
            if status != OK or values['message']:
                print(f"status={values['status']} message={values['message']}")
            return Pixels(output) if status == OK else None, values

        name = args.group
        if name == 'fills':
            for scale in (1, 2):
                image, _ = render('plain', scale=scale, memory=scale == 2)
                actual = []
                for (left, top, right, bottom), color in zip(BOXES, COLORS):
                    point = ((left + right) // 2 * scale, (bottom - 15) * scale)
                    actual.append(image.check(point, color))
                    box = ((left + 15) * scale, (top + 40) * scale, (right - 15) * scale, (bottom - 15) * scale)
                    pixels = color_pixels(image, color, box)
                    assert len(pixels) == (box[2] - box[0]) * (box[3] - box[1]), (color, len(pixels))
                print(f'scale={scale} fill_rgb={actual} maximum_error=0')
        elif name == 'borders':
            for scale in (1, 2):
                image, values = render('plain', scale=scale)
                vertical = color_pixels(image, BORDER, (235 * scale, 100 * scale, 246 * scale, 150 * scale))
                horizontal = color_pixels(image, BORDER, (100 * scale, 165 * scale, 180 * scale, 176 * scale))
                width_x = sum(all(abs(a - b) <= 2 for a, b in zip(image.at(x, 110 * scale), BORDER))
                              for x in range(235 * scale, 246 * scale))
                width_y = sum(all(abs(a - b) <= 2 for a, b in zip(image.at(100 * scale, y), BORDER))
                              for y in range(165 * scale, 176 * scale))
                widths = [float(value) for key, value in values.items() if key.startswith('draw_') and key.endswith('_width')
                          and values[key[:-5] + 'stroke'] == 'a04020ff']
                assert vertical and horizontal and widths and all(value == 3 for value in widths), widths
                assert abs(width_x - 3 * scale) <= 1 and abs(width_y - 3 * scale) <= 1, (width_x, width_y)
                print(f'scale={scale} border_pixels=({len(vertical)},{len(horizontal)}) record_w=38100 '
                      f'width_pt={widths[0]} measured_px=({width_x},{width_y}) expected_px={3 * scale}')
        elif name == 'text':
            for scale in (1, 2):
                image, _ = render('plain', scale=scale)
                for index, letter in ((0, 'A'), (3, 'B')):
                    left, top, right, bottom = BOXES[index]
                    interior = ((left + 4) * scale, (top + 4) * scale, (right - 4) * scale, (bottom - 4) * scale)
                    glyphs = changed_pixels(image, COLORS[index], interior)
                    bbox = bounds(glyphs)
                    assert glyphs and left * scale <= bbox[0] < bbox[2] <= right * scale
                    assert top * scale <= bbox[1] < bbox[3] <= bottom * scale
                    print(f'scale={scale} cell={index} text={letter} glyph_pixels={len(glyphs)} bbox={bbox}')
                for index in (1, 2):
                    left, top, right, bottom = BOXES[index]
                    assert not changed_pixels(image, COLORS[index], ((left+4)*scale, (top+4)*scale, (right-4)*scale, (bottom-4)*scale))
            image, _ = render(data=presentation(table(cells(extra=textbox('MW' * 200, color=0xFE00FF00)))))
            all_green = color_pixels(image, (0,255,0), (0,0,image.width,image.height))
            inside = color_pixels(image, (0,255,0), BOXES[0])
            assert inside and all_green == inside
            print(f'overflow_text_inside_pixels={len(inside)} outside_cell_pixels={len(all_green-inside)}')
        elif name == 'merge':
            for scale in (1, 2):
                image, _ = render('merge', scale=scale)
                divider = color_pixels(image, BORDER, (235*scale, 85*scale, 246*scale, 165*scale))
                bottom = color_pixels(image, BORDER, (235*scale, 180*scale, 246*scale, 250*scale))
                assert not divider and bottom
                image.check((330*scale, 130*scale), COLORS[0])
                print(f'scale={scale} merged_row_divider_pixels={len(divider)} unmerged_row_divider_pixels={len(bottom)}')
            # An expanded first cell is the merge start; the stale covered cell
            # and stale internal border must not overwrite it.
            start = shape(rgb=COLORS[0], box=(0, 0, 360, 90), child=True)
            stale = shape(rgb=(255, 0, 0), box=(180, 0, 180, 90), child=True)
            line = shape(rgb=BORDER, box=(180, 0, 0, 90), child=True, kind=20, line=True, fill=False)
            bottom = b''.join(shape(rgb=COLORS[i], box=((i%2)*180,90,180,90), child=True) for i in (2,3))
            image, _ = render(data=presentation(table(start + stale + bottom + line)), warning='table-merge')
            image.check((330,130), COLORS[0])
            assert not color_pixels(image, BORDER, (235,85,246,165))
            assert not color_pixels(image, (255,0,0), (65,85,415,165))
            print('contradictory_overlap=first-start-wins covered_fill_pixels=0 stale_divider_pixels=0')
        elif name == 'malformed':
            for declared, values in ((3, [720,720]), (1, [720]), (2, [720]), (0, []), (2, [0,0])):
                image, _ = render(data=presentation(table(cells(), declared_rows=declared, row_values=values)), warning='table-malformed')
                for (left, top, right, bottom), color in zip(BOXES,COLORS):
                    image.check(((left+right)//2,bottom-15),color)
                print(f'declared_rows={declared} row_elements={len(values)} recovered_rectangle=2x2 status=0')
            drawing = bytearray(table(cells()))
            offset = drawing.index(struct.pack('<HI',0xC3A0,14))
            struct.pack_into('<I',drawing,offset+2,65535)
            image, _ = render(data=presentation(drawing),warning='table-malformed')
            for (left,top,right,bottom),color in zip(BOXES,COLORS):
                image.check(((left+right)//2,bottom-15),color)
            print('row_property_declared_bytes=65535 available_bytes=14 recovered_rectangle=2x2 status=0')
            final = shape(rgb=COLORS[3],box=(180,90,180,90),child=True)[:-7]
            image, _ = render(data=presentation(table(cells(count=3)+final)),warning='malformed')
            for (left,top,right,bottom),color in zip(BOXES[:3],COLORS[:3]):
                image.check(((left+right)//2,bottom-15),color)
            image.check((330,245),(255,255,255))
            print('truncated_final_cell status=0 readable_cells=3 missing_cell_rgb=(255,255,255)')
        elif name == 'missing':
            for drawing in (table(b''), table(b'',rows=False)):
                image, _ = render(data=presentation(drawing), warning='table-missing')
                assert image.at(240,170) == (255,255,255)
                assert any(min(image.at(x,y)) < 245 for y in range(77,84) for x in range(60,420))
                print('missing_table_records status=0 empty_frame_pixels>0 interior_rgb=(255,255,255)')
            image, _ = render(data=presentation(table(cells(),rows=False)), warning='table-missing')
            for (left,top,right,bottom),color in zip(BOXES,COLORS):
                image.check(((left+right)//2,bottom-15),color)
            print('missing_row_metadata status=0 recovered_rectangle=2x2')
        elif name == 'indices':
            image, _ = render(data=presentation(table(cells(extra=textbox(index=999)))), warning='text-index')
            assert not changed_pixels(image,COLORS[0],(65,85,235,165))
            print('out_of_range_text_index=999 status=0 empty_cell_text_pixels=0')
            body = record(0xF9F,struct.pack('<I',4)) + record(0xFA0,'A'.encode('utf-16le'))
            body += record(0xFA1,pf(2)+cf(2,size=24,color=0xFE000000))
            inline, _ = render(data=presentation(table(cells(extra=textbox('A')))))
            indexed, _ = render(data=presentation(table(cells(extra=textbox(index=0))),outline=body))
            assert inline.data == indexed.data
            print('valid_outline_index=0 inline_indexed_pixels_identical=true')
        elif name == 'limits':
            render(data=presentation(table(b'',declared_rows=201)), status=LIMIT)
            narrow = b''.join(shape(box=(i,0,1,180), child=True) for i in range(201))
            render(data=presentation(table(narrow,declared_rows=1,row_values=[1440])),status=LIMIT)
            print('row_limit=201 status=6; column_limit=201 status=6')
            # Local integer cell coordinates avoid roundoff gaps, and exercise
            # the entire legal table budget past M2's 5000 generic-shape cap.
            maximum = b''.join(shape(box=(column/8,row/8,1/8,1/8), child=True)
                               for row in range(200) for column in range(200))
            _, values = render(data=presentation(table(maximum,declared_rows=200,row_values=[1]*200,extent=(200,200))),
                               metadata=True,timeout=120)
            assert (values['table_0_rows'],values['table_0_columns'],values['table_0_cells'])==('200','200','40000')
            print('maximum_legal_grid=200x200 cells=40000 status=0 generic_shape_limit_bypassed=true')
        elif name == 'cjk':
            image, values = render(data=presentation(table(cells(extra=textbox('中文测试',cjk=True)))))
            pixels = changed_pixels(image,COLORS[0],(65,85,235,165))
            assert pixels
            if not has_cjk_font():
                assert 'glyph ' in values['message'] and ('missing' in values['message'] or 'fallback' in values['message'])
            print(f'host_cjk={has_cjk_font()} glyph_pixels={len(pixels)} bbox={bounds(pixels)}')
        elif name == 'structure':
            for case, rectangle_count in (('plain',4),('merge',3)):
                data = stream(args.fixtures / fixtures[case]['file'])
                groups = list(table_groups(data))
                assert len(groups) == 1
                _,_,_,start,stop=groups[0]
                members=list(records(data,start,stop))
                kinds=[]
                for _,_,_,a,b in members[1:]:
                    for _,packed,kind,p,e in records(data,a,b):
                        if kind==0xF00A:kinds.append(packed>>4)
                assert kinds.count(1)==rectangle_count and kinds.count(20)>0,kinds
                print(f'{case}: recType=F003 marker=F122/039F=1 rows=C3A0 rectangles={rectangle_count} border_lines={kinds.count(20)}')
                _, values = render(case, metadata=True)
                assert values['table_count']=='1' and values['table_0_rows']=='2' and values['table_0_columns']=='2', values
                assert values['table_0_cells']==str(rectangle_count) and values['table_0_merged']==str(case=='merge' and 1 or 0), values
                assert values['table_0_shape_0_text']=='A'
                assert values[f'table_0_shape_{rectangle_count-1}_text']=='B'
                assert values['table_0_shape_0_bounds']==('60,80,420,170' if case=='merge' else '60,80,240,170')
                print(f"{case}: parsed_rows={values['table_0_rows']} parsed_columns={values['table_0_columns']} "
                      f"cells={values['table_0_cells']} merged={values['table_0_merged']} text=A/B anchor={values['table_0_shape_0_bounds']}")
            spanning = shape(box=(0,0,360,180), child=True)
            _, values = render(data=presentation(table(spanning,declared_rows=200,row_values=[1]*200)),metadata=True)
            assert (values['table_0_rows'],values['table_0_columns'],values['table_0_cells'],values['table_0_merged'])==('200','1','1','1')
            print('fully_merged_rows=200 columns=1 cells=1 merged=1 status=0')
        else:
            raise AssertionError(name)
    print(f'native-ppt-table-{name}: {checks} native opens/renders passed')


if __name__ == '__main__':
    main()
