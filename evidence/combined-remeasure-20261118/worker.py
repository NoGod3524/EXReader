# SPDX-License-Identifier: MIT
"""Persistent EXReader render worker at 1200 px.

stdin: '<page index> <cold flag>' per line; stdout: '@[ns, sha256-or-null]'.
Adapted from the slides ablation worker.
"""
import ctypes as c
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
from bench_real_doc import Bitmap, Error, Page, hash_active_rgba

dll, pdf = map(Path, sys.argv[1:])
directory = os.add_dll_directory(str(dll.parent))
lib = c.CDLL(str(dll))
lib.exr_fixed_open.argtypes = [c.c_char_p, c.c_void_p, c.POINTER(c.c_void_p), c.POINTER(Error)]
lib.exr_fixed_pages.argtypes = [c.c_void_p, c.POINTER(c.c_size_t)]
lib.exr_fixed_pages.restype = c.POINTER(Page)
lib.exr_fixed_render.argtypes = [c.c_void_p, c.c_size_t, c.c_double, c.c_void_p, c.POINTER(Bitmap), c.POINTER(Error)]
lib.exr_bitmap_free.argtypes = [c.POINTER(Bitmap)]
lib.exr_fixed_free.argtypes = [c.c_void_p]
doc, err, n = c.c_void_p(), Error(), c.c_size_t()
assert lib.exr_fixed_open(os.fsencode(pdf), None, c.byref(doc), c.byref(err)) == 0
pages = lib.exr_fixed_pages(doc, c.byref(n))
assert n.value in (100, 120)
scales = {}
for i in range(n.value):
    geom = pages[i].geometry
    x0, y0, x1, y1 = geom.bounds
    width = y1 - y0 if geom.rotation % 180 else x1 - x0
    scales[i] = 1200 / (width * geom.unit_scale)
print('@ready', flush=True)
for line in sys.stdin:
    i, cold = map(int, line.split())
    bitmap = Bitmap()
    start = time.perf_counter_ns()
    status = lib.exr_fixed_render(doc, i, scales[i], None, c.byref(bitmap), c.byref(err))
    ns = time.perf_counter_ns() - start
    assert status == 0 and bitmap.width == 1200 and bitmap.height > 0 and bitmap.channels == 4 and bitmap.pixels
    sig = hash_active_rgba(bitmap)[0] if cold else None
    lib.exr_bitmap_free(c.byref(bitmap))
    print('@' + json.dumps([ns, sig]), flush=True)
lib.exr_fixed_free(doc)
