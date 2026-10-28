#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Exercise path probing with a real temporary Windows access-denied ACL."""
import argparse
import csv
import json
import os
from pathlib import Path
import subprocess


def run(*args):
    return subprocess.run(args, capture_output=True, text=True, check=True)


def state(probe, path):
    return int(run(probe, str(path)).stdout)


def main():
    assert os.name == 'nt' and os.environ.get('GITHUB_ACTIONS') == 'true'
    parser = argparse.ArgumentParser()
    parser.add_argument('--probe', required=True)
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    args.work.mkdir(parents=True, exist_ok=False)
    blocked = args.work / 'private-fixture'
    blocked.mkdir()
    child = blocked / 'child'
    child.write_text('fixture', encoding='utf-8')
    sid = next(csv.reader([run('whoami', '/user', '/fo', 'csv', '/nh').stdout.strip()]))[-1]
    assert sid.startswith('S-1-'), 'cannot identify runner SID'
    account = '*' + sid
    assert state(args.probe, child) == 1
    assert state(args.probe, blocked / 'absent') == 0
    try:
        run('icacls', str(blocked), '/deny', account + ':(OI)(CI)(RX)')
        assert state(args.probe, child) == -1, 'existing child must be inaccessible'
        assert state(args.probe, blocked / 'absent') == -1, 'inaccessible path must not look absent'
    finally:
        run('icacls', str(blocked), '/remove:d', account)
    assert state(args.probe, child) == 1, 'fixture access was not restored'
    assert state(args.probe, blocked / 'absent') == 0
    child.unlink()
    blocked.rmdir()
    print(json.dumps({'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
                      'attempt': os.environ['GITHUB_RUN_ATTEMPT'],
                      'checks': ['present', 'absent', 'acl-denied-existing', 'acl-denied-absent', 'acl-restored']}))


if __name__ == '__main__':
    main()
