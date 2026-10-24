#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Build/run real Swift session regressions in GitHub Actions against installed SDK."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--resources', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if os.environ.get('GITHUB_ACTIONS') != 'true' or sys.platform != 'darwin':
        parser.error('Run only on GitHub Actions macOS')
    sdk, resources, output = args.sdk.resolve(), args.resources.resolve(), args.output.resolve()
    if output.exists():
        parser.error('Preserve earlier evidence: choose a new output')
    output.mkdir(parents=True)
    program = output/'model-review'
    command = [sys.executable, str(ROOT/'tools/apple_swift.py'), '--sdk', str(sdk), '--', '-swift-version', '5', '-parse-as-library',
                    '-D', 'EXR_APPLE_HOST_REVIEW',
                    '-I', str(sdk/'include'), '-L', str(sdk/'lib'), '-lexreader',
                    '-Xlinker', '-rpath', '-Xlinker', str(sdk/'lib'),
                    str(ROOT/'examples/apple/HostSDK.swift'),
                    str(ROOT/'examples/apple/HostModel.swift'),
                    str(ROOT/'examples/apple/HostCatalog.swift'),
                    str(ROOT/'examples/apple/HostAccount.swift'),
                    str(ROOT/'examples/apple/SelectableText.swift'),
                    str(ROOT/'tests/apple_host/review/ModelReview.swift'),
                    '-o', str(program)]
    for phase, arguments in [('compile', command), ('model-review', [str(program), str(resources), str(output), str(sdk)])]:
        try:
            completed = subprocess.run(arguments, timeout=180)
        except subprocess.TimeoutExpired:
            print(json.dumps({'phase': phase, 'accepted': False, 'timed_out': True, 'budget_seconds': 180}), flush=True)
            raise SystemExit(1)
        if phase == 'model-review':
            report = output/'model-review.json'
            if report.is_file():
                data = json.loads(report.read_text())
                sources = ('examples/apple/HostSDK.swift', 'examples/apple/HostModel.swift',
                           'examples/apple/HostCatalog.swift', 'examples/apple/HostAccount.swift', 'examples/apple/SelectableText.swift',
                           'tests/apple_host/review/ModelReview.swift', 'tools/check_apple_model_review.py',
                           'apps/reader/store/001_catalog.sql')
                data['source_files_sha256'] = {
                    name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in sources}
                report.write_text(json.dumps(data, indent=2, sort_keys=True) + '\n')
                print(json.dumps({'phase': phase, 'return_code': completed.returncode,
                                  'source_sha': data.get('source_sha'), 'run_id': data.get('run_id'),
                                  'accepted': data.get('accepted'), 'check_count': len(data.get('checks', []))}), flush=True)
        if completed.returncode:
            print(json.dumps({'phase': phase, 'accepted': False, 'return_code': completed.returncode}), flush=True)
            raise SystemExit(1)


if __name__ == '__main__':
    main()
