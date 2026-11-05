#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Generate the deterministic scan-page fixtures for the OCR overlay probe.

Runs only inside GitHub Actions. The page is a synthetic clean print (white
paper, one font, no noise) so Tesseract output is stable for the same runner
image; every byte, box and digest is recorded and re-hashed by the checker.
"""
import argparse
import hashlib
import json
import pathlib
import sys

from PIL import Image, ImageDraw, ImageFont

PAGE = (900, 1200)
LINES = [
    "Reading library",
    "Quiet pages",
    "Record 31415",
    "Check 27182",
]
ROW_Y = [110, 210, 310, 410]
LEFT = 70
SIZE = 48
BARS = [(120, 300, 780, 340), (120, 400, 780, 440), (120, 500, 780, 560)]


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_font(path, size):
    if path.suffix.lower() == '.ttc':
        return ImageFont.truetype(str(path), size, index=0)
    return ImageFont.truetype(str(path), size)


def word_boxes(draw, text, x, y, font):
    """Exact ink box per whitespace-separated word, in fixture pixels."""
    boxes, cursor = [], 0
    for word in text.split(' '):
        if not word:
            continue
        start = text.index(word, cursor)
        prefix = text[:start]
        wx = x + draw.textlength(prefix, font=font)
        boxes.append({'word': word, 'box': [float(v) for v in draw.textbbox((wx, y), word, font=font)]})
        cursor = start + len(word)
    return boxes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', required=True)
    parser.add_argument('--font', required=True)
    args = parser.parse_args()
    root = pathlib.Path(args.out)
    root.mkdir(parents=True, exist_ok=True)
    font_path = pathlib.Path(args.font)
    if not font_path.is_file():
        print(f'fixture font is missing: {font_path}', file=sys.stderr)
        return 2
    font = load_font(font_path, SIZE)

    scan = Image.new('L', PAGE, 255)
    draw = ImageDraw.Draw(scan)
    lines = []
    for index, (text, y) in enumerate(zip(LINES, ROW_Y)):
        draw.text((LEFT, y), text, font=font, fill=0)
        words = word_boxes(draw, text, LEFT, y, font)
        lines.append({'index': index, 'text': text,
                      'box': [float(v) for v in draw.textbbox((LEFT, y), text, font=font)],
                      'words': words,
                      'token': words[-1]['word'],
                      'token_box': words[-1]['box']})
    # No noise and no extra ink: a clean print keeps Tesseract deterministic and
    # leaves the image-only case entirely to bars.png.
    scan_path = root / 'scan.png'
    scan.save(scan_path, optimize=False)

    bars = Image.new('L', PAGE, 255)
    bars_draw = ImageDraw.Draw(bars)
    for box in BARS:
        bars_draw.rectangle(box, fill=0)
    bars_path = root / 'bars.png'
    bars.save(bars_path, optimize=False)

    empty = root / 'empty-models'
    empty.mkdir(parents=True, exist_ok=True)
    broken = root / 'empty-model-file'
    broken.mkdir(parents=True, exist_ok=True)
    (broken / 'eng.traineddata').write_bytes(b'')

    # TSV view for the C++ probe: fixed columns, tab separated, no quoting.
    rows = ['#index\ttext\tbox\ttoken\ttoken_box']
    for line in lines:
        box = ' '.join(f'{v:g}' for v in line['box'])
        token_box = ' '.join(f'{v:g}' for v in line['token_box'])
        rows.append(f"{line['index']}\t{line['text']}\t{box}\t{line['token']}\t{token_box}")
    (root / 'lines.tsv').write_text('\n'.join(rows) + '\n', encoding='utf-8')

    manifest = {
        'schema': 1,
        'kind': 'synthetic clean print rendered once per run; not a real book or user scan',
        'page': {'width': PAGE[0], 'height': PAGE[1], 'unit_scale': 1.0, 'y_down': 1},
        'font': {'path': str(font_path), 'sha256': sha256(font_path), 'size': SIZE},
        'images': {
            'scan': {'path': 'scan.png', 'sha256': sha256(scan_path), 'bytes': scan_path.stat().st_size,
                     'width': PAGE[0], 'height': PAGE[1], 'mode': scan.mode},
            'bars': {'path': 'bars.png', 'sha256': sha256(bars_path), 'bytes': bars_path.stat().st_size,
                     'width': PAGE[0], 'height': PAGE[1], 'mode': bars.mode},
        },
        'lines': lines,
    }
    (root / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'fixtures': str(root), 'scan_sha256': manifest['images']['scan']['sha256'],
                      'lines': [line['text'] for line in lines]}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
