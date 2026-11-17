#!/usr/bin/env python3
"""Alternate two Release DLLs and compare every active RGBA pixel."""
# SPDX-License-Identifier: MIT
import argparse
import json
from pathlib import Path
import platform
import statistics
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from bench_engine import cpu_busy_percent, cpu_times, run_capture, wait_idle
from benchmark_pdf_rect import compare, digest, write_json

FIXTURES = {
    'pptx-20': ('pdf-hybrid-real/pptx-20.pdf', 20, (600, 1200, 2400)),
    'deck': ('pdf-ppt/deck.pdf', 15, (600, 1200)),
    'word-5': ('pdf-hybrid-real/word-5.pdf', 5, (600, 1200)),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('baseline', type=Path)
    parser.add_argument('simd', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--idle-timeout', type=float, default=900)
    parser.add_argument('--pairs', type=int, default=3)
    args = parser.parse_args()
    if args.pairs < 1 or not 0 < args.idle_timeout < float('inf'):
        parser.error('Require positive pairs and a finite positive idle timeout')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    libraries = {'A': args.baseline.resolve(), 'B': args.simd.resolve()}
    script = ROOT / 'tools/benchmark_pdf_rect.py'
    report = {
        'platform': platform.platform(), 'processor': platform.processor(), 'python': sys.version,
        'libraries': {name: digest(path) for name, path in libraries.items()},
        'capture_script_sha256': digest(script), 'idle_threshold_percent': 15,
        'requested_pairs': args.pairs, 'runs_per_capture': 5, 'captures': [], 'complete': False,
    }
    comparisons = []
    write_json(output / 'ab.json', report)
    for repeat in range(1, args.pairs + 1):
        for name, (relative, pages, widths) in FIXTURES.items():
            pdf = ROOT / 'tests/fixtures' / relative
            for width in widths:
                paths = {}
                for variant, library in libraries.items():
                    directory = output / 'captures' / str(repeat) / name / str(width) / variant
                    busy = wait_idle(report['idle_threshold_percent'], args.idle_timeout)
                    if busy is None:
                        report['idle_timeout_at'] = [repeat, name, width, variant]
                        write_json(output / 'ab.json', report)
                        raise SystemExit(f'Idle gate timed out at pair {repeat}, {name}, {width}px, {variant}')
                    before = cpu_times()
                    run_capture(script, library, pdf, pages, [width], 5, directory)
                    capture_cpu = cpu_busy_percent(before, cpu_times())
                    data = json.loads((directory / f'{width}.json').read_text(encoding='utf-8'))
                    paths[variant] = directory
                    pixel_count = sum(w * h for w, h in (p['dimensions'] for p in data['pages']))
                    report['captures'].append({
                        'pair': repeat, 'fixture': name, 'width': width, 'variant': variant,
                        'pre_cpu_percent': busy, 'capture_cpu_percent': capture_cpu,
                        'p50_ms': data['p50_ms'], 'p95_ms': data['p95_ms'],
                        'open_ms': data['open_ms'], 'first_open_ms': data['open_ms_samples'][0],
                        'mean_render_ns_per_output_pixel': sum(map(sum, data['rounds'])) * 1e6
                        / (pixel_count * len(data['rounds'])),
                        'raw': str(directory.relative_to(output) / f'{width}.json'),
                    })
                    write_json(output / 'ab.json', report)
                    print(f'{repeat} {name} {width} {variant}: {data["p50_ms"]:.4f} ms, CPU {busy:.2f}%', flush=True)
                if repeat == 1:
                    comparisons.append((name, width, paths))
    rows = []
    for name, (_, _, widths) in FIXTURES.items():
        for width in widths:
            row = {'fixture': name, 'width': width}
            for variant in libraries:
                captures = [r for r in report['captures']
                            if (r['fixture'], r['width'], r['variant']) == (name, width, variant)]
                row[variant] = {key: statistics.median(r[key] for r in captures)
                                for key in ('p50_ms', 'p95_ms', 'open_ms', 'first_open_ms',
                                            'mean_render_ns_per_output_pixel')}
                p50s = [r['p50_ms'] for r in captures]
                row[variant]['p50_spread_percent'] = 100 * (max(p50s) - min(p50s)) / min(p50s)
            rows.append(row)
    report.update(rows=rows, complete=True)
    write_json(output / 'ab.json', report)

    # Compare after timing so the pixel walk cannot influence the next capture.
    diffs = []
    for name, width, paths in comparisons:
        directory = output / 'pixels' / name / str(width)
        directory.mkdir(parents=True)
        compare(argparse.Namespace(before=paths['A'], after=paths['B'], output=directory))
        diff = json.loads((directory / 'diff.json').read_text(encoding='utf-8'))
        for page in diff['pages']:
            page['fixture'] = name
            diffs.append(page)
    pixels = {'compared_pixels': sum(p['compared_pixels'] for p in diffs),
              'different_pixels': sum(p['different_pixels'] for p in diffs),
              'max_channel_delta': max(p['max_channel_delta'] for p in diffs),
              'rgba_rmse': (sum(p['rgba_rmse'] ** 2 * p['compared_pixels'] for p in diffs)
                            / sum(p['compared_pixels'] for p in diffs)) ** 0.5,
              'pages': diffs}
    write_json(output / 'pixels.json', pixels)
    return bool(pixels['different_pixels'])


if __name__ == '__main__':
    sys.exit(main())
