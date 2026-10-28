#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Check whether restoring a deleted note can leave ledger bytes unchanged."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import legacy_data as L


def migrate(tool, pack, target):
    p = subprocess.run([tool, 'migrate', '--pack', str(pack), '--target', str(target)], capture_output=True, text=True)
    assert p.returncode == 0, (p.returncode, p.stdout, p.stderr)
    return json.loads(p.stdout)


def snapshot(target):
    with sqlite3.connect(target) as db:
        return (db.execute('SELECT data FROM exr_migration_ledger WHERE id=1').fetchone()[0],
                db.execute('SELECT id, text FROM notes ORDER BY id').fetchall())


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    parser = argparse.ArgumentParser()
    parser.add_argument('--tool', required=True)
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    args.work.mkdir(parents=True, exist_ok=False)
    target, pack = args.work / 'library.sqlite', args.work / 'pack.exrpack'
    book = L.entry(L.book_record('book', 'book.txt'), L.TXT)
    note = L.note_record('note', 'book', 'lantern keeper', 'kept comment')
    pack.write_bytes(L.build_pack([book], [note]))
    migrate(args.tool, pack, target)
    initial_ledger, initial_notes = snapshot(target)
    assert len(initial_notes) == 1, initial_notes
    with sqlite3.connect(target) as db:
        db.execute('DELETE FROM notes')
    before_ledger, before_notes = snapshot(target)
    assert not before_notes and before_ledger == initial_ledger
    result = migrate(args.tool, pack, target)
    after_ledger, after_notes = snapshot(target)
    assert any(entry['code'] == 'note-recreated' for entry in result['entries']), result
    assert after_notes == initial_notes, (initial_notes, after_notes)
    assert after_ledger == before_ledger, 'ledger bytes differed; hash-only ambiguity not demonstrated'
    print(json.dumps({'source_sha':os.environ['GITHUB_SHA'], 'run_id':os.environ['GITHUB_RUN_ID'],
                      'attempt':os.environ['GITHUB_RUN_ATTEMPT'], 'old_note_count':len(before_notes),
                      'new_note_count':len(after_notes), 'ledger_sha256':hashlib.sha256(after_ledger).hexdigest(),
                      'ledger_bytes_identical':True}))


if __name__ == '__main__':
    main()
