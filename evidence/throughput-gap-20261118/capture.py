# SPDX-License-Identifier: MIT
"""Throughput gap @1200 on current main: EXReader vs PDF.js 3.11.174 plus whole-document
class ablations (EXR_ATTRIBUTION_SKIP). No renderer or harness edits.

Each repeat runs one fresh child per arm: EXReader full, PDF.js, and EXReader with one
class skipped. Arm order rotates by repeat and reverses on odd repeats, so every arm is
alternated against the others. Children reuse the unchanged tools/bench_real_doc.py and
tools/bench_large_vs_pdfjs.py child launchers, each behind the unchanged fail-closed
<=15% CPU gate, plus a competing-workload check before and after every child; a child
overlapping a competitor is moved to excluded/ and re-captured.

  python -X utf8 evidence/throughput-gap-20261118/capture.py \
      --library build/perf/libexreader.dll --pdfjs-root C:/Users/Oscar/Documents/Codex/pdfjs-bench2
Re-running resumes from raw/index.json.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
import bench_real_doc as real  # noqa: E402
import bench_large_vs_pdfjs as large  # noqa: E402

CASES = {'real-mixed-120': 120, 'image-heavy-100': 100, 'vector-heavy-100': 100}
ARMS = ('full', 'pdfjs', 'image', 'image-paint', 'path', 'glyph', 'shading', 'softmask', 'group')
WIDTH = 1200


def competitors():
    script = ("Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^(python|node|gcc|cc1|ninja|cmake)\\.exe$' }"
              " | Select-Object ProcessId,ParentProcessId,CommandLine | ConvertTo-Json -Compress")
    proc = subprocess.run(['powershell', '-NoProfile', '-Command', script], capture_output=True, text=True, check=True)
    rows = json.loads(proc.stdout or '[]')
    if isinstance(rows, dict):
        rows = [rows]
    mine = HERE.name
    return [r for r in rows if r['ProcessId'] != os.getpid() and r['ParentProcessId'] != os.getpid()
            and mine not in (r['CommandLine'] or '')
            and any(w in (r['CommandLine'] or '').lower()
                    for w in ('bench', 'capture.py', 'pdfjs', 'cc1', 'ninja', 'cmake', 'ctest'))]


def quiet():
    deadline = time.monotonic() + 3 * 3600
    while rows := competitors():
        print('waiting for competing workload: ' + ', '.join(str(r['ProcessId']) for r in rows), flush=True)
        with (HERE / 'competition.jsonl').open('a', encoding='utf-8') as f:
            f.write(json.dumps({'time': time.time(), 'processes': rows}) + '\n')
        if time.monotonic() >= deadline:
            raise SystemExit('competing workload did not finish (fail closed)')
        time.sleep(20)


def order(rep):
    k = (2 * rep) % len(ARMS)
    arms = list(ARMS[k:] + ARMS[:k])
    return arms[::-1] if rep % 2 else arms


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--library', type=Path, required=True)
    ap.add_argument('--pdfjs-root', type=Path, required=True)
    ap.add_argument('--runs', type=int, default=5)
    ap.add_argument('--repeat', type=int, default=5)
    ap.add_argument('--case', action='append', choices=CASES)
    args = ap.parse_args()
    lib, root = args.library.resolve(), args.pdfjs_root.resolve()
    raw = HERE / 'raw'
    raw.mkdir(exist_ok=True)
    (HERE / 'excluded').mkdir(exist_ok=True)
    index_path = raw / 'index.json'
    record = {'library': str(lib), 'library_sha256': real.digest_file(lib), 'pdfjs_root': str(root),
              'runs': args.runs, 'repeat': args.repeat, 'width': WIDTH, 'idle_threshold': 15.0,
              'arms': list(ARMS), 'samples': []}
    if index_path.exists():
        prev = json.loads(index_path.read_text(encoding='utf-8'))
        assert prev['library_sha256'] == record['library_sha256'], 'DLL changed; use a new directory'
        assert prev['runs'] == args.runs and prev['repeat'] == args.repeat
        record = prev
    done = {(s['case'], s['arm'], s['rep']) for s in record['samples']}
    os.environ.pop('EXR_PDF_IMAGE_CACHE_BYTES', None)
    os.environ.pop('EXR_BUFFER_POOL', None)
    for label in args.case or CASES:
        pdf = ROOT / f'tests/fixtures/pdf-large/{label}.pdf'
        pages = CASES[label]
        for rep in range(args.repeat):
            for pos, arm in enumerate(order(rep)):
                if (label, arm, rep) in done:
                    continue
                path = raw / f'{label}-{arm}-r{rep}.json'
                while True:
                    quiet()
                    os.environ.pop('EXR_ATTRIBUTION_SKIP', None)
                    started = time.time()
                    if arm == 'pdfjs':
                        data = large.run_pdfjs_gated(root, pdf, pages, WIDTH, args.runs, path, 15.0, 900.0)
                    else:
                        if arm != 'full':
                            os.environ['EXR_ATTRIBUTION_SKIP'] = arm
                        data = real.run_child_gated(lib, pdf, pages, WIDTH, args.runs, path, 15.0, 900.0)
                        os.environ.pop('EXR_ATTRIBUTION_SKIP', None)
                    late = competitors()
                    if not late:
                        break
                    dest = HERE / 'excluded' / f'{path.stem}-{int(started)}.json'
                    shutil.move(str(path), dest)
                    with (HERE / 'competition.jsonl').open('a', encoding='utf-8') as f:
                        f.write(json.dumps({'time': time.time(), 'excluded': dest.name, 'processes': late}) + '\n')
                    print(f'excluded {dest.name}: competitor appeared during capture; re-capturing', flush=True)
                assert data['page_count'] == pages
                record['samples'].append({'case': label, 'arm': arm, 'rep': rep, 'position': pos,
                                          'file': path.name, 'started': started,
                                          'pre_cpu_percent': data['pre_cpu_percent'],
                                          'capture_cpu_percent': data['capture_cpu_percent'],
                                          'throughput_pages_per_s': data['throughput_pages_per_s']})
                index_path.write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
                print(f'{label} r{rep} #{pos} {arm:<11} {data["throughput_pages_per_s"]:7.2f} p/s '
                      f'gate={data["pre_cpu_percent"]}%', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
