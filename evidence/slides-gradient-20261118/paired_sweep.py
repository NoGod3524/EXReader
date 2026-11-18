# SPDX-License-Identifier: MIT
"""Time native renders in alternating page order and compare active RGBA bytes."""
import argparse
import ctypes as c
import hashlib
import json
import math
import os
from pathlib import Path
import statistics as st
import subprocess
import sys
import time
from contextlib import ExitStack

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from bench_real_doc import Bitmap, Error, Page, digest_file, wait_idle


class NativeDocument:
    def __init__(self, path, pdf, width):
        self.library = lib = c.CDLL(str(path))
        self.document, self.error = c.c_void_p(), Error()
        for name, argtypes in {
            'exr_fixed_open': [c.c_char_p, c.c_void_p, c.POINTER(c.c_void_p), c.POINTER(Error)],
            'exr_fixed_pages': [c.c_void_p, c.POINTER(c.c_size_t)],
            'exr_fixed_render': [c.c_void_p, c.c_size_t, c.c_double, c.c_void_p,
                                 c.POINTER(Bitmap), c.POINTER(Error)],
            'exr_bitmap_free': [c.POINTER(Bitmap)],
            'exr_fixed_free': [c.c_void_p],
        }.items():
            getattr(lib, name).argtypes = argtypes
        lib.exr_fixed_pages.restype = c.POINTER(Page)
        assert lib.exr_fixed_open(str(pdf).encode(), None, c.byref(self.document), c.byref(self.error)) == 0
        count = c.c_size_t()
        pages = lib.exr_fixed_pages(self.document, c.byref(count))
        self.scales = []
        for i in range(count.value):
            geom = pages[i].geometry
            axis = int(geom.rotation % 180 != 0)
            self.scales.append(width / ((geom.bounds[axis+2] - geom.bounds[axis]) * geom.unit_scale))
        self.width = width

    def render(self, page, verify, height):
        bitmap = Bitmap()
        start = time.perf_counter_ns()
        status = self.library.exr_fixed_render(self.document, page, self.scales[page], None,
                                               c.byref(bitmap), c.byref(self.error))
        ms = (time.perf_counter_ns() - start) / 1e6
        try:
            assert status == 0, self.error.message
            assert bitmap.width == self.width and bitmap.channels == 4 and bitmap.pixels
            if height:
                assert bitmap.height == height
            rows = [c.string_at(bitmap.pixels+y*bitmap.stride, self.width*4)
                    for y in range(bitmap.height)] if verify else None
            return ms, rows
        finally:
            self.library.exr_bitmap_free(c.byref(bitmap))

    def close(self):
        self.library.exr_fixed_free(self.document)


def gate():
    while True:
        try:
            busy = wait_idle(15, 45)
        except RuntimeError as error:
            if str(error) != 'Invalid system CPU counters':
                raise
            busy = None
        if busy is not None:
            return busy
        print('Idle gate failed. Retrying the same sweep.', flush=True)


def response(worker):
    for line in worker.stdout:
        if line.startswith('@'):
            return line.strip()[1:]
    raise RuntimeError(f'PDF.js worker ended with {worker.poll()}')


def close_worker(worker):
    worker.stdin.close()
    try:
        assert worker.wait(timeout=20) == 0
    except subprocess.TimeoutExpired:
        worker.kill()
        worker.wait()
        raise


def pixels_different(a, b):
    assert len(a) == len(b)
    return sum(row_a[x:x+4] != row_b[x:x+4]
               for row_a, row_b in zip(a, b) if row_a != row_b
               for x in range(0, len(row_a), 4))


def capture(args, docs, worker):
    count = len(docs['A'].scales)
    assert count == len(docs['B'].scales)
    if args.pages:
        assert 1 <= args.pages <= count
        count = args.pages
    tags = 'ABC' if worker else 'AB'
    height = 900 if args.pages and args.pdf.stem == 'image-heavy-100' and args.width == 1200 else None
    rows = [{'page': i+1, **{tag: [] for tag in tags}, 'hashes': {}} for i in range(count)]
    gates, mismatches = [], []
    sums = {tag: [] for tag in tags}
    pixels = differing = 0
    gate_every = 3 if worker else (1 if args.pages or count > 20 else max(args.runs, 1))

    for sweep in range(args.runs+1):
        cold_gate = sweep == 0 and (args.pages or count > 20)
        warm_gate = sweep > 0 and (sweep-1) % gate_every == 0
        if args.runs and (cold_gate or warm_gate):
            gates.append({'round': sweep, 'cpu_percent': gate()})
        totals = dict.fromkeys(tags, 0)
        for i, row in enumerate(rows):
            parity = (sweep+i) % 2
            order = 'BA' if parity else 'AB'
            if worker:
                order = 'C'+order if parity else order+'C'
            raw = {}
            for tag in order:
                if args.trace:
                    print(f'BEGIN round={sweep} page={i+1} arm={tag}', file=sys.stderr, flush=True)
                if tag == 'C':
                    worker.stdin.write(f'{i} {int(sweep == 0)}\n')
                    worker.stdin.flush()
                    ns, signature = json.loads(response(worker))
                    assert ns > 0
                    ms = ns/1e6
                    if sweep == 0:
                        row['hashes'][tag] = signature
                else:
                    ms, rgba = docs[tag].render(i, sweep == 0, height)
                    if sweep == 0:
                        raw[tag] = rgba
                        row['hashes'][tag] = hashlib.sha256(b''.join(rgba)).hexdigest()
                if sweep:
                    row[tag].append(ms)
                    totals[tag] += ms
            if sweep == 0:
                pixels += len(raw['A'])*args.width
                if raw['A'] != raw['B']:
                    mismatches.append(i+1)
                    differing += pixels_different(raw['A'], raw['B'])
        if sweep:
            for tag in tags:
                sums[tag].append(totals[tag])
            print(f'{args.out.stem} sweep {sweep} '
                  + ' '.join(f'{tag}={totals[tag]:.2f}' for tag in tags), flush=True)
        else:
            print(f'{args.out.stem} warmup complete', flush=True)

    summary = {}
    for tag in tags if args.runs else ():
        samples = sorted(value for row in rows for value in row[tag])
        summary[tag] = {'p50_ms': st.median(samples), 'p95_ms': samples[math.ceil(.95*len(samples))-1],
                        'throughput_pages_s': count*1000/st.median(sums[tag]), 'round_sum_ms': sums[tag]}
        for row in rows:
            row[tag+'_p50_ms'] = st.median(row[tag])
    return {'pdf': str(args.pdf), 'pdf_sha256': digest_file(args.pdf),
            'a_sha256': digest_file(args.a), 'b_sha256': digest_file(args.b),
            'width': args.width, 'runs': args.runs,
            'order': 'AB then optional C on even (round+page index), reverse on odd',
            'pdfjs_root': str(args.pdfjs_root) if worker else None,
            'idle_gates': gates, 'gate_every': gate_every if args.runs else None, 'compared_pixels': pixels,
            'mismatched_pages': mismatches, 'differing_pixels': differing,
            'summary': summary, 'pages': rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ('a', 'b', 'pdf'):
        parser.add_argument(arg, type=Path)
    parser.add_argument('width', type=int)
    parser.add_argument('runs', type=int, help='Warm timing sweeps, or 0 for pixel comparison only')
    parser.add_argument('out', type=Path)
    parser.add_argument('--pages', type=int, help='Render only the first N pages')
    parser.add_argument('--trace', action='store_true')
    parser.add_argument('--pdfjs-root', type=Path)
    args = parser.parse_args()
    for name in tuple(os.environ):
        if name.startswith('EXR_') or name == 'NODE_OPTIONS':
            del os.environ[name]
    for arg in ('a', 'b', 'pdf', 'out'):
        setattr(args, arg, getattr(args, arg).resolve())

    with ExitStack() as stack:
        docs = {}
        for tag, path in zip('AB', (args.a, args.b)):
            docs[tag] = NativeDocument(path, args.pdf, args.width)
            stack.callback(docs[tag].close)
        worker = None
        if args.pdfjs_root:
            assert args.width == 1200 and args.pages == 10
            script = Path(__file__).with_name('pdfjs_worker.cjs')
            worker = subprocess.Popen(['node', str(script), str(args.pdfjs_root.resolve()), str(args.pdf)],
                                      stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
            stack.callback(close_worker, worker)
            assert response(worker) == 'ready'
        result = capture(args, docs, worker)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=1)+'\n')
    assert result['differing_pixels'] == 0, result['mismatched_pages']


if __name__ == '__main__':
    main()
