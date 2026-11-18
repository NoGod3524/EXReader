# SPDX-License-Identifier: MIT
"""Gate every batch and alternate render order per page and per sweep."""
import argparse
import ctypes as c
import gzip
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from bench_real_doc import Bitmap, Error, Page, digest_file, hash_active_rgba
from bench_engine import cpu_busy_percent, cpu_times, wait_idle
from benchmark_pdf_rect import process_memory_bytes


class Document:
    def __init__(self, dll, path, width, detail):
        self.path = dll.resolve()
        self.directory = os.add_dll_directory(str(self.path.parent))
        self.lib = lib = c.CDLL(str(self.path))
        self.doc, self.error = c.c_void_p(), Error()
        for name, args in {
            'exr_fixed_open': [c.c_char_p, c.c_void_p, c.POINTER(c.c_void_p), c.POINTER(Error)],
            'exr_fixed_pages': [c.c_void_p, c.POINTER(c.c_size_t)],
            'exr_fixed_render': [c.c_void_p, c.c_size_t, c.c_double, c.c_void_p,
                                 c.POINTER(Bitmap), c.POINTER(Error)],
            'exr_bitmap_free': [c.POINTER(Bitmap)],
            'exr_fixed_free': [c.c_void_p],
        }.items():
            getattr(lib, name).argtypes = args
        lib.exr_fixed_pages.restype = c.POINTER(Page)
        self.check(lib.exr_fixed_open(str(path).encode('utf-8'), None,
                                      c.byref(self.doc), c.byref(self.error)))
        n = c.c_size_t()
        pages = lib.exr_fixed_pages(self.doc, c.byref(n))
        self.scales = []
        for i in range(n.value):
            g = pages[i].geometry
            j = int(g.rotation % 180 != 0)
            self.scales.append(width / ((g.bounds[j+2] - g.bounds[j])*g.unit_scale))
        self.width = width
        self.detail = detail
        if detail is not None:
            lib.probe_start.argtypes = [c.c_int]
            lib.probe_read.argtypes = [c.POINTER(c.c_double)]
            lib.probe_read.restype = c.c_uint

    def check(self, status):
        if status:
            raise RuntimeError(self.error.message.decode('utf-8', errors='replace'))

    def render(self, i, verify):
        lib = self.lib
        b = Bitmap()
        if self.detail is not None:
            lib.probe_start(self.detail)
        start = time.perf_counter_ns()
        status = lib.exr_fixed_render(self.doc, i, self.scales[i], None,
                                      c.byref(b), c.byref(self.error))
        ns = time.perf_counter_ns() - start
        try:
            self.check(status)
            assert b.width == self.width and b.channels == 4
            result = {'ns': ns}
            if verify:
                result['rgba'], result['pixels'] = hash_active_rgba(b)
            if self.detail is not None:
                v = (c.c_double * (97*33))()
                n = lib.probe_read(v)
                result['probe'] = [v[k*33:(k+1)*33] for k in range(n)]
            return result
        finally:
            lib.exr_bitmap_free(c.byref(b))

    def close(self):
        self.lib.exr_fixed_free(self.doc)
        self.directory.close()


def core_times(core):
    import psutil
    times = psutil.cpu_times(percpu=True)[core]
    return times.idle, sum(times)


def gate(core=None):
    while True:
        try:
            if core is None:
                busy = wait_idle(15, 20)
            else:
                before = core_times(core)
                time.sleep(0.5)
                busy = cpu_busy_percent(before, core_times(core))
                if busy > 15:
                    time.sleep(1)
                    continue
        except RuntimeError as exc:
            if str(exc) != 'Invalid system CPU counters':
                raise
            busy = None
        if busy is not None:
            return busy
        print('Idle gate closed. Retrying.', flush=True)


def main(args):
    for name in tuple(os.environ):
        if name.startswith('EXR_'):
            del os.environ[name]
    if args.core is not None:
        import psutil
        psutil.Process().cpu_affinity([args.core])
    details = (args.detail_a, args.detail)
    docs = [Document(p, args.pdf.resolve(), args.width, details[tag])
            for tag, p in enumerate((args.a, args.b)) if p is not None]
    rows, gates, cpu = [], [], []
    try:
        assert all(len(d.scales) == len(docs[0].scales) for d in docs)
        first, last = (1, len(docs[0].scales)) if not args.pages else args.pages
        assert 1 <= first <= last <= len(docs[0].scales)
        r = 0
        rejected = []
        while r <= args.runs:
            pre = gate(args.core)
            before = cpu_times()
            started, started_cpu = time.perf_counter(), time.process_time()
            core_before = core_times(args.core) if args.core is not None else None
            batch = []
            stop = 1 if r == 0 else min(args.runs+1, r+args.batch)
            for sweep in range(r, stop):
                side = [{} for _ in docs]
                for i in range(first-1, last):
                    order = range(len(docs))
                    if (sweep+i+args.reverse) % 2:
                        order = reversed(order)
                    for tag in order:
                        side[tag][i+1] = docs[tag].render(i, sweep == 0)
                    if sweep == 0 and len(docs) == 2:
                        assert side[0][i+1]['rgba'] == side[1][i+1]['rgba'], i+1
                batch.append(side)
            busy = cpu_busy_percent(before, cpu_times())
            seconds = time.process_time()-started_cpu
            own = 100 * seconds / ((time.perf_counter()-started)*os.cpu_count())
            sample = {'system': busy, 'capture_process': own}
            if core_before is not None:
                core_after = core_times(args.core)
                idle, total = (after-begin for after, begin in zip(core_after, core_before))
                background = max(0, 100*(total-idle-seconds)/total) if total > 0 else None
                sample['core_background'] = background
                if background is None or background > 15:
                    rejected.append({'sweep': r, 'gate_percent': pre, **sample})
                    print(f'{args.out.name} sweep={r} pinned CPU gate closed during capture. Retrying.', flush=True)
                    continue
            gates.append({'sweep': r, 'cpu_percent': pre})
            cpu.append(sample)
            rows.extend(batch)
            for i, side in enumerate(batch, r):
                totals = [round(sum(p['ns'] for p in s.values())/1e6, 3) for s in side]
                print(f'{args.out.name} sweep={i} gate={pre:.2f} sys_cpu={busy:.2f} ms={totals}', flush=True)
            r = stop
        result = {
            'pdf': args.pdf.name, 'pdf_sha256': digest_file(args.pdf), 'width': args.width,
            'dll_sha256': [digest_file(d.path) for d in docs],
            'detail': details, 'reverse': args.reverse, 'batch': args.batch, 'core': args.core,
            'peak_rss_bytes': process_memory_bytes()[1], 'gate_percent': gates,
            'capture_percent': cpu, 'rejected_batches': rejected, 'sweeps': rows,
        }
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_bytes(gzip.compress(json.dumps(result).encode(), mtime=0))
    finally:
        for doc in docs:
            doc.close()


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('a', type=Path)
    p.add_argument('out', type=Path)
    p.add_argument('--b', type=Path)
    p.add_argument('--pdf', type=Path, default=ROOT / 'tests/fixtures/pdf-large/image-heavy-100.pdf')
    p.add_argument('--pages', type=int, nargs=2)
    p.add_argument('--width', type=int, default=1200)
    p.add_argument('--runs', type=int, default=5)
    p.add_argument('--batch', type=int, default=1)
    p.add_argument('--core', type=int)
    p.add_argument('--detail', type=int, choices=(0, 1))
    p.add_argument('--detail-a', type=int, choices=(0, 1))
    p.add_argument('--reverse', action='store_true')
    main(p.parse_args())
