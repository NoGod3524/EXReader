#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Alternate baseline/current fresh-process measurements using the existing PDF harness."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('baseline', type=Path)
    parser.add_argument('current', type=Path)
    parser.add_argument('fixtures', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--runs', type=int, default=5)
    parser.add_argument('--scale', type=float, default=4)
    parser.add_argument('--repaints', type=int, default=8)
    parser.add_argument('--case', action='append', choices=['flat', 'primitives', 'state', 'groups', 'compound', 'ap-groups'])
    args = parser.parse_args()
    if args.runs < 5:
        parser.error('at least five alternating rounds are required')
    script = Path(__file__).with_name('benchmark_pdf_blend.py')
    report = {'runs': args.runs, 'scale': args.scale, 'repaints': args.repaints, 'order': 'baseline/current on even rounds, reversed on odd rounds',
              'scope': 'fresh Python/ctypes hosts; RSS includes host; disk cache/background load uncontrolled',
              'libraries': {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in
                            [('baseline', args.baseline), ('current', args.current)]}, 'cases': {}}
    for case in (args.case or ['flat', 'primitives', 'state', 'groups', 'compound', 'ap-groups']):
        records = {'baseline': [], 'current': []}
        for run in range(args.runs):
            order = [('baseline', args.baseline), ('current', args.current)]
            if run % 2:
                order.reverse()
            for name, library in order:
                result = subprocess.run([sys.executable, '-X', 'utf8', str(script), str(library.resolve()),
                                         str(args.fixtures.resolve()), str(args.output.parent.resolve()),
                                         '--scale', str(args.scale), '--repaints', str(args.repaints), '--child', case+'.pdf'],
                                        capture_output=True, text=True, check=True, timeout=120)
                records[name].append(json.loads(result.stdout))
        if len({r['rgba_sha256'] for group in records.values() for r in group}) != 1:
            raise RuntimeError(case+': ordinary scene output changed')
        summary = {name: {key: statistics.median(r[key] for r in group) for key in
                          ['open_ms', 'first_render_ms', 'repaint_p95_ms', 'incremental_peak_rss_bytes']}
                   for name, group in records.items()}
        summary['first_render_ratio'] = summary['current']['first_render_ms']/summary['baseline']['first_render_ms']
        summary['repaint_p95_ratio'] = summary['current']['repaint_p95_ms']/summary['baseline']['repaint_p95_ms']
        report['cases'][case] = {'samples': records, 'summary': summary,
                                'pdf_sha256': hashlib.sha256((args.fixtures/(case+'.pdf')).read_bytes()).hexdigest()}
        print(case, 'first ratio %.3f, repaint p95 ratio %.3f' % (summary['first_render_ratio'], summary['repaint_p95_ratio']), flush=True)
    args.output.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')


if __name__ == '__main__':
    main()
