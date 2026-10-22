#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Collect per-platform UI acceptance evidence: cases, steps, attachments, state."""
import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path


def run(command):
    return subprocess.run([str(value) for value in command], capture_output=True, text=True)


def digest(path):
    sha = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            sha.update(chunk)
    return sha.hexdigest()


def load_results(xcresult):
    proc = run(['xcrun', 'xcresulttool', 'get', 'test-results', 'tests',
                '--path', xcresult, '--format', 'json'])
    if proc.returncode != 0:
        return {'error': (proc.stderr or proc.stdout)[-4000:]}, []
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as error:
        return {'error': str(error)}, []
    cases = []

    def walk(node):
        if node.get('nodeType') == 'Test Case':
            activities = [child.get('name') for child in node.get('children', [])
                          if 'Activity' in str(child.get('nodeType'))]
            cases.append({'name': node.get('name'), 'result': node.get('result'),
                          'duration': node.get('duration'), 'steps': activities,
                          'step_count': len(activities)})
        for child in node.get('children', []):
            walk(child)

    for node in payload.get('testNodes', []):
        walk(node)
    return {'raw_nodes': len(payload.get('testNodes', []))}, cases


def export_attachments(xcresult, output):
    target = output/'attachments'
    proc = run(['xcrun', 'xcresulttool', 'export', 'attachments',
                '--path', xcresult, '--output-path', target])
    files = sorted(path.name for path in target.glob('*')) if target.exists() else []
    manifest = []
    manifest_path = target/'manifest.json'
    if manifest_path.exists():
        try:
            data = json.loads(manifest_path.read_text())
            manifest = data if isinstance(data, list) else data.get('attachments', [])
        except json.JSONDecodeError:
            manifest = []
    return {'status': proc.returncode, 'stderr': proc.stderr[-2000:],
            'file_count': len(files), 'files': files[:400], 'manifest': manifest[:400]}


def collect_database(container, output):
    if not container:
        return {'status': 'container-not-provided'}
    root = Path(container)
    db = root/'Library/Application Support/EXReader/library.sqlite'
    if not db.exists():
        return {'status': 'missing', 'expected': str(db)}
    target = output/'library.sqlite'
    try:
        source = sqlite3.connect('file:'+str(db)+'?mode=ro', uri=True)
        backup = sqlite3.connect(target)
        source.backup(backup)
        backup.close()
        source.close()
    except sqlite3.Error as error:
        return {'status': 'copy-failed', 'error': str(error)}
    counts = {}
    try:
        con = sqlite3.connect(target)
        for table in ['books', 'notes', 'fixed_notes', 'book_progress']:
            try:
                counts[table] = con.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]
            except sqlite3.Error:
                counts[table] = None
        con.close()
    except sqlite3.Error:
        pass
    return {'status': 'copied', 'sha256': digest(target), 'bytes': target.stat().st_size,
            'rows': counts, 'source_name': 'library.sqlite'}


def copy_state(container, output):
    if not container:
        return {'status': 'container-not-provided'}
    for candidate in [Path(container)/'Documents/host-state.json',
                      Path(container)/'host-state.json']:
        if candidate.exists():
            target = output/'host-state.json'
            shutil.copyfile(candidate, target)
            try:
                payload = json.loads(target.read_text())
            except json.JSONDecodeError:
                payload = {}
            return {'status': 'copied', 'sha256': digest(target), 'payload': payload}
    return {'status': 'missing'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--platform', required=True)
    parser.add_argument('--xcresult', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--container', default='')
    parser.add_argument('--identity', type=Path)
    args = parser.parse_args()
    output = args.output.absolute()
    output.mkdir(parents=True, exist_ok=True)
    metadata, cases = load_results(args.xcresult)
    attachments = export_attachments(args.xcresult, output)
    identity = json.loads(args.identity.read_text()) if args.identity and args.identity.exists() else {}
    passed = sum(1 for case in cases if case['result'] == 'Passed')
    failed = sum(1 for case in cases if case['result'] == 'Failed')
    evidence = {
        'schema': 1,
        'platform': args.platform,
        'date': identity.get('date', ''),
        'source_sha': identity.get('source_sha', os.environ.get('GITHUB_SHA', '')),
        'run': {'id': os.environ.get('GITHUB_RUN_ID', ''),
                'job': os.environ.get('GITHUB_JOB', ''),
                'attempt': os.environ.get('GITHUB_RUN_ATTEMPT', ''),
                'url': identity.get('run_url', '')},
        'environment': identity,
        'tests': cases,
        'totals': {'cases': len(cases), 'passed': passed, 'failed': failed,
                   'steps': sum(case['step_count'] for case in cases)},
        'xcresult': {'path': str(args.xcresult), 'sha256_directory': None,
                     'parsed': metadata},
        'attachments': attachments,
        'state': {'database': collect_database(args.container, output),
                  'host_state': copy_state(args.container, output)},
        'physical_device_execution': False,
        'scope': 'UI acceptance drives real controls, touches and keyboard events on macOS and both simulators'
    }
    (output/'evidence.json').write_text(json.dumps(evidence, indent=2, sort_keys=True)+'\n')
    print(json.dumps({'platform': args.platform, 'cases': len(cases), 'passed': passed,
                      'failed': failed, 'steps': evidence['totals']['steps'],
                      'attachments': attachments.get('file_count', 0)}, indent=2))
    if failed or not cases:
        sys.exit('UI acceptance failed for '+args.platform)


if __name__ == '__main__':
    main()
