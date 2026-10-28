#!/usr/bin/env python3
"""Independent review assertions for transaction candidate; Actions only."""
import argparse, hashlib, json, os, sqlite3, subprocess, sys, traceback
from pathlib import Path
import legacy_data as L

p = argparse.ArgumentParser()
p.add_argument('--tx', required=True); p.add_argument('--legacy', required=True)
p.add_argument('--old', required=True); p.add_argument('--close-helper', required=True)
p.add_argument('--work', required=True, type=Path)
a = p.parse_args()
assert os.environ.get('GITHUB_ACTIONS') == 'true'
a.work.mkdir(parents=True, exist_ok=False)
results = []

def run(tool, *args, fault=None):
    env = dict(os.environ)
    if fault:
        env['EXR_MIGRATE_TEST_FAULTS'] = '1'
        args += ('--inject', fault)
    proc = subprocess.run([tool, *map(str, args)], capture_output=True, text=True, env=env, timeout=120)
    return proc.returncode, proc.stdout, proc.stderr

def check(name, fn):
    try:
        fn()
        results.append({'name': name, 'passed': True})
        print('PASS', name, flush=True)
    except Exception as exc:
        results.append({'name': name, 'passed': False, 'error': repr(exc)})
        print('FAIL', name, repr(exc), flush=True)
        traceback.print_exc()

def folder(name):
    d = a.work / name; d.mkdir(); return d

def simple(d):
    f = d / 'pack.exrpack'
    f.write_bytes(L.build_pack([L.entry(L.book_record('old', 'old.txt'), L.TXT)], []))
    return f

def seed(tool, d):
    pack = simple(d); db = d / 'library.sqlite'
    rc, out, err = run(tool, 'migrate', '--pack', pack, '--target', db)
    assert rc == 0, (rc, out, err)
    return pack, db

def target_files(d):
    return sorted(x.name for x in d.iterdir() if x.name.startswith('library.sqlite'))

def new_no_residue(mode):
    d = folder('new-' + mode); pack = simple(d); db = d/'library.sqlite'
    options = ('--dry-run',) if mode == 'dry-run' else ()
    fault = {'dry-run': None, 'failure': 'publish-fail', 'cancel': 'cancel@1'}[mode]
    rc, out, err = run(a.tx, 'migrate', '--pack', pack, '--target', db, *options, fault=fault)
    assert (rc == 0 if mode == 'dry-run' else rc != 0), (rc, out, err)
    assert not target_files(d), (target_files(d), out)

for mode in ('dry-run', 'failure', 'cancel'):
    check('new-target-' + mode + '-no-residue', lambda mode=mode: new_no_residue(mode))

def orphan():
    d = folder('orphan'); pack, db = seed(a.old, d)
    side = Path(str(db)+'.legacy-map.json'); before = side.read_bytes(); db.unlink()
    rc, out, err = run(a.tx, 'migrate', '--pack', pack, '--target', db)
    assert rc != 0 and 'orphan-ledger' in out, (rc, out, err)
    assert not db.exists() and side.read_bytes() == before
check('orphan-sidecar-refused-unchanged', orphan)

def audio():
    d = folder('audio'); db = d/'library.sqlite'; pack = d/'pack.exrpack'
    books, notes = L.dataset(); pack.write_bytes(L.build_pack(books, notes))
    rc, out, err = run(a.tx, 'migrate', '--pack', pack, '--target', db, '--allow-partial')
    assert rc == 0, (rc, out, err)
    side = Path(str(db)+'.legacy-map.json')
    errors = []
    for variant in ('missing', 'stale'):
        if variant == 'stale': side.write_text(json.dumps({'format':'exreader-legacy-map','version':1,'books':[],'notes':[],'packs':[]}))
        rc, out, err = run(a.tx, 'dump', '--target', db)
        try:
            assert rc == 0 and len(json.loads(out)['audio']) == 1, (variant, rc, out, err)
        except Exception as exc: errors.append(('dump', variant, repr(exc)))
        rc, out, err = run(a.tx, 'verify', '--pack', pack, '--target', db)
        if rc != 0: errors.append(('verify', variant, rc, out, err))
        dest = d / (variant + '.json')
        rc, out, err = run(a.tx, 'export-ledger', '--target', db, '--output', dest)
        try:
            assert rc == 0 and any(x['legacy_id'] == 'b-audio' for x in json.loads(dest.read_text())['books']), (variant, rc, out, err)
        except Exception as exc: errors.append(('export', variant, repr(exc)))
    assert not errors, errors
check('dump-verify-export-use-authoritative-audio-ledger', audio)

def wal():
    d = folder('wal'); pack, db = seed(a.old, d)
    conn = sqlite3.connect(db, timeout=1)
    try:
        assert conn.execute('PRAGMA journal_mode=WAL').fetchone()[0].lower() == 'wal'
        conn.execute('PRAGMA wal_autocheckpoint=0')
        conn.execute('BEGIN'); assert conn.execute('PRAGMA user_version').fetchone()[0] == 6
        rc, out, err = run(a.tx, 'migrate', '--pack', pack, '--target', db)
        assert rc == 0, (rc, out, err)
        assert int.from_bytes(db.read_bytes()[60:64], 'big') == 6, 'fixture checkpointed unexpectedly'
        errors = []
        for command in ('verify', 'dump', 'export-ledger'):
            args = ('--pack', pack, '--target', db) if command == 'verify' else ('--target', db)
            if command == 'export-ledger': args += ('--output', d/'export.json')
            rc, out, err = run(a.tx, command, *args)
            if rc != 0: errors.append((command, rc, out, err))
        assert not errors, errors
    finally: conn.close()
check('wal-uncheckpointed-schema-read', wal)

def retained_source():
    d = folder('close-source'); pack, db = seed(a.tx, d)
    proc = subprocess.Popen([a.close_helper, str(db)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        assert proc.stdout.readline().strip() == 'READY', 'helper failed to acquire source'
        connection = sqlite3.connect(db, timeout=0)
        try:
            connection.execute('BEGIN IMMEDIATE'); connection.rollback()
        finally: connection.close()
    finally:
        proc.communicate('\n', timeout=30)
    assert proc.returncode == 0
    with sqlite3.connect(db) as conn:
        data = conn.execute('SELECT data FROM exr_migration_ledger WHERE id=1').fetchone()[0]
        assert data != b'probe', 'uncommitted ledger unexpectedly persisted'
check('close-rolls-back-even-with-retained-source', retained_source)

def legacy_conflict():
    d = folder('legacy-conflict'); pack, db = seed(a.tx, d)
    with sqlite3.connect(db) as conn:
        before = conn.execute('SELECT data FROM exr_migration_ledger WHERE id=1').fetchone()[0]
    rc, out, err = run(a.legacy, 'migrate', '--pack', pack, '--target', db)
    assert rc != 0, ('legacy accepted internal-ledger library', out, err)
    with sqlite3.connect(db) as conn:
        assert conn.execute('SELECT data FROM exr_migration_ledger WHERE id=1').fetchone()[0] == before
check('legacy-tool-refuses-authoritative-internal-ledger', legacy_conflict)

report = {'source': os.environ['GITHUB_SHA'], 'run': os.environ['GITHUB_RUN_ID'], 'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'checks': results}
(a.work/'review.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
sys.exit(0 if all(x['passed'] for x in results) else 1)
