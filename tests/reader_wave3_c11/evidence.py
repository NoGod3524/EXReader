#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actions-only audit of one recorded C11 Android acceptance artifact.

Prints the per-suite outcome that the uploaded bytes of one run/attempt already
contain: the strict acceptance matrix, each frozen driver summary, every failing
case, and the wave3 phase reports. Nothing is rebuilt or re-executed here, and no
number is derived from a listing: each value is read out of the artifact.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path

assert os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only'
DROP = ('frame_observations', 'observations', 'tree', 'samples')


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def trim(value, depth=0):
    if isinstance(value, dict):
        if depth > 3:
            return '{...}'
        return {key: trim(item, depth + 1) for key, item in value.items() if key not in DROP}
    if isinstance(value, list):
        if depth > 3:
            return '[...]'
        return [trim(item, depth + 1) for item in value]
    return value


def line(label, value):
    print(label + ' ' + json.dumps(value, ensure_ascii=False, sort_keys=True), flush=True)


def find(root, name):
    return sorted(path for path in root.rglob(name) if path.is_file())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    root = args.root
    print('AUDIT_ROOT ' + str(root.resolve()), flush=True)
    for path in sorted(item for item in root.rglob('*') if item.is_file()):
        print('FILE ' + str(path.relative_to(root)).replace(os.sep, '/') + ' ' + str(path.stat().st_size), flush=True)

    for apk in sorted(root.rglob('*.apk')):
        print('APK_SHA256 ' + str(apk.relative_to(root)).replace(os.sep, '/') + ' ' + sha256(apk) + ' ' + str(apk.stat().st_size), flush=True)

    for path in find(root, 'result.json'):
        try:
            data = load(path)
        except (OSError, ValueError) as error:
            print('RESULT_UNREADABLE ' + str(path) + ' ' + type(error).__name__, flush=True)
            continue
        kind = data.get('kind') or data.get('suite') or ''
        relative = str(path.relative_to(root)).replace(os.sep, '/')
        if 'problems' in data:
            line('ACCEPTANCE ' + relative, {key: data.get(key) for key in
                                            ('accepted', 'problems', 'missing_operations', 'app_sha256',
                                             'capture_count', 'source_sha', 'run_id', 'attempt', 'kind')})
            continue
        line('SUITE_RESULT ' + relative, {key: data.get(key) for key in
                                          ('accepted', 'checks', 'apk_sha256', 'installed_apk_sha256',
                                           'checkjni', 'source_sha', 'run_id', 'attempt',
                                           'reading_ui_accepted', 'navigation_ui_accepted', 'wave3_ui_accepted')})
        phases = data.get('phases') or []
        for phase in phases:
            checks = phase.get('checks') or []
            failed = [item for item in checks if item.get('pass') is not True]
            line('PHASE ' + relative, {'phase': phase.get('phase'), 'passed': phase.get('passed'),
                                       'count': phase.get('count'), 'checks': len(checks),
                                       'pid': phase.get('pid'), 'failed_checks': phase.get('failed_checks'),
                                       'font_leases': phase.get('font_leases'),
                                       'failed_check': phase.get('failed_check'),
                                       'failure': phase.get('failure'), 'failed': failed})
        stops = data.get('process_stops') or []
        line('STOPS ' + relative, stops)
        if data.get('sources'):
            line('SOURCES ' + relative, data['sources'])
        kill = data.get('real_postcommit_kill')
        if kill:
            line('POSTCOMMIT_KILL ' + relative, kill)

    for path in find(root, 'validation.json'):
        relative = str(path.relative_to(root)).replace(os.sep, '/')
        try:
            data = load(path)
        except (OSError, ValueError) as error:
            print('VALIDATION_UNREADABLE ' + relative + ' ' + type(error).__name__, flush=True)
            continue
        cases = data.get('cases') or []
        line('VALIDATION ' + relative, {'suite': data.get('suite'), 'summary': data.get('summary'),
                                        'case_count': len(cases), 'apk_sha256': data.get('apk_sha256'),
                                        'source_sha': data.get('source_sha'), 'run_id': data.get('run_id'),
                                        'attempt': data.get('attempt'), 'api': data.get('api'),
                                        'abi': data.get('abi'), 'device_is_emulator': data.get('device_is_emulator')})
        for case in cases:
            line('CASE ' + relative, {key: case.get(key) for key in
                                      ('id', 'status', 'error', 'detail', 'screenshot', 'assertions', 'duration_ms')})
        sequence = data.get('sequence')
        if sequence:
            line('SEQUENCE ' + relative, sequence)

    for path in find(root, 'execution.json'):
        relative = str(path.relative_to(root)).replace(os.sep, '/')
        try:
            data = load(path)
        except (OSError, ValueError):
            continue
        line('WALKTHROUGH ' + relative, {key: data.get(key) for key in
                                         ('completed', 'errors', 'suites', 'installed_sha256', 'app_sha256',
                                          'source_sha', 'run_id', 'attempt', 'fixtures')})

    for path in find(root, 'candidate-provenance.json'):
        relative = str(path.relative_to(root)).replace(os.sep, '/')
        try:
            data = load(path)
        except (OSError, ValueError):
            continue
        line('PROVENANCE ' + relative, trim(data))

    for path in find(root, 'java-gate.json'):
        line('JAVA_GATE', load(path))

    for path in find(root, 'guard.json'):
        try:
            data = load(path)
        except (OSError, ValueError):
            continue
        line('GUARD', {key: data.get(key) for key in ('seed', 'sdk_approved', 'source_sha', 'run_id', 'attempt',
                                                      'changed_paths', 'module_trees', 'sdk_difference_from_approved')})
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
