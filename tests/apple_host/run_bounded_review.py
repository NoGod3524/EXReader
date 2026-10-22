#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Build and run the Apple bounded consumer only in GitHub Actions."""
import argparse
import json
import os
from pathlib import Path
import resource
import subprocess
import sys

from evidence_contract import cloud_identity, digest, inventory, load, require, BOUNDED_CHECKS

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--resources', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timeout', type=int, default=900, help='lower budgets are diagnostic only; maximum 900 seconds')
    args = parser.parse_args()
    require(sys.platform == 'darwin' and os.environ.get('GITHUB_ACTIONS') == 'true', 'cloud macOS only')
    require(1 <= args.timeout <= 900, 'consumer budget must be between 1 and 900 seconds')
    sdk, fixtures, out = args.sdk.resolve(), args.resources.resolve(), args.output.resolve()
    require(not out.exists(), 'preserve previous evidence; use a fresh output')
    out.mkdir(parents=True)
    sources = ['examples/apple/HostSDK.swift', 'examples/apple/HostModel.swift', 'examples/apple/SelectableText.swift',
               'tests/apple_host/bounded_review/BoundedReview.swift']
    command = ['xcrun', 'swiftc', '-swift-version', '5', '-parse-as-library', '-O', '-D', 'EXR_APPLE_HOST_REVIEW',
               '-I', str(sdk/'include'), '-L', str(sdk/'lib'), '-lexreader',
               '-Xlinker', '-rpath', '-Xlinker', str(sdk/'lib'),
               *[str(ROOT/p) for p in sources], '-o', str(out/'bounded-review')]
    with (out/'compile.log').open('w') as log:
        compiled = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=180)
    if compiled.returncode:
        print((out/'compile.log').read_text(), flush=True)
        raise SystemExit(compiled.returncode)
    try:
        result = subprocess.run([sys.executable, __file__, '--measure-child', str(args.timeout), str(out/'bounded-review'), str(fixtures), str(out/'consumer'), str(out/'run.log')],
                                capture_output=True, text=True, timeout=args.timeout + 20)
    except subprocess.TimeoutExpired:
        print((out/'run.log').read_text(), flush=True)
        raise
    if result.returncode:
        print((out/'run.log').read_text(), flush=True)
        print(result.stderr, flush=True)
    report = load(out/'consumer/bounded-review.json')
    checks = report.get('checks', [])
    print(json.dumps({'bounded_checks': checks, 'exit_code': result.returncode}), flush=True)
    require(result.returncode == 0 and report.get('accepted') is True and
            [c.get('name') for c in checks] == BOUNDED_CHECKS and all(c.get('passed') is True for c in checks),
            'bounded consumer failed or omitted checks')
    report.update({**cloud_identity('bounded-macos'), 'program_sha256': digest(out/'bounded-review'),
                   'sdk_files_sha256': inventory(sdk),
                   'fixtures': {name: digest(fixtures/name) for name in ('Bounded.epub', 'BoundedLong.epub', 'Unicode.epub', 'Reader.otf', 'Repeated.epub')},
                   'source_files_sha256': {p: digest(ROOT/p) for p in [*sources, 'tests/apple_host/run_bounded_review.py']},
                   'process_peak_rss_bytes': json.loads(result.stdout)['process_peak_rss_bytes'],
                   'runtime_budget_seconds': args.timeout,
                   'diagnostic_only': args.timeout != 900 or report['measurements'].get('repeated_window_bytes') != 16384,
                   'rss_scope': 'bounded consumer process high water; includes font, both accepted/candidate frames, all cases and allocator; compiler excluded',
                   'physical_device_execution': False})
    (out/'bounded-review.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'accepted': True, 'checks': len(checks), 'measurements': report['measurements']}))


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--measure-child':
        with open(sys.argv[6], 'w') as log:
            child = subprocess.run(sys.argv[3:6], stdout=log, stderr=subprocess.STDOUT, timeout=int(sys.argv[2]))
        print(json.dumps({'process_peak_rss_bytes': resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss}))
        raise SystemExit(child.returncode)
    else:
        main()
