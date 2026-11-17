#!/usr/bin/env python3
"""Canonical EXReader PDF render benchmark.

Why this exists: earlier measurements of the same build varied 5.7 ms vs 9.5 ms only
because one run happened while two agents were compiling. Timing must be taken on an
idle machine and reported with dispersion, otherwise the target is meaningless.

Usage:
  python bench_engine.py --library build/perf/libexreader.dll \
      --input tests/fixtures/pdf-hybrid-real/pptx-20.pdf --expect-pages 20 \
      --widths 600 1200 2400 --runs 20 --repeat 3 --out evidence/bench.json

It refuses to time while the machine is busy, runs the upstream capture harness
`--repeat` times, and reports per-width p50/p95 plus the spread across repeats.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import ctypes as c


def cpu_busy_percent():
    if os.name != 'nt':
        return 0.0
    import ctypes.wintypes as w
    class FILETIME(c.Structure):
        _fields_ = [('lo', w.DWORD), ('hi', w.DWORD)]
    idle, kernel, user = FILETIME(), FILETIME(), FILETIME()
    c.windll.kernel32.GetSystemTimes(c.byref(idle), c.byref(kernel), c.byref(user))
    def q(f):
        return (f.hi << 32) | f.lo
    idle1, busy1 = q(idle), q(kernel) + q(user)
    time.sleep(0.5)
    c.windll.kernel32.GetSystemTimes(c.byref(idle), c.byref(kernel), c.byref(user))
    idle2, busy2 = q(idle), q(kernel) + q(user)
    di, db = idle2 - idle1, busy2 - busy1
    # GetSystemTimes kernel includes idle: total is kernel + user,
    # and busy is total minus idle (adding idle again makes idle CPUs read 50%).
    total = db
    return 100.0 * (db - di) / total if total else 0.0


def wait_idle(threshold, timeout_s):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        busy = cpu_busy_percent()
        if busy <= threshold:
            return busy
        time.sleep(2.0)
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

    script = args.repo / 'tools' / 'benchmark_pdf_rect.py'
    if not script.exists():
        raise SystemExit(f'missing capture harness: {script}')

    busy = wait_idle(args.idle_threshold, args.idle_timeout)
    if busy is None:
        print('WARNING: machine never went idle; results are contended', file=sys.stderr)
        busy = -1.0

    report = {'library': str(args.library), 'input': str(args.input),
              'runs': args.runs, 'repeat': args.repeat,
              'idle_cpu_percent': round(busy, 2), 'widths': {}}

    for width in args.widths:
        repeats = []
        for index in range(args.repeat):
            out_dir = args.out.parent / f'.repeat-{index}' / str(width)
            run_capture(script, args.library, args.input, args.expect_pages,
                        [width], args.runs, out_dir)
            data = json.loads((out_dir / f'{width}.json').read_text(encoding='utf-8'))
            repeats.append({'p50_ms': data['p50_ms'], 'p95_ms': data['p95_ms'],
                            'open_ms': data['open_ms'],
                            'pages': [p.get('p50_ms') for p in data['pages']]})
        p50s = sorted(r['p50_ms'] for r in repeats)
        p95s = sorted(r['p95_ms'] for r in repeats)
        report['widths'][str(width)] = {
            'p50_ms_repeats': [round(v, 3) for v in p50s],
            'p95_ms_repeats': [round(v, 3) for v in p95s],
            'p50_ms_median': round(p50s[len(p50s) // 2], 3),
            'p50_ms_best': round(p50s[0], 3),
            'p95_ms_median': round(p95s[len(p95s) // 2], 3),
            'spread_percent': round(100.0 * (p50s[-1] - p50s[0]) / p50s[0], 1) if p50s[0] else 0.0,
            'open_ms_median': round(sorted(r['open_ms'] for r in repeats)[len(repeats) // 2], 3),
        }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    for width, row in report['widths'].items():
        print('%6s px  p50 median %7.3f ms  best %7.3f  p95 %7.3f  spread %5.1f%%  open %6.3f ms'
              % (width, row['p50_ms_median'], row['p50_ms_best'], row['p95_ms_median'],
                 row['spread_percent'], row['open_ms_median']))


if __name__ == '__main__':
    main()
