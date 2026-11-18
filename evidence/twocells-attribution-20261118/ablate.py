# SPDX-License-Identifier: MIT
"""Slides ablation driver adapted to run the two @1200 cells.

Usage: ablate.py <libexreader.dll> <fixture stem> <first page> <last page> [class ...]
Omit classes for a two-arm baseline. Each class uses four arms and its own full control.
"""
import gzip
import json
import os
import subprocess
import sys
import time
from contextlib import ExitStack
from pathlib import Path

import psutil

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from bench_engine import cpu_busy_percent, cpu_times, wait_idle  # noqa: E402
sys.path.insert(0, str(HERE))
from variants import sha  # noqa: E402

NODE = ROOT.parent / 'pdfjs-bench2'
WORK = HERE / '_work'
RAW = HERE / 'raw'
SWEEPS = 6  # 1 cold + 5 warm

def competing():
    for p in psutil.process_iter(['name']):
        name = (p.info['name'] or '').lower()
        if name in ('cc1.exe', 'cc1plus.exe', 'cl.exe', 'ld.exe', 'ninja.exe', 'ctest.exe'):
            return True
        if name in ('python.exe', 'node.exe'):
            try:
                args = p.cmdline()[1:]
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
            scripts = [Path(a).name.lower() for a in args if len(a) < 350 and a.endswith(('.py', '.cjs', '.js'))]
            if any(s.startswith(('interleaved_', 'benchmark_', 'paired_')) or
                   (s.startswith('bench_') and (s != 'bench_real_doc.py' or '--child-width' in args)) or
                   (s in ('worker.py', 'worker.cjs') and not any(HERE == Path(a).parent for a in args)) or
                   (s == 'capture.py' and any(a in ('child', 'probe-child') for a in args))
                   for s in scripts):
                return True
    return False

def response(worker):
    for line in worker.stdout:
        if line.startswith('@'):
            return line.strip()[1:]
    raise RuntimeError(f'worker exited with {worker.poll()}')

def close(w):
    w.stdin.close()
    try:
        code = w.wait(timeout=20)
    except subprocess.TimeoutExpired:
        w.terminate()
        w.wait()
        raise
    if code:
        raise RuntimeError(f'worker exited with status {code}')

def gate():
    start = time.monotonic()
    while True:
        if competing():
            time.sleep(1)
            continue
        try:
            idle = wait_idle(15, .5)
        except RuntimeError as error:
            if str(error) != 'Invalid system CPU counters':
                raise
            continue
        if idle is None or competing():
            continue
        return idle, time.monotonic() - start

def run(dll, pdf, pages, name, rep):
    out = RAW / f'{pdf.stem}-r{rep + 1}-{name}.json.gz'
    if out.exists():
        return True
    edited = WORK / f'{pdf.stem}-{name}.pdf' if name != 'baseline' else None
    pairs = [('X full', 'J full')]
    if edited:
        pairs.append(('X edit', 'J edit'))
    names = [arm for pair in pairs for arm in pair]
    env = {k: v for k, v in os.environ.items() if not k.startswith('EXR_') and k != 'NODE_OPTIONS'}
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    idle, waited = gate()
    with ExitStack() as stack:
        log = stack.enter_context((WORK / f'{pdf.stem}-stderr.log').open('a', encoding='utf-8'))
        workers = {}
        for arm in names:
            engine, role = arm.split()
            src = edited if role == 'edit' else pdf
            if engine == 'X':
                cmd = [sys.executable, '-B', str(HERE / 'worker.py'), str(dll), str(src)]
            else:
                cmd = ['node', str(HERE / 'worker.cjs'), str(NODE), str(src)]
            w = subprocess.Popen(cmd, env=env, stdin=subprocess.PIPE, stderr=log,
                                 stdout=subprocess.PIPE, text=True, bufsize=1)
            stack.callback(close, w)
            assert response(w) == 'ready'
            workers[arm] = w
        times = {k: [] for k in names}
        hashes = {k: [] for k in names}
        ab_first = []
        edit_first = []
        before = cpu_times()
        for r in range(SWEEPS):
            for k in names:
                times[k].append([])
            for offset, i in enumerate(pages):
                if offset % 5 == 0 and competing():
                    print(rep + 1, name, 'discarded for competing process', flush=True)
                    return False
                # Alternate engines page by page and reverse the starting engine each warm sweep.
                # On four-arm runs, balance which document is rendered first independently.
                js_first = (offset + rep + max(0, r - 1)) % 2
                reverse_pairs = (offset // 2 + rep + r) % 2
                if offset == 0:
                    ab_first.append('J' if js_first else 'X')
                    if edited:
                        edit_first.append(bool(reverse_pairs))
                order = [arm for pair in (pairs[::-1] if reverse_pairs else pairs)
                         for arm in (pair[::-1] if js_first else pair)]
                for k in order:
                    w = workers[k]
                    w.stdin.write(f'{i} {int(r == 0)}\n')
                    w.stdin.flush()
                    ns, sig = json.loads(response(w))
                    assert ns > 0
                    times[k][r].append(ns)
                    if r == 0:
                        assert len(sig) == 64
                        hashes[k].append(sig)
        if competing():
            print(rep + 1, name, 'discarded for competing process', flush=True)
            return False
        busy = cpu_busy_percent(before, cpu_times())
    data = dict(name=name, rep=rep + 1, width=1200, pages=[p + 1 for p in pages], sweeps=SWEEPS, fixture=sha(pdf),
                edit_sha=sha(edited) if edited else None, dll=sha(dll), times_ns=times, hashes=hashes,
                idle_before=idle, gate_seconds=waited, busy=busy, engine_first=ab_first, edit_first=edit_first, arms=names)
    RAW.mkdir(exist_ok=True)
    out.write_bytes(gzip.compress(json.dumps(data).encode(), mtime=0))
    means = {k: round(sum(map(sum, times[k][1:])) / (len(times[k]) - 1) / 1e6, 2) for k in names}
    print(pdf.stem, rep + 1, name, means, f'idle gate={idle:.2f}% busy', flush=True)
    return True

def main():
    dll = Path(sys.argv[1]).resolve()
    pdf = ROOT / 'tests/fixtures/pdf-large' / (sys.argv[2] + '.pdf')
    first, last = map(int, sys.argv[3:5])
    pages = range(first - 1, last)
    selected = sys.argv[5:] or ['baseline']
    WORK.mkdir(exist_ok=True)
    for rep in range(3):
        order = selected[::-1] if rep % 2 else selected
        for name in order:
            while not run(dll, pdf, pages, name, rep):
                time.sleep(1)

if __name__ == '__main__':
    main()
