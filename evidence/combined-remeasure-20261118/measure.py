# SPDX-License-Identifier: MIT
"""Same-session interleaved capture of PDF.js and the eight-build factorial at 1200 px.

Usage: measure.py <dll root> [cell ...]
<dll root>/<arm>/libexreader.dll must exist for every EXReader arm below.
Adapted from evidence/twocells-attribution-20261118/ablate.py (same idle gate,
competing-process check, workers and timers). Each round opens one fresh process
per arm, runs one cold sweep for pixel hashes and five warm sweeps for timing.
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

NODE = ROOT.parent / 'pdfjs-bench2'
WORK = HERE / '_work'
RAW = HERE / 'raw'
SWEEPS = 6  # 1 cold + 5 warm
CELLS = ['image-heavy-100', 'real-mixed-120', 'vector-heavy-100']
# J = PDF.js. orig = the DLL behind the brief's fresh baselines. base = same renderer rebuilt here.
# G = #264 canvas.c, I = #263 affine_image.c, V = densevec blend.c.
ARMS = ['J', 'orig', 'base', 'G', 'I', 'V', 'GI', 'GV', 'IV', 'GIV']


def sha(path):
    import hashlib
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


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
            if any(s.startswith(('interleaved_', 'benchmark_', 'paired_', 'ablate', 'capture')) or
                   (s.startswith('bench_') and (s != 'bench_real_doc.py' or '--child-width' in args)) or
                   (s in ('worker.py', 'worker.cjs') and not any(HERE == Path(a).parent for a in args))
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
        code = w.wait(timeout=30)
    except subprocess.TimeoutExpired:
        w.terminate()
        w.wait()
        raise
    if code:
        raise RuntimeError(f'worker exited with status {code}')


def gate():
    """Fail closed: wait for no competing process and a 500 ms sample at or below 15% busy."""
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


def order_for(offset, sweep, rep):
    """Pages 2m and 2m+1 are exact mirrors (AB.../...BA). The rotation moves a new arm
    to the ends every two pages so no arm keeps the back-to-back boundary. The starting
    direction flips between warm sweeps and between rounds."""
    k = (offset // 2 + 3 * rep) % len(ARMS)
    seq = ARMS[k:] + ARMS[:k]
    return seq[::-1] if (offset + rep + max(0, sweep - 1)) % 2 else seq


def run(dlls, pdf, rep):
    out = RAW / f'{pdf.stem}-r{rep + 1}.json.gz'
    if out.exists():
        return True
    pages = list(range(int(json.loads((ROOT / 'tests/fixtures/pdf-large/manifest.json').read_text())[pdf.stem]['pages'])))
    env = {k: v for k, v in os.environ.items() if not k.startswith('EXR_') and k != 'NODE_OPTIONS'}
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    idle, waited = gate()
    with ExitStack() as stack:
        log = stack.enter_context((WORK / f'{pdf.stem}-stderr.log').open('a', encoding='utf-8'))
        workers = {}
        for arm in ARMS:
            if arm == 'J':
                cmd = ['node', str(HERE / 'worker.cjs'), str(NODE), str(pdf)]
            else:
                cmd = [sys.executable, '-B', str(HERE / 'worker.py'), str(dlls[arm]), str(pdf)]
            w = subprocess.Popen(cmd, env=env, stdin=subprocess.PIPE, stderr=log,
                                 stdout=subprocess.PIPE, text=True, bufsize=1)
            stack.callback(close, w)
            assert response(w) == 'ready'
            workers[arm] = w
        times = {k: [] for k in ARMS}
        hashes = {k: [] for k in ARMS}
        first = []
        before = cpu_times()
        for r in range(SWEEPS):
            for k in ARMS:
                times[k].append([])
            for offset, i in enumerate(pages):
                if offset % 5 == 0 and competing():
                    print(pdf.stem, rep + 1, 'discarded for competing process', flush=True)
                    return False
                order = order_for(offset, r, rep)
                if offset == 0:
                    first.append(order[0])
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
            print(pdf.stem, rep + 1, 'discarded for competing process', flush=True)
            return False
        busy = cpu_busy_percent(before, cpu_times())
    data = dict(cell=pdf.stem, rep=rep + 1, width=1200, pages=[p + 1 for p in pages], sweeps=SWEEPS,
                fixture=sha(pdf), dll={k: sha(v) for k, v in dlls.items()}, arms=ARMS,
                times_ns=times, hashes=hashes, idle_before=idle, gate_seconds=waited, busy=busy,
                first_arm_per_sweep=first)
    RAW.mkdir(exist_ok=True)
    out.write_bytes(gzip.compress(json.dumps(data).encode(), mtime=0))
    means = {k: round(sum(map(sum, times[k][1:])) / (SWEEPS - 1) / 1e6, 1) for k in ARMS}
    print(pdf.stem, rep + 1, means, f'idle gate={idle:.2f}% busy, run busy={busy:.1f}%', flush=True)
    return True


def main():
    root = Path(sys.argv[1]).resolve()
    dlls = {a: root / a / 'libexreader.dll' for a in ARMS if a != 'J'}
    assert all(p.exists() for p in dlls.values())
    cells = sys.argv[2:] or CELLS
    WORK.mkdir(exist_ok=True)
    for rep in range(3):
        for cell in (cells[::-1] if rep % 2 else cells):
            while not run(dlls, ROOT / 'tests/fixtures/pdf-large' / f'{cell}.pdf', rep):
                time.sleep(1)


if __name__ == '__main__':
    main()
