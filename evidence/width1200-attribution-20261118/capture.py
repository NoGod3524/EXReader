# SPDX-License-Identifier: MIT
"""Width attribution, no render-source edits. Run from any directory.

Reuses #252's linker probe and Document bindings, bench_real_doc's complete
throughput child, and bench_firstscreen's fresh-process first-page child.
Every child is fail-closed idle gated; width pairs reverse on alternate repeats.
"""
import argparse
import ctypes as c
import importlib.util
import json
import os
from pathlib import Path
import statistics as st
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
import bench_real_doc as real
import bench_firstscreen as first
from benchmark_pdf_rect import process_memory_bytes

spec = importlib.util.spec_from_file_location('tail_capture', ROOT / 'evidence/p95-tail-20261118/capture.py')
tail = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tail)
MODES = ('full', 'path', 'glyph', 'image', 'shading', 'group')
MODE_ID = {'full': 0, 'image': 1, 'path': 2, 'glyph': 3, 'group': 4, 'shading': 5}
CASES = {'real-mixed-120': 120, 'image-heavy-100': 100, 'vector-heavy-100': 100}
FIELDS = ('malloc calloc realloc free requested_bytes allocator_ms canvas_create_ms canvas_creates '
          'canvas_image_ms canvas_images canvas_paint_ms canvas_paints pdf_pool_bytes fixed_pool_bytes mask_canvas_paint_ms canvas_output_bytes').split()


def competitors():
    script = "Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^(python|node|gcc|cc1|ninja|cmake)\\.exe$' } | Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress"
    proc = subprocess.run(['powershell', '-NoProfile', '-Command', script], capture_output=True, text=True, check=True)
    rows = json.loads(proc.stdout or '[]')
    if isinstance(rows, dict):
        rows = [rows]
    return [r for r in rows if r['ProcessId'] != os.getpid()
            and 'width1200-attribution-20261118' not in (r['CommandLine'] or '')
            and any(w in (r['CommandLine'] or '').lower() for w in ('bench', 'capture.py', 'pdfjs_ab', 'cc1', 'ninja', 'cmake'))]


def quiet():
    deadline = time.monotonic() + 1800
    while rows := competitors():
        print('Waiting for competing workload: ' + ', '.join(str(r['ProcessId']) for r in rows), flush=True)
        with (HERE / 'competition.jsonl').open('a', encoding='utf-8') as f:
            f.write(json.dumps({'time': time.time(), 'processes': rows}) + '\n')
        if time.monotonic() >= deadline:
            raise SystemExit('Competing workload did not finish (fail closed)')
        time.sleep(15)


def save(path, data):
    path.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')


def telemetry(args):
    tail.WIDTH = args.width
    os.environ['EXR_PDF_IMAGE_PROFILE'] = '1'
    with os.add_dll_directory(str(args.dll.parent)):
        engine = c.CDLL(str(args.dll))
        engine.width_read.argtypes = [c.POINTER(c.c_double)]
        start = process_memory_bytes()
        doc = tail.Document(engine, args.pdf)
        original_read = engine.tail_read
        last_metrics = []

        def read_before_bitmap_free(page, images):
            original_read(page, images)
            values = (c.c_double * 16)()
            engine.width_read(values)
            last_metrics[:] = values

        engine.tail_read = read_before_bitmap_free
        opened = process_memory_bytes()
        rounds = []
        prior = dict.fromkeys(('hits', 'misses', 'evictions', 'decode_ms'), 0)
        for iteration in range(args.runs + 1):
            pages = []
            for page in range(1, len(doc.scales) + 1):
                row = doc.render(page, trace=True, checksum=iteration == 0, timed=True)
                row['metrics'] = dict(zip(FIELDS, last_metrics))
                images = row['images']
                row['cache_delta'] = {k: images[k] - prior[k] for k in prior}
                prior = {k: images[k] for k in prior}
                row['rss_bytes'], row['peak_bytes'] = process_memory_bytes()
                pages.append(row)
            rounds.append(pages)
        doc.close()
    save(args.out, {'width': args.width, 'page_count': len(doc.scales), 'rss_start': start,
                    'rss_open': opened, 'rounds': rounds})


def run(args):
    os.environ.pop('EXR_BUFFER_POOL', None)
    os.environ['EXR_PDF_IMAGE_PROFILE'] = '0'
    os.environ['EXR_PDF_IMAGE_CACHE_BYTES'] = str(args.cache_mib * 1024**2)
    out = HERE / (args.phase + (f'-{args.cache_mib}mib' if args.cache_mib != 64 else ''))
    out.mkdir(exist_ok=True)
    record = {'phase': args.phase, 'dll': str(args.dll), 'dll_sha256': real.digest_file(args.dll),
              'runs': args.runs, 'repeat': args.repeat, 'idle_threshold': 15, 'cache_mib': args.cache_mib, 'samples': []}
    if (out / 'index.json').exists():
        previous = json.loads((out / 'index.json').read_text())
        assert previous['dll_sha256'] == record['dll_sha256']
        assert previous['runs'] == args.runs and previous['repeat'] == args.repeat
        record = previous
    completed = {(r['case'], r['mode'], r['width'], r['rep']) for r in record['samples']}
    modes = MODES if args.phase == 'ablation' else ('full',)
    for label in args.case or CASES:
        pdf = ROOT / f'tests/fixtures/pdf-large/{label}.pdf'
        for rep in range(args.repeat):
            rotated = modes[rep % len(modes):] + modes[:rep % len(modes)]
            for mode in rotated:
                for width in ((600, 1200) if rep % 2 == 0 else (1200, 600)):
                    if (label, mode, width, rep) in completed:
                        continue
                    quiet()
                    path = out / f'{label}-{mode}-{width}-r{rep}.json'
                    os.environ.pop('EXR_ATTRIBUTION_SKIP', None)
                    if mode != 'full':
                        os.environ['EXR_ATTRIBUTION_SKIP'] = mode
                    control = None
                    control_path = out / f'{label}-control64-{width}-r{rep}.json'

                    def cache_control():
                        quiet()
                        os.environ['EXR_PDF_IMAGE_CACHE_BYTES'] = str(64 * 1024**2)
                        data = real.run_child_gated(args.dll, pdf, CASES[label], width, args.runs, control_path, 15, 60)
                        os.environ['EXR_PDF_IMAGE_CACHE_BYTES'] = str(args.cache_mib * 1024**2)
                        if competitors():
                            raise SystemExit('Competing workload during cache control (fail closed)')
                        return {k: v for k, v in data.items() if k != 'pages'}

                    paired_cache = args.phase == 'baseline' and args.cache_mib != 64
                    if paired_cache and rep % 2 == 0:
                        control = cache_control()
                    if args.phase in ('baseline', 'ablation', 'parity'):
                        row = real.run_child_gated(args.dll, pdf, CASES[label], width, args.runs, path, 15, 60)
                        assert row['page_count'] == CASES[label]
                        summary = {k: v for k, v in row.items() if k != 'pages'}
                    else:
                        busy = first.gate(15, 60)
                        if args.phase == 'firstscreen':
                            summary = first.run_child(args.dll, pdf, width)
                            save(path, summary)
                        else:
                            subprocess.run([sys.executable, '-X', 'utf8', str(__file__), 'child',
                                            '--dll', str(args.dll), '--pdf', str(pdf), '--width', str(width),
                                            '--runs', str(args.runs), '--out', str(path)], check=True)
                            data = json.loads(path.read_text())
                            assert data['page_count'] == CASES[label]
                            summary = {'page_count': data['page_count']}
                        summary['pre_cpu_percent'] = busy
                    if paired_cache:
                        if rep % 2:
                            control = cache_control()
                        summary['control64'] = control
                        summary['control64_file'] = str(control_path.relative_to(HERE))
                        summary['cache_order'] = '64/256' if rep % 2 == 0 else '256/64'
                    if competitors():
                        raise SystemExit('Competing workload appeared during capture; sample excluded (fail closed)')
                    record['samples'].append({'case': label, 'mode': mode, 'width': width, 'rep': rep,
                                              'file': str(path.relative_to(HERE)), **summary})
                    save(out / 'index.json', record)
                    print(f'{args.phase} {label} {mode} {width} r{rep}: '
                          f'{summary.get("round_wall_ms_p50", "captured")} CPU={summary["pre_cpu_percent"]}', flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('phase', choices=('build', 'baseline', 'ablation', 'telemetry', 'firstscreen', 'parity', 'child'))
    ap.add_argument('--dll', type=Path)
    ap.add_argument('--build', type=Path)
    ap.add_argument('--case', action='append', choices=CASES)
    ap.add_argument('--runs', type=int, default=5)
    ap.add_argument('--repeat', type=int, default=3)
    ap.add_argument('--cache-mib', type=int, default=64)
    ap.add_argument('--pdf', type=Path)
    ap.add_argument('--width', type=int)
    ap.add_argument('--out', type=Path)
    args = ap.parse_args()
    if args.phase == 'build':
        tail.HERE = HERE
        scratch = ROOT / 'build/width-probe'
        scratch.mkdir(parents=True, exist_ok=True)
        print(tail.build_probe(args.build, scratch))
    elif args.phase == 'child':
        telemetry(args)
    else:
        run(args)


if __name__ == '__main__':
    main()
