"""COM text oracles and bounded binary text corruption cases (stdlib only)."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")

from check_ppt import compound, record
from check_ppt_shapes import Pixels, document_header, shape, slide_record, prop_table
from check_ppt_fills import records, stream


def has_cjk_font():
    """Same host-font split as PPTX M4's has_cjk_font."""
    import glob, os, shutil
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


def mask(image, box=None, threshold=245, rgb=None):
    left, top, right, bottom = box or (0, 0, image.width, image.height)
    result = set()
    for y in range(max(0, int(top)), min(int(bottom), image.height)):
        row = image.data[y * image.width * 3:(y + 1) * image.width * 3]
        if not row.strip(b'\xff'):
            continue
        for x in range(max(0, int(left)), min(int(right), image.width)):
            pixel = row[x * 3:x * 3 + 3]
            if min(pixel) < threshold and (rgb is None or all(abs(a - b) <= 2 for a, b in zip(pixel, rgb))):
                result.add((x, y))
    return result


def bounds(pixels):
    assert pixels, "no glyph pixels"
    xs, ys = zip(*pixels)
    return min(xs), min(ys), max(xs) + 1, max(ys) + 1


def stats(image, box=None):
    pixels = mask(image, box)
    bbox = bounds(pixels)
    return dict(bbox=bbox, height=bbox[3] - bbox[1], pixels=len(pixels))


def normalized(pixels):
    left, top, _, _ = bounds(pixels)
    return {(x - left, y - top) for x, y in pixels}


def bands(image):
    result = []
    for y in sorted({y for _, y in mask(image)}):
        if not result or y > result[-1][-1] + 1:
            result.append([y])
        else:
            result[-1].append(y)
    return [(row[0], row[-1] + 1) for row in result]


def pf(count, *, alignment=0, spacing=None):
    flags, values = 0x800, struct.pack('<H', alignment)
    if spacing is not None:
        flags |= 0x1000
        values += struct.pack('<h', spacing)
    return struct.pack('<IHI', count, 0, flags) + values


def cf(count, *, size=18, font=0, color=0xFE000000, bold=False):
    return struct.pack('<IIHHHI', count, 0x70001, int(bold), font, size, color)


def text_ppt(text='Hello', *, style=None, bytes_text=False, fonts=('Arial',), color=0xFE000000,
             font=0, alignment=0, raw_text=None, size=18, scheme=None,
             environment_styles=b'', master_runs=None, outline=None):
    raw = raw_text if raw_text is not None else text.encode('latin-1' if bytes_text else 'utf-16le')
    count = len(raw) if bytes_text else len(raw) // 2
    body = record(0xF9F, struct.pack('<I', 4)) + record(0xFA8 if bytes_text else 0xFA0, raw)
    if style is not False:
        body += record(0xFA1, style if style is not None else pf(count + 1, alignment=alignment) + cf(count + 1, size=size, font=font, color=color))
    if master_runs is not None:
        body += record(0xFA2, master_runs)
    textbox = record(0xF00D, body if outline is None else record(0xF9E, struct.pack('<I', outline)), 15)
    margins = prop_table([(0x81, 127000), (0x82, 127000), (0x83, 127000), (0x84, 127000)])
    drawing = shape(box=(40, 40, 400, 300), fill=False, extra=margins + textbox)
    entities = b''.join(record(0xFB7, (name + '\0').encode('utf-16le').ljust(64, b'\0') + bytes(4) if name is not None else b'bad', instance=i)
                        for i, name in enumerate(fonts))
    environment = record(0x3F2, record(0x7D5, entities, 15) + environment_styles, 15)
    core = document_header(1)[8:]
    if outline is not None:
        persist = record(0x3F3, struct.pack('<IIIII', 1, 0, 0, 256, 0))
        core = record(0x3E9, struct.pack('<II', 5760, 4320) + bytes(32)) + record(0xFF0, persist + body, 15)
    header = record(0x3E8, core + environment, 15)
    slide = slide_record(drawing)
    if scheme is not None:
        slide = record(0x3EE, slide[8:] + record(0x7F0, struct.pack('<8I', *scheme), instance=1), 15)
    return compound(header + slide)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('probe', type=Path)
    parser.add_argument('fixtures', type=Path)
    parser.add_argument('group')
    args = parser.parse_args()
    manifest = json.loads((args.fixtures / 'manifest.json').read_text(encoding='utf-8'))
    fixtures = {item['case']: item for item in manifest['fixtures']}
    checks = 0
    with tempfile.TemporaryDirectory(prefix='exr-ppt-text-') as temp:
        source, output = Path(temp) / 'input.ppt', Path(temp) / 'output.ppm'

        def render(case=None, data=None, scale=1, warning=None, memory=False):
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
            if memory:
                command.append('memory')
            result = subprocess.run(command, capture_output=True, encoding='utf-8', check=True, timeout=30)
            values = dict(line.split('=', 1) for line in result.stdout.splitlines())
            assert values['status'] == '0', result.stdout
            if warning:
                assert 'warning' in values['message'].lower() and warning.lower() in values['message'].lower(), result.stdout
            image = Pixels(output)
            checks += 1
            if values['message']:
                print(f"status=0 message={values['message']}")
            return image, values['message']

        name = args.group
        if name == 'hello':
            for scale, memory in ((1, False), (2, True)):
                image, _ = render('hello', scale=scale, memory=memory)
                result = stats(image)
                center = (result['bbox'][0] + result['bbox'][2]) / 2
                delta = abs(center - 240 * scale)
                assert result['pixels'] > 0 and delta <= 2 * scale, result
                assert all(r == g == b for x, y in mask(image) for r, g, b in [image.at(x, y)])
                print(f'COM Hello 18pt black: scale={scale} {result} shape_center={240 * scale} glyph_center={center} delta={delta}px')
        elif name == 'sizes':
            values = [stats(render(f'size{size}', scale=4)[0]) for size in (12, 24, 48)]
            heights = [item['height'] for item in values]
            ratios = [height / heights[0] for height in heights]
            assert all(abs(actual / expected - 1) <= .1 for actual, expected in zip(ratios, (1, 2, 4))), ratios
            print(f'COM 12/24/48pt at 4px/pt: heights={heights}px ratios={ratios}')
        elif name == 'bold':
            values, widths = [], []
            for case in ('regular', 'bold'):
                image, _ = render(case, scale=4)
                value = stats(image)
                values.append(value)
                left, top, right, bottom = value['bbox']
                widths.append(sum(min(image.at(x, (top + bottom) // 2)) < 128 for x in range(left, right)) / 8)
            assert values[1]['pixels'] > values[0]['pixels'] * 1.1 and widths[1] > widths[0] * 1.1, (values, widths)
            print(f'COM b=0/b=1 48pt: mean_stem_width={widths}px ink_pixels={[value["pixels"] for value in values]}')
        elif name == 'cjk':
            image, message = render('cjk', scale=2)
            if not has_cjk_font():
                assert 'fallback' in message.lower(), message
                print('no CJK font on this host: fallback path + warning verified')
            else:
                value = stats(image)
                cells = [normalized(mask(image, (100 + index * 56, 0, 100 + (index + 1) * 56, image.height))) for index in range(4)]
                assert value['pixels'] > 100 and len({frozenset(cell) for cell in cells}) == 4
                assert not re.search(r'U\+[0-9A-Fa-f]+ missing\b', message), message
                print(f'COM SimHei index 中文测试: {value}; 4 distinct CJK silhouettes, cell_pixels={[len(cell) for cell in cells]}')
        elif name == 'alignment':
            boxes = [stats(render('align-' + align)[0])['bbox'] for align in ('l', 'ctr', 'r')]
            assert boxes[0][0] < boxes[1][0] < boxes[2][0], boxes
            assert abs((boxes[1][0] + boxes[1][2]) / 2 - 240) <= 2 and abs(boxes[2][2] - 430) <= 2, boxes
            print(f'COM l/ctr/r bbox_left={[box[0] for box in boxes]}px bboxes={boxes}')
        elif name == 'bullets':
            image, _ = render('bullets', scale=4)
            reference, _ = render('dot', scale=4)
            expected = normalized(mask(reference))
            rows = bands(image)
            assert len(rows) == 3, rows
            scores = []
            for top, bottom in rows:
                actual = normalized(mask(image, (0, top, 300, bottom)))
                score = max(len(actual & {(x + dx, y + dy) for x, y in expected}) /
                            len(actual | {(x + dx, y + dy) for x, y in expected})
                            for dx in (-1, 0, 1) for dy in (-1, 0, 1))
                assert score >= .9, score
                scores.append(round(score, 6))
            print(f'COM three bullet dots vs independent literal dot: mask_IoU={scores} rows={rows}')
        elif name == 'malformed':
            for count in (1000, 0):
                image, message = render(data=text_ppt(style=pf(count) + cf(6, size=24, color=0xFE0000FF, bold=True)), warning='run')
                assert mask(image)
                if count == 1000:
                    clipped = image
                print(f'PF count={count}, text_length=5: status=0 ink_pixels={len(mask(image))} warning={message}')
            image, _ = render(data=text_ppt(style=pf(6) + cf(1000)), warning='run')
            assert mask(image)
            short, _ = render(data=text_ppt(style=pf(6) + cf(3, size=24, color=0xFE0000FF, bold=True)), warning='run')
            full, _ = render(data=text_ppt(style=pf(6) + cf(6, size=24, color=0xFE0000FF, bold=True)))
            assert short.data == full.data
            assert clipped.data == full.data
            print('PF count1000 clipped to target6 while retaining red/bold/24pt CF properties: exact complete-reference raster match')
            print('CF sum=3 vs target=6: missing tail inherits final red/bold/24pt run, exact complete-reference raster match')
            for payload in (b'\x01', pf(6) + b'\x00', pf(6) + struct.pack('<II', 6, 0x70000)):
                image, _ = render(data=text_ppt(style=payload), warning='text')
                assert mask(image)
            print('short PF/CF properties recover with visible text; no crash')
            expected, _ = render(data=text_ppt())
            reserved_pf = pf(6)[:6] + struct.pack('<I', 0xA00) + pf(6)[10:]
            reserved_cf = struct.pack('<IIHHI', 6, 0x70008, 0, 18, 0xFE000000)
            for style in (reserved_pf + cf(6), pf(6) + reserved_cf):
                actual, _ = render(data=text_ppt(style=style))
                assert actual.data == expected.data
            print('PF reserved bit9 / CF reserved bit3 independently set: no phantom field consumed, exact clean-reference rasters')
        elif name == 'unicode':
            clean, _ = render(data=text_ppt('A\ufffdB'))
            broken, _ = render(data=text_ppt(raw_text=b'A\x00\x00\xd8B\x00'), warning='surrogate')
            assert clean.data == broken.data
            print('isolated high surrogate -> U+FFFD: exact clean-reference raster match')
            broken, _ = render(data=text_ppt(raw_text=b'A\x00\x00\xdcB\x00'), warning='surrogate')
            assert clean.data == broken.data
            valid, message = render(data=text_ppt('A\U0001f600B'))
            assert 'surrogate' not in message.lower() and mask(valid)
            print('isolated low surrogate -> U+FFFD; valid surrogate pair accepted')
        elif name == 'bytes':
            latin, _ = render(data=text_ppt('Héllo', bytes_text=True), warning='latin')
            unicode, _ = render(data=text_ppt('Héllo'))
            assert latin.data == unicode.data
            print('TextBytesAtom Latin-1 é vs TextCharsAtom Unicode: exact raster match + warning')
        elif name == 'indices':
            raw = stream(args.fixtures / fixtures['hello']['file'])
            collection = next(payload for kind, _, payload, parents in records(raw) if kind == 0x7D5 and 0x3E8 in parents)
            fonts = dict(enumerate(payload[:64].decode('utf-16le').split('\0', 1)[0]
                                   for kind, _, payload, _ in records(collection) if kind == 0xFB7))
            assert fonts[1] == 'Arial' and fonts[3] == 'SimHei', fonts
            print(f'COM FontEntityAtom array table={fonts}; slide CF latin=1, EA=3, ANSI=1')
            raw = stream(args.fixtures / fixtures['scheme']['file'])
            palette = next(payload for kind, index, payload, parents in records(raw) if kind == 0x7F0 and index == 1)
            colors = [tuple(palette[index * 4:index * 4 + 3]) for index in range(8)]
            print(f'COM ColorSchemeAtom slots={dict(enumerate(colors))}; text direct COLORINDEX=0xFE22170C -> RGB(12,23,34)')
            image, _ = render('scheme')
            assert mask(image, rgb=(12, 23, 34))
            palette = [red | green << 8 | blue << 16 for red, green, blue in colors]
            for slot, color in enumerate(palette):
                indexed, _ = render(data=text_ppt(color=slot << 24, scheme=palette))
                direct, _ = render(data=text_ppt(color=0xFE000000 | color))
                assert indexed.data == direct.data, slot
                print(f'COLORINDEX high byte {slot} -> scheme[{slot}] RGB{colors[slot]}: exact direct-color raster match')
            image, _ = render(data=text_ppt(font=65535), warning='font')
            assert mask(image)
            image, _ = render(data=text_ppt(fonts=()), warning='font')
            assert mask(image)
            damaged, _ = render(data=text_ppt(fonts=(None, 'Arial'), font=1), warning='text')
            explicit, _ = render(data=text_ppt())
            assert damaged.data == explicit.data
            print('damaged FontEntity[0] preserves its slot: valid Arial index1 equals explicit Arial raster')
            image, _ = render(data=text_ppt(color=0x08000000), warning='color')
            assert mask(image, rgb=(0, 0, 0))
            print('fontIndex=65535 -> default font; colorIndex=8 -> black; both status=0 + warning')
        elif name == 'wrap':
            image, _ = render('wrap')
            rows = bands(image)
            widths = [stats(image, (0, top, image.width, bottom))['bbox'][2] - stats(image, (0, top, image.width, bottom))['bbox'][0] for top, bottom in rows]
            assert len(rows) > 1 and max(widths) <= 182, (rows, widths)
            print(f'COM wrap: lines={len(rows)} widths={widths}px <= inner_width=180pt')
        elif name == 'spacing':
            image, _ = render('spacing')
            rows = bands(image)
            assert len(rows) == 3, rows
            gaps = [rows[i + 1][0] - rows[i][0] for i in range(2)]
            assert all(abs(gap - 52) <= 2 for gap in gaps), (rows, gaps)
            print(f'COM exact lineSpacing=40pt + spaceAfter=12pt: visible-line gaps={gaps}px')
        elif name == 'runs':
            image, _ = render('runs', scale=2)
            colors = ((255, 0, 0), (0, 170, 0), (0, 0, 255))
            boxes = [bounds(mask(image, rgb=color)) for color in colors]
            assert boxes[0][0] < boxes[1][0] < boxes[2][0], boxes
            assert boxes[2][3] - boxes[2][1] > boxes[0][3] - boxes[0][1], boxes
            print(f'COM CF mixed runs Red/Green/Blue: RGB={colors}, bboxes={boxes}')
        elif name == 'master':
            levels = struct.pack('<H', 2) + b''.join(pf(0)[6:] + cf(0, size=size)[4:] for size in (28, 24))
            environment = record(0xFA3, levels, instance=4)
            for level, size in ((0, 28), (1, 24)):
                actual, _ = render(data=text_ppt(style=False, environment_styles=environment,
                    master_runs=struct.pack('<IH', 6, level)), scale=2)
                explicit, _ = render(data=text_ppt(size=size), scale=2)
                assert actual.data == explicit.data, (level, stats(actual), stats(explicit))
                print(f'Environment Other MasterTextProp level{level} -> {size}pt: exact explicit-style raster match')
        elif name == 'outline':
            for text, size in (('Hello', 24), ('中文测试', 28)):
                actual, _ = render(data=text_ppt(text, size=size, outline=0), scale=2)
                inline, _ = render(data=text_ppt(text, size=size), scale=2)
                assert actual.data == inline.data
                assert mask(actual)
                print(f'OutlineTextRef index0 -> SlideListWithText {text!r}/{size}pt: exact inline-text raster match')
        else:
            raise ValueError(name)
    print(f'native-ppt-text-{name}: {checks} checks passed')


if __name__ == '__main__':
    main()
