# SPDX-License-Identifier: MIT
"""Measure vector-heavy courseware slides at 1200 px with the #267 driver.

Usage: ablate.py <libexreader.dll> <fixture stem> <first page> <last page> [class ...] [--raw path]
Omit classes for a two-arm baseline. Each class uses four arms and its own full control.
"""
import argparse
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
        if p.pid == os.getpid():
            continue
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

def run(dll, pdf, pages, name, rep, candidate):
    out = RAW / f'{pdf.stem}-r{rep + 1}-{name}.json.gz'
    edited = WORK / f'{pdf.stem}-{name}.pdf' if name not in ('baseline', 'group', 'candidate') else None
    hashes_in = dict(fixture=sha(pdf), edit_sha=sha(edited) if edited else None, dll=sha(dll))
    if name == 'candidate':
        hashes_in['candidate_dll'] = sha(candidate)
    if out.exists():
        previous = json.loads(gzip.decompress(out.read_bytes()))
        assert all(previous[key] == value for key, value in hashes_in.items()), out
        assert previous['pages'] == [p + 1 for p in pages], out
        return True
    pairs = [('X full', 'J full')]
    if edited or name in ('group', 'candidate'):
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
            src = (edited or pdf) if role == 'edit' else pdf
            if engine == 'X':
                arm_dll = candidate if name == 'candidate' and role == 'edit' else dll
                cmd = [sys.executable, '-B', str(HERE / 'worker.py'), str(arm_dll), str(src)]
            else:
                cmd = ['node', str(HERE / 'worker.cjs'), str(NODE), str(src)]
            worker_env = env | {'EXR_ATTRIBUTION_SKIP': 'group'} if name == 'group' and arm == 'X edit' else env
            w = subprocess.Popen(cmd, env=worker_env, stdin=subprocess.PIPE, stderr=log,
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
                    if len(pairs) > 1:
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
    data = dict(name=name, rep=rep + 1, width=1200, pages=[p + 1 for p in pages], sweeps=SWEEPS,
                **hashes_in, times_ns=times, hashes=hashes,
                idle_before=idle, gate_seconds=waited, busy=busy, engine_first=ab_first, edit_first=edit_first, arms=names)
    RAW.mkdir(parents=True, exist_ok=True)
    out.write_bytes(gzip.compress(json.dumps(data).encode(), mtime=0))
    means = {k: round(sum(map(sum, times[k][1:])) / (len(times[k]) - 1) / 1e6, 2) for k in names}
    print(pdf.stem, rep + 1, name, means, f'idle gate={idle:.2f}% busy', flush=True)
    return True

def main():
    global RAW
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dll', type=Path)
    parser.add_argument('fixture')
    parser.add_argument('first', type=int)
    parser.add_argument('last', type=int)
    parser.add_argument('classes', nargs='*')
    parser.add_argument('--raw', type=Path, default=RAW)
    parser.add_argument('--candidate', type=Path)
    parser.add_argument('--rounds', type=int, default=3)
    args = parser.parse_args()
    RAW = args.raw
    dll = args.dll.resolve()
    pdf = ROOT / 'tests/fixtures/pdf-large' / (args.fixture + '.pdf')
    pages = range(args.first - 1, args.last)
    selected = args.classes or ['baseline']
    if 'candidate' in selected and not args.candidate:
        parser.error('candidate requires --candidate DLL')
    candidate = args.candidate.resolve() if args.candidate else None
    WORK.mkdir(exist_ok=True)
    for rep in range(args.rounds):
        order = selected[::-1] if rep % 2 else selected
        for name in order:
            while not run(dll, pdf, pages, name, rep, candidate):
                time.sleep(1)

if __name__ == '__main__':
    main()
