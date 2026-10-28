#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Exercise ordered use of both migrators without rewriting the input library."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import legacy_data as L


def invoke(tool, pack, target):
    p = subprocess.run([tool, 'migrate', '--pack', str(pack), '--target', str(target)], capture_output=True, text=True)
    return p.returncode, json.loads(p.stdout), p.stderr


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    parser = argparse.ArgumentParser()
    parser.add_argument('--old', required=True)
    parser.add_argument('--tx', required=True)
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    args.work.mkdir(parents=True, exist_ok=False)
    pack = args.work / 'pack.exrpack'
    pack.write_bytes(L.build_pack([L.entry(L.book_record('one', 'one.txt'), L.TXT)], []))
    old_target = args.work / 'old.sqlite'
    rc, report, err = invoke(args.old, pack, old_target)
    assert rc == 0, (rc, report, err)
    rc, report, err = invoke(args.old, pack, old_target)
    assert rc == 0, (rc, report, err)
    target = args.work / 'transaction.sqlite'
    rc, report, err = invoke(args.tx, pack, target)
    assert rc == 0, (rc, report, err)
    ledger = Path(str(target) + '.legacy-map.json')
    before = digest(target), digest(ledger)
    rc, report, err = invoke(args.old, pack, target)
    assert rc == 2 and report['code'] == 'transactional-ledger', (rc, report, err)
    assert before == (digest(target), digest(ledger))
    assert not Path(str(target) + '.migrate-lock').exists()
    verify = subprocess.run([args.tx, 'verify', '--pack', str(pack), '--target', str(target)], capture_output=True, text=True)
    assert verify.returncode == 0, (verify.stdout, verify.stderr)
    print(json.dumps({'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
                      'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'checks': ['legacy-rerun', 'transaction-then-legacy-rejected', 'files-unchanged', 'transaction-verify']}))


if __name__ == '__main__':
    main()
