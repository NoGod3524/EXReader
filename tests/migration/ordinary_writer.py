#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Cloud regression: an ordinary SQLite commit must survive publication."""
import argparse
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import time

import legacy_data as L


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--tool', required=True)
    p.add_argument('--work', type=Path, required=True)
    a = p.parse_args()
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    a.work.mkdir(parents=True, exist_ok=False)
    target = a.work / 'library.sqlite'
    pack = a.work / 'pack.exrpack'
    pack.write_bytes(L.build_pack([L.entry(L.book_record('old', 'old.txt'), L.TXT)], []))
    seed = subprocess.run([a.tool, 'migrate', '--pack', str(pack), '--target', str(target)],
                          capture_output=True, text=True)
    assert seed.returncode == 0, (seed.stdout, seed.stderr)
    (a.work / 'seed.json').write_text(seed.stdout, encoding='utf-8')
    ready = Path(str(target) + '.writer-ready')
    resume = Path(str(target) + '.writer-resume')
    env = dict(os.environ, EXR_MIGRATE_TEST_FAULTS='1')
    with (a.work / 'migration.log').open('w', encoding='utf-8') as log:
        process = subprocess.Popen([a.tool, 'migrate', '--pack', str(pack), '--target', str(target),
                                    '--inject', 'writer-pause'], stdout=log, stderr=subprocess.STDOUT, env=env)
        try:
            end = time.monotonic() + 30
            while not ready.exists() and process.poll() is None and time.monotonic() < end:
                time.sleep(.02)
            assert ready.exists(), 'missing post-check publication rendezvous'
            db = sqlite3.connect(target, timeout=3)
            try:
                db.execute("UPDATE books SET title = 'committed ordinary writer' WHERE id = 1")
                assert db.total_changes == 1
                db.commit()
                assert db.execute('SELECT title FROM books WHERE id = 1').fetchone()[0] == 'committed ordinary writer'
            finally:
                db.close()
            resume.write_text('resume', encoding='utf-8')
            process.wait(timeout=30)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
    result = json.loads((a.work / 'migration.log').read_text(encoding='utf-8'))
    db = sqlite3.connect(target)
    try:
        title = db.execute('SELECT title FROM books WHERE id = 1').fetchone()[0]
    finally:
        db.close()
    record = {'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
              'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'writer_committed': True,
              'migration_exit': process.returncode, 'migration_result': result['result'],
              'published_title': title, 'writer_data_preserved': title == 'committed ordinary writer'}
    (a.work / 'writer-result.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(record), flush=True)
    assert record['writer_data_preserved'], 'ordinary committed writer data was lost during publication'


if __name__ == '__main__':
    main()
