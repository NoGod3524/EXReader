"""Untimed census: reciprocal-path versus quotient-fallback pixels per fixture.

One fresh process per fixture/width renders every page once with the count
DLL (build.py count); the DLL prints its tallies at process exit.
"""
from pathlib import Path
import ctypes as c
import json
import os
import re
import subprocess
import sys

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
CASES = [('pdf-large/real-mixed-120', 1200), ('pdf-large/image-heavy-100', 1200), ('pdf-large/vector-heavy-100', 1200),
         ('pdf-large/real-mixed-120', 600), ('pdf-large/image-heavy-100', 600),
         ('pdf-ppt/deck', 1200), ('pdf-hybrid-real/word-5', 1200), ('pdf-hybrid-real/pptx-20', 1200)]


def child(pdf, width):
    sys.path.insert(0, str(OUT.parent / 'image-paint-path-20261118'))
    from verify_pixels import load
    from benchmark_pdf_blend import Bitmap, Error
    lib, _ = load(ROOT / 'build/diag/count/libexreader.dll')
    error, doc, count = Error(), c.c_void_p(), c.c_size_t()
    assert not lib.exr_fixed_open(os.fsencode(pdf), None, c.byref(doc), c.byref(error))
    pages = lib.exr_fixed_pages(doc, c.byref(count))
    for page in range(count.value):
        g = pages[page].geometry
        native = g.bounds[3] - g.bounds[1] if g.rotation % 180 else g.bounds[2] - g.bounds[0]
        bitmap = Bitmap()
        assert not lib.exr_fixed_render(doc, page, width / (native * g.unit_scale), None, c.byref(bitmap), c.byref(error))
        lib.exr_bitmap_free(c.byref(bitmap))
    lib.exr_fixed_free(doc)
    print(count.value)


if __name__ == '__main__':
    if len(sys.argv) == 3:
        child(sys.argv[1], int(sys.argv[2]))
        sys.exit(0)
    rows = []
    for fixture, width in CASES:
        pdf = ROOT / 'tests/fixtures' / f'{fixture}.pdf'
        run = subprocess.run([sys.executable, '-X', 'utf8', __file__, str(pdf), str(width)], capture_output=True, text=True, cwd=ROOT, check=True)
        fast, fallback = map(int, re.search(r'UNPREMUL fast=(\d+) fallback=(\d+)', run.stderr).groups())
        total = fast + fallback
        rows.append({'fixture': fixture, 'width': width, 'pages': int(run.stdout.strip()), 'pixels': total,
                     'reciprocal': fast, 'fallback': fallback, 'fallback_percent': round(100 * fallback / total, 4) if total else 0})
        print(rows[-1], flush=True)
    (OUT / 'count.json').write_text(json.dumps(rows, indent=2) + '\n')
