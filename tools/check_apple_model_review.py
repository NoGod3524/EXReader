#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Build/run real Swift session regressions in GitHub Actions against installed SDK."""
import argparse
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
    subprocess.run(['xcrun', 'swiftc', '-swift-version', '5', '-parse-as-library',
                    '-I', str(sdk/'include'), '-L', str(sdk/'lib'), '-lexreader',
                    '-Xlinker', '-rpath', '-Xlinker', str(sdk/'lib'),
                    str(ROOT/'examples/apple/HostSDK.swift'),
                    str(ROOT/'examples/apple/HostModel.swift'),
                    str(ROOT/'examples/apple/SelectableText.swift'),
                    str(ROOT/'tests/apple_host/review/ModelReview.swift'),
                    '-o', str(program)], check=True)
    subprocess.run([str(program), str(resources), str(output), str(sdk)], check=True)


if __name__ == '__main__':
    main()
