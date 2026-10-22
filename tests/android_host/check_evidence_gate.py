#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Exercise the Android gate against real same-run evidence and altered copies, in CI only."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'tools'))
from android_host_evidence import check_evidence, cloud_identity, load, require, sha256

SUITE_MUTATIONS = ['missing_case', 'duplicate_case', 'reordered_case', 'unknown_case', 'skipped_case',
                   'summary_skipped', 'case_json', 'missing_shot', 'empty_shot', 'changed_shot', 'reused_shot',
                   'escaping_shot']
OTHER_MUTATIONS = ['source', 'run', 'attempt', 'app_apk', 'test_apk', 'installed_apk', 'sdk', 'native',
                   'font', 'fixture', 'device_fixture', 'missing_log', 'failed_instrumentation',
                   'missing_review', 'sequence', 'suite_identity', 'skipped_build', 'source_inventory', 'log_hash']
UPSTREAM_MUTATIONS = ['failed_build', 'cancelled_emulator', 'skipped_static', 'missing_emulator']


def expected_names():
    return ['positive'] + [suite + ':' + name for suite in ('walkthrough', 'review')
                          for name in SUITE_MUTATIONS] + OTHER_MUTATIONS + UPSTREAM_MUTATIONS


def write(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + '.replacement')
    temporary.write_bytes(value if isinstance(value, bytes) else
                          (json.dumps(value, indent=2, sort_keys=True) + '\n').encode())
    temporary.replace(path)


def edit(path, mutation):
    value = load(path)
    mutation(value)
    write(path, value)


def mutate(name, evidence, build):
    if ':' in name:
        suite, name = name.split(':')
        root = evidence/('device' if suite == 'walkthrough' else 'review')
        report_path = root/'validation.json'
        report = load(report_path)
        cases = report['cases']
        first = cases[0]
        if name == 'missing_case':
            cases.pop()
        elif name == 'duplicate_case':
            cases[-1] = cases[0]
        elif name == 'reordered_case':
            cases[0], cases[1] = cases[1], cases[0]
        elif name == 'unknown_case':
            first['id'] = 'unknown_case'
        elif name == 'skipped_case':
            first['status'] = 'skip'
        elif name == 'summary_skipped':
            report['summary']['skipped'] = 1
        elif name == 'case_json':
            path = next((root/'cases').glob('*' + first['id'] + '.json'))
            edit(path, lambda value: value.update(status='fail'))
        elif name == 'missing_shot':
            (root/first['screenshot']).unlink()
        elif name == 'empty_shot':
            write(root/first['screenshot'], b'')
        elif name == 'changed_shot':
            path = root/first['screenshot']
            write(path, path.read_bytes() + b'changed')
        elif name == 'reused_shot':
            for key in ('screenshot', 'screenshot_bytes', 'screenshot_sha256'):
                cases[1][key] = first[key]
            path = next((root/'cases').glob('*' + cases[1]['id'] + '.json'))
            write(path, cases[1])
        elif name == 'escaping_shot':
            first['screenshot'] = '../outside.png'
        write(report_path, report)
        return
    report_path = evidence/'device/validation.json'
    if name in ('source', 'run', 'attempt'):
        key = {'source': 'source_sha', 'run': 'run_id', 'attempt': 'attempt'}[name]
        edit(report_path, lambda value: value.update({key: 'different'}))
    elif name in ('app_apk', 'test_apk'):
        apk = 'app-debug.apk' if name == 'app_apk' else 'uitest-debug-androidTest.apk'
        path = evidence/'artifacts'/apk
        write(path, path.read_bytes() + b'changed')
    elif name == 'installed_apk':
        path = evidence/'installed/uitest-debug.apk'
        write(path, path.read_bytes() + b'changed')
    elif name == 'sdk':
        edit(build, lambda value: value.update(sdk_files_sha256={}))
    elif name == 'native':
        edit(build, lambda value: value.update(native={}))
    elif name == 'font':
        edit(build, lambda value: value['font'].update(sha256='different'))
    elif name == 'fixture':
        fixture = next(iter(load(build)['fixtures']))
        path = build.parent/'fixtures'/fixture
        write(path, path.read_bytes() + b'changed')
    elif name == 'device_fixture':
        edit(evidence/'execution.json', lambda value: value.update(fixtures={}))
    elif name == 'missing_log':
        (evidence/'review-logcat.txt').unlink()
    elif name == 'failed_instrumentation':
        path = evidence/'review-instrumentation.txt'
        write(path, path.read_bytes() + b'\nINSTRUMENTATION_FAILED\n')
    elif name == 'missing_review':
        (evidence/'review/validation.json').unlink()
    elif name == 'sequence':
        edit(evidence/'review/validation.json', lambda value: value['sequence'].update(recovery_calls=1))
    elif name == 'suite_identity':
        edit(evidence/'execution.json', lambda value: value['suites']['review'].update(method='wrong'))
    elif name == 'skipped_build':
        edit(build, lambda value: value.update(sdk_built=False))
    elif name == 'source_inventory':
        edit(build, lambda value: value.update(source_files_sha256={}))
    elif name == 'log_hash':
        edit(evidence/'execution.json', lambda value: value.update(files_sha256={}))
    else:
        raise ValueError('unknown controlled mutation')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--stage', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    identity = cloud_identity()
    require(sys.platform == 'linux', 'gate regression runs in Linux cloud CI')
    upstream = {'build': 'success', 'static': 'success', 'emulator': 'success'}
    checks = []
    report = {**identity, 'schema': 1, 'accepted': False, 'script_sha256': sha256(__file__), 'checks': checks}
    try:
        check_evidence(args.evidence, args.build, args.stage, upstream, identity)
        checks.append({'name': 'positive', 'passed': True})
        for name in expected_names()[1:]:
            with tempfile.TemporaryDirectory(prefix='android-gate-') as temporary:
                root = Path(temporary)
                evidence = root/'evidence'
                build = root/'build.json'
                # Every mutation replaces a hardlink atomically. Original evidence is never changed.
                shutil.copytree(args.evidence, evidence, copy_function=os.link)
                shutil.copytree(args.build.parent/'fixtures', root/'fixtures', copy_function=os.link)
                os.link(args.build, build)
                outcomes = dict(upstream)
                if name in UPSTREAM_MUTATIONS:
                    status, step = name.split('_', 1)
                    if status == 'missing':
                        outcomes.pop(step)
                    else:
                        outcomes[step] = {'failed': 'failure', 'cancelled': 'cancelled', 'skipped': 'skipped'}[status]
                else:
                    mutate(name, evidence, build)
                try:
                    check_evidence(evidence, build, args.stage, outcomes, identity)
                except Exception:
                    checks.append({'name': name, 'passed': True})
                else:
                    checks.append({'name': name, 'passed': False})
        report['accepted'] = [item['name'] for item in checks] == expected_names() and all(item['passed'] for item in checks)
    except Exception as error:
        report['problem'] = type(error).__name__ + ': ' + str(error)[:500]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write(args.output, report)
    print(json.dumps({'accepted': report['accepted'], 'checks': len(checks), 'expected': len(expected_names())}))
    return 0 if report['accepted'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
