# SPDX-License-Identifier: MIT
"""Run the same installed-package native consumer in preflight and full Actions jobs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from reading_contract import NATIVE_CHECKS


def main():
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise RuntimeError('Actions only')
    parser = argparse.ArgumentParser()
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--resources', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[3]
    sdk, resources, output = args.sdk.absolute(), args.resources.absolute(), args.output.absolute()
    output.mkdir(parents=True, exist_ok=True)

    def run(command, log, timeout=900):
        print('READING_NATIVE_PHASE ' + log, flush=True)
        with (output / log).open('wb') as stream:
            result = subprocess.run([str(value) for value in command], cwd=repo, stdout=stream,
                                    stderr=subprocess.STDOUT, timeout=timeout, check=False)
        print((output / log).read_text(errors='replace'), flush=True)
        if result.returncode:
            raise RuntimeError('Native command failed: ' + log + '; exit=' + str(result.returncode))

    run([sys.executable, 'tests/apple_host/prepare_fixtures.py', '--resources', resources], 'fixtures.log')
    run([sys.executable, 'tests/apple_host/navigation/prepare_navigation_fixture.py', '--resources', resources], 'navigation-fixtures.log')
    run(['cc', '-I', sdk / 'include', 'tests/apple_host/navigation/make_cfi.c', '-L', sdk / 'lib', '-lexreader',
         '-Wl,-rpath,' + str(sdk / 'lib'), '-o', output / 'make-cfi'], 'cfi-build.log')
    run([output / 'make-cfi', resources / 'Sample.epub'], 'authored-cfi.txt')
    run([sys.executable, 'tests/apple_host/navigation/prepare_navigation_fixture.py', '--resources', resources,
         '--cfi', output / 'authored-cfi.txt'], 'authored-fixtures.log')
    run([sys.executable, 'tests/apple_host/reading/prepare_reading_fixture.py', '--resources', resources], 'reading-fixtures.log')
    run([sys.executable, 'tools/apple_swift.py', '--sdk', sdk, '--', '-swift-version', '5', '-parse-as-library', '-O',
         '-D', 'EXR_APPLE_HOST_REVIEW', '-I', sdk / 'include', '-L', sdk / 'lib', '-lexreader', '-Xlinker', '-rpath',
         '-Xlinker', sdk / 'lib', 'examples/apple/HostSDK.swift', 'examples/apple/HostModel.swift',
         'examples/apple/HostCatalog.swift', 'examples/apple/SelectableText.swift',
         'tests/apple_host/reading/ReadingReview.swift', '-o', output / 'reading-review'], 'build.log')
    run([output / 'reading-review', resources, output / 'consumer'], 'consumer.log')
    report = json.loads((output / 'consumer/reading-review.json').read_text())
    if not (report['accepted'] is True and report['failed'] == report['skipped'] == 0 and
            len(report['checks']) == len(NATIVE_CHECKS) and {row['id'] for row in report['checks']} == NATIVE_CHECKS and
            all(row['passed'] is True for row in report['checks']) and
            report['source_sha'] == os.environ['GITHUB_SHA'] and str(report['run_id']) == os.environ['GITHUB_RUN_ID'] and
            str(report['attempt']) == os.environ['GITHUB_RUN_ATTEMPT']):
        raise RuntimeError('Native named checks or source/run/attempt differ')
    provider = json.loads((output / 'reading-review.product.json').read_text())
    if not (provider['installed_reading_commands_linked'] is True and provider['installed_annotation_view_linked'] is True and
            provider['static_sdk_linked'] is False and provider['binary_sha256'] == hashlib.sha256((output / 'reading-review').read_bytes()).hexdigest()):
        raise RuntimeError('Native installed providers or actual executable differ')
    print('READING_NATIVE_VERIFIED checks=' + str(len(NATIVE_CHECKS)), flush=True)


if __name__ == '__main__':
    main()
