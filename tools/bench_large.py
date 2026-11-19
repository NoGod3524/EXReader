#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""One fresh EXReader process per width; report open, per-page render and RSS."""
import argparse
import ctypes as c
import json
import os
import subprocess
import sys
import threading
import time
from contextlib import ExitStack
from pathlib import Path

from bench_real_doc import Bitmap, Error, Page, digest_file


def rss_bytes():
    if sys.platform.startswith('linux'):
        with open('/proc/self/statm', encoding='ascii') as f:
            return int(f.read().split()[1]) * os.sysconf('SC_PAGE_SIZE')
    if os.name == 'nt':
        from bench_memory import process_memory
        return process_memory(-1)['rss']
    raise RuntimeError('current working set sampler supports Windows and Linux')


class Sampler:
    """Maximum of periodic RSS observations, not the OS lifetime high-water mark."""
    def __init__(self, read=rss_bytes, interval=0.01):
        self.read, self.interval = read, interval
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.run)
        self.count = self.peak = 0
        self.error = None

    def sample(self):
        self.peak = max(self.peak, self.read())
        self.count += 1

    def run(self):
        try:
            while not self.stop.wait(self.interval):
                self.sample()
        except Exception as exc:
            self.error = exc

    def __enter__(self):
        self.sample()
        self.thread.start()
        return self

    def __exit__(self, kind, *_):
        self.stop.set()
        self.thread.join()
        if kind is None:
            if self.error:
                raise self.error
            self.sample()


def capture(library, pdf, width, limit):
    clock = time.perf_counter_ns
    rows = []
    with ExitStack() as stack:
        if os.name == 'nt':
            stack.enter_context(os.add_dll_directory(str(library.parent)))
        dll = c.CDLL(str(library))
        doc, err = c.c_void_p(), Error()
        dll.exr_fixed_open.argtypes = [c.c_char_p, c.c_void_p, c.POINTER(c.c_void_p), c.POINTER(Error)]
        dll.exr_fixed_pages.argtypes = [c.c_void_p, c.POINTER(c.c_size_t)]
        dll.exr_fixed_pages.restype = c.POINTER(Page)
        dll.exr_fixed_render.argtypes = [c.c_void_p, c.c_size_t, c.c_double, c.c_void_p,
                                         c.POINTER(Bitmap), c.POINTER(Error)]
        dll.exr_bitmap_free.argtypes = [c.POINTER(Bitmap)]
        dll.exr_fixed_free.argtypes = [c.c_void_p]

        def check(rc):
            if rc:
                raise RuntimeError(f'{rc}: {err.message!r}')

        sampler = stack.enter_context(Sampler())
        path = str(pdf).encode('utf-8')
        start = clock()
        check(dll.exr_fixed_open(path, None, c.byref(doc), c.byref(err)))
        opened = clock() - start
        stack.callback(dll.exr_fixed_free, doc)
        count = c.c_size_t()
        pages = dll.exr_fixed_pages(doc, c.byref(count))
        if not pages or not count.value:
            raise ValueError('no page geometry')
        for i in range(min(limit or count.value, count.value)):
            geom = pages[i].geometry
            x, y, right, top = geom.bounds
            native = (top - y if geom.rotation % 180 else right - x) * geom.unit_scale
            bitmap = Bitmap()
            scale = width / native
            try:
                before = clock()
                rc = dll.exr_fixed_render(doc, i, scale, None, c.byref(bitmap), c.byref(err))
                elapsed = clock() - before
                check(rc)
                if bitmap.width != width or not bitmap.pixels or bitmap.channels != 4:
                    raise ValueError(f'invalid bitmap for page {i + 1}')
                rows.append({'page': i + 1, 'render_ns': elapsed})
            finally:
                dll.exr_bitmap_free(c.byref(bitmap))
    return {'width': width, 'open_ns': opened, 'document_pages': count.value,
            'pages': rows, 'sampled_peak_rss_bytes': sampler.peak,
            'rss_observations': sampler.count, 'rss_interval_seconds': sampler.interval}


def positive(s):
    n = int(s)
    if n < 1:
        raise ValueError('expected positive integer')
    return n


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--library', required=True, type=Path)
    ap.add_argument('--input', required=True, type=Path)
    ap.add_argument('--widths', default='1200,2400')
    ap.add_argument('--pages-limit', type=positive)
    ap.add_argument('--child-width', type=positive, help=argparse.SUPPRESS)
    ap.add_argument('--out', type=Path)
    args = ap.parse_args()
    lib, pdf = args.library.resolve(), args.input.resolve()
    if args.child_width:
        print(json.dumps(capture(lib, pdf, args.child_width, args.pages_limit)))
        return
    widths = [positive(s) for s in args.widths.split(',')]
    report = {'library_sha256': digest_file(lib), 'input_sha256': digest_file(pdf), 'cases': []}
    for width in widths:
        cmd = [sys.executable, __file__, '--library', str(lib), '--input', str(pdf),
               '--child-width', str(width)]
        if args.pages_limit:
            cmd.extend(['--pages-limit', str(args.pages_limit)])
        report['cases'].append(json.loads(subprocess.check_output(cmd, text=True)))
    data = json.dumps(report, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(data + '\n', encoding='utf-8')
    else:
        print(data)


if __name__ == '__main__':
    main()
