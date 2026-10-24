# SPDX-License-Identifier: MIT
"""Actions-only installed product annotation keysets and snapshot isolation."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess

BOOK = 'txt:' + 'a' * 64


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--consumer', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    a = p.parse_args(); assert os.environ.get('GITHUB_ACTIONS') == 'true'
    root = a.output.resolve(); root.mkdir(parents=True)
    db = root / 'annotations.sqlite'; checks = []
    def record(name):
        assert name not in checks; checks.append(name); print('PASS ' + name, flush=True)
    def encode(value): return json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode()
    def call(action, *args, expected=0):
        done = subprocess.run([str(a.consumer.resolve()), action, str(db), *map(str, args)],
                              capture_output=True, text=True, encoding='utf-8', timeout=30)
        assert done.returncode == 0, (action, done.stderr)
        value = json.loads(done.stdout); assert value['status'] == expected, (action, expected, value)
        return value
    def revision(i, n=None, book=BOOK):
        aid = '%032x' % i
        return {'version': 1, 'id': '%032x' % (n or 100000 + i), 'entity_kind': 'annotation',
                'entity_key': book + ':' + aid, 'operation': 'put', 'location_kind': 'reflow_global', 'parents': [],
                'payload': {'book_key': book, 'annotation_id': aid, 'text': '书签 ' + str(i),
                            'location': {'mode': 'reflow_global', 'anchor_version': 2, 'parser_version': '3.40.0',
                                         'selector': {'exact': '', 'prefix': '', 'suffix': '', 'start': 0, 'end': 0, 'chapter': None}}}}
    def batch(values):
        target = root / 'batch.txt'
        target.write_bytes(b''.join(hashlib.sha256(encode(v)).hexdigest().encode() + b' ' + encode(v) + b'\n' for v in values))
        assert call('receive-batch', target)['accepted_count'] == len(values)
    def page(cursor='-', direction=1, limit=100, stop=0, flag='normal', book=BOOK, expected=0, action='annotations-page', extra=()):
        return call(action, book, cursor, direction, limit, stop, flag, *extra, expected=expected)
    book = {'version': 1, 'id': '%032x' % 100, 'entity_kind': 'book', 'entity_key': BOOK,
            'operation': 'put', 'location_kind': 'none', 'parents': [],
            'payload': {'format': 'txt', 'source_sha256': 'a' * 64, 'source_bytes': 100,
                        'title': '书', 'author': '', 'favorite': False}}
    batch([book] + [revision(i) for i in range(1, 236)])
    assert page(book='pdf:' + 'f' * 64)['annotations'] == []
    record('missing_book_is_an_empty_read_page')
    edit = revision(1, 200001); edit['parents'] = [revision(1)['id']]
    delete = revision(2, 200002); delete.update(parents=[revision(2)['id']], operation='delete', payload=None)
    pending = revision(3, 200003); pending['parents'] = ['%032x' % 99999999]
    conflict = revision(4, 200004)
    tombstone = revision(5, 200005); tombstone.update(parents=[revision(5)['id']], operation='delete', payload=None)
    blocked = revision(5, 300005); blocked['parents'] = [tombstone['id']]
    other = revision(1, 400001, 'txt:' + 'b' * 64)
    progress = copy.deepcopy(revision(8, 400008)); progress.update(entity_kind='progress', entity_key=BOOK)
    progress['payload'].pop('annotation_id'); progress['payload'].pop('text')
    batch([edit, delete, pending, conflict, tombstone, blocked, other, progress])
    with sqlite3.connect(db) as c:
        initial = list(c.iterdump())
    def traverse(direction):
        rows = []; cursor = '-'; sizes = []
        while True:
            chunk = page(cursor=cursor, direction=direction)['annotations']; sizes.append(len(chunk))
            if not chunk: break
            rows.extend(chunk); cursor = chunk[-1]['annotation_id']
        return rows, sizes
    forward, sizes = traverse(1)
    assert sizes == [100, 100, 35, 0]
    assert [r['annotation_id'] for r in forward] == ['%032x' % i for i in range(1, 236)]
    record('forward_keyset_crosses_100_boundaries_without_duplicates_or_other_books')
    reverse, sizes = traverse(-1)
    assert sizes == [100, 100, 35, 0] and reverse == forward[::-1]
    record('reverse_keyset_returns_every_retained_global_id_once')
    assert forward[0]['revisions'] == 2 and forward[0]['id'] == edit['id']
    assert forward[0]['wire'] == encode(edit).decode() and forward[0]['selection_kind'] == 4
    assert forward[1]['deleted'] == 1 and forward[1]['wire'] == encode(delete).decode()
    record('safe_latest_bytes_and_tombstones_are_explicit')
    for offset, kind in [(2, 1), (3, 2), (4, 3)]:
        row = forward[offset]
        assert row['selection_kind'] == kind and row['wire'] is None and row['id'] == '' and row['bytes'] == 0
    record('pending_concurrent_and_implicit_restore_have_no_chosen_wire')
    stopped = page(stop=5)['annotations']
    assert stopped == forward[:5]
    assert page(cursor=stopped[-1]['annotation_id'], limit=1)['annotations'] == forward[5:6]
    assert page(cursor='0' * 32, direction=-1)['annotations'] == []
    assert page(cursor='f' * 32)['annotations'] == []
    record('callback_stop_and_boundary_cursors_preserve_keysets')
    for change in [dict(limit=0), dict(limit=101), dict(direction=0), dict(direction=2),
                   dict(book='NULL'), dict(flag='null-callback')]:
        assert page(**change, expected=1)['annotations'] == []
    for change in [dict(cursor=''), dict(cursor='A' * 32), dict(cursor='0' * 31), dict(book='txt:bad')]:
        assert page(**change, expected=4)['annotations'] == []
    record('invalid_bounds_identity_direction_cursor_and_callback_are_refused')
    value = page(limit=1, flag='reentry')
    assert value['nested_status'] == 11 and value['annotations'] == forward[:1]
    assert page(action='annotations-wrong-thread', expected=11)['annotations'] == []
    record('callback_reentry_and_nonowner_calls_are_refused')
    with sqlite3.connect(db) as c:
        assert list(c.iterdump()) == initial
        assert c.execute('PRAGMA user_version').fetchone() == (1,)
        assert c.execute('PRAGMA application_id').fetchone() == (1163416144,)
        for direction in ('', ' DESC'):
            plan = c.execute("EXPLAIN QUERY PLAN SELECT DISTINCT entity_key FROM reader_revisions "
                             "WHERE entity_kind='annotation' AND entity_key>?1 AND entity_key<?2 "
                             "ORDER BY entity_key" + direction + ' LIMIT ?3', (BOOK + ':', BOOK + ':g', 100)).fetchall()
            detail = ' '.join(str(row[3]) for row in plan)
            assert 'SEARCH' in detail and 'reader_revisions_entity' in detail and 'TEMP B-TREE' not in detail, detail
    record('pages_are_read_only_and_both_directions_use_schema1_index_ranges')
    with sqlite3.connect(db) as c: assert c.execute('PRAGMA journal_mode=WAL').fetchone()[0] == 'wal'
    restored = revision(2, 500002); restored.update(operation='restore', parents=[delete['id']])
    target = root / 'concurrent-restore.json'; target.write_bytes(encode(restored))
    snapshot = page(flag='mutate', extra=(target,))
    assert snapshot['nested_status'] == 0 and snapshot['annotations'] == forward[:100]
    after = page()['annotations']
    assert after[1]['id'] == restored['id'] and after[1]['deleted'] == 0
    assert after[:1] == forward[:1] and after[2:] == forward[2:100]
    record('one_read_snapshot_excludes_a_real_second_connection_commit_until_next_page')
    assert len(checks) == 10
    report = {'accepted': True, 'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
              'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'checks': checks, 'count': len(checks),
              'entities': 235, 'schema_changed': False, 'sdk_changed': False, 'host_ui_accepted': False}
    (root / 'result.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report), flush=True)


if __name__ == '__main__': main()
