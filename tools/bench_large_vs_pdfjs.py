#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Hundred-page PDFs: EXReader vs PDF.js, alternating A/B in one session.

Each repeat runs one fresh EXReader child (tools/bench_real_doc.py child mode) and one
fresh PDF.js child (tools/bench_pdfjs_large.cjs), ABAB on even repeats and BA on odd
ones, each behind the same fail-closed CPU idle gate as bench_engine.py. Both children
write the same JSON schema and both are summarized by bench_real_doc.summarize_repeats,
so p50 / p95 / worst page / throughput / peak RSS / first screen share one definition.

Usage (from the repository root):
  python -X utf8 tools/bench_large_vs_pdfjs.py \
      --library build/perf/libexreader.dll \
      --pdfjs-root C:/Users/Oscar/Documents/Codex/pdfjs-bench2 \
      --case real-mixed-120=tests/fixtures/pdf-large/real-mixed-120.pdf:120 \
      --case image-heavy-100=tests/fixtures/pdf-large/image-heavy-100.pdf:100 \
      --case vector-heavy-100=tests/fixtures/pdf-large/vector-heavy-100.pdf:100 \
      --widths 600 1200 --runs 5 --repeat 3 --out evidence/pdfjs-large-doc-20261118/results.json
"""
import argparse
import json
import platform
import statistics
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from bench_engine import cpu_busy_percent, cpu_times, wait_idle  # noqa: E402
from bench_real_doc import digest_file, run_child_gated, summarize_repeats  # noqa: E402

MiB = 1024.0 * 1024.0


def run_pdfjs_gated(root, input_pdf, pages, width, runs, out_json, threshold, timeout):
    busy = wait_idle(threshold, timeout)
    if busy is None:
        raise SystemExit(f'CPU did not fall to {threshold:g}% or less before pdfjs@{width}px (fail closed; retry)')
    before = cpu_times()
    cmd = ['node', str(HERE / 'bench_pdfjs_large.cjs'), '--pdfjs-root', str(root), '--input', str(input_pdf),
           '--expect-pages', str(pages), '--width', str(width), '--runs', str(runs), '--out', str(out_json)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f'pdfjs child failed:\n{proc.stdout[-4000:]}\n{proc.stderr[-4000:]}')
    data = json.loads(out_json.read_text(encoding='utf-8'))
    data['pre_cpu_percent'] = round(busy, 2)
    data['capture_cpu_percent'] = round(cpu_busy_percent(before, cpu_times()), 2)
    return data


def extra(repeats):
    """Fields summarize_repeats does not carry: renderer-only RSS delta and PDF.js GC share."""
    med = statistics.median
    row = {'peak_rss_delta_mib_median': round(med((r['peak_rss_bytes'] - r['rss_start_bytes']) / MiB
                                                  for r in repeats), 2),
           'cold_round_wall_ms_median': round(med(r['cold_round_wall_ms'] for r in repeats), 2)}
    if 'gc_warm_share_pct' in repeats[0]:
        row['gc_warm_share_pct_median'] = round(med(r['gc_warm_share_pct'] for r in repeats), 2)
        row['render_only_p50_ms_median'] = round(med(r['render_only_p50_ms'] for r in repeats), 3)
    return row


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--library', type=Path, required=True)
    ap.add_argument('--pdfjs-root', type=Path, required=True)
    ap.add_argument('--case', action='append', required=True, help='label=<pdf>:<pages>')
    ap.add_argument('--widths', type=int, nargs='+', default=[600, 1200])
    ap.add_argument('--runs', type=int, default=5)
    ap.add_argument('--repeat', type=int, default=3)
    ap.add_argument('--idle-threshold', type=float, default=15.0)
    ap.add_argument('--idle-timeout', type=float, default=900.0)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()

    lib = args.library.resolve()
    root = args.pdfjs_root.resolve()
    out = args.out.resolve()
    scratch = out.parent / f'.raw-{out.stem}'
    scratch.mkdir(parents=True, exist_ok=True)
    pdfjs_version = json.loads((root / 'node_modules/pdfjs-dist/package.json').read_text(encoding='utf-8'))['version']
    canvas_version = json.loads((root / 'node_modules/canvas/package.json').read_text(encoding='utf-8'))['version']
    report = {
        'platform': platform.platform(), 'processor': platform.processor(), 'python': sys.version.split()[0],
        'node': subprocess.run(['node', '--version'], capture_output=True, text=True).stdout.strip(),
        'pdfjs_dist': pdfjs_version, 'pdfjs_build': 'legacy (Node, in-process fake worker)',
        'canvas': canvas_version,
        'library': str(lib), 'library_sha256': digest_file(lib),
        'runs': args.runs, 'repeat': args.repeat, 'idle_threshold_percent': args.idle_threshold,
        'cases': {},
    }
    for spec in args.case:
        label, rest = spec.split('=', 1)
        pdf, pages = rest.rsplit(':', 1)
        pdf, pages = Path(pdf).resolve(), int(pages)
        for width in args.widths:
            key = f'{label}@{width}'
            raw = {'exreader': [], 'pdfjs': []}
            orders = []
            for rep in range(args.repeat):
                order = ['exreader', 'pdfjs'] if rep % 2 == 0 else ['pdfjs', 'exreader']
                orders.append('/'.join(order))
                for side in order:
                    path = scratch / f'{label}-w{width}-r{rep}-{side}.json'
                    if side == 'exreader':
                        data = run_child_gated(lib, pdf, pages, width, args.runs, path,
                                               args.idle_threshold, args.idle_timeout)
                    else:
                        data = run_pdfjs_gated(root, pdf, pages, width, args.runs, path,
                                               args.idle_threshold, args.idle_timeout)
                    raw[side].append(data)
                print(f'  {key} repeat {rep + 1}/{args.repeat} {orders[-1]}', flush=True)
            case = {'input': str(pdf), 'input_sha256': digest_file(pdf), 'width': width, 'orders': orders}
            for side, repeats in raw.items():
                summary = summarize_repeats(repeats)
                summary.update(extra(repeats))
                case[side] = summary
                print(f'{key:>22} {side:<8} p50 {summary["p50_ms_median"]:8.3f}  p95 {summary["p95_ms_median"]:8.3f}'
                      f'  worst p{summary["worst_page"]} {summary["worst_page_p50_ms_median"]:8.3f}'
                      f' (max {summary["worst_page_max_ms_median"]:8.3f})  tput {summary["throughput_pages_per_s_median"]:7.2f} p/s'
                      f'  peakRSS {summary["peak_rss_mib_median"]:7.2f} MiB (+{summary["peak_rss_delta_mib_median"]:.2f})'
                      f'  first {summary["first_screen_ms_median"]:8.3f} ms'
                      + (f'  gc {summary["gc_warm_share_pct_median"]:.1f}%' if 'gc_warm_share_pct_median' in summary else ''),
                      flush=True)
            report['cases'][key] = case
            out.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')  # checkpoint per case
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
