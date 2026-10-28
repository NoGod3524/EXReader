#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Prove concurrent external ledger changes abort the candidate transaction."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import legacy_data as L


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    parser = argparse.ArgumentParser()
    parser.add_argument('--tx', required=True)
    parser.add_argument('--old', required=True)
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    args.work.mkdir(parents=True, exist_ok=False)
    pack = args.work / 'pack.exrpack'
    pack.write_bytes(L.build_pack([L.entry(L.book_record('one', 'one.txt'), L.TXT)], []))
    for existing in (False, True):
        folder = args.work / ('existing' if existing else 'created')
        folder.mkdir()
        target = folder / 'library.sqlite'
        if existing:
            old_seed = subprocess.run([args.old, 'migrate', '--pack', str(pack), '--target', str(target)], capture_output=True, text=True)
            assert old_seed.returncode == 0, (old_seed.stdout, old_seed.stderr)
        seed = subprocess.run([args.tx, 'migrate', '--pack', str(pack), '--target', str(target)], capture_output=True, text=True)
        assert seed.returncode == 0, (seed.stdout, seed.stderr)
        ledger = Path(str(target) + '.legacy-map.json')
        before = sha(target)
        ready, resume = Path(str(target) + '.review-ready'), Path(str(target) + '.review-resume')
        env = dict(os.environ, EXR_MIGRATE_TEST_FAULTS='1')
        process = subprocess.Popen([args.tx, 'migrate', '--pack', str(pack), '--target', str(target), '--inject', 'publish-pause'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
        try:
            deadline = time.monotonic() + 30
            while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(.02)
            assert ready.exists(), 'review rendezvous missing'
            ledger.write_bytes(b'external concurrent change')
            resume.write_text('resume', encoding='utf-8')
            out, err = process.communicate(timeout=30)
            assert process.returncode == 3 and json.loads(out)['code'] == 'ledger-changed', (process.returncode, out, err)
            assert sha(target) == before and ledger.read_bytes() == b'external concurrent change'
            assert not Path(str(target) + '.migrate-lock').exists()
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()
    print(json.dumps({'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'], 'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'checks': ['ledger-created', 'ledger-content-changed', 'rollback-preserves-external-change']}))


if __name__ == '__main__':
    main()
