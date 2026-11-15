# SPDX-License-Identifier: MIT
"""Open real v1/v2 product SQL layouts with the installed current native provider."""
import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ROOT / 'apps/reader/store'
KEY = 'txt:' + '0' * 63 + '1'
TABLES = ('reader_books', 'reader_local_books', 'reader_shelves', 'reader_book_shelves',
          'reader_tags', 'reader_book_tags', 'reader_series', 'reader_book_series',
          'reader_revisions', 'reader_outbox')


def snapshot(db, tables=TABLES):
    return {table: db.execute(f'SELECT * FROM {table} ORDER BY 1,2').fetchall()
            for table in tables}


def fixture(path, version):
    with closing(sqlite3.connect(path)) as db, db:
        for schema in ('001_catalog.sql', '002_originals.sql')[:version]:
            db.executescript((SCHEMAS / schema).read_text(encoding='utf-8'))
        db.execute('INSERT INTO reader_books VALUES(?,?,?,?,?,?,?,?,?)',
                   (KEY, 'txt', '0' * 63 + '1', 23, 'Legacy user title', 'Saved author', 'Sort', 1, 0))
        db.execute('INSERT INTO reader_local_books VALUES(?,?,?)', (KEY, 42, 'reflow_global'))
        for table, column, ident in (('shelves', 'shelf', '1'), ('tags', 'tag', '2'), ('series', 'series', '3')):
            db.execute(f'INSERT INTO reader_{table}({column}_id,name) VALUES(?,?)',
                       (ident * 32, 'Saved ' + table))
        db.execute('INSERT INTO reader_book_shelves VALUES(?,?,?)', ('1' * 32, KEY, 7))
        db.execute('INSERT INTO reader_book_tags VALUES(?,?)', (KEY, '2' * 32))
        db.execute('INSERT INTO reader_book_series VALUES(?,?,?)', ('3' * 32, KEY, 9))
        # Retain the legacy wire bytes and retry state; wire validity is tested by
        # revisions tests, while this test isolates the catalog schema migration.
        for number, operation in ((4, 'put'), (5, 'delete')):
            body = '{"legacy":"bytes preserved \\u4e66"}'
            revision = str(number) * 32
            db.execute('INSERT INTO reader_revisions VALUES(?,?,?,?,?,?)',
                       (revision, 'annotation', KEY, operation, body, hashlib.sha256(body.encode()).hexdigest()))
            db.execute('INSERT INTO reader_outbox VALUES(?,?,?,?)',
                       (number + 100, revision, 3, 'offline; retry after upgrade'))
        if version == 2:
            for number, state in enumerate(('ready', 'staged', 'deleting'), 1):
                book_key = 'txt:' + str(number) * 64
                db.execute('INSERT INTO reader_books VALUES(?,?,?,?,?,?,?,?,?)',
                           (book_key, 'txt', str(number) * 64, 10, state, '', state, 0, 0))
                db.execute('INSERT INTO reader_originals VALUES(?,?,?)',
                           (book_key, 'originals/' + state + '.txt', state))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--probe', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    output = Path(tempfile.mkdtemp(prefix='catalog-upgrade-', dir=args.output))
    passed = []
    complete = False

    def check(condition, name):
        if not condition:
            raise AssertionError(name)
        passed.append(name)
        print('PASS', name, flush=True)

    def run(path, mode='open'):
        result = subprocess.run([str(args.probe.resolve()), str(path), mode],
                                capture_output=True, text=True)
        with (output / 'native-processes.txt').open('a', encoding='utf-8') as stream:
            stream.write(f'{path.name} {mode}: exit={result.returncode}\n{result.stdout}{result.stderr}')
        check(result.returncode == 0, f'{path.name}: native {mode}')

    try:
        for version in (1, 2):
            path = output / f'v{version}.db'
            fixture(path, version)
            tables = TABLES + (('reader_originals',) if version == 2 else ())
            with closing(sqlite3.connect(path)) as db, db:
                before = snapshot(db, tables)
            run(path)
            for stage in ('upgrade', 'reopen'):
                if stage == 'reopen':
                    run(path)
                with closing(sqlite3.connect(path)) as db, db:
                    check(db.execute('PRAGMA user_version').fetchone()[0] == 3 and
                          db.execute('PRAGMA application_id').fetchone()[0] == 1163416144,
                          f'v{version}: {stage} identity/schema3')
                    check(snapshot(db, tables) == before,
                          f'v{version}: {stage} metadata, organization, mappings, revisions/outbox retained')
                    check(not db.execute('PRAGMA foreign_key_check').fetchall() and
                          db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok',
                          f'v{version}: {stage} integrity')
        # Inject a CREATE collision in each transaction. This tests rollback and
        # a later process retry, not a physical power loss or OS process kill.
        for version, collision, retained_version in ((1, 'reader_originals', 1),
                                                     (1, 'reader_original_pending', 2),
                                                     (2, 'reader_original_pending', 2)):
            path = output / f'fault-v{version}-{collision}.db'
            fixture(path, version)
            tables = TABLES + (('reader_originals',) if version == 2 else ())
            with closing(sqlite3.connect(path)) as db, db:
                before = snapshot(db, tables)
                db.execute(f'CREATE TABLE {collision}(sentinel TEXT)')
                db.execute(f'INSERT INTO {collision} VALUES(?)', ('keep fault sentinel',))
            run(path, 'reject')
            with closing(sqlite3.connect(path)) as db, db:
                check(db.execute('PRAGMA user_version').fetchone()[0] == retained_version and
                      snapshot(db, tables) == before,
                      f'{path.name}: failed transaction rolled back with legacy rows retained')
                check(db.execute(f'SELECT sentinel FROM {collision}').fetchone()[0] == 'keep fault sentinel',
                      f'{path.name}: conflicting table retained')
                db.execute(f'DROP TABLE {collision}')
            run(path)
            with closing(sqlite3.connect(path)) as db, db:
                check(db.execute('PRAGMA user_version').fetchone()[0] == 3 and snapshot(db, tables) == before,
                      f'{path.name}: new process resumes upgrade without outbox loss')
        path = output / 'future-schema.db'
        fixture(path, 2)
        with closing(sqlite3.connect(path)) as db, db:
            db.execute('PRAGMA user_version=4')
        before = path.read_bytes()
        run(path, 'reject')
        check(path.read_bytes() == before, 'future schema rejected with byte-identical database')
        complete = True
    finally:
        (output / 'result.json').write_text(json.dumps({
            'scope': 'synthetic historical product SQL layouts opened by current native provider',
            'passed': complete, 'checks': passed, 'count': len(passed), 'host_upgrade_verified': False,
            'physical_device_verified': False,
        }, indent=2) + '\n', encoding='utf-8')
    print(f'DFINAL-C product catalog upgrade: {len(passed)} checks passed', flush=True)


if __name__ == '__main__':
    main()
