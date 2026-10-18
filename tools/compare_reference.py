
#!/usr/bin/env python3
"""Compare EXReader against MuPDF (PyMuPDF) page by page.

For every PDF in a directory the first page is rendered by both engines at the
same scale and compared pixel by pixel. The report is the evidence used to
claim or refute competitive parity; see docs/COMPETITIVE.md.
"""
# SPDX-License-Identifier: GPL-3.0-only
import argparse
import ctypes as c
import json
import os
import sys
from pathlib import Path

import pymupdf


class Error(c.Structure):
    _fields_ = [('code', c.c_int), ('message', c.c_char * 256)]


class Bitmap(c.Structure):
    _fields_ = [('width', c.c_uint32), ('height', c.c_uint32), ('stride', c.c_uint32),
                ('pixels', c.c_void_p), ('channels', c.c_uint32)]


STATUS = {0: 'ok', 1: 'argument', 2: 'memory', 3: 'io', 4: 'encoding', 5: 'format',
          6: 'limit', 7: 'database', 8: 'font', 9: 'cancelled', 10: 'password', 11: 'unsupported'}


def load(library):
    if sys.platform == 'win32':
        os.add_dll_directory(str(Path(library).parent))
    engine = c.CDLL(str(library))
    engine.exr_fixed_open.argtypes = [c.c_char_p, c.c_void_p, c.POINTER(c.c_void_p), c.POINTER(Error)]
    engine.exr_fixed_render.argtypes = [c.c_void_p, c.c_size_t, c.c_double, c.c_void_p, c.POINTER(Bitmap), c.POINTER(Error)]
    engine.exr_fixed_free.argtypes = [c.c_void_p]
    engine.exr_fixed_free.restype = None
    engine.exr_bitmap_free.argtypes = [c.POINTER(Bitmap)]
    engine.exr_bitmap_free.restype = None
    return engine


def ours(engine, path, scale):
    document = c.c_void_p()
    error = Error()
    status = engine.exr_fixed_open(str(path).encode('utf-8'), None, c.byref(document), c.byref(error))
    if status:
        return None, STATUS.get(status, status), error.message.decode('utf-8', 'replace')
    bitmap = Bitmap()
    try:
        status = engine.exr_fixed_render(document, 0, scale, None, c.byref(bitmap), c.byref(error))
        if status:
            return None, STATUS.get(status, status), error.message.decode('utf-8', 'replace')
        data = c.string_at(bitmap.pixels, bitmap.stride * bitmap.height)
        return (bitmap.width, bitmap.height, data), 'ok', ''
    finally:
        engine.exr_bitmap_free(c.byref(bitmap))
        engine.exr_fixed_free(document)


def reference(path, scale):
    doc = pymupdf.open(path)
    if doc.page_count == 0:
        raise RuntimeError('no pages')
    pix = doc[0].get_pixmap(matrix=pymupdf.Matrix(scale, scale), colorspace=pymupdf.csRGB, alpha=False)
    return pix.width, pix.height, pix.samples


def compare(path, engine, scale):
    record = {'file': path.name}
    try:
        width, height, raw = reference(path, scale)
    except Exception as exc:                       # noqa: BLE001 - report every failure
        record.update({'result': 'reference-failed', 'detail': str(exc)[:160]})
        return record
    got, status, detail = ours(engine, path, scale)
    if got is None:
        record.update({'result': 'exreader-' + str(status), 'detail': detail[:160]})
        return record
    if got[0] != width or got[1] != height:
        record.update({'result': 'size-mismatch', 'detail': f'{got[0]}x{got[1]} vs {width}x{height}'})
        return record
    data = got[2]
    total = 0
    worst = 0
    differing = 0
    for i in range(0, width * height * 4, 4):
        for k in range(3):
            a = data[i + k]
            b = raw[(i // 4) * 3 + k]
            d = a - b
            if d < 0:
                d = -d
            total += d
            if d > worst:
                worst = d
            if d > 8:
                differing += 1
                break
    pixels = width * height
    record.update({'result': 'compared', 'mean_abs': round(total / (pixels * 3), 3),
                   'max_abs': worst, 'percent_differing': round(100 * differing / pixels, 3)})
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('library', type=Path)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--scale', type=float, default=1.0)
    parser.add_argument('--limit', type=int, default=0)
    parser.add_argument('--json', type=Path)
    args = parser.parse_args()
    engine = load(args.library)
    files = sorted(p for p in args.directory.rglob('*.pdf'))
    if args.limit:
        files = files[:args.limit]
    records = [compare(path, engine, args.scale) for path in files]
    counts = {}
    for record in records:
        counts[record['result']] = counts.get(record['result'], 0) + 1
    compared = [r for r in records if r['result'] == 'compared']
    print(f'{len(records)} files: ' + ', '.join(f'{k}={v}' for k, v in sorted(counts.items())))
    if compared:
        mean = sum(r['mean_abs'] for r in compared) / len(compared)
        worst = max(compared, key=lambda r: r['mean_abs'])
        print(f'compared {len(compared)}: mean |diff| {mean:.3f}, worst {worst["file"]} {worst["mean_abs"]}')
    for record in sorted(records, key=lambda r: -r.get('mean_abs', -1))[:10]:
        if record['result'] != 'compared':
            print(f'  {record["result"]:>22}  {record["file"]}  {record.get("detail", "")}')
    if args.json:
        args.json.write_text(json.dumps(records, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
