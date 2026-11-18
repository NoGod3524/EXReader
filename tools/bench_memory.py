#!/usr/bin/env python3
"""Memory and first-screen benchmark: EXReader fixed-layout PDF vs PDF.js (stdlib only).

Every sample is taken in a NEW child process. The parent drives the child through
named stages over stdin/stdout and reads the child's counters with
GetProcessMemoryInfo(PROCESS_MEMORY_COUNTERS_EX) on the child handle, so both
renderers are measured by the same code path:

  loaded      runtime + renderer code loaded, no document open
  opened      all inputs opened, nothing rendered
  first_page  page 1 of the first input rendered once (the first screen)
  rendered    every page of every input rendered once
  steady      every page rendered --rounds more times (cache steady state)
  closed      every document closed (PDF.js: before GC)
  closed_gc   PDF.js only: after an explicit global.gc()
  cycle_N     after N extra open -> render-all -> close cycles (leak check)

Per stage the parent records WorkingSetSize (RSS), PeakWorkingSetSize,
PrivateUsage and PeakPagefileUsage (peak commit). First screen is the wall time
of the first page render in a fresh process, plus open + first render.

Usage (run from the repository root):
  python -X utf8 tools/bench_memory.py run \
      --side engine=engine:build/perf/libexreader.dll \
      --side pdfjs=pdfjs:C:/Users/Oscar/Documents/Codex/pdfjs-bench2 \
      --case deck=tests/fixtures/pdf-ppt/deck.pdf \
      --case pptx-20=tests/fixtures/pdf-hybrid-real/pptx-20.pdf \
      --widths 1200 --runs 3 --out out/memory.json

Sides alternate in ABAB/BABA order inside one session; each run is gated on the
same CPU idle check as bench_engine.py. Reported values are medians of --runs.
"""
# SPDX-License-Identifier: MIT
import argparse
import ctypes as c
import hashlib
import json
import os
import platform
import statistics
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
MiB = 1024.0 * 1024.0


# ---------------------------------------------------------------- counters
class PMC_EX(c.Structure):
    _fields_ = [('cb', c.c_uint32), ('PageFaultCount', c.c_uint32),
                ('PeakWorkingSetSize', c.c_size_t), ('WorkingSetSize', c.c_size_t),
                ('QuotaPeakPagedPoolUsage', c.c_size_t), ('QuotaPagedPoolUsage', c.c_size_t),
                ('QuotaPeakNonPagedPoolUsage', c.c_size_t), ('QuotaNonPagedPoolUsage', c.c_size_t),
                ('PagefileUsage', c.c_size_t), ('PeakPagefileUsage', c.c_size_t),
                ('PrivateUsage', c.c_size_t)]


def process_memory(handle):
    if os.name != 'nt':
        raise SystemExit('bench_memory.py reads Windows psapi counters; run it on Windows')
    k32 = c.WinDLL('kernel32', use_last_error=True)
    k32.K32GetProcessMemoryInfo.argtypes = [c.c_void_p, c.POINTER(PMC_EX), c.c_uint32]
    k32.K32GetProcessMemoryInfo.restype = c.c_int
    counters = PMC_EX()
    counters.cb = c.sizeof(PMC_EX)
    if not k32.K32GetProcessMemoryInfo(c.c_void_p(handle), c.byref(counters), counters.cb):
        raise OSError(c.get_last_error(), 'GetProcessMemoryInfo failed')
    return {'rss': counters.WorkingSetSize, 'peak_rss': counters.PeakWorkingSetSize,
            'private': counters.PrivateUsage, 'peak_private': counters.PeakPagefileUsage}


# ---------------------------------------------------------------- idle gate
def wait_idle(threshold, timeout_s):
    sys.path.insert(0, str(HERE))
    from bench_engine import wait_idle as gate  # same fail-closed gate as render timing
    return gate(threshold, timeout_s)


# ---------------------------------------------------------------- engine child
def stage(name):
    sys.stdout.write(f'STAGE {name}\n')
    sys.stdout.flush()
    if sys.stdin.readline() == '':
        raise SystemExit('parent went away')


def engine_child(args):
    from benchmark_pdf_blend import Bitmap, Error
    from benchmark_pdf_rect import Page
    directory = os.add_dll_directory(str(Path(args.library).resolve().parent))
    engine = c.CDLL(str(Path(args.library).resolve()))
    engine.exr_fixed_open.argtypes = [c.c_char_p, c.c_void_p, c.POINTER(c.c_void_p), c.POINTER(Error)]
    engine.exr_fixed_pages.argtypes = [c.c_void_p, c.POINTER(c.c_size_t)]
    engine.exr_fixed_pages.restype = c.POINTER(Page)
    engine.exr_fixed_render.argtypes = [c.c_void_p, c.c_size_t, c.c_double, c.c_void_p,
                                      c.POINTER(Bitmap), c.POINTER(Error)]
    engine.exr_bitmap_free.argtypes = [c.POINTER(Bitmap)]
    engine.exr_fixed_free.argtypes = [c.c_void_p]
    error = Error()
    result = {'open_ms': [], 'pages': []}

    def check(status):
        if status:
            raise RuntimeError(f'{status}: {error.message.decode("utf-8", errors="replace")}')

    def open_all():
        docs = []
        for path in args.inputs:
            doc = c.c_void_p()
            t0 = time.perf_counter_ns()
            check(engine.exr_fixed_open(path.encode('utf-8'), None, c.byref(doc), c.byref(error)))
            docs.append([doc, (time.perf_counter_ns() - t0) / 1e6, []])
        for item in docs:
            count = c.c_size_t()
            pages = engine.exr_fixed_pages(item[0], c.byref(count))
            for index in range(count.value):
                g = pages[index].geometry
                native = g.bounds[3] - g.bounds[1] if g.rotation % 180 else g.bounds[2] - g.bounds[0]
                item[2].append(args.width / (native * g.unit_scale))
        return docs

    def render(doc, index, scale):
        bitmap = Bitmap()
        t0 = time.perf_counter_ns()
        status = engine.exr_fixed_render(doc, index, scale, None, c.byref(bitmap), c.byref(error))
        elapsed = (time.perf_counter_ns() - t0) / 1e6
        try:
            check(status)
            if bitmap.width != args.width or not bitmap.pixels:
                raise ValueError(f'unexpected bitmap {bitmap.width}x{bitmap.height}')
        finally:
            engine.exr_bitmap_free(c.byref(bitmap))
        return elapsed

    def render_all(docs, skip_first):
        for d, item in enumerate(docs):
            for index, scale in enumerate(item[2]):
                if skip_first and d == 0 and index == 0:
                    continue
                render(item[0], index, scale)

    def close_all(docs):
        for item in docs:
            engine.exr_fixed_free(item[0])

    stage('loaded')
    docs = open_all()
    result['open_ms'] = [item[1] for item in docs]
    result['pages'] = [len(item[2]) for item in docs]
    stage('opened')
    result['first_render_ms'] = render(docs[0][0], 0, docs[0][2][0])
    stage('first_page')
    render_all(docs, True)
    stage('rendered')
    if args.rounds:
        for _ in range(args.rounds):
            render_all(docs, False)
        stage('steady')
    close_all(docs)
    stage('closed')
    for cycle in range(args.cycles):
        docs = open_all()
        render_all(docs, False)
        close_all(docs)
        stage(f'cycle_{cycle + 1}')
    directory.close()
    sys.stdout.write('RESULT ' + json.dumps(result) + '\n')
    sys.stdout.flush()


# ---------------------------------------------------------------- parent
def drive(cmd, cwd=None, env=None):
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, encoding='utf-8', cwd=cwd, env=env, bufsize=1)
    stages, result = {}, None
    try:
        for line in proc.stdout:
            line = line.rstrip('\n')
            if line.startswith('STAGE '):
                stages[line[6:]] = process_memory(int(proc._handle))
                proc.stdin.write('\n')
                proc.stdin.flush()
            elif line.startswith('RESULT '):
                result = json.loads(line[7:])
        proc.wait(timeout=600)
    finally:
        if proc.poll() is None:
            proc.kill()
    if proc.returncode != 0 or result is None:
        raise SystemExit(f'child failed ({proc.returncode}): {" ".join(map(str, cmd))}\n{proc.stderr.read()[-4000:]}')
    return {'stages': stages, 'result': result}


def side_command(kind, target, inputs, width, rounds, cycles):
    if kind == 'engine':
        return [sys.executable, '-X', 'utf8', str(Path(__file__).resolve()), 'engine-child',
                '--library', str(Path(target).resolve()), '--width', str(width),
                '--rounds', str(rounds), '--cycles', str(cycles), '--inputs', *inputs], None
    if kind == 'pdfjs':
        return ['node', '--expose-gc', str(HERE / 'bench_memory_pdfjs.cjs'), '--pdfjs-root', str(Path(target).resolve()),
                '--width', str(width), '--rounds', str(rounds), '--cycles', str(cycles), '--', *inputs], None
    raise SystemExit(f'unknown side kind {kind}')


def median(values):
    return statistics.median(values) if values else None


def summarize(samples):
    out = {'runs': len(samples), 'stages': {}}
    names = list(samples[0]['stages'])
    for name in names:
        row = {}
        for key in ('rss', 'peak_rss', 'private', 'peak_private'):
            values = [s['stages'][name][key] for s in samples if name in s['stages']]
            row[key + '_mib_samples'] = [round(v / MiB, 2) for v in values]
            row[key + '_mib'] = round(median(values) / MiB, 2)
        out['stages'][name] = row
    first = [s['result']['first_render_ms'] for s in samples]
    opens = [s['result']['open_ms'][0] for s in samples]
    out['first_render_ms_samples'] = [round(v, 3) for v in first]
    out['first_render_ms'] = round(median(first), 3)
    out['open_ms_samples'] = [round(v, 3) for v in opens]
    out['open_ms'] = round(median(opens), 3)
    out['first_screen_ms'] = round(median([a + b for a, b in zip(opens, first)]), 3)
    out['pages'] = samples[0]['result']['pages']
    st = out['stages']
    loaded = st['loaded']['rss_mib']
    pages = sum(out['pages'])
    out['derived'] = {
        'open_delta_mib': round(st['opened']['rss_mib'] - loaded, 2),
        'rendered_delta_mib': round(st['rendered']['rss_mib'] - loaded, 2),
        'peak_delta_mib': round(st[names[-1]]['peak_rss_mib'] - loaded, 2),
        'per_page_mib': round((st['rendered']['rss_mib'] - st['opened']['rss_mib']) / pages, 3) if pages else None,
        'closed_delta_mib': round(st['closed_gc' if 'closed_gc' in st else 'closed']['rss_mib'] - loaded, 2),
        'closed_private_delta_mib': round(st['closed_gc' if 'closed_gc' in st else 'closed']['private_mib']
                                          - st['loaded']['private_mib'], 2),
    }
    return out


def run(args):
    sides = []
    for spec in args.side:
        label, rest = spec.split('=', 1)
        kind, target = rest.split(':', 1)
        sides.append((label, kind, target))
    cases = []
    for spec in args.case:
        label, paths = spec.split('=', 1)
        cases.append((label, [str(Path(p).resolve()) for p in paths.split('+')]))
    report = {'host': {'platform': platform.platform(), 'processor': platform.processor(),
                       'python': sys.version.split()[0],
                       'node': subprocess.run(['node', '--version'], capture_output=True, text=True).stdout.strip()},
              'runs': args.runs, 'rounds': args.rounds, 'cycles': args.cycles,
              'idle_threshold': args.idle_threshold, 'sides': {}, 'inputs': {}, 'cases': {}}
    for label, kind, target in sides:
        path = Path(target)
        report['sides'][label] = {'kind': kind, 'target': str(path.resolve())}
        if kind == 'engine':
            report['sides'][label]['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    for _, paths in cases:
        for p in paths:
            report['inputs'][p] = hashlib.sha256(Path(p).read_bytes()).hexdigest()
    for case, paths in cases:
        for width in args.widths:
            key = f'{case}@{width}'
            raw = {label: [] for label, _, _ in sides}
            gates = []
            for index in range(args.runs):
                busy = wait_idle(args.idle_threshold, args.idle_timeout)
                if busy is None:
                    raise SystemExit(f'machine never went idle before {key} run {index}; retry (fail closed)')
                gates.append(round(busy, 2))
                order = sides if index % 2 == 0 else list(reversed(sides))
                for label, kind, target in order:
                    cmd, cwd = side_command(kind, target, paths, width, args.rounds, args.cycles)
                    raw[label].append(drive(cmd, cwd))
                print(f'  {key} run {index + 1}/{args.runs} idle {busy:.1f}% order '
                      + '/'.join(s[0] for s in order), flush=True)
            report['cases'][key] = {'idle_cpu_percent': gates, 'raw': raw,
                                    'summary': {label: summarize(raw[label]) for label in raw}}
            for label in raw:
                s = report['cases'][key]['summary'][label]
                st = s['stages']
                last = list(st)[-1]
                print(f'{key:>18} {label:<10} loaded {st["loaded"]["rss_mib"]:7.2f}  opened {st["opened"]["rss_mib"]:7.2f}'
                      f'  rendered {st["rendered"]["rss_mib"]:7.2f}  closed {st["closed"]["rss_mib"]:7.2f}'
                      f'  peak {st[last]["peak_rss_mib"]:7.2f} MiB  first {s["first_render_ms"]:8.3f} ms'
                      f'  open+first {s["first_screen_ms"]:8.3f} ms', flush=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')


def main():
    sys.path.insert(0, str(HERE))
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='command', required=True)
    r = sub.add_parser('run')
    r.add_argument('--side', action='append', required=True, help='label=engine:<dll> or label=pdfjs:<root>')
    r.add_argument('--case', action='append', required=True, help='label=<pdf>[+<pdf>...] (+ opens together)')
    r.add_argument('--widths', type=int, nargs='+', default=[1200])
    r.add_argument('--runs', type=int, default=3)
    r.add_argument('--rounds', type=int, default=3)
    r.add_argument('--cycles', type=int, default=0)
    r.add_argument('--idle-threshold', type=float, default=15.0)
    r.add_argument('--idle-timeout', type=float, default=900.0)
    r.add_argument('--out', type=Path, required=True)
    e = sub.add_parser('engine-child')
    e.add_argument('--library', required=True)
    e.add_argument('--width', type=int, required=True)
    e.add_argument('--rounds', type=int, default=0)
    e.add_argument('--cycles', type=int, default=0)
    e.add_argument('--inputs', nargs='+', required=True)
    args = ap.parse_args()
    if args.command == 'run':
        run(args)
    else:
        engine_child(args)


if __name__ == '__main__':
    main()
