#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Exercise a real file read denial on a disposable Windows fixture."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
import legacy_data as L


def run(*args):
    return subprocess.run(args, capture_output=True, text=True, check=True)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert os.name == 'nt' and os.environ.get('GITHUB_ACTIONS') == 'true'
    parser = argparse.ArgumentParser()
    parser.add_argument('--old', required=True)
    parser.add_argument('--tx', required=True)
    parser.add_argument('--probe', required=True)
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    args.work.mkdir(parents=True, exist_ok=False)
    target = args.work / 'library.sqlite'
    ledger = Path(str(target) + '.legacy-map.json')
    pack = args.work / 'pack.exrpack'
    pack.write_bytes(L.build_pack([L.entry(L.book_record('one', 'one.txt'), L.TXT)], []))
    for tool in (args.old, args.tx):
        run(tool, 'migrate', '--pack', str(pack), '--target', str(target))
    target_before, ledger_before = digest(target), digest(ledger)
    sid = next(csv.reader([run('whoami', '/user', '/fo', 'csv', '/nh').stdout.strip()]))[-1]
    assert sid.startswith('S-1-'), 'cannot identify runner SID'
    account = '*' + sid
    try:
        run('icacls', str(ledger), '/deny', account + ':(R)')
        try:
            ledger.read_bytes()
        except PermissionError:
            pass
        else:
            raise AssertionError('fixture ACL did not deny the runner file read')
        # Windows may expose file attributes even though file reads are denied.
        path_state = int(run(args.probe, str(ledger)).stdout)
        for command in ('migrate', 'verify', 'dump'):
            cmd = [args.tx, command, '--target', str(target)]
            if command != 'dump':
                cmd += ['--pack', str(pack)]
            p = subprocess.run(cmd, capture_output=True, text=True)
            expected = 3 if command == 'migrate' else 2
            assert p.returncode == expected and json.loads(p.stdout)['code'] == 'ledger-unreadable', (p.returncode, p.stdout, p.stderr)
            assert digest(target) == target_before
    finally:
        run('icacls', str(ledger), '/remove:d', account)
    assert digest(target) == target_before and digest(ledger) == ledger_before, 'fixture access or content not restored'
    run(args.tx, 'verify', '--pack', str(pack), '--target', str(target))
    print(json.dumps({'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
                      'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'acl_denied_path_state': path_state,
                      'checks': ['file-read-denied', 'migrate-refused', 'verify-refused', 'dump-refused', 'unchanged', 'acl-restored']}))


if __name__ == '__main__':
    main()
