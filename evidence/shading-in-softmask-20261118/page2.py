import ctypes as c
import json
import statistics as st
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from bench_real_doc import Bitmap, Error, Page, digest_file, hash_active_rgba, wait_idle

here = Path(__file__).resolve().parent
pdf = ROOT / 'tests/fixtures/pdf-large/real-mixed-120.pdf'
names = ('mask_build mask_raster mask_lum paint_mask paint_page img_load img_draw '
         'group_begin_mask group_end_mask group_begin_page group_end_page sh_table '
         'canvas_create_mask canvas_take_mask raster_page path glyph clip canvas_free_mask '
         'sample_mask sample_page scale_mask scale_page lookup_mask lookup_page frame_mask frame_page').split()

class Arm:
    def __init__(self, library):
        self.engine = engine = c.CDLL(str(library))
        engine.exr_fixed_open.argtypes = [c.c_char_p,c.c_void_p,c.POINTER(c.c_void_p),c.POINTER(Error)]
        engine.exr_fixed_pages.argtypes = [c.c_void_p,c.POINTER(c.c_size_t)]
        engine.exr_fixed_pages.restype = c.POINTER(Page)
        engine.exr_fixed_render.argtypes = [c.c_void_p,c.c_size_t,c.c_double,c.c_void_p,c.POINTER(Bitmap),c.POINTER(Error)]
        engine.exr_bitmap_free.argtypes = [c.POINTER(Bitmap)]
        engine.exr_fixed_free.argtypes = [c.c_void_p]
        self.diag = hasattr(engine, 'exr_diag_read')
        self.doc = c.c_void_p()
        self.error = Error()
        self.check(engine.exr_fixed_open(str(pdf).encode(), None, c.byref(self.doc), c.byref(self.error)))
        count = c.c_size_t()
        geom = engine.exr_fixed_pages(self.doc, c.byref(count))[1].geometry
        assert count.value == 120
        bounds = geom.bounds
        self.scale = 1200 / ((bounds[3]-bounds[1] if geom.rotation % 180 else bounds[2]-bounds[0]) * geom.unit_scale)

    def check(self, status):
        if status:
            raise RuntimeError((status, self.error.message))

    def capture(self, flag):
        if self.diag:
            self.engine.exr_diag_set_flags(flag)
            self.engine.exr_diag_reset()
        bitmap = Bitmap()
        start = time.perf_counter_ns()
        self.check(self.engine.exr_fixed_render(self.doc, 1, self.scale, None, c.byref(bitmap), c.byref(self.error)))
        elapsed = (time.perf_counter_ns() - start)/1e6
        assert bitmap.width == 1200
        signature, pixels = hash_active_rgba(bitmap)
        self.engine.exr_bitmap_free(c.byref(bitmap))
        row = dict(ms=elapsed, hash=signature, pixels=pixels)
        if self.diag:
            ms, count = (c.c_double*32)(), (c.c_double*32)()
            assert self.engine.exr_diag_read(ms, count) == 32
            row['scopes'] = {name: [ms[i],int(count[i])] for i,name in enumerate(names) if count[i]}
        return row

if __name__ == '__main__':
    a_path, b_path, out = [Path(arg).resolve() for arg in sys.argv[1:4]]
    flags = [int(flag) for flag in sys.argv[4:]]
    a, b = Arm(a_path), Arm(b_path)
    cases = {}
    for flag in flags:
        rows = []
        busy = wait_idle(15, 45)
        while busy is None:
            print('Idle gate timed out. Retrying same batch.', flush=True)
            busy = wait_idle(15, 45)
        for i in range(9):
            order = 'AB' if i % 2 == 0 else 'BA'
            row = dict(order=order, pre_cpu=busy)
            for side in order:
                row[side] = a.capture(0) if side == 'A' else b.capture(flag)
            rows.append(row)
        cases[flag] = rows
        print(flag, *(round(st.median(row[side]['ms'] for row in rows[1:]), 3) for side in 'AB'), flush=True)
        out.write_text(json.dumps(dict(a_sha256=digest_file(a_path), b_sha256=digest_file(b_path), pdf_sha256=digest_file(pdf), cases=cases), indent=2)+'\n')
    for arm in (a,b):
        arm.engine.exr_fixed_free(arm.doc)
