#!/usr/bin/env python3
"""Canonical EXReader PDF render benchmark.

Why this exists: earlier measurements of the same build varied 5.7 ms vs 9.5 ms only
because one run happened while two agents were compiling. Timing must be taken on an
idle machine and reported with dispersion, otherwise the target is meaningless.

Usage:
  python bench_engine.py --library build/perf/libexreader.dll \
      --input tests/fixtures/pdf-hybrid-real/pptx-20.pdf --expect-pages 20 \
      --widths 600 1200 2400 --runs 20 --repeat 3 --out evidence/bench.json

Each capture is idle-gated. The report includes per-width p50/p95, repeat spread,
and system CPU before and during each capture (including the benchmark itself).
"""
import argparse
import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

import ctypes as c


def cpu_times():
    if os.name == 'nt':
        idle, kernel, user = (c.c_uint64() for _ in range(3))
        if not c.windll.kernel32.GetSystemTimes(c.byref(idle), c.byref(kernel), c.byref(user)):
            raise c.WinError()
        return idle.value, kernel.value + user.value
    if sys.platform.startswith('linux'):
        with open('/proc/stat', encoding='ascii') as stat:
            times = [int(value) for value in stat.readline().split()[1:9]]
        return times[3] + times[4], sum(times)
    raise SystemExit(f'System CPU sampling is unavailable on {sys.platform}')


def cpu_busy_percent(before, after):
    idle = after[0] - before[0]
    total = after[1] - before[1]
    if total <= 0 or not 0 <= idle <= total:
        raise RuntimeError('Invalid system CPU counters')
    return 100.0 * (total - idle) / total


def wait_idle(threshold, timeout_s):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        before = cpu_times()
        time.sleep(0.5)
        busy = cpu_busy_percent(before, cpu_times())
        if busy <= threshold:
            return busy
        time.sleep(max(0.0, min(2.0, deadline - time.monotonic())))
    return None


def run_capture(script, library, input_pdf, pages, widths, runs, out_dir):
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, '-X', 'utf8', str(script), 'capture',
           '--library', str(library), '--input', str(input_pdf),
           '--expect-pages', str(pages), '--output', str(out_dir),
           '--widths', *[str(w) for w in widths], '--runs', str(runs)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit('capture failed:\n' + proc.stdout[-4000:] + proc.stderr[-4000:])
    return proc.stdout


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--library', type=Path, required=True)
    ap.add_argument('--input', type=Path, required=True)
    ap.add_argument('--expect-pages', type=int, required=True)
    ap.add_argument('--widths', type=int, nargs='+', default=[600, 1200, 2400])
    ap.add_argument('--runs', type=int, default=20)
    ap.add_argument('--repeat', type=int, default=3)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--repo', type=Path, default=Path('.'))
    ap.add_argument('--idle-threshold', type=float, default=15.0)
    ap.add_argument('--idle-timeout', type=float, default=900.0)
    args = ap.parse_args()
    if args.repeat < 1:
        ap.error('--repeat must be at least 1')
    if not 0 <= args.idle_threshold <= 100 or not 0 <= args.idle_timeout < float('inf'):
        ap.error('Require a CPU threshold in [0, 100] and a finite nonnegative timeout')

    script = args.repo / 'tools' / 'benchmark_pdf_rect.py'
    if not script.exists():
        raise SystemExit(f'missing capture harness: {script}')

    report = {'library': str(args.library), 'input': str(args.input),
              'runs': args.runs, 'repeat': args.repeat,
              'idle_threshold_percent': args.idle_threshold, 'widths': {}}

    for width in args.widths:
        repeats = []
        for index in range(args.repeat):
            out_dir = args.out.parent / f'.repeat-{index}' / str(width)
            busy = wait_idle(args.idle_threshold, args.idle_timeout)
            if busy is None:
                raise SystemExit(f'CPU did not fall to {args.idle_threshold:g}% or less '
                                 f'for {width}px repeat {index + 1}')
            pre_cpu = round(busy, 2)
            report.setdefault('idle_cpu_percent', pre_cpu)
            before = cpu_times()
            run_capture(script, args.library, args.input, args.expect_pages,
                        [width], args.runs, out_dir)
            capture_cpu = round(cpu_busy_percent(before, cpu_times()), 2)
            data = json.loads((out_dir / f'{width}.json').read_text(encoding='utf-8'))
            repeats.append({'p50_ms': data['p50_ms'], 'p95_ms': data['p95_ms'],
                            'open_ms': data['open_ms'],
                            'first_page_render_ms': data['pages'][0]['first_render_ms'],
                            'pre_cpu_percent': pre_cpu, 'capture_cpu_percent': capture_cpu})
        p50s = sorted(r['p50_ms'] for r in repeats)
        p95s = sorted(r['p95_ms'] for r in repeats)
        report['widths'][str(width)] = {
            'p50_ms_repeats': [round(v, 3) for v in p50s],
            'p95_ms_repeats': [round(v, 3) for v in p95s],
            'p50_ms_median': round(statistics.median(p50s), 3),
            'p50_ms_best': round(p50s[0], 3),
            'p95_ms_median': round(statistics.median(p95s), 3),
            'spread_percent': round(100.0 * (p50s[-1] - p50s[0]) / p50s[0], 1) if p50s[0] else 0.0,
            'open_ms_median': round(statistics.median(r['open_ms'] for r in repeats), 3),
            'first_page_render_ms_median': round(statistics.median(r['first_page_render_ms'] for r in repeats), 3),
            'repeats': repeats,
        }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    for width, row in report['widths'].items():
        print('%6s px  p50 median %7.3f ms  best %7.3f  p95 %7.3f  spread %5.1f%%  open %6.3f ms'
              % (width, row['p50_ms_median'], row['p50_ms_best'], row['p95_ms_median'],
                 row['spread_percent'], row['open_ms_median']))
        for index, repeat in enumerate(row['repeats'], 1):
            print(f'  repeat {index}: p50 {repeat["p50_ms"]:.3f} ms  p95 {repeat["p95_ms"]:.3f} ms'
                  f'  first page {repeat["first_page_render_ms"]:.3f} ms'
                  f'  CPU pre {repeat["pre_cpu_percent"]:.2f}% / capture {repeat["capture_cpu_percent"]:.2f}%')


if __name__ == '__main__':
    main()
