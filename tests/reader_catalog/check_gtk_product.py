# SPDX-License-Identifier: MIT
"""Cloud-only checks on the actual GTK product after the original 20 UI cases."""
import argparse
import configparser
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from check_linux_host import Session


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--payload', type=Path, required=True)
    parser.add_argument('--original-evidence', type=Path, required=True)
    args = parser.parse_args()
    folder = args.original_evidence.resolve()
    original = json.loads((folder / 'report.json').read_text())
    assert original['passed'] is True and len(original['checks']) == 20
    assert all(row['pass'] is True for row in original['checks'])
    assert original['source_sha'] == os.environ['GITHUB_SHA']
    assert original['run_id'] == os.environ['GITHUB_RUN_ID']
    catalog = folder / 'profile/library.sqlite.product.sqlite'
    expected = {}
    for file, kind, mode in (('示例 reader.epub', 'epub', 'epub_chapter'),
                             ('Z unicode.txt', 'txt', 'reflow_global')):
        source = (folder / 'corpus' / file).read_bytes()
        expected[kind + ':' + hashlib.sha256(source).hexdigest()] = (len(source), mode)
    with sqlite3.connect(catalog) as db:
        assert db.execute('PRAGMA application_id').fetchone()[0] == 1163416144
        assert db.execute('PRAGMA user_version').fetchone()[0] == 1
        rows = db.execute('SELECT b.book_key,b.source_bytes,l.location_kind FROM reader_books b JOIN reader_local_books l USING(book_key)').fetchall()
        assert {key: (size, mode) for key, size, mode in rows} == expected and len(rows) == 2
        db.execute('DELETE FROM reader_local_books')
        db.execute("UPDATE reader_books SET title='User metadata retained'")
    host = Session((args.payload / 'bin/exreader-linux').resolve(),
                   (args.payload / 'Reader.otf').resolve(), folder)
    second = None
    checks = []
    try:
        host.launch()
        host.wait(lambda state: state['books'] == 2 and not state['busy'])
        end = time.monotonic() + 30
        while True:
            with sqlite3.connect(catalog) as db:
                count = db.execute('SELECT count(*) FROM reader_local_books').fetchone()[0]
            if count == 2:
                break
            assert time.monotonic() < end, 'GTK startup did not repair the local mappings'
            time.sleep(.1)
        checks.append('actual_gtk_startup_repairs_missing_local_mappings')
        with sqlite3.connect(catalog) as db:
            assert db.execute("SELECT count(*) FROM reader_books WHERE title='User metadata retained'").fetchone()[0] == 2
        checks.append('actual_gtk_repair_preserves_user_metadata')
        # A second real host cannot observe/reconcile this owner's pending import.
        second_state = folder / 'second-state.ini'
        with (folder / 'second-application.log').open('wb') as log:
            second = subprocess.Popen([str(host.binary), str(host.font), str(folder / 'profile'),
                                       str(second_state)], stdout=log, stderr=subprocess.STDOUT)
            end = time.monotonic() + 30
            while True:
                state = configparser.ConfigParser()
                if second_state.exists():
                    state.read(second_state)
                if state.has_option('host', 'error') and state.getint('host', 'error') == 3:
                    assert state.getint('host', 'books') == 0
                    break
                assert second.poll() is None and time.monotonic() < end, 'Second GTK host did not refuse the library'
                time.sleep(.1)
            second.terminate()
            second.wait(timeout=20)
            second = None
        assert host.read()['books'] == 2 and host.read()['error'] == 0
        checks.append('second_real_host_refuses_active_library_without_disturbing_owner')
        host.close()
    finally:
        if second is not None and second.poll() is None:
            second.kill()
            second.wait(timeout=20)
        if host.process is not None and host.process.poll() is None:
            host.process.kill()
            host.process.wait(timeout=20)
        if host.log:
            host.log.close()
    report = {'accepted': True, 'source_sha': os.environ['GITHUB_SHA'],
              'run_id': os.environ['GITHUB_RUN_ID'], 'attempt': os.environ['GITHUB_RUN_ATTEMPT'],
              'original_ui_cases': 20, 'checks': checks, 'complete_product': False,
              'scope': 'GTK catalog publication and startup repair; shelf display still uses SDK full books array'}
    (folder / 'product-result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
