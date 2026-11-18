# SPDX-License-Identifier: MIT
"""Paired bilateral drawing-class ablation on pages 1-10 of image-heavy-100 at 1200 px.

Each (repeat, class) run keeps every arm in its own live process (document open)
and times one page at a time, rotating the arm order per page and reversing it on
alternate warm sweeps. The first sweep is cold and only supplies pixel hashes.
Usage: ablate.py <libexreader.dll> <repeats> [class ...]
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
from variants import PDF, sha  # noqa: E402

NODE = ROOT.parent / 'pdfjs-bench2'
WORK = HERE / '_work'
RAW = HERE / 'raw'
PAGES = list(range(10))
SWEEPS = 9  # 1 cold + 8 warm

# name -> (EXReader hook value or None, edited PDF present, PDF.js arms present)
CASES = {
    'image':        dict(hook='image', edit=True, js=True),
    'shading':      dict(hook='shading', edit=True, js=True),
    'shading-page': dict(hook=None, edit=True, js=True),
    'softmask':     dict(hook='softmask', edit=True, js=True),
    'gradient':     dict(hook=None, edit=True, js=True),
    'path':         dict(hook='path', edit=True, js=True),
    'glyph':        dict(hook='glyph', edit=True, js=True),
    'clip':         dict(hook=None, edit=True, js=True),
    'group':        dict(hook='group', edit=False, js=False),
}

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
            if p.pid == os.getpid():
                continue
            scripts = [Path(a).name.lower() for a in args if len(a) < 350 and a.endswith(('.py', '.cjs', '.js'))]
            if any(s.startswith(('interleaved_', 'benchmark_', 'paired_')) or
                   (s.startswith('bench_') and (s != 'bench_real_doc.py' or '--child-width' in args)) or
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
    waited = 0
    while True:
        if competing():
            waited += 1
            time.sleep(1)
            continue
        try:
            idle = wait_idle(15 if time.monotonic() - start < 5 else 30, .5)
        except RuntimeError as error:
            if str(error) != 'Invalid system CPU counters':
                raise
            continue
        if idle is None or competing():
            continue
        return idle, time.monotonic() - start

def run(dll, name, rep, reverse_offset):
    case = CASES[name]
    out = RAW / f'r{rep}-{name}.json.gz'
    if out.exists():
        return
    edited = WORK / f'{name}.pdf'
    arms = [('X full', None)]
    if case['hook']:
        arms.append(('X skip', case['hook']))
    if case['edit']:
        arms.append(('X edit', None))
    arms.append(('J full', None))
    if case['js'] and case['edit']:
        arms.append(('J edit', None))
    if not case['js']:
        arms.remove(('J full', None))
    names = [a[0] for a in arms]
    env = {k: v for k, v in os.environ.items() if not k.startswith('EXR_')}
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    idle, waited = gate()
    with ExitStack() as stack:
        workers = {}
        for arm, hook in arms:
            engine, role = arm.split()
            src = edited if role == 'edit' else PDF
            if engine == 'X':
                cmd = [sys.executable, '-B', str(HERE / 'worker.py'), str(dll), str(src)]
            else:
                cmd = ['node', str(HERE / 'worker.cjs'), str(NODE), str(src)]
            w = subprocess.Popen(cmd, env=env | ({'EXR_ATTRIBUTION_SKIP': hook} if hook else {}), stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, text=True, bufsize=1)
            stack.callback(close, w)
            assert response(w) == 'ready'
            workers[arm] = w
        times = {k: [] for k in names}
        hashes = {k: [] for k in names}
        overlaps = 0
        before = cpu_times()
        for r in range(SWEEPS):
            for k in names:
                times[k].append([])
            for i in PAGES:
                if i % 5 == 0 and competing():
                    overlaps += 1
                    while competing():
                        time.sleep(1)
                off = (i + max(0, r - 1) // 2 + reverse_offset) % len(names)
                order = names[off:] + names[:off]
                if r > 0 and r % 2 == 0:
                    order.reverse()
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
        busy = cpu_busy_percent(before, cpu_times())
    data = dict(name=name, rep=rep, width=1200, pages=[p + 1 for p in PAGES], sweeps=SWEEPS, fixture=sha(PDF),
                edit_sha=sha(edited) if case['edit'] else None, dll=sha(dll), times_ns=times, hashes=hashes,
                idle_before=idle, gate_seconds=waited, busy=busy, overlaps=overlaps, arms=names)
    RAW.mkdir(exist_ok=True)
    out.write_bytes(gzip.compress(json.dumps(data).encode(), mtime=0))
    means = {k: round(sum(map(sum, times[k][1:])) / (len(times[k]) - 1) / 1e6, 2) for k in names}
    print(rep, name, means, f'busy={busy:.1f}%', flush=True)

def main():
    dll = Path(sys.argv[1]).resolve()
    repeats = int(sys.argv[2])
    selected = sys.argv[3:] or list(CASES)
    for rep in range(repeats):
        order = selected[::-1] if rep % 2 else selected
        for name in order:
            run(dll, name, rep, rep)

if __name__ == '__main__':
    main()
