#!/usr/bin/env python3
"""Idle-gated, alternating PDF open and optional render measurements."""
# SPDX-License-Identifier: MIT
import argparse
import ctypes as c
import hashlib
import json
import os
from pathlib import Path
import statistics
import time

from bench_engine import wait_idle
from benchmark_pdf_blend import Error
from benchmark_pdf_rect import Bitmap, Page


def paired_render(engines, filename, width):
    documents, geometry, samples = {}, {}, {name: [] for name in engines}
    error = Error()
    for name, engine in engines.items():
        engine.exr_fixed_pages.argtypes = [c.c_void_p, c.POINTER(c.c_size_t)]
        engine.exr_fixed_pages.restype = c.POINTER(Page)
        engine.exr_fixed_render.argtypes = [c.c_void_p, c.c_size_t, c.c_double, c.c_void_p, c.POINTER(Bitmap), c.POINTER(Error)]
        engine.exr_bitmap_free.argtypes = [c.POINTER(Bitmap)]
        document, count = c.c_void_p(), c.c_size_t()
        if engine.exr_fixed_open(filename, None, c.byref(document), c.byref(error)):
            raise RuntimeError(error.message.decode())
        documents[name] = document
        pages = engine.exr_fixed_pages(document, c.byref(count))
        geometry[name] = []
        for page in range(count.value):
            g = pages[page].geometry
            native = g.bounds[3] - g.bounds[1] if g.rotation % 180 else g.bounds[2] - g.bounds[0]
            geometry[name].append(width / (native * g.unit_scale))
    assert len(geometry['baseline']) == len(geometry['candidate'])
    try:
        for iteration in range(13):
            for page in range(len(geometry['baseline'])):
                order = list(engines) if (iteration + page) % 2 else list(reversed(engines))
                warm_pixels = []
                for name in order:
                    bitmap = Bitmap()
                    started = time.perf_counter_ns()
                    status = engines[name].exr_fixed_render(documents[name], page, geometry[name][page], None, c.byref(bitmap), c.byref(error))
                    elapsed = (time.perf_counter_ns() - started) / 1e6
                    if status:
                        raise RuntimeError(error.message.decode())
                    if iteration:
                        samples[name].append(elapsed)
                    else:
                        warm_pixels.append(b''.join(c.string_at(bitmap.pixels + row * bitmap.stride, bitmap.width * 4) for row in range(bitmap.height)))
                    engines[name].exr_bitmap_free(c.byref(bitmap))
                if not iteration:
                    assert warm_pixels[0] == warm_pixels[1]
    finally:
        for name, document in documents.items():
            engines[name].exr_fixed_free(document)
    result = {'width': width, 'rounds': 12, 'warmup_rounds': 1}
    for name, values in samples.items():
        result[name] = {'p50_ms': statistics.median(values), 'samples_ms': values}
    result['change_percent'] = 100 * (result['candidate']['p50_ms'] / result['baseline']['p50_ms'] - 1)
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--baseline', type=Path, required=True)
    ap.add_argument('--candidate', type=Path, required=True)
    ap.add_argument('--input', type=Path, nargs='+', required=True)
    ap.add_argument('--samples', type=int, default=1000)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--render-width', type=int, default=0)
    args = ap.parse_args()
    engines, directories = {}, []
    report = {'samples': args.samples, 'libraries': {}, 'inputs': {}}
    for name in ('baseline', 'candidate'):
        path = getattr(args, name).resolve()
        if os.name == 'nt':
            directories.append(os.add_dll_directory(str(path.parent)))
        engine = c.CDLL(str(path))
        engine.exr_fixed_open.argtypes = [c.c_char_p, c.c_void_p, c.POINTER(c.c_void_p), c.POINTER(Error)]
        engine.exr_fixed_free.argtypes = [c.c_void_p]
        engines[name] = engine
        report['libraries'][name] = {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    assert engines['baseline']._handle != engines['candidate']._handle
    for path in args.input:
        busy = wait_idle(15, 900)
        if busy is None:
            raise RuntimeError('Machine did not become idle')
        samples = {name: [] for name in engines}
        filename = str(path.resolve()).encode('utf-8')
        for iteration in range(args.samples + 50):
            order = list(engines) if iteration % 2 else list(reversed(engines))
            for name in order:
                document, error = c.c_void_p(), Error()
                started = time.perf_counter_ns()
                status = engines[name].exr_fixed_open(filename, None, c.byref(document), c.byref(error))
                elapsed = (time.perf_counter_ns() - started) / 1e6
                if status:
                    raise RuntimeError(error.message.decode())
                engines[name].exr_fixed_free(document)
                if iteration >= 50:
                    samples[name].append(elapsed)
        result = {'idle_cpu_percent': busy, 'input_sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
        for name, values in samples.items():
            result[name] = {'p50_ms': statistics.median(values), 'samples_ms': values}
        result['change_percent'] = 100 * (result['candidate']['p50_ms'] / result['baseline']['p50_ms'] - 1)
        if args.render_width:
            if wait_idle(15, 900) is None:
                raise RuntimeError('Machine did not become idle')
            result['render'] = paired_render(engines, filename, args.render_width)
        report['inputs'][str(path)] = result
        print(f"{path.name}: {result['baseline']['p50_ms']:.6f} -> {result['candidate']['p50_ms']:.6f} ms ({result['change_percent']:+.2f}%)")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    for directory in directories:
        directory.close()


if __name__ == '__main__':
    main()
