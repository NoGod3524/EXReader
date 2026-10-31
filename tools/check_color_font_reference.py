#!/usr/bin/env python3
"""Compare EXReader colour-font output with a fixed Chrome/Skia reference.

The reference renders COLR v1 through the browser's text stack and OT-SVG
through the browser's SVG stack. Both sides are cropped to their content
bounding box, aligned with a small shift search, and compared on flat interior
pixels so antialiasing differences are reported separately.
"""
# SPDX-License-Identifier: MIT
import argparse
import base64
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[1]
FONTS = ROOT / 'tests/fixtures/fonts'
CHROME = Path(r'C:/Users/Oscar/.cache/puppeteer/chrome/win64-152.0.7977.42/chrome-win64/chrome.exe')
CELL = 320
COLS = 6
# The grid's text layer clips the left overhang of this shear; capture it alone.
SINGLE_PAGE = {'skew'}
SIZE = 100
FLAT_TOLERANCE = 16
MEAN_TOLERANCE = 4.0
BBOX_TOLERANCE = 3


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def glyph_names(path):
    font = TTFont(path)
    order = font.getGlyphOrder()
    cmap = font.getBestCmap() or {}
    by_name = {name: cp for cp, name in cmap.items()}
    return order, by_name


def colrv1_scenes():
    order, by_name = glyph_names(FONTS / 'colrv1.ttf')
    skip = {'composite_src', 'composite_clear', 'cycle', 'palette_oob', 'deep', 'many',
            'many_stops', 'missing_colr_glyph', 'bad_clipbox', 'outline_only'}
    scenes = []
    for name in order[7:]:
        if name in skip or name not in by_name:
            continue
        scenes.append({'name': name, 'glyph': order.index(name), 'char': chr(by_name[name])})
    return scenes


def svg_scenes():
    order, by_name = glyph_names(FONTS / 'svgfont.ttf')
    font = TTFont(FONTS / 'svgfont.ttf')
    docs = {}
    for record in font['SVG '].docList:
        for gid in range(record.startGlyphID, record.endGlyphID + 1):
            docs[gid] = record.data
    scenes = []
    for gid, data in sorted(docs.items()):
        name = order[gid]
        if name.startswith('bad_') or gid < 2:
            continue
        scenes.append({'name': name, 'glyph': gid, 'doc': data})
    return scenes


def svg_reference_doc(scene, upem):
    """Return an SVG document that renders only this glyph with the same
    user-to-device scale as the OT-SVG mapping."""
    data = scene['doc']
    start = data.index('<svg')
    end = data.index('>', start) + 1
    root = data[start:end]
    inner = data[end:data.rindex('</svg>')]
    attrs = []
    for name in ('viewBox', 'preserveAspectRatio'):
        key = name + '="'
        if key in root:
            begin = root.index(key)
            finish = root.index('"', begin + len(key))
            attrs.append(root[begin:finish + 1])
    if not any(a.startswith('viewBox') for a in attrs):
        attrs.append(f'viewBox="0 {-upem} {upem} {upem}"')
    marker = f'id="glyph{scene["glyph"]}"'
    if marker in data:
        return '<svg xmlns="http://www.w3.org/2000/svg" ' + ' '.join(attrs) + \
            '><defs>' + inner + '</defs><use href="#glyph' + str(scene['glyph']) + '"/></svg>'
    return '<svg xmlns="http://www.w3.org/2000/svg" ' + ' '.join(attrs) + '>' + inner + '</svg>'


def render_pages(scenes, kind, work):
    font_path = FONTS / ('colrv1.ttf' if kind == 'colrv1' else 'svgfont.ttf')
    encoded = base64.b64encode(font_path.read_bytes()).decode()
    cols = COLS
    rows = (len(scenes) + cols - 1) // cols
    width = cols * CELL
    height = rows * CELL
    parts = []
    if kind == 'colrv1':
        parts.append('<style>@font-face{font-family:cf;src:url(data:font/ttf;base64,' + encoded +
                     ') format("truetype");}html,body{margin:0;background:#fff;}' +
                     '.t{position:absolute;font-family:cf;font-size:' + str(SIZE) +
                     'px;line-height:' + str(SIZE) + 'px;color:#000;}</style>')
    else:
        parts.append('<style>html,body{margin:0;background:#fff;}</style>')
    for index, scene in enumerate(scenes):
        x = (index % cols) * CELL
        y = (index // cols) * CELL
        if kind == 'colrv1':
            parts.append(f'<div class="t" style="left:{x + CELL // 2}px;top:{y + CELL - 60 - 90}px">'
                         f'{scene["char"]}</div>')
        else:
            doc = svg_reference_doc(scene, 1000)
            encoded_doc = base64.b64encode(doc.encode('utf-8')).decode()
            parts.append(f'<img style="position:absolute;left:{x + CELL // 2}px;top:{y + CELL // 2 - SIZE}px;'
                         f'width:{SIZE}px;height:{SIZE}px" '
                         f'src="data:image/svg+xml;base64,{encoded_doc}">')
    html = '<!doctype html><html><head><meta charset="utf-8"></head><body>' + ''.join(parts) + '</body></html>'
    page = work / f'reference-{kind}.html'
    page.write_text(html, encoding='utf-8')
    shot = work / f'reference-{kind}.png'
    chrome = str(CHROME)
    subprocess.run([chrome, '--headless=new', '--disable-gpu', '--hide-scrollbars',
                    '--force-device-scale-factor=1', '--virtual-time-budget=3000',
                    f'--window-size={width},{height}',
                    f'--screenshot={shot}', page.as_uri()],
                   check=True, capture_output=True, timeout=180)
    return Image.open(shot).convert('RGB')


def render_single(scene, kind, work):
    font_path = FONTS / ('colrv1.ttf' if kind == 'colrv1' else 'svgfont.ttf')
    if kind == 'colrv1':
        encoded = base64.b64encode(font_path.read_bytes()).decode()
        body = ('<style>@font-face{font-family:cf;src:url(data:font/ttf;base64,' + encoded +
                ') format("truetype");}html,body{margin:0;background:#fff}'
                '.t{position:absolute;font-family:cf;font-size:' + str(SIZE) +
                'px;line-height:' + str(SIZE) + 'px;color:#000;}</style>'
                f'<div class="t" style="left:{CELL // 2}px;top:{CELL - 60 - 90}px">{scene["char"]}</div>')
    else:
        doc = svg_reference_doc(scene, 1000)
        encoded_doc = base64.b64encode(doc.encode('utf-8')).decode()
        body = ('<style>html,body{margin:0;background:#fff}</style>'
                f'<img style="position:absolute;left:{CELL // 2}px;top:{CELL // 2 - SIZE}px;'
                f'width:{SIZE}px;height:{SIZE}px" src="data:image/svg+xml;base64,{encoded_doc}">')
    html = '<!doctype html><html><head><meta charset="utf-8"></head><body>' + body + '</body></html>'
    page = work / f'single-{scene["name"]}.html'
    page.write_text(html, encoding='utf-8')
    shot = work / f'single-{scene["name"]}.png'
    subprocess.run([str(CHROME), '--headless=new', '--disable-gpu', '--hide-scrollbars',
                    '--force-device-scale-factor=1', '--virtual-time-budget=3000',
                    f'--window-size={CELL},{CELL}', f'--screenshot={shot}', page.as_uri()],
                   check=True, capture_output=True, timeout=180)
    return Image.open(shot).convert('RGB')


def mask(image):
    return ImageChops.difference(image, Image.new('RGB', image.size, 'white')).convert('L').point(lambda v: 255 if v > 8 else 0)


def bbox(image):
    return mask(image).getbbox()


def crop_content(image):
    box = bbox(image)
    if not box:
        return None
    return image.crop(box)


def flat_mask(image):
    """Pixels whose 3x3 neighbourhood is uniform in this image."""
    px = image.load()
    w, h = image.size
    out = Image.new('L', (w, h), 0)
    dst = out.load()
    for y in range(1, h - 1):
        for x in range(1, w - 1):
            r, g, b = px[x, y]
            ok = True
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    q = px[x + dx, y + dy]
                    if abs(q[0] - r) > 2 or abs(q[1] - g) > 2 or abs(q[2] - b) > 2:
                        ok = False
                        break
                if not ok:
                    break
            if ok:
                dst[x, y] = 255
    return out


def interior_mask(covered):
    # Cropping touches the content boundary. MinFilter extends edge pixels,
    # so provide the actual empty exterior before the fixed 3px erosion.
    padded = Image.new('L', (covered.width + 6, covered.height + 6), 0)
    padded.paste(covered, (3, 3))
    return padded.filter(ImageFilter.MinFilter(7)).crop((3, 3, covered.width + 3, covered.height + 3))


def compare(ours, ref):
    a = crop_content(ours)
    b = crop_content(ref)
    if a is None or b is None:
        return {'ok': False, 'reason': 'empty content', 'ours_empty': a is None, 'reference_empty': b is None}
    if abs(a.width - b.width) > BBOX_TOLERANCE or abs(a.height - b.height) > BBOX_TOLERANCE:
        return {'ok': False, 'reason': 'bbox size differs', 'ours': [a.width, a.height], 'reference': [b.width, b.height]}
    best = None
    fa = flat_mask(a)
    fb = flat_mask(b)
    for dy in range(-2, 3):
        for dx in range(-2, 3):
            shifted = Image.new('RGB', a.size, 'white')
            shifted.paste(b, (dx, dy))
            mask_shifted = Image.new('L', a.size, 0)
            mask_shifted.paste(fb, (dx, dy))
            flat = ImageChops.multiply(fa, mask_shifted)
            # Interior mask: content in both images, eroded by three pixels.
            covered = ImageChops.multiply(mask(a), mask(shifted))
            interior = interior_mask(covered)
            total = sum(1 for v in interior.getdata() if v)
            if not total:
                continue
            diff = ImageChops.difference(a, shifted).convert('L')
            values = [diff.getpixel((x, y)) for y in range(a.height) for x in range(a.width) if interior.getpixel((x, y))]
            values.sort()
            mean = sum(values) / len(values)
            flat_values = [diff.getpixel((x, y)) for y in range(a.height) for x in range(a.width)
                           if flat.getpixel((x, y))]
            key = (mean, -total)
            if best is None or key < best[0]:
                best = (key, {'dx': dx, 'dy': dy, 'interior_pixels': total,
                              'interior_fraction': total / (a.width * a.height),
                              'max_difference': values[-1], 'mean_difference': round(mean, 3),
                              'p99_difference': values[int(len(values) * 0.99)],
                              'outlier_fraction': round(sum(1 for v in values if v > 32) / len(values), 6),
                              'flat_pixels': len(flat_values),
                              'flat_max_difference': max(flat_values) if flat_values else None})
    if best is None:
        return {'ok': False, 'reason': 'no interior pixels'}
    result = best[1]
    result['judged_on'] = 'interior' if result['interior_fraction'] >= 0.2 else 'flat'
    if result['judged_on'] == 'flat':
        # Thin strokes have no 3-px interior after erosion; judge the flat core.
        flat_values = [diff.getpixel((x, y)) for y in range(a.height) for x in range(a.width)
                       if flat.getpixel((x, y))]
        if flat_values:
            flat_values.sort()
            result['flat_mean_difference'] = round(sum(flat_values) / len(flat_values), 3)
            result['flat_p99_difference'] = flat_values[int(len(flat_values) * 0.99)]
        result['ok'] = (result.get('flat_p99_difference', 0) <= 12 and
                        result.get('flat_mean_difference', 0) <= MEAN_TOLERANCE and
                        len(flat_values) >= 0.1 * a.width * a.height)
    else:
        result['ok'] = (result['p99_difference'] <= 8 and
                        result['mean_difference'] <= MEAN_TOLERANCE and
                        result['outlier_fraction'] <= 0.002 and
                        result['interior_fraction'] >= 0.2)
    return result


def save_diff_sheet(tiles, path):
    tile = 120
    columns = 5
    rows = (len(tiles) + columns - 1) // columns
    sheet = Image.new('RGB', (columns * 3 * tile, rows * (tile + 14)), 'white')
    draw = ImageDraw.Draw(sheet)
    for index, (name, ours, reference) in enumerate(tiles):
        x = (index % columns) * 3 * tile
        y = (index // columns) * (tile + 14)
        draw.text((x + 2, y + 1), name, fill='black')
        size = (tile - 4, tile - 4)
        sheet.paste(ours.resize(size), (x, y + 13))
        sheet.paste(reference.resize(size), (x + tile, y + 13))
        diff = ImageChops.difference(ours, reference).resize(size)
        sheet.paste(diff, (x + 2 * tile, y + 13))
    sheet.save(path)


def main():
    global CHROME, FONTS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--renderer', type=Path, required=True)
    parser.add_argument('--chrome', type=Path, default=CHROME)
    parser.add_argument('--fonts', type=Path, default=FONTS)
    args = parser.parse_args()
    CHROME = args.chrome.absolute()
    FONTS = args.fonts.absolute()
    work = args.output.absolute()
    work.mkdir(parents=True, exist_ok=True)
    tool = args.renderer.absolute()
    report = {'reference': 'Google Chrome 152.0.7977.42 (Skia)', 'size_px': SIZE,
              'flat_tolerance': FLAT_TOLERANCE, 'mean_tolerance': MEAN_TOLERANCE,
              'bbox_tolerance': BBOX_TOLERANCE, 'fonts': {}, 'scenes': {}}
    tiles = []
    for kind, scenes, font_name in (('colrv1', colrv1_scenes(), 'colrv1.ttf'),
                                    ('svg', svg_scenes(), 'svgfont.ttf')):
        reference = render_pages(scenes, kind, work)
        reference.save(work / f'reference-{kind}.png')
        report['fonts'][kind] = {'file': font_name, 'sha256': sha256(FONTS / font_name),
                                 'reference_sha256': sha256(work / f'reference-{kind}.png'),
                                 'scene_count': len(scenes)}
        ours_dir = work / f'ours-{kind}'
        ours_dir.mkdir(exist_ok=True)
        for index, scene in enumerate(scenes):
            x = (index % COLS) * CELL
            y = (index // COLS) * CELL
            cell = (render_single(scene, kind, work) if scene['name'] in SINGLE_PAGE
                    else reference.crop((x, y, x + CELL, y + CELL)))
            png = ours_dir / f'{scene["name"]}.png'
            subprocess.run([str(tool), str(FONTS / font_name), str(scene['glyph']), str(SIZE),
                            str(CELL // 2), str(CELL - 60), str(CELL), str(CELL), str(png)],
                           check=True, capture_output=True, timeout=60)
            ours = Image.open(png).convert('RGB')
            result = compare(ours, cell)
            a = crop_content(ours)
            b = crop_content(cell)
            if a is not None and b is not None:
                tiles.append((scene['name'], a, b))
            result['glyph'] = scene['glyph']
            result['ours_sha256'] = sha256(png)
            result['reference_sha256'] = hashlib.sha256(cell.tobytes()).hexdigest()
            report['scenes'][scene['name']] = result
    report['passed'] = sum(1 for r in report['scenes'].values() if r.get('ok'))
    report['total'] = len(report['scenes'])
    save_diff_sheet(tiles, work / 'reference-diff.png')
    (work / 'reference.json').write_text(json.dumps(report, indent=1, sort_keys=True) + '\n', encoding='utf-8')
    for name, result in sorted(report['scenes'].items()):
        print(f'{name:22s} {"PASS" if result.get("ok") else "FAIL"} '
              f'max={result.get("max_difference")} mean={result.get("mean_difference")} '
              f'interior={result.get("interior_fraction", 0):.2f} flat={result.get("flat_pixels", 0)} '
              f'{result.get("reason", "")}')
    print(f'{report["passed"]}/{report["total"]} reference scenes pass')
    return 0 if report['passed'] == report['total'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
