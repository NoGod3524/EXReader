#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Record Decimal, renderer and MuPDF probes without conflating their results."""
import argparse
import ctypes as c
import hashlib
import json
from pathlib import Path
import pymupdf
from compare_reference import load, Bitmap, Error, Control


class Options(c.Structure):
    _fields_ = [('channels', c.c_uint32), ('background', c.c_uint32),
                ('mask_budget', c.c_size_t), ('control', Control)]


def pixel(engine, path, white):
    document = c.c_void_p();error = Error();bitmap = Bitmap();options = Options()
    options.channels = 4;options.background = 0xffffffff if white else 0
    status = engine.exr_fixed_open(str(path).encode('utf-8'), None, c.byref(document), c.byref(error))
    if status:
        raise RuntimeError(error.message.decode())
    try:
        status = engine.exr_fixed_render(document, 0, 1, c.byref(options), c.byref(bitmap), c.byref(error))
        if status:
            raise RuntimeError(error.message.decode())
        data = list(c.string_at(bitmap.pixels+8*bitmap.stride+8*4, 4))
        if not white:
            data[:3] = [(v*data[3]+127)//255 for v in data[:3]]
        return data
    finally:
        engine.exr_bitmap_free(c.byref(bitmap));engine.exr_fixed_free(document)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('library', type=Path);parser.add_argument('--baseline', type=Path)
    parser.add_argument('--output', type=Path, required=True);args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent/'tests/fixtures/pdf-blend'
    manifest = json.loads((root/'nested-manifest.json').read_text(encoding='utf-8'))
    current = load(args.library.resolve());baseline = load(args.baseline.resolve()) if args.baseline else None
    rows = [];maximum = {'current': 0, 'mupdf': 0, 'baseline': 0}
    for scene in manifest['scenes']:
        path = root/scene['file'];row = dict(scene)
        row['comparisons'] = {}
        with pymupdf.open(path) as document:
            for white in [False, True]:
                key = 'white' if white else 'premultiplied'
                samples = {'current': pixel(current, path, white),
                           'mupdf': list(document[0].get_pixmap(alpha=not white).pixel(8, 8))}
                if baseline:
                    samples['baseline'] = pixel(baseline, path, white)
                differences = {name: max(abs(x-y) for x, y in zip(data, scene[key])) for name, data in samples.items()}
                for name, difference in differences.items():
                    maximum[name] = max(maximum[name], difference)
                row['comparisons'][key] = {'samples': samples, 'differences_from_decimal': differences}
        rows.append(row)
    report = {'reference': 'MuPDF '+pymupdf.VersionBind, 'max_difference_from_decimal': maximum,
              'library_sha256': hashlib.sha256(args.library.read_bytes()).hexdigest(),
              'baseline_sha256': hashlib.sha256(args.baseline.read_bytes()).hexdigest() if baseline else None,
              'scenes': rows}
    args.output.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print('128 nested scenes, max Decimal differences:', maximum)
    if maximum['current'] > 3:
        raise SystemExit('Current engine exceeds the frozen Decimal probe limit')


if __name__ == '__main__':
    main()
