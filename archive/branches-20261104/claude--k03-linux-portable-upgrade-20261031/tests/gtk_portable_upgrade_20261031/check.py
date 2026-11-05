# SPDX-License-Identifier: MIT
"""Independent K03 evidence check: recomputes the key conclusions from the uploaded raw evidence
(profile copies, process records, install identity) without trusting the driver's pass/fail.
usage: check.py EVIDENCE_DIR --report FILE"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile

NOTE_A, NOTE_B = 'K03 旧包批注 café', 'K03 新包批注 नमस्ते'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def library(profile):
    """Reads a temporary copy of an evidence profile copy; the evidence itself is never opened by SQLite."""
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / 'p'
        shutil.copytree(profile, copy)
        with sqlite3.connect(copy / 'library.sqlite') as db:
            books = [(r[0], hashlib.sha256(r[1] or b'').hexdigest()) for r in db.execute('SELECT id,source FROM books ORDER BY id')]
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            notes = []
            for table in ('notes', 'epub_notes', 'fixed_notes'):
                if table in tables:
                    notes += [r[0] for r in db.execute(f'SELECT text FROM {table}')]
            version = db.execute('PRAGMA user_version').fetchone()[0]
            integrity = db.execute('PRAGMA integrity_check').fetchone()[0]
        shelves = []
        catalog = copy / 'library.sqlite.product.sqlite'
        if catalog.is_file():
            with sqlite3.connect(catalog) as db:
                if db.execute("SELECT 1 FROM sqlite_master WHERE name='reader_shelves'").fetchone():
                    shelves = sorted(r[0] for r in db.execute('SELECT name FROM reader_shelves'))
        prefs = (copy / 'preferences.json').read_text(errors='replace') if (copy / 'preferences.json').is_file() else ''
    return dict(books=books, notes=sorted(notes), version=version, integrity=integrity, shelves=shelves, prefs=prefs)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('evidence', type=Path)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    ev = args.evidence
    report = json.loads((ev / 'report.json').read_text())
    install = json.loads((ev / 'install.json').read_text())
    findings, facts = [], {}

    def need(name, condition, value=None):
        facts[name] = dict(ok=bool(condition), value=value)
        if not condition:
            findings.append(name)

    need('evidence-file-hashes', all((ev / name).is_file() and sha(ev / name) == digest
                                      for name, digest in report['files'].items()), len(report['files']))
    need('a-authentic-artifact', install['a_artifact']['outer']['sha256'] == install['a_artifact']['sha256'] and
         install['a']['manifest_source_sha'] == '8f8acf3234cba747165f001c0c96efe1b911e6ad')
    need('b-from-this-source', install['b']['manifest_source_sha'] == report['source_sha'])
    entries = {install['a']['entry_sha256']: 'A', install['b']['entry_sha256']: 'B'}
    procs = report['processes']
    launched = [p for p in procs if p.get('exe_sha256')]
    need('every-mapped-process-is-a-or-b-entry', all(p['exe_sha256'] in entries for p in launched),
         [(p['label'], entries.get(p['exe_sha256'])) for p in launched])
    need('no-argument-launcher', all(p['argv'][-1].endswith('/EXReader-Linux/Start-EXReader.sh') for p in procs) and
         all(p.get('cmdline', ['x'])[1:] == [] for p in launched))
    need('distinct-pids', len({p['pid'] for p in procs}) == len(procs))
    need('only-test-pid-killed', [p['label'] for p in procs if p.get('killed_by_test')] in ([], ['B4-kill']))
    profiles = {p.name: p for p in (ev / 'profiles').iterdir()} if (ev / 'profiles').is_dir() else {}
    snaps = {name: library(path) for name, path in profiles.items() if (path / 'library.sqlite').is_file()}
    fixtures = {v['sha256'] for k, v in report['fixtures'].items() if k in ('epub', 'txt')}
    a = snaps.get('after-A')
    need('a-profile-has-three-books-with-originals', a and len(a['books']) == 3 and
         fixtures <= {h for _, h in a['books']}, a and a['books'])
    need('a-profile-note-shelf-setting', a and NOTE_A in a['notes'] and a['shelves'] and '25.5' in a['prefs'])
    b = snaps.get('after-B-edit')
    need('b-keeps-books-identity-and-bytes', a and b and a['books'] == b['books'], b and b['books'])
    need('b-keeps-a-notes-and-adds-its-own', a and b and set(a['notes']) <= set(b['notes']) and NOTE_B in b['notes'])
    need('b-keeps-shelves', a and b and a['shelves'] == b['shelves'])
    for label in ('after-lock', 'after-kill'):
        if label in snaps:
            need(f'{label}-integrity-and-books', snaps[label]['integrity'] == 'ok' and b and snaps[label]['books'] == b['books'])
    r = snaps.get('after-restore')
    need('restore-equals-pre-update-backup', a and r and r['books'] == a['books'] and r['notes'] == a['notes'])
    facts['library_user_version'] = {k: v['version'] for k, v in snaps.items()}
    statuses = {c['item']: c['status'] for c in report['checks']}
    need('driver-items-recorded', all(i in statuses for i in range(1, 13)), statuses)
    verdict = dict(accepted=not findings, findings=findings, facts=facts, driver_statuses=statuses)
    args.report.write_text(json.dumps(verdict, indent=2, ensure_ascii=False, default=str) + '\n')
    print('K03-INDEPENDENT ' + json.dumps(dict(accepted=not findings, findings=findings), ensure_ascii=False))
    return 0 if not findings else 1


if __name__ == '__main__':
    sys.exit(main())
