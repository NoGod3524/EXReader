#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Run one existing Apple XCUITest suite and record its own real result.

The suite, project file and assertions belong to the platform owner. This wrapper
only selects a real destination, keeps the raw log and result bundle, and writes
the executed test names and verdicts so the S20 matrix can bind them.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

TEST_LINE = re.compile(r"Test Case '-\[(?P<suite>[A-Za-z0-9_.]+) (?P<name>[A-Za-z0-9_]+)\]' (?P<result>passed|failed)")


def destination(platform):
    if platform == 'macos':
        return 'platform=macOS', None, 'macOS host', 'macOS'
    listing = json.loads(subprocess.check_output(['xcrun', 'simctl', 'list', 'devices', 'available', '--json']))
    prefix = 'iPhone' if platform == 'iphone' else 'iPad'
    choices = [(runtime, device['name'], device['udid']) for runtime, devices in listing['devices'].items()
               for device in devices if device.get('isAvailable') and device['name'].startswith(prefix)]
    if not choices:
        raise SystemExit('no available ' + prefix + ' simulator')
    runtime, name, udid = max(choices)
    subprocess.run(['xcrun', 'simctl', 'shutdown', udid], check=False, capture_output=True)
    subprocess.run(['xcrun', 'simctl', 'erase', udid], check=True, capture_output=True)
    return 'platform=iOS Simulator,id=' + udid, udid, name, runtime


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--scheme', required=True)
    parser.add_argument('--platform', required=True, choices=('macos', 'iphone', 'ipad'))
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--derived', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timeout', type=float, default=3600.0)
    args = parser.parse_args(argv)
    if sys.platform != 'darwin' or os.environ.get('GITHUB_ACTIONS') != 'true':
        raise SystemExit('Apple UI suites run in Actions on macOS only')
    output = args.output.resolve()
    if output.exists():
        raise SystemExit('choose a new evidence directory to preserve earlier results')
    output.mkdir(parents=True)
    spec, udid, device, runtime = destination(args.platform)
    (output / 'destination.txt').write_text('\n'.join((spec, udid or 'macos', device, runtime)) + '\n', encoding='utf-8')
    bundle = output / (args.platform + '.xcresult')
    signing = 'NO' if udid else 'YES'
    argv = ['xcodebuild', 'test', '-project', str(args.project.resolve()), '-scheme', args.scheme,
            '-destination', spec, '-derivedDataPath', str(args.derived.resolve()),
            '-resultBundlePath', str(bundle), '-parallel-testing-enabled', 'NO',
            '-test-timeouts-enabled', 'YES', '-default-test-execution-time-allowance', '180',
            '-maximum-test-execution-time-allowance', '300',
            'EXR_SDK_DIR=' + str(args.sdk.resolve()), 'CODE_SIGNING_ALLOWED=' + signing]
    started = time.monotonic()
    timed_out = False
    with (output / 'xcodebuild.log').open('wb') as log:
        process = subprocess.Popen(argv, stdout=log, stderr=subprocess.STDOUT)
        try:
            code = process.wait(timeout=args.timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            process.terminate()
            try:
                process.wait(timeout=60)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            code = 124
    text = (output / 'xcodebuild.log').read_text(encoding='utf-8', errors='replace')
    tests, seen = [], set()
    for match in TEST_LINE.finditer(text):
        name = match.group('name')
        if name in seen:
            continue
        seen.add(name)
        tests.append({'name': name, 'suite': match.group('suite'), 'result': match.group('result').capitalize()})
    passed = sum(1 for item in tests if item['result'] == 'Passed')
    failed = sum(1 for item in tests if item['result'] == 'Failed')
    result = {
        'schema': 1,
        'kind': 'apple-xcuitest',
        'platform': args.platform,
        'device': device,
        'runtime': runtime,
        'udid': udid,
        'destination': spec,
        'scheme': args.scheme,
        'source_sha': os.environ.get('GITHUB_SHA', ''),
        'run_id': os.environ.get('GITHUB_RUN_ID', ''),
        'attempt': os.environ.get('GITHUB_RUN_ATTEMPT', ''),
        'physical_device_execution': False,
        'exit': code,
        'timed_out': timed_out,
        'elapsed_seconds': round(time.monotonic() - started, 3),
        'tests': tests,
        'passed': passed,
        'failed': failed,
        'succeeded_marker': '** TEST SUCCEEDED **' in text,
        'failed_marker': '** TEST FAILED **' in text,
        'result_bundle': str(bundle) if bundle.exists() else None,
        'result_bundle_bytes': sum(item.stat().st_size for item in bundle.rglob('*') if item.is_file()) if bundle.exists() else 0,
        'log': str(output / 'xcodebuild.log'),
    }
    (output / 'status.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps({'platform': args.platform, 'exit': code, 'passed': passed, 'failed': failed,
                      'tests': len(tests)}, ensure_ascii=True))
    if code != 0 or failed:
        tail = '\n'.join(text.splitlines()[-80:])
        print(tail, flush=True)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
