#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""End-to-end N-page real-document throughput, worst-page, first-screen, and Peak RSS benchmark.

Supports:
1. Single-DLL measurement (--library)
2. Paired A/B alternating measurement in one session (--library-a, --library-b)
   Alternates AB / BA order across repeats so both builds share identical session conditions
   while each child process keeps an isolated cold start and PeakWorkingSetSize (GetProcessMemoryInfo).
3. Exhaustive active-RGBA pixel equivalence verification (--verify-pixels) across all N pages.
"""
import argparse
import ctypes as c
import hashlib
import json
import math
import os
import platform
import statistics
import subprocess
import sys
import time
from pathlib import Path

from bench_engine import cpu_busy_percent, cpu_times, wait_idle
from benchmark_pdf_blend import Bitmap, Error
from benchmark_pdf_rect import Page, percentiles, process_memory_bytes


def digest_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def hash_active_rgba(bitmap: Bitmap) -> tuple[str, int]:
    """Hash active RGBA rows without allocating a whole-page Python byte buffer."""
    h = hashlib.sha256()
    row_bytes = bitmap.width * 4
    for y in range(bitmap.height):
        h.update(c.string_at(bitmap.pixels + y * bitmap.stride, row_bytes))
    return h.hexdigest(), bitmap.width * bitmap.height


def child_capture(args):
    directory = os.add_dll_directory(str(args.library.parent)) if os.name == 'nt' else None
    engine = c.CDLL(str(args.library))
    engine.exr_fixed_open.argtypes = [c.c_char_p, c.c_void_p, c.POINTER(c.c_void_p), c.POINTER(Error)]
    engine.exr_fixed_pages.argtypes = [c.c_void_p, c.POINTER(c.c_size_t)]
    engine.exr_fixed_pages.restype = c.POINTER(Page)
    engine.exr_fixed_render.argtypes = [
        c.c_void_p, c.c_size_t, c.c_double, c.c_void_p, c.POINTER(Bitmap), c.POINTER(Error)
    ]
    engine.exr_bitmap_free.argtypes = [c.POINTER(Bitmap)]
    engine.exr_fixed_free.argtypes = [c.c_void_p]
    error = Error()

    def check(status):
        if status:
            raise RuntimeError(f'{status}: {error.message.decode("utf-8", errors="replace")}')

    rss_start, peak_start = process_memory_bytes()
    document = c.c_void_p()
    t0 = time.perf_counter_ns()
    check(engine.exr_fixed_open(str(args.input).encode('utf-8'), None, c.byref(document), c.byref(error)))
    open_ms = (time.perf_counter_ns() - t0) / 1e6
    rss_after_open, peak_after_open = process_memory_bytes()

    try:
        count = c.c_size_t()
        pages_ptr = engine.exr_fixed_pages(document, c.byref(count))
        if not pages_ptr or (args.expect_pages and count.value != args.expect_pages):
            raise ValueError(f'Expected {args.expect_pages} pages, found {count.value}')
        page_count = count.value
        pages = []
        for idx in range(page_count):
            geom = pages_ptr[idx].geometry
            bounds = geom.bounds
            native_w = bounds[3] - bounds[1] if geom.rotation % 180 else bounds[2] - bounds[0]
            scale = args.child_width / (native_w * geom.unit_scale)
            pages.append({
                'page': idx + 1,
                'scale': scale,
                'render_ms': [],
            })

        rounds = []
        round_wall_ms = []
        for iteration in range(args.runs + 1):
            round_times = []
            round_started = time.perf_counter_ns()
            for page in pages:
                bitmap = Bitmap()
                started = time.perf_counter_ns()
                status = engine.exr_fixed_render(
                    document, page['page'] - 1, page['scale'], None, c.byref(bitmap), c.byref(error)
                )
                elapsed = (time.perf_counter_ns() - started) / 1e6
                try:
                    check(status)
                    if bitmap.width != args.child_width or bitmap.channels != 4 or not bitmap.pixels:
                        raise ValueError(f'Unexpected bitmap: {bitmap.width}x{bitmap.height}/{bitmap.channels}')
                    if iteration == 0:
                        rss_now, rss_peak = process_memory_bytes()
                        sig, px_count = hash_active_rgba(bitmap)
                        page.update(
                            dimensions=[bitmap.width, bitmap.height],
                            pixels=px_count,
                            rgba_sha256=sig,
                            first_render_ms=elapsed,
                            rss_after_first_render_bytes=rss_now,
                            peak_rss_after_first_render_bytes=rss_peak,
                        )
                    else:
                        if args.check_determinism:
                            sig, _ = hash_active_rgba(bitmap)
                            if sig != page['rgba_sha256']:
                                raise ValueError(f'Pixels changed between rounds on page {page["page"]}')
                        page['render_ms'].append(elapsed)
                        round_times.append(elapsed)
                finally:
                    engine.exr_bitmap_free(c.byref(bitmap))
            round_elapsed = (time.perf_counter_ns() - round_started) / 1e6
            if iteration == 0:
                cold_round_wall_ms = round_elapsed
            else:
                rounds.append(round_times)
                round_wall_ms.append(round_elapsed)

        rss_end, peak_end = process_memory_bytes()
    finally:
        engine.exr_fixed_free(document)
        if directory:
            directory.close()

    for page in pages:
        page.update(percentiles(page['render_ms']))
    all_samples = [t for row in rounds for t in row]
    page_p50s = [p['p50_ms'] for p in pages]
    worst_by_p50 = max(pages, key=lambda p: p['p50_ms'])
    worst_by_max = max(pages, key=lambda p: p['max_ms'])
    round_sum_ms = [sum(row) for row in rounds]
    wall_p50_ms = statistics.median(round_sum_ms)
    total_wall_ms = sum(round_sum_ms)

    result = {
        'width': args.child_width,
        'page_count': page_count,
        'runs': args.runs,
        'open_ms': round(open_ms, 4),
        'first_page_render_ms': round(pages[0]['first_render_ms'], 4),
        'first_screen_ms': round(open_ms + pages[0]['first_render_ms'], 4),
        'cold_round_wall_ms': round(cold_round_wall_ms, 3),
        'p50_ms': round(statistics.median(all_samples), 4),
        'p95_ms': round(sorted(all_samples)[math.ceil(0.95 * len(all_samples)) - 1], 4),
        'page_p50_median_ms': round(statistics.median(page_p50s), 4),
        'page_p95_ms': round(sorted(page_p50s)[math.ceil(0.95 * len(page_p50s)) - 1], 4),
        'worst_page': worst_by_p50['page'],
        'worst_page_p50_ms': round(worst_by_p50['p50_ms'], 4),
        'worst_page_max_ms': round(worst_by_max['max_ms'], 4),
        'worst_max_page': worst_by_max['page'],
        'round_wall_ms_p50': round(wall_p50_ms, 3),
        'total_measured_wall_ms': round(total_wall_ms, 3),
        'throughput_pages_per_s': round(page_count * 1000.0 / wall_p50_ms, 2) if wall_p50_ms > 0 else 0.0,
        'rss_start_bytes': rss_start,
        'rss_after_open_bytes': rss_after_open,
        'rss_end_bytes': rss_end,
        'peak_rss_bytes': peak_end,
        'peak_rss_mib': round(peak_end / (1024.0 * 1024.0), 2),
        'active_pixels_per_round': sum(p['pixels'] for p in pages),
        'pages': pages,
    }
    args.child_out.parent.mkdir(parents=True, exist_ok=True)
    args.child_out.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    return 0


def run_child_gated(library: Path, input_pdf: Path, expect_pages: int, width: int, runs: int,
                    out_json: Path, idle_threshold: float, idle_timeout: float) -> dict:
    busy = wait_idle(idle_threshold, idle_timeout)
    if busy is None:
        raise SystemExit(f'CPU did not fall to {idle_threshold:g}% or less before {library.name}@{width}px')
    pre_cpu = round(busy, 2)
    before = cpu_times()
    cmd = [
        sys.executable, '-X', 'utf8', str(Path(__file__).resolve()),
        '--library', str(library),
        '--input', str(input_pdf),
        '--expect-pages', str(expect_pages),
        '--runs', str(runs),
        '--child-width', str(width),
        '--child-out', str(out_json),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f'child capture failed ({library}):\n{proc.stdout[-4000:]}\n{proc.stderr[-4000:]}')
    capture_cpu = round(cpu_busy_percent(before, cpu_times()), 2)
    data = json.loads(out_json.read_text(encoding='utf-8'))
    data['pre_cpu_percent'] = pre_cpu
    data['capture_cpu_percent'] = capture_cpu
    return data


def summarize_repeats(repeats: list[dict]) -> dict:
    p50s = sorted(r['p50_ms'] for r in repeats)
    p95s = sorted(r['p95_ms'] for r in repeats)
    worst_p50s = sorted(r['worst_page_p50_ms'] for r in repeats)
    worst_maxs = sorted(r['worst_page_max_ms'] for r in repeats)
    tputs = sorted(r['throughput_pages_per_s'] for r in repeats)
    walls = sorted(r['round_wall_ms_p50'] for r in repeats)
    rss_list = sorted(r['peak_rss_bytes'] for r in repeats)
    first_pages = sorted(r['first_page_render_ms'] for r in repeats)
    first_screens = sorted(r['first_screen_ms'] for r in repeats)
    opens = sorted(r['open_ms'] for r in repeats)
    median_rep = min(repeats, key=lambda r: abs(r['worst_page_p50_ms'] - statistics.median(worst_p50s)))

    # Per-page median across repeats
    page_count = repeats[0]['page_count']
    per_page_summary = []
    for idx in range(page_count):
        pg_p50 = statistics.median(r['pages'][idx]['p50_ms'] for r in repeats)
        pg_p95 = statistics.median(r['pages'][idx]['p95_ms'] for r in repeats)
        pg_max = max(r['pages'][idx]['max_ms'] for r in repeats)
        pg_rss = int(statistics.median(r['pages'][idx]['rss_after_first_render_bytes'] for r in repeats))
        per_page_summary.append({
            'page': idx + 1,
            'p50_ms': round(pg_p50, 4),
            'p95_ms': round(pg_p95, 4),
            'max_ms': round(pg_max, 4),
            'rss_bytes': pg_rss,
            'rgba_sha256': repeats[0]['pages'][idx]['rgba_sha256'],
            'pixels': repeats[0]['pages'][idx]['pixels'],
        })
    worst_pg = max(per_page_summary, key=lambda p: p['p50_ms'])

    return {
        'page_count': page_count,
        'active_pixels_per_round': repeats[0]['active_pixels_per_round'],
        'p50_ms_repeats': [round(v, 3) for v in p50s],
        'p95_ms_repeats': [round(v, 3) for v in p95s],
        'p50_ms_median': round(statistics.median(p50s), 3),
        'p95_ms_median': round(statistics.median(p95s), 3),
        'spread_percent': round(100.0 * (p50s[-1] - p50s[0]) / p50s[0], 1) if p50s[0] else 0.0,
        'worst_page': worst_pg['page'],
        'worst_page_p50_ms_median': round(statistics.median(worst_p50s), 3),
        'worst_page_p50_ms_repeats': [round(v, 3) for v in worst_p50s],
        'worst_page_max_ms_median': round(statistics.median(worst_maxs), 3),
        'round_wall_ms_median': round(statistics.median(walls), 2),
        'throughput_pages_per_s_median': round(statistics.median(tputs), 2),
        'throughput_pages_per_s_repeats': [round(v, 2) for v in tputs],
        'peak_rss_bytes_median': int(statistics.median(rss_list)),
        'peak_rss_mib_median': round(statistics.median(rss_list) / (1024.0 * 1024.0), 2),
        'peak_rss_mib_repeats': [round(v / (1024.0 * 1024.0), 2) for v in rss_list],
        'open_ms_median': round(statistics.median(opens), 3),
        'first_page_render_ms_median': round(statistics.median(first_pages), 3),
        'first_screen_ms_median': round(statistics.median(first_screens), 3),
        'per_page': per_page_summary,
        'repeats': [
            {k: v for k, v in r.items() if k != 'pages'}
            for r in repeats
        ],
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--library', type=Path, help='Single DLL path')
    ap.add_argument('--library-a', type=Path, help='Baseline A DLL path for paired A/B')
    ap.add_argument('--library-b', type=Path, help='Candidate B DLL path for paired A/B')
    ap.add_argument('--input', type=Path, required=True)
    ap.add_argument('--expect-pages', type=int, default=0)
    ap.add_argument('--widths', type=int, nargs='+', default=[1200])
    ap.add_argument('--runs', type=int, default=5)
    ap.add_argument('--repeat', type=int, default=3)
    ap.add_argument('--out', type=Path)
    ap.add_argument('--idle-threshold', type=float, default=15.0)
    ap.add_argument('--idle-timeout', type=float, default=900.0)
    ap.add_argument('--check-determinism', action='store_true')
    ap.add_argument('--child-width', type=int, help=argparse.SUPPRESS)
    ap.add_argument('--child-out', type=Path, help=argparse.SUPPRESS)
    args = ap.parse_args()

    if args.child_width:
        return child_capture(args)

    if not args.out:
        ap.error('--out is required')
    paired = bool(args.library_a and args.library_b)
    if not paired and not args.library:
        ap.error('Provide either --library or both --library-a and --library-b')

    args.input = args.input.resolve()
    args.out = args.out.resolve()
    scratch_dir = args.out.parent / f'.realdoc-{args.out.stem}'
    scratch_dir.mkdir(parents=True, exist_ok=True)

    if not paired:
        lib = args.library.resolve()
        report = {
            'mode': 'single',
            'platform': platform.platform(),
            'python': sys.version,
            'input': str(args.input),
            'input_sha256': digest_file(args.input),
            'library': str(lib),
            'library_sha256': digest_file(lib),
            'runs': args.runs,
            'repeat': args.repeat,
            'idle_threshold_percent': args.idle_threshold,
            'widths': {},
        }
        for width in args.widths:
            repeats = []
            for rep in range(args.repeat):
                out_json = scratch_dir / f'single-w{width}-r{rep}.json'
                data = run_child_gated(
                    lib, args.input, args.expect_pages, width, args.runs,
                    out_json, args.idle_threshold, args.idle_timeout
                )
                repeats.append(data)
            summary = summarize_repeats(repeats)
            report['widths'][str(width)] = summary
            print(
                f"{width:5d} px | pages={summary['page_count']} | p50={summary['p50_ms_median']:7.3f} ms "
                f"| p95={summary['p95_ms_median']:7.3f} ms | worst(p{summary['worst_page']})={summary['worst_page_p50_ms_median']:7.3f} ms "
                f"(max {summary['worst_page_max_ms_median']:7.3f}) | wall={summary['round_wall_ms_median']:8.2f} ms "
                f"| tput={summary['throughput_pages_per_s_median']:6.2f} p/s | RSS={summary['peak_rss_mib_median']:6.2f} MiB "
                f"| first={summary['first_screen_ms_median']:7.3f} ms (open {summary['open_ms_median']:6.3f} + p1 {summary['first_page_render_ms_median']:7.3f})",
                flush=True,
            )
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        return 0

    lib_a = args.library_a.resolve()
    lib_b = args.library_b.resolve()
    report = {
        'mode': 'paired_ab',
        'platform': platform.platform(),
        'python': sys.version,
        'input': str(args.input),
        'input_sha256': digest_file(args.input),
        'library_a': str(lib_a),
        'library_a_sha256': digest_file(lib_a),
        'library_b': str(lib_b),
        'library_b_sha256': digest_file(lib_b),
        'runs': args.runs,
        'repeat': args.repeat,
        'idle_threshold_percent': args.idle_threshold,
        'widths': {},
    }
    for width in args.widths:
        repeats_a, repeats_b = [], []
        pair_orders = []
        for rep in range(args.repeat):
            # Alternate AB on even repeats, BA on odd repeats in the same session
            order = [('A', lib_a), ('B', lib_b)] if rep % 2 == 0 else [('B', lib_b), ('A', lib_a)]
            pair_orders.append(''.join(tag for tag, _ in order))
            pair_results = {}
            for tag, lib in order:
                out_json = scratch_dir / f'pair-{tag}-w{width}-r{rep}.json'
                pair_results[tag] = run_child_gated(
                    lib, args.input, args.expect_pages, width, args.runs,
                    out_json, args.idle_threshold, args.idle_timeout
                )
            repeats_a.append(pair_results['A'])
            repeats_b.append(pair_results['B'])

        sum_a = summarize_repeats(repeats_a)
        sum_b = summarize_repeats(repeats_b)
        mismatched_pages = []
        compared_pixels = 0
        for pa, pb in zip(sum_a['per_page'], sum_b['per_page']):
            compared_pixels += pa['pixels']
            if pa['rgba_sha256'] != pb['rgba_sha256']:
                mismatched_pages.append(pa['page'])

        def pct_delta(before, after):
            return round(100.0 * (after - before) / before, 2) if before else 0.0

        comparison = {
            'pair_orders': pair_orders,
            'identical_pixels': len(mismatched_pages) == 0,
            'compared_pixels': compared_pixels,
            'mismatched_pages': mismatched_pages,
            'p50_ms_delta_pct': pct_delta(sum_a['p50_ms_median'], sum_b['p50_ms_median']),
            'worst_page_p50_ms_delta_pct': pct_delta(sum_a['worst_page_p50_ms_median'], sum_b['worst_page_p50_ms_median']),
            'throughput_delta_pct': pct_delta(sum_a['throughput_pages_per_s_median'], sum_b['throughput_pages_per_s_median']),
            'peak_rss_delta_pct': pct_delta(sum_a['peak_rss_bytes_median'], sum_b['peak_rss_bytes_median']),
            'first_screen_delta_pct': pct_delta(sum_a['first_screen_ms_median'], sum_b['first_screen_ms_median']),
            'A': sum_a,
            'B': sum_b,
        }
        report['widths'][str(width)] = comparison
        print(
            f"{width:5d} px [paired {'/'.join(pair_orders)}] pixels={compared_pixels:,} identical={comparison['identical_pixels']}\n"
            f"  A: p50={sum_a['p50_ms_median']:7.3f} ms | p95={sum_a['p95_ms_median']:7.3f} ms | worst(p{sum_a['worst_page']})={sum_a['worst_page_p50_ms_median']:7.3f} ms "
            f"| tput={sum_a['throughput_pages_per_s_median']:6.2f} p/s | RSS={sum_a['peak_rss_mib_median']:6.2f} MiB | first={sum_a['first_screen_ms_median']:7.3f} ms\n"
            f"  B: p50={sum_b['p50_ms_median']:7.3f} ms ({comparison['p50_ms_delta_pct']:+.2f}%) | p95={sum_b['p95_ms_median']:7.3f} ms "
            f"| worst(p{sum_b['worst_page']})={sum_b['worst_page_p50_ms_median']:7.3f} ms ({comparison['worst_page_p50_ms_delta_pct']:+.2f}%) "
            f"| tput={sum_b['throughput_pages_per_s_median']:6.2f} p/s ({comparison['throughput_delta_pct']:+.2f}%) "
            f"| RSS={sum_b['peak_rss_mib_median']:6.2f} MiB ({comparison['peak_rss_delta_pct']:+.2f}%) "
            f"| first={sum_b['first_screen_ms_median']:7.3f} ms ({comparison['first_screen_delta_pct']:+.2f}%)",
            flush=True,
        )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
