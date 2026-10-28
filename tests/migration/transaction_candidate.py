#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Candidate transaction, real old SDK, rollback, WAL and ordinary writer checks."""
import argparse
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import time
import legacy_data as L


def call(tool, *args, fault=None):
    env = dict(os.environ)
    if fault:
        env['EXR_MIGRATE_TEST_FAULTS'] = '1'
        args += ('--inject', fault)
    p = subprocess.run([tool, *map(str, args)], capture_output=True, text=True, env=env)
    return p.returncode, p.stdout, p.stderr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tool', required=True)
    ap.add_argument('--old-tool', required=True)
    ap.add_argument('--work', type=Path, required=True)
    a = ap.parse_args()
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    a.work.mkdir(parents=True, exist_ok=False)
    checks = []
    for schema in (6, 7):
        for mode in ('delete', 'wal'):
            folder = a.work / ('schema%d-%s' % (schema, mode))
            folder.mkdir()
            target = folder / 'library.sqlite'
            pack = folder / 'pack.exrpack'
            book = L.entry(L.book_record('old', 'old.txt'), L.TXT)
            note = L.note_record('old-note', 'old', 'lantern keeper', 'retained comment')
            pack.write_bytes(L.build_pack([book], [note]))
            seed_tool = a.old_tool if schema == 6 else a.tool
            rc, out, err = call(seed_tool, 'migrate', '--pack', pack, '--target', target)
            assert rc == 0, (rc, out, err)
            db = sqlite3.connect(target, timeout=0)
            assert db.execute('PRAGMA user_version').fetchone()[0] == schema
            assert db.execute('PRAGMA journal_mode=' + mode).fetchone()[0].lower() == mode
            old = db.execute('SELECT title FROM books WHERE id=1').fetchone()[0]
            old_ledger = db.execute("SELECT count(*) FROM sqlite_master WHERE name='exr_migration_ledger'").fetchone()[0]
            rc, out, err = call(a.tool, 'migrate', '--pack', pack, '--target', target, fault='publish-fail')
            assert rc != 0, (out, err)
            assert db.execute('PRAGMA user_version').fetchone()[0] == schema
            assert db.execute('SELECT title FROM books WHERE id=1').fetchone()[0] == old
            ready, resume = Path(str(target)+'.writer-ready'), Path(str(target)+'.writer-resume')
            env = dict(os.environ, EXR_MIGRATE_TEST_FAULTS='1')
            crash_pack = folder/'crash.exrpack'
            extra = L.entry(L.book_record('extra', 'extra.txt'), L.TXT_OTHER)
            crash_pack.write_bytes(L.build_pack([book, extra], [note]))
            with (folder/'crash.log').open('w', encoding='utf-8') as log:
                killed = subprocess.Popen([a.tool, 'migrate', '--pack', str(crash_pack), '--target', str(target), '--inject', 'writer-pause'], stdout=log, stderr=subprocess.STDOUT, env=env)
                try:
                    end = time.monotonic()+30
                    while not ready.exists() and killed.poll() is None and time.monotonic()<end:
                        time.sleep(.02)
                    assert ready.exists(), 'crash rendezvous missing'
                    killed.kill();killed.wait(timeout=30)
                finally:
                    if killed.poll() is None:
                        killed.kill();killed.wait()
            ready.unlink(missing_ok=True)
            assert db.execute('PRAGMA user_version').fetchone()[0] == schema
            assert db.execute('SELECT count(*) FROM books').fetchone()[0] == 1
            assert db.execute("SELECT count(*) FROM sqlite_master WHERE name='exr_migration_ledger'").fetchone()[0] == old_ledger
            with (folder/'migration.log').open('w', encoding='utf-8') as log:
                process = subprocess.Popen([a.tool, 'migrate', '--pack', str(pack), '--target', str(target), '--inject', 'writer-pause'], stdout=log, stderr=subprocess.STDOUT, env=env)
                try:
                    end = time.monotonic()+30
                    while not ready.exists() and process.poll() is None and time.monotonic()<end:
                        time.sleep(.02)
                    assert ready.exists(), 'transaction rendezvous missing'
                    try:
                        db.execute("UPDATE books SET title='concurrent committed writer' WHERE id=1")
                        db.commit()
                        raise AssertionError('writer committed while migration transaction was open')
                    except sqlite3.OperationalError as error:
                        assert 'locked' in str(error).lower() or 'busy' in str(error).lower(), error
                        db.rollback()
                    resume.write_text('resume', encoding='utf-8')
                    process.wait(timeout=30)
                finally:
                    if process.poll() is None:
                        process.kill();process.wait()
            assert process.returncode == 0, (folder/'migration.log').read_text(encoding='utf-8')
            db.execute("UPDATE books SET title='concurrent committed writer' WHERE id=1")
            db.commit()
            assert db.execute('SELECT title FROM books WHERE id=1').fetchone()[0] == 'concurrent committed writer'
            assert db.execute('PRAGMA user_version').fetchone()[0] == 7
            db.close()
            rc, out, err = call(a.tool, 'verify', '--pack', pack, '--target', target)
            assert rc == 0, (out, err)
            output = folder/'ledger.json'
            rc, out, err = call(a.tool, 'export-ledger', '--target', target, '--output', output)
            assert rc == 0 and json.loads(output.read_text(encoding='utf-8'))['format'] == 'exreader-legacy-map', (out, err)
            exported = output.read_bytes()
            rc, out, err = call(a.tool, 'export-ledger', '--target', target, '--output', output)
            assert rc != 0 and output.read_bytes() == exported, (out, err)
            rc, out, err = call(a.tool, 'migrate', '--pack', pack, '--target', target)
            assert rc == 0, (out, err)
            db = sqlite3.connect(target)
            assert db.execute('SELECT title FROM books WHERE id=1').fetchone()[0] == 'concurrent committed writer'
            db.close()
            committed_ready = Path(str(target)+'.commit-ready')
            with (folder/'committed-crash.log').open('w', encoding='utf-8') as log:
                killed = subprocess.Popen([a.tool, 'migrate', '--pack', str(crash_pack), '--target', str(target), '--inject', 'commit-pause'], stdout=log, stderr=subprocess.STDOUT, env=env)
                try:
                    end = time.monotonic()+30
                    while not committed_ready.exists() and killed.poll() is None and time.monotonic()<end:
                        time.sleep(.02)
                    assert committed_ready.exists(), 'post-commit crash rendezvous missing'
                    killed.kill();killed.wait(timeout=30)
                finally:
                    if killed.poll() is None:
                        killed.kill();killed.wait()
            committed_ready.unlink(missing_ok=True)
            db = sqlite3.connect(target)
            assert db.execute('SELECT count(*) FROM books').fetchone()[0] == 2
            assert db.execute('SELECT title FROM books WHERE id=1').fetchone()[0] == 'concurrent committed writer'
            db.close()
            rc, out, err = call(a.tool, 'verify', '--pack', crash_pack, '--target', target)
            assert rc == 0, (out, err)
            rc, out, err = call(a.tool, 'migrate', '--pack', crash_pack, '--target', target)
            assert rc == 0, (out, err)
            db = sqlite3.connect(target)
            ledger = db.execute('SELECT data FROM exr_migration_ledger WHERE id=1').fetchone()[0]
            damaged = b'{"format":"exreader-legacy-map","version":99,"books":[],"notes":[]}'
            db.execute('UPDATE exr_migration_ledger SET data=? WHERE id=1', (damaged,))
            db.commit()
            db.close()
            rc, out, err = call(a.tool, 'migrate', '--pack', crash_pack, '--target', target)
            assert rc == 2 and json.loads(out)['code'] == 'ledger-unknown-version', (out, err)
            db = sqlite3.connect(target)
            assert db.execute('SELECT count(*) FROM books').fetchone()[0] == 2
            assert db.execute('SELECT data FROM exr_migration_ledger WHERE id=1').fetchone()[0] == damaged
            db.execute('UPDATE exr_migration_ledger SET data=? WHERE id=1', (ledger,))
            db.commit();db.close()
            checks.append({'schema':schema,'journal':mode,'passed':True})
            print('PASS', checks[-1], flush=True)
    folder = a.work/'full-ledger'
    folder.mkdir()
    target = folder/'library.sqlite'
    pack = folder/'full.exrpack'
    books, notes = L.dataset()
    pack.write_bytes(L.build_pack(books, notes))
    rc, out, err = call(a.tool, 'migrate', '--pack', pack, '--target', target, '--allow-partial')
    assert rc == 0, (out, err)
    report = json.loads(out)
    ambiguous = next(n for n in report['notes'] if n['legacy_id'] == 'n-txt-ambiguous')
    assert ambiguous['status'] == 'unlocated' and ambiguous['reason'] == 'quote-ambiguous'
    first = folder/'first-ledger.json'
    rc, out, err = call(a.tool, 'export-ledger', '--target', target, '--output', first)
    assert rc == 0, (out, err)
    ledger = json.loads(first.read_text(encoding='utf-8'))
    ambiguous = next(n for n in ledger['notes'] if n['legacy_id'] == 'n-txt-ambiguous')
    assert ambiguous['located'] is False and ambiguous['retained']['note'] == 'appears twice'
    assert ambiguous['retained']['quote'] == 'Repeat this phrase twice.'
    fixed = next(n for n in ledger['notes'] if n['legacy_id'] == 'n-pdf-quote')
    assert fixed['retained']['rects'][0]['w'] == 0.4
    orphan = next(n for n in ledger['notes'] if n['legacy_id'] == 'n-orphan')
    assert orphan['retained']['note'] == 'orphan'
    rc, out, err = call(a.tool, 'migrate', '--pack', pack, '--target', target, '--allow-partial')
    assert rc == 0, (out, err)
    counts = json.loads(out)['counts']
    assert counts['books_created'] == 0 and counts['notes_created'] == 0
    second = folder/'second-ledger.json'
    rc, out, err = call(a.tool, 'export-ledger', '--target', target, '--output', second)
    assert rc == 0 and first.read_bytes() == second.read_bytes(), (out, err)
    rc, out, err = call(a.tool, 'verify', '--pack', pack, '--target', target)
    assert rc == 0, (out, err)
    checks.append({'case':'full-ledger-export-and-idempotence','passed':True})
    print('PASS', checks[-1], flush=True)
    report = {'source_sha':os.environ['GITHUB_SHA'],'run_id':os.environ['GITHUB_RUN_ID'],
              'attempt':os.environ['GITHUB_RUN_ATTEMPT'],'checks':checks,'passed':len(checks)==5}
    (a.work/'transaction-result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
