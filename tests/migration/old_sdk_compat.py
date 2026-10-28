#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Exercise a real SDK 3.40 schema-6 library with the candidate migrator."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess

import legacy_data as L


def run(tool, *args, fault=None):
    env = dict(os.environ)
    if fault:
        env['EXR_MIGRATE_TEST_FAULTS'] = '1'
        args += ('--inject', fault)
    p = subprocess.run([tool, *map(str, args)], capture_output=True, text=True, env=env)
    try:
        result = json.loads(p.stdout)
    except ValueError:
        raise AssertionError((p.returncode, p.stdout, p.stderr))
    return p.returncode, result


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def version(path):
    with sqlite3.connect('file:' + path.resolve().as_posix() + '?mode=ro', uri=True) as db:
        return db.execute('PRAGMA user_version').fetchone()[0]


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--old-tool', required=True)
    p.add_argument('--tool', required=True)
    p.add_argument('--work', type=Path, required=True)
    a = p.parse_args()
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    a.work.mkdir(parents=True, exist_ok=False)
    target = a.work / 'old.sqlite'
    ledger = Path(str(target) + '.legacy-map.json')
    book = L.entry(L.book_record('old', 'old.txt'), L.TXT)
    note = L.note_record('old-note', 'old', 'lantern keeper', 'retained comment')
    pack = a.work / 'old.exrpack'
    pack.write_bytes(L.build_pack([book], [note]))
    code, result = run(a.old_tool, 'migrate', '--pack', pack, '--target', target)
    assert code == 0, result
    assert version(target) == 6
    code, before = run(a.old_tool, 'dump', '--target', target)
    assert code == 0 and len(before['books']) == 1, before
    original = (digest(target), digest(ledger))
    code, result = run(a.tool, 'dump', '--target', target)
    assert code != 0 and result['code'] == 'target-schema', result
    assert original == (digest(target), digest(ledger)) and version(target) == 6
    code, result = run(a.tool, 'migrate', '--pack', pack, '--target', target, '--dry-run')
    assert code == 0 and result['result'] == 'dry-run', result
    assert original == (digest(target), digest(ledger)) and version(target) == 6
    code, result = run(a.tool, 'migrate', '--pack', pack, '--target', target, fault='publish-fail')
    assert code != 0 and original == (digest(target), digest(ledger)) and version(target) == 6, result
    code, result = run(a.tool, 'migrate', '--pack', pack, '--target', target)
    assert code == 0 and version(target) == 7, result
    code, after = run(a.tool, 'dump', '--target', target)
    assert code == 0 and before['books'] == after['books'] and before['audio'] == after['audio'], after
    code, result = run(a.tool, 'verify', '--pack', pack, '--target', target)
    assert code == 0, result
    code, result = run(a.tool, 'migrate', '--pack', pack, '--target', target)
    assert code == 0, result
    code, final = run(a.tool, 'dump', '--target', target)
    assert code == 0 and final == after, final
    report = {'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
              'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'passed': True,
              'checks': ['old-sdk-schema-6', 'read-refusal-unchanged', 'dry-run-unchanged',
                         'publication-failure-unchanged', 'upgrade-preserves-books-notes-and-originals',
                         'verify-and-retry'], 'old_tool_sha256': digest(Path(a.old_tool)),
              'tool_sha256': digest(Path(a.tool))}
    (a.work / 'old-sdk-compat.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
