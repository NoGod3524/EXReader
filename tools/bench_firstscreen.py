#!/usr/bin/env python3
"""First-screen benchmark with one explicit definition (stdlib only).

Definition (the "unified first screen"):
  fresh process -> load renderer -> open the document once -> render page 1 once.
  first_render_ms  = wall time of that one render call. Bitmap allocation is
                     inside the timer. PNG encoding, hashing, copying and freeing
                     are outside it.
  open_ms          = wall time of the single open call, reported separately.
  first_screen_ms  = open_ms + first_render_ms.
  Process start-up and renderer module load are excluded from both timers.

Subcommands:
  tools   Run the child code paths of the existing tools (benchmark_pdf_rect.py as
          driven by bench_engine.py, bench_memory.py, bench_real_doc.py) and this
          tool's own child on the same DLL and fixture. The order rotates on every
          run and each run is idle-gated.
  run     Unified first screen for EXReader and PDF.js. Every sample is a new
          process, sides alternate ABAB/BABA, and every run is idle-gated.
  ablate  Per-class disabling with a diagnostic DLL that honours
          EXR_ATTRIBUTION_SKIP=<image|path|glyph|group|shading>. Every arm is a
          new process. The arm order rotates on each run.
  child   (internal) one unified sample.

  python -X utf8 tools/bench_firstscreen.py run \
      --side engine=engine:build/perf/libexreader.dll \
      --side pdfjs=pdfjs:C:/Users/Oscar/Documents/Codex/pdfjs-bench2 \
      --case deck=tests/fixtures/pdf-ppt/deck.pdf --widths 600 1200 --runs 3 --out out/fs.json
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
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def stats(values):
    ordered = sorted(values)
    low = ordered[0]
    return {'median': round(statistics.median(ordered), 3), 'min': round(low, 3), 'max': round(ordered[-1], 3),
            'spread_percent': round(100.0 * (ordered[-1] - low) / low, 1) if low else 0.0,
            'samples': [round(v, 3) for v in values]}


def gate(threshold, timeout):
    from bench_engine import wait_idle
    busy = wait_idle(threshold, timeout)
    if busy is None:
        raise SystemExit(f'CPU never fell to {threshold:g}% or less; retry (fail closed)')
    return round(busy, 2)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# ------------------------------------------------------------------ unified child
def child(args):
    from benchmark_pdf_blend import Bitmap, Error
    from benchmark_pdf_rect import Page
    library = Path(args.library).resolve()
    directory = os.add_dll_directory(str(library.parent))
    engine = c.CDLL(str(library))
    engine.exr_fixed_open.argtypes = [c.c_char_p, c.c_void_p, c.POINTER(c.c_void_p), c.POINTER(Error)]
    engine.exr_fixed_pages.argtypes = [c.c_void_p, c.POINTER(c.c_size_t)]
    engine.exr_fixed_pages.restype = c.POINTER(Page)
    engine.exr_fixed_render.argtypes = [c.c_void_p, c.c_size_t, c.c_double, c.c_void_p,
                                      c.POINTER(Bitmap), c.POINTER(Error)]
    engine.exr_bitmap_free.argtypes = [c.POINTER(Bitmap)]
    engine.exr_fixed_free.argtypes = [c.c_void_p]
    error, doc = Error(), c.c_void_p()

    def check(status):
        if status:
            raise RuntimeError(f'{status}: {error.message.decode("utf-8", errors="replace")}')

    t0 = time.perf_counter_ns()
    check(engine.exr_fixed_open(os.fsencode(args.input), None, c.byref(doc), c.byref(error)))
    open_ms = (time.perf_counter_ns() - t0) / 1e6
    count = c.c_size_t()
    pages = engine.exr_fixed_pages(doc, c.byref(count))
    g = pages[args.page - 1].geometry
    native = g.bounds[3] - g.bounds[1] if g.rotation % 180 else g.bounds[2] - g.bounds[0]
    scale = args.width / (native * g.unit_scale)
    times, digest = [], None
    for i in range(1 + args.warm):
        bitmap = Bitmap()
        t0 = time.perf_counter_ns()
        status = engine.exr_fixed_render(doc, args.page - 1, scale, None, c.byref(bitmap), c.byref(error))
        elapsed = (time.perf_counter_ns() - t0) / 1e6
        try:
            check(status)
            if bitmap.width != args.width or not bitmap.pixels:
                raise ValueError(f'unexpected bitmap {bitmap.width}x{bitmap.height}')
            if i == 0:
                h = hashlib.sha256()
                for y in range(bitmap.height):
                    h.update(c.string_at(bitmap.pixels + y * bitmap.stride, bitmap.width * 4))
                digest = h.hexdigest()
        finally:
            engine.exr_bitmap_free(c.byref(bitmap))
        times.append(elapsed)
    engine.exr_fixed_free(doc)
    directory.close()
    sys.stderr.flush()
    print('RESULT ' + json.dumps({'open_ms': open_ms, 'first_render_ms': times[0], 'warm_render_ms': times[1:],
                                  'page_count': count.value, 'page': args.page, 'rgba_sha256': digest}), flush=True)


def run_child(library, pdf, width, page=1, warm=0, env=None):
    cmd = [sys.executable, '-X', 'utf8', str(Path(__file__).resolve()), 'child', '--library', str(library),
           '--input', str(pdf), '--width', str(width), '--page', str(page), '--warm', str(warm)]
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if proc.returncode:
        raise SystemExit(f'child failed: {proc.stderr[-3000:]}')
    line = next(l for l in proc.stdout.splitlines() if l.startswith('RESULT '))
    out = json.loads(line[7:])
    out['trace'] = [l.split()[1:] for l in proc.stderr.splitlines() if l.startswith('ATTR ')]
    # Optional diagnostic line per image-cache miss: object, decode ms, width, height, has soft mask.
    out['image_decodes'] = [{'object': int(f[0]), 'decode_ms': float(f[1]), 'width': int(f[2]), 'height': int(f[3]),
                             'soft_mask': bool(int(f[4]))}
                            for f in (l.split()[1:] for l in proc.stderr.splitlines() if l.startswith('IMGDEC '))]
    return out


def parse_cases(specs):
    cases = []
    for spec in specs:
        label, path = spec.split('=', 1)
        cases.append((label, Path(path).resolve()))
    return cases


# ------------------------------------------------------------------ tools
def tool_rect(library, pdf, pages, width, scratch):
    # Exactly what bench_engine.py runs per repeat (it defaults to --runs 20).
    out = scratch / 'rect'
    out.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, '-X', 'utf8', str(HERE / 'benchmark_pdf_rect.py'), 'capture', '--library', str(library),
           '--input', str(pdf), '--expect-pages', str(pages), '--output', str(out), '--widths', str(width),
           '--runs', '20', '--child', str(width)]
    subprocess.run(cmd, check=True, capture_output=True)
    data = json.loads((out / f'{width}.json').read_text(encoding='utf-8'))
    return {'first_render_ms': data['pages'][0]['first_render_ms'], 'open_ms': data['open_ms'],
            'open_calls_before_render': len(data['open_ms_samples'])}


def tool_memory(library, pdf, pages, width, scratch):
    # bench_memory.py's engine side with the #247 settings (--rounds 3 --cycles 2).
    import bench_memory
    cmd, cwd = bench_memory.side_command('engine', str(library), [str(pdf)], width, 3, 2)
    data = bench_memory.drive(cmd, cwd)['result']
    return {'first_render_ms': data['first_render_ms'], 'open_ms': data['open_ms'][0],
            'open_calls_before_render': 1}


def tool_realdoc(library, pdf, pages, width, scratch, realdoc_tools):
    out = scratch / 'realdoc.json'
    cmd = [sys.executable, '-X', 'utf8', str(realdoc_tools / 'bench_real_doc.py'), '--library', str(library),
           '--input', str(pdf), '--expect-pages', str(pages), '--runs', '5', '--child-width', str(width),
           '--child-out', str(out)]
    subprocess.run(cmd, check=True, capture_output=True)
    data = json.loads(out.read_text(encoding='utf-8'))
    return {'first_render_ms': data['first_page_render_ms'], 'open_ms': data['open_ms'],
            'open_calls_before_render': 1}


def tool_unified(library, pdf, pages, width, scratch):
    data = run_child(library, pdf, width)
    if data['page_count'] != pages:
        raise SystemExit(f'expected {pages} pages, found {data["page_count"]}')
    return {'first_render_ms': data['first_render_ms'], 'open_ms': data['open_ms'], 'open_calls_before_render': 1}


def tools_cmd(args):
    library = args.library.resolve()
    realdoc = args.realdoc_tools.resolve()
    tools = [('bench_engine/benchmark_pdf_rect', tool_rect), ('bench_memory', tool_memory),
             ('bench_real_doc', lambda *a: tool_realdoc(*a, realdoc)), ('bench_firstscreen', tool_unified)]
    report = {'library': str(library), 'library_sha256': sha256(library), 'runs': args.runs,
              'platform': platform.platform(), 'cases': {}}
    with tempfile.TemporaryDirectory() as tmp:
        scratch = Path(tmp)
        for spec in args.case:
            label, rest = spec.split('=', 1)
            path, pages = rest.rsplit(':', 1)
            pdf, pages = Path(path).resolve(), int(pages)
            for width in args.widths:
                key = f'{label}@{width}'
                raw = {name: [] for name, _ in tools}
                orders, gates = [], []
                for run in range(args.runs):
                    gates.append(gate(args.idle_threshold, args.idle_timeout))
                    order = tools[run % len(tools):] + tools[:run % len(tools)]
                    orders.append([n for n, _ in order])
                    for name, fn in order:
                        raw[name].append(fn(library, pdf, pages, width, scratch))
                    print(f'  {key} run {run + 1}/{args.runs} idle {gates[-1]:.1f}%', flush=True)
                report['cases'][key] = {'input': str(pdf), 'input_sha256': sha256(pdf), 'idle_cpu_percent': gates,
                                        'orders': orders, 'tools': {
                    name: {'first_render_ms': stats([r['first_render_ms'] for r in rows]),
                           'open_ms': stats([r['open_ms'] for r in rows]),
                           'open_calls_before_render': rows[0]['open_calls_before_render']}
                    for name, rows in raw.items()}}
                for name, row in report['cases'][key]['tools'].items():
                    f = row['first_render_ms']
                    print(f'{key:>16} {name:<32} first {f["median"]:9.3f} ms (spread {f["spread_percent"]:5.1f}%)'
                          f'  open {row["open_ms"]["median"]:7.3f} ms', flush=True)
    write(args.out, report)


# ------------------------------------------------------------------ run
def run_cmd(args):
    import bench_memory
    sides = []
    for spec in args.side:
        label, rest = spec.split('=', 1)
        kind, target = rest.split(':', 1)
        sides.append((label, kind, Path(target).resolve()))
    report = {'definition': 'fresh process -> open once -> render page 1 once; render timer only '
                            '(bitmap allocation inside; PNG/hash/copy/free outside); open reported separately',
              'platform': platform.platform(), 'runs': args.runs, 'sides': {}, 'cases': {}}
    for label, kind, target in sides:
        report['sides'][label] = {'kind': kind, 'target': str(target)}
        if kind == 'engine':
            report['sides'][label]['sha256'] = sha256(target)
    for label, pdf in parse_cases(args.case):
        for width in args.widths:
            key = f'{label}@{width}'
            raw = {s[0]: [] for s in sides}
            gates = []
            for run in range(args.runs):
                gates.append(gate(args.idle_threshold, args.idle_timeout))
                for name, kind, target in (sides if run % 2 == 0 else sides[::-1]):
                    if kind == 'engine':
                        r = run_child(target, pdf, width)
                        raw[name].append({'first_render_ms': r['first_render_ms'], 'open_ms': r['open_ms'],
                                          'rgba_sha256': r['rgba_sha256']})
                    else:
                        cmd, cwd = bench_memory.side_command('pdfjs', str(target), [str(pdf)], width, 0, 0)
                        r = bench_memory.drive(cmd, cwd)['result']
                        raw[name].append({'first_render_ms': r['first_render_ms'], 'open_ms': r['open_ms'][0]})
            summary = {}
            for name, rows in raw.items():
                summary[name] = {'first_render_ms': stats([r['first_render_ms'] for r in rows]),
                                 'open_ms': stats([r['open_ms'] for r in rows]),
                                 'first_screen_ms': stats([r['first_render_ms'] + r['open_ms'] for r in rows])}
            report['cases'][key] = {'input': str(pdf), 'input_sha256': sha256(pdf), 'idle_cpu_percent': gates,
                                    'raw': raw, 'summary': summary}
            print(f'{key:>16} ' + '  '.join(
                f'{n} {s["first_render_ms"]["median"]:8.3f} ms ({s["first_render_ms"]["spread_percent"]:4.1f}%)'
                for n, s in summary.items()), flush=True)
    write(args.out, report)


# ------------------------------------------------------------------ ablate
TRACE_FIELDS = ['page', 'content_bytes', 'source_paint_ms', 'source_paints', 'mask_build_ms', 'mask_builds',
                'shading_samples', 'image_ms', 'image_decode_ms', 'image_cache_hits', 'image_cache_misses',
                'axial_samples']


def ablate_cmd(args):
    library = args.library.resolve()
    modes = ['full'] + args.modes
    report = {'library': str(library), 'library_sha256': sha256(library), 'runs': args.runs, 'warm': args.warm,
              'platform': platform.platform(), 'cases': {}}
    for label, pdf in parse_cases(args.case):
        for width in args.widths:
            key = f'{label}@{width}#p{args.page}'
            raw = {m: [] for m in modes}
            gates = []
            for run in range(args.runs):
                gates.append(gate(args.idle_threshold, args.idle_timeout))
                for mode in modes[run % len(modes):] + modes[:run % len(modes)]:
                    env = dict(os.environ, EXR_ATTRIBUTION_TRACE='1', EXR_PDF_IMAGE_PROFILE='1')
                    env.pop('EXR_ATTRIBUTION_SKIP', None)
                    if mode != 'full':
                        env['EXR_ATTRIBUTION_SKIP'] = mode
                    r = run_child(library, pdf, width, page=args.page, warm=args.warm, env=env)
                    r['trace'] = [dict(zip(TRACE_FIELDS, map(float, t))) for t in r['trace']]
                    raw[mode].append(r)
            summary = {}
            for mode in modes:
                rows = raw[mode]
                row = {'cold_ms': stats([r['first_render_ms'] for r in rows]),
                       'warm_ms': stats([statistics.median(r['warm_render_ms']) for r in rows]) if args.warm else None,
                       'cold_trace': {k: statistics.median(r['trace'][0][k] for r in rows) for k in TRACE_FIELDS}}
                if mode != 'full':
                    # Unchanged pixels mean the page has nothing of this class to skip.
                    row['pixels_changed'] = rows[0]['rgba_sha256'] != raw['full'][0]['rgba_sha256']
                    row['paired_cold_saving_ms'] = stats([f['first_render_ms'] - d['first_render_ms']
                                                          for f, d in zip(raw['full'], rows)])
                    if args.warm:
                        row['paired_warm_saving_ms'] = stats([statistics.median(f['warm_render_ms'])
                                                              - statistics.median(d['warm_render_ms'])
                                                              for f, d in zip(raw['full'], rows)])
                if mode == 'full':
                    # Decodes happen only on the cold render (cache misses); median per image across runs.
                    per_image = {}
                    for r in rows:
                        for d in r['image_decodes']:
                            per_image.setdefault(d['object'], dict(d, decode_ms=[]))['decode_ms'].append(d['decode_ms'])
                    row['cold_image_decodes'] = sorted(
                        (dict(d, decode_ms=round(statistics.median(d['decode_ms']), 3)) for d in per_image.values()),
                        key=lambda d: -d['decode_ms'])
                summary[mode] = row
            report['cases'][key] = {'input': str(pdf), 'input_sha256': sha256(pdf), 'idle_cpu_percent': gates,
                                    'raw': raw, 'summary': summary}
            for mode, row in summary.items():
                save = row.get('paired_cold_saving_ms', {}).get('median', 0.0)
                warm = row['warm_ms']['median'] if row['warm_ms'] else float('nan')
                print(f'{key:>18} {mode:<8} cold {row["cold_ms"]["median"]:8.3f} ms  warm {warm:8.3f} ms'
                      f'  cold saving {save:8.3f} ms', flush=True)
    write(args.out, report)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='command', required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument('--widths', type=int, nargs='+', default=[600, 1200])
    common.add_argument('--runs', type=int, default=3)
    common.add_argument('--idle-threshold', type=float, default=15.0)
    common.add_argument('--idle-timeout', type=float, default=900.0)
    common.add_argument('--out', type=Path, required=True)
    t = sub.add_parser('tools', parents=[common])
    t.add_argument('--library', type=Path, required=True)
    t.add_argument('--case', action='append', required=True, help='label=<pdf>:<pages>')
    t.add_argument('--realdoc-tools', type=Path, required=True,
                   help='directory holding bench_real_doc.py and the helpers it imports')
    r = sub.add_parser('run', parents=[common])
    r.add_argument('--side', action='append', required=True, help='label=engine:<dll> or label=pdfjs:<root>')
    r.add_argument('--case', action='append', required=True, help='label=<pdf>')
    a = sub.add_parser('ablate', parents=[common])
    a.add_argument('--library', type=Path, required=True, help='diagnostic DLL honouring EXR_ATTRIBUTION_SKIP')
    a.add_argument('--case', action='append', required=True, help='label=<pdf>')
    a.add_argument('--page', type=int, default=1)
    a.add_argument('--warm', type=int, default=3)
    a.add_argument('--modes', nargs='+', default=['image', 'path', 'glyph', 'group', 'shading'])
    ch = sub.add_parser('child')
    ch.add_argument('--library', required=True)
    ch.add_argument('--input', required=True)
    ch.add_argument('--width', type=int, required=True)
    ch.add_argument('--page', type=int, default=1)
    ch.add_argument('--warm', type=int, default=0)
    args = ap.parse_args()
    {'tools': tools_cmd, 'run': run_cmd, 'ablate': ablate_cmd, 'child': child}[args.command](args)


if __name__ == '__main__':
    main()
