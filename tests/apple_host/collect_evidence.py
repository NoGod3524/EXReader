#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Collect and validate the actual Apple UI result, executable and persisted state."""
import argparse
import datetime
import json
from pathlib import Path
import platform as host_platform
import shutil
import sqlite3
import subprocess

from evidence_contract import (attachment_records, case_key, cloud_identity, database_state,
    digest, inventory, load, require, tree_digest, validate_cases, validate_platform, validate_sdk)


def command(*args):
    return subprocess.check_output([str(arg) for arg in args], text=True).strip()


def load_results(xcresult):
    payload = json.loads(command('xcrun', 'xcresulttool', 'get', 'test-results', 'tests',
                                 '--path', xcresult, '--format', 'json'))
    cases = []

    def walk(node):
        require(isinstance(node, dict), 'invalid xcresult test node')
        if node.get('nodeType') == 'Test Case':
            cases.append({'name': node.get('name'), 'result': node.get('result'),
                          'duration': node.get('duration'), 'steps': [], 'step_count': 0})
        for child in node.get('children', []):
            walk(child)

    require(isinstance(payload.get('testNodes'), list), 'xcresult has no test nodes')
    for node in payload['testNodes']:
        walk(node)
    return cases


def copy_persisted(container, output):
    require(bool(container), 'application container missing')
    root = Path(container)
    db = next((path for path in (root/'Library/Application Support/EXReader/library.sqlite',
                                root/'library.sqlite') if path.is_file()), None)
    require(db is not None, 'persisted database missing')
    with sqlite3.connect(db.resolve().as_uri() + '?mode=ro', uri=True) as source:
        with sqlite3.connect(output/'library.sqlite') as target:
            source.backup(target)
    for name in ('host-state.json', 'host-log.txt'):
        candidate = next((folder/name for folder in (root/'Documents', root, root/'EXReader')
                          if (folder/name).is_file()), None)
        require(candidate is not None, 'persisted host file missing: ' + name)
        shutil.copyfile(candidate, output/name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--platform', choices=['macos', 'iphone', 'ipad'], required=True)
    parser.add_argument('--xcresult', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--container', required=True)
    parser.add_argument('--sdk-root', type=Path, required=True)
    parser.add_argument('--sdk-identity', type=Path, required=True)
    parser.add_argument('--app', type=Path, required=True)
    parser.add_argument('--fixtures', type=Path, required=True)
    parser.add_argument('--destination-file', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.absolute()
    output.mkdir(parents=True, exist_ok=True)
    evidence = {'schema': 2, 'platform': args.platform, 'accepted': False,
                'physical_device_execution': False, 'collector_status': 1, 'errors': []}
    try:
        identity = cloud_identity(args.platform)
        require(command('git', 'rev-parse', 'HEAD') == identity['source_sha'], 'checkout source differs from cloud source')
        sdk = load(args.sdk_identity)
        validate_sdk(args.sdk_root, sdk, identity['source_sha'], identity['run_id'], identity['attempt'],
                     'macos' if args.platform == 'macos' else 'iphonesimulator')
        lines = args.destination_file.read_text().splitlines()
        require(len(lines) == 4 and all(lines), 'destination identity incomplete')
        require((args.platform == 'macos' and lines[0] == 'platform=macOS') or
                (args.platform != 'macos' and lines[0].startswith('platform=iOS Simulator,id=') and
                 lines[2].lower().startswith(args.platform)), 'destination platform mismatch')
        bundle = args.app
        mac = args.platform == 'macos'
        executable = bundle/('Contents/MacOS/EXReaderHost' if mac else 'EXReaderHost')
        plist = bundle/('Contents/Info.plist' if mac else 'Info.plist')
        manifest = load(args.fixtures)
        identity.update({'date': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'destination': lines[0], 'device': lines[2], 'runtime': lines[3],
            'host': host_platform.platform(), 'xcode': command('xcodebuild', '-version'),
            'sdk': sdk, 'fixtures': manifest, 'font_sha256': manifest['Reader.otf'],
            'input_driver': 'XCUITest tap/doubleTap/typeText/drag and simulator orientation',
            'app': {'bundle': str(bundle), 'executable_sha256': digest(executable),
                    'info_plist_sha256': digest(plist)}})
        evidence.update({'environment': identity, 'source_sha': identity['source_sha'],
            'date': identity['date'], 'run': {'id': identity['run_id'], 'attempt': identity['attempt'],
                'job': identity['job'], 'url': identity['run_url']}})
        cases = load_results(args.xcresult)
        attachments = output/'attachments'
        subprocess.run(['xcrun', 'xcresulttool', 'export', 'attachments', '--path', str(args.xcresult),
                        '--output-path', str(attachments)], check=True, capture_output=True, text=True)
        records, steps = attachment_records(attachments)
        for case in cases:
            case['steps'] = steps[case_key(case['name'])]
            case['step_count'] = len(case['steps'])
        evidence.update({'tests': cases, 'totals': validate_cases(cases),
                         'attachments': {'status': 0, 'count': len(records), 'records': records}})
        program = output/'program/EXReaderHost.app'
        shutil.copytree(bundle, program)
        evidence['program_files_sha256'] = inventory(program)
        copy_persisted(args.container, output)
        evidence['state'] = database_state(output, identity)
        evidence['xcresult_sha256'] = tree_digest(args.xcresult)
        evidence['xcodebuild_log_sha256'] = digest(args.xcresult.parent/(args.platform + '-xcodebuild.log'))
        evidence.update({'accepted': True, 'collector_status': 0})
        (output/'evidence.json').write_text(json.dumps(evidence, indent=2, sort_keys=True) + '\n')
        validate_platform(output, args.platform, identity['source_sha'], identity['run_id'], identity['attempt'],
                          sdk, args.xcresult.parent)
    except Exception as error:
        evidence.update({'accepted': False, 'collector_status': 1, 'errors': [type(error).__name__ + ': ' + str(error)[:500]]})
    (output/'evidence.json').write_text(json.dumps(evidence, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'platform': args.platform, 'accepted': evidence['accepted'],
                      'totals': evidence.get('totals'), 'errors': evidence['errors']}))
    return evidence['collector_status']


if __name__ == '__main__':
    raise SystemExit(main())
