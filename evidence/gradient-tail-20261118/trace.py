# SPDX-License-Identifier: MIT
"""Production EXR_ATTRIBUTION_TRACE scopes for the six pages (stderr ATTR lines)."""
import ctypes as c, os, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from bench_real_doc import Bitmap, Error, Page
lib = Path(sys.argv[1]).resolve(); rounds = int(sys.argv[2]) if len(sys.argv) > 2 else 9
os.add_dll_directory(str(lib.parent)); e = c.CDLL(str(lib))
e.exr_fixed_open.argtypes = [c.c_char_p, c.c_void_p, c.POINTER(c.c_void_p), c.POINTER(Error)]
e.exr_fixed_pages.argtypes = [c.c_void_p, c.POINTER(c.c_size_t)]; e.exr_fixed_pages.restype = c.POINTER(Page)
e.exr_fixed_render.argtypes = [c.c_void_p, c.c_size_t, c.c_double, c.c_void_p, c.POINTER(Bitmap), c.POINTER(Error)]
e.exr_bitmap_free.argtypes = [c.POINTER(Bitmap)]
err, doc = Error(), c.c_void_p()
assert not e.exr_fixed_open(str(ROOT / 'tests/fixtures/pdf-large/real-mixed-120.pdf').encode(), None, c.byref(doc), c.byref(err))
n = c.c_size_t(); pg = e.exr_fixed_pages(doc, c.byref(n))
def scale(i):
    g = pg[i].geometry; b = g.bounds; w = b[3]-b[1] if g.rotation % 180 else b[2]-b[0]; return 1200/(w*g.unit_scale)
for r in range(rounds):
    for p in (2, 11, 12, 14, 16, 17):
        bm = Bitmap(); t = time.perf_counter_ns()
        assert not e.exr_fixed_render(doc, p-1, scale(p-1), None, c.byref(bm), c.byref(err))
        print(f'TOTAL {p} {(time.perf_counter_ns()-t)/1e6:.4f}', flush=True); e.exr_bitmap_free(c.byref(bm))
