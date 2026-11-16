#!/usr/bin/env python3
"""Alternate HEAD/candidate fresh processes for PDF open, first render and repaint."""
# SPDX-License-Identifier: MIT
import argparse
import hashlib
import json
from pathlib import Path
import platform
import statistics
import subprocess
import sys

from benchmark_pdf_blend import measure
from benchmark_pdf_rect import percentiles


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before', type=Path, required=True)
    parser.add_argument('--after', type=Path, required=True)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--runs', type=int, default=9)
    parser.add_argument('--widths', type=int, nargs='+', default=[1200, 2400])
    parser.add_argument('--native-width', type=float, default=960)
    parser.add_argument('--child', choices=['before', 'after'])
    args = parser.parse_args()
    args.before, args.after, args.input = args.before.resolve(), args.after.resolve(), args.input.resolve()
    if args.runs < 5 or args.native_width <= 0 or any(not 1 <= width <= 16384 for width in args.widths):
        parser.error('At least five runs and positive native width / device widths required')
    if args.child:
        print(json.dumps(measure(getattr(args, args.child), args.input, args.widths[0] / args.native_width, 8)))
        return
    report = {'platform': platform.platform(), 'python': sys.version, 'runs': args.runs,
              'widths': args.widths, 'native_width': args.native_width, 'repaints_per_process': 8,
              'clock': 'time.perf_counter_ns',
              'scope': 'Alternating fresh Python/ctypes processes; first native open (DLL already loaded), first page-1 render, eight repaints. Disk cache/frequency/background load uncontrolled.',
              'input_sha256': hashlib.sha256(args.input.read_bytes()).hexdigest(),
              'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'library_sha256': {name: hashlib.sha256(getattr(args, name).read_bytes()).hexdigest()
                                 for name in ('before', 'after')}, 'results': {}}
    for width in args.widths:
        records = {'before': [], 'after': []}
        order = []
        for iteration in range(args.runs):
            names = ('before', 'after') if iteration % 2 == 0 else ('after', 'before')
            for name in names:
                result = subprocess.run([sys.executable, __file__, '--before', str(args.before), '--after', str(args.after),
                                         '--input', str(args.input), '--output', str(args.output), '--child', name,
                                         '--widths', str(width), '--native-width', str(args.native_width)],
                                        capture_output=True, text=True, check=True)
                records[name].append(json.loads(result.stdout))
                order.append(name)
        signatures = {record['rgba_sha256'] for samples in records.values() for record in samples}
        if len(signatures) != 1:
            raise ValueError('Pixel hashes differ between fresh processes / implementations')
        entry = {'process_order': order, 'samples': records, 'summary': {},
                 'paired_first_render_delta_p50_ms': statistics.median(
                     b['first_render_ms'] - a['first_render_ms'] for a, b in zip(records['before'], records['after']))}
        for name, samples in records.items():
            entry['summary'][name] = {
                'open': percentiles([r['open_ms'] for r in samples]),
                'first_render': percentiles([r['first_render_ms'] for r in samples]),
                'open_plus_first_render': percentiles([r['open_ms'] + r['first_render_ms'] for r in samples]),
                'repaint': percentiles([t for r in samples for t in r['repaint_ms_samples']])}
        report['results'][str(width)] = entry
        print(f'{width}px: ' + json.dumps(entry['summary']), flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
