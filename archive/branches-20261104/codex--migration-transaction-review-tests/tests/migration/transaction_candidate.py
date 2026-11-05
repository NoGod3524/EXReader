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
            rc, out, err = call(a.tool, 'migrate', '--pack', pack, '--target', target, fault='publish-fail')
            assert rc != 0, (out, err)
            assert db.execute('PRAGMA user_version').fetchone()[0] == schema
            assert db.execute('SELECT title FROM books WHERE id=1').fetchone()[0] == old
            ready, resume = Path(str(target)+'.writer-ready'), Path(str(target)+'.writer-resume')
            env = dict(os.environ, EXR_MIGRATE_TEST_FAULTS='1')
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
            rc, out, err = call(a.tool, 'migrate', '--pack', pack, '--target', target)
            assert rc == 0, (out, err)
            db = sqlite3.connect(target)
            assert db.execute('SELECT title FROM books WHERE id=1').fetchone()[0] == 'concurrent committed writer'
            db.close()
            checks.append({'schema':schema,'journal':mode,'passed':True})
            print('PASS', checks[-1], flush=True)
    report = {'source_sha':os.environ['GITHUB_SHA'],'run_id':os.environ['GITHUB_RUN_ID'],
              'attempt':os.environ['GITHUB_RUN_ATTEMPT'],'checks':checks,'passed':len(checks)==4}
    (a.work/'transaction-result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
