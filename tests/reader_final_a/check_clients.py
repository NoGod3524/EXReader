"""Local installed-native two-client tests. Relay simulates disconnection; no TLS/UI claim."""
import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import time


class Clients:
    def __init__(self, consumer, folder):
        self.consumer, self.folder = consumer, folder
        self.number = 0
        self.a, self.b = folder / 'a.sqlite', folder / 'b.sqlite'
        for db in (self.a, self.b):
            self.call(db, 'identity')

    def call(self, db, action, *args, expected=0):
        result = subprocess.run([str(self.consumer), action, str(db), *map(str, args)],
                                capture_output=True, encoding='utf-8', timeout=30, check=True)
        value = json.loads(result.stdout)
        assert value['status'] == expected, (action, expected, value)
        return value

    def rev(self, kind, key, payload=None, parents=(), operation='put'):
        self.number += 1
        return dict(version=1, id=f'{self.number:032x}', entity_kind=kind, entity_key=key,
                    operation=operation, location_kind='none', parents=list(parents),
                    payload=None if operation == 'delete' else payload)

    def wire(self, value):
        body = json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        path = self.folder / (hashlib.sha256(body).hexdigest() + '.json')
        path.write_bytes(body)
        return path

    def local(self, db, value, expected=0):
        return self.call(db, 'project-local', self.wire(value), ','.join(value['parents']) or '-',
                         value['payload']['title'] if value['entity_kind'] == 'book' and value['payload'] else '-',
                         expected=expected)

    def receive(self, db, value):
        path = self.wire(value)
        return self.call(db, 'receive', path, hashlib.sha256(path.read_bytes()).hexdigest())

    def project(self, db, value, expected=0):
        return self.call(db, 'project-remote', value['entity_kind'], value['entity_key'], value['id'],
                         value['payload']['title'] if value['entity_kind'] == 'book' and value['payload'] else '-',
                         expected=expected)

    def relay(self, source, target, acknowledge=True):
        rows = self.call(source, 'outbox')['outbox']
        for row in rows:
            value = json.loads(row['wire'])
            self.receive(target, value)
            if acknowledge:
                self.call(source, 'ack', row['id'], row['sha256'])
        return [json.loads(row['wire']) for row in rows]

    @staticmethod
    def sql(db, query):
        with closing(sqlite3.connect(db)) as connection:
            with connection:
                return connection.execute(query).fetchall()

    def equal_metadata(self):
        for table in ('reader_books', 'reader_shelves', 'reader_tags', 'reader_series',
                      'reader_book_shelves', 'reader_book_tags', 'reader_book_series'):
            left, right = (self.sql(db, f'SELECT * FROM {table} ORDER BY 1,2') for db in (self.a, self.b))
            assert left == right, (table, left, right)


def passed(name):
    print(f'PASS {name}', flush=True)


def organization(c):
    book_key = 'txt:' + 'a' * 64
    book = c.rev('book', book_key, dict(format='txt', source_sha256='a' * 64,
                                      source_bytes=123, title='离线书', author='作者', favorite=False))
    parent = c.rev('shelf', '1' * 32, dict(name='父书架', parent_id=None, ordinal=0))
    child = c.rev('shelf', '2' * 32, dict(name='子书架', parent_id=parent['entity_key'], ordinal=1))
    tag = c.rev('tag', '3' * 32, dict(name='分类'))
    series = c.rev('series', '4' * 32, dict(name='系列'))
    collections = [parent, child, tag, series]
    values = [book, *collections]
    for ordinal, item in enumerate((child, tag, series), 3):
        kind, key = item['entity_kind'], item['entity_key']
        values.append(c.rev('membership', f'{kind}:{key}:{book_key}',
                            dict(collection_kind=kind, collection_id=key, book_key=book_key, ordinal=ordinal)))
    for value in values:
        c.local(c.a, value)
    assert c.sql(c.b, 'SELECT count(*) FROM reader_books') == [(0,)]
    c.relay(c.a, c.b)
    for value in values:
        c.project(c.b, value)
    c.equal_metadata()
    assert c.sql(c.b, 'SELECT parent_id,ordinal FROM reader_shelves WHERE parent_id IS NOT NULL') == [('1' * 32, 1)]
    assert c.sql(c.b, 'SELECT ordinal FROM reader_book_series') == [(5,)]
    passed('offline_nested_shelves_tags_series_memberships_converge_after_reopen')
    for old in [*reversed(collections), *values[5:], book]:
        deleted = c.rev(old['entity_kind'], old['entity_key'], parents=[old['id']], operation='delete')
        c.local(c.a, deleted)
        c.relay(c.a, c.b)
        c.project(c.b, deleted)
        c.equal_metadata()
        implicit = c.rev(old['entity_kind'], old['entity_key'], old['payload'], [deleted['id']])
        c.local(c.a, implicit, expected=10)
        restored = c.rev(old['entity_kind'], old['entity_key'], old['payload'], [deleted['id']], 'restore')
        c.local(c.a, restored)
        c.relay(c.a, c.b)
        c.project(c.b, restored)
        c.equal_metadata()
        passed(f"{old['entity_kind']}_{old['entity_key'].split(':')[0]}_delete_blocks_put_explicit_restore_converges")
    for db in (c.a, c.b):
        assert c.sql(db, 'PRAGMA integrity_check') == [('ok',)]
        assert c.sql(db, 'PRAGMA foreign_key_check') == []
        assert c.call(db, 'outbox')['outbox'] == []
    passed('both_catalogs_integrity_and_foreign_keys_ok_no_remote_echo')


def reconnect(c):
    base = c.rev('tag', '5' * 32, dict(name='Initial'))
    c.local(c.a, base)
    c.relay(c.a, c.b)
    c.project(c.b, base)
    edit = c.rev('tag', base['entity_key'], dict(name='Offline edit'), [base['id']])
    tombstone = c.rev('tag', base['entity_key'], parents=[base['id']], operation='delete')
    c.local(c.a, edit)
    c.local(c.b, tombstone)
    assert len(c.call(c.a, 'outbox')['outbox']) == len(c.call(c.b, 'outbox')['outbox']) == 1
    passed('two_disconnected_clients_persist_independent_edit_and_tombstone')
    c.relay(c.a, c.b, acknowledge=False)  # simulated cancellation after receive, before acknowledgement
    assert len(c.call(c.a, 'outbox')['outbox']) == 1
    assert c.receive(c.b, edit)['created'] == 0
    c.relay(c.b, c.a)
    c.relay(c.a, c.b)
    for db in (c.a, c.b):
        state = c.call(db, 'heads', 'tag', base['entity_key'])
        assert {h['id'] for h in state['heads']} == {edit['id'], tombstone['id']}
        c.project(db, edit, expected=10)
        c.project(db, tombstone, expected=10)
    passed('reconnect_preserves_both_heads_replay_is_idempotent_no_silent_winner')
    restored = c.rev('tag', base['entity_key'], dict(name='Explicit merged restore'),
                     [edit['id'], tombstone['id']], 'restore')
    c.local(c.a, restored)
    c.relay(c.a, c.b)
    c.project(c.b, restored)
    c.equal_metadata()
    for db in (c.a, c.b):
        assert c.sql(db, 'SELECT name,deleted FROM reader_tags') == [('Explicit merged restore', 0)]
        assert c.call(db, 'outbox')['outbox'] == []
        assert c.call(db, 'heads', 'tag', base['entity_key'])['state']['heads'] == 1
    passed('explicit_restore_covers_all_heads_and_converges_without_outbox_echo')


def crash(c):
    for action, committed in [('crash-project-before-metadata', False), ('crash-project-after-commit', True)]:
        db = c.folder / (action + '.sqlite')
        c.call(db, 'identity')
        if not committed:
            c.sql(db, 'CREATE TRIGGER pause_projection BEFORE INSERT ON reader_tags BEGIN SELECT reader_test_pause(); END')
        value = c.rev('tag', ('7' if committed else '6') * 32, dict(name='Crash recovery'))
        marker = c.folder / (action + '.ready')
        process = subprocess.Popen([str(c.consumer), action, str(db), str(c.wire(value)), '-', '-', str(marker)],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 30
            while not marker.exists():
                assert process.poll() is None and time.monotonic() < deadline, 'crash gate not reached'
                time.sleep(.02)
            process.kill()
            process.communicate(timeout=20)
            assert process.returncode != 0
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=20)
        counts = c.sql(db, 'SELECT (SELECT count(*) FROM reader_revisions),(SELECT count(*) FROM reader_outbox),(SELECT count(*) FROM reader_tags)')
        assert counts == [(int(committed),) * 3], counts
        if not committed:
            c.sql(db, 'DROP TRIGGER pause_projection')
        c.local(db, value)
        replay = c.local(db, value)
        assert replay['created'] == replay['applied'] == 0
        c.relay(db, c.b, acknowledge=False)
        assert c.receive(c.b, value)['created'] == 0
        c.relay(db, c.b)
        c.project(c.b, value)
        assert c.sql(db, 'PRAGMA integrity_check') == [('ok',)]
        assert c.sql(db, 'SELECT count(*) FROM reader_revisions') == [(1,)]
        assert c.call(db, 'outbox')['outbox'] == []
        passed(action + '_real_kill_atomic_recovery_retry_and_second_client_receive')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--consumer', required=True, type=Path)
    parser.add_argument('--scenario', choices=('organization', 'reconnect', 'crash'), required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='exreader-final-a-') as folder:
        globals()[args.scenario](Clients(args.consumer.resolve(), Path(folder)))


if __name__ == '__main__':
    main()
