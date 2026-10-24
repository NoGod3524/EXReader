# SPDX-License-Identifier: MIT
"""Actions-only received-entity discovery and host-fenced metadata projection."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import unicodedata

BOOK = 'txt:' + 'a' * 64
PARENT, CHILD = 'f' * 32, '%032x' % 1


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--consumer', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args(); assert os.environ.get('GITHUB_ACTIONS') == 'true'
    root = a.output.resolve(); root.mkdir(parents=True)
    db = root / 'received.sqlite'; checks = []
    def record(name):
        assert name not in checks; checks.append(name); print('PASS ' + name, flush=True)
    def raw(value): return json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode()
    def call(action, *args, expected=0):
        done = subprocess.run([str(a.consumer.resolve()), action, str(db), *map(str, args)],
                              capture_output=True, encoding='utf-8', timeout=30)
        assert done.returncode == 0, (action, done.stderr)
        value = json.loads(done.stdout); assert value['status'] == expected, (action, expected, value)
        return value
    def rev(n, kind='tag', key=None, payload=None, parents=(), operation='put', mode='none'):
        return {'version': 1, 'id': '%032x' % n, 'entity_kind': kind, 'entity_key': key or '%032x' % n,
                'operation': operation, 'location_kind': mode, 'parents': list(parents),
                'payload': None if operation == 'delete' else payload if payload is not None else {'name': '标签 ' + str(n)}}
    def file(value):
        target = root / (value['id'] + '.json'); target.write_bytes(raw(value)); return target
    def batch(values):
        target = root / 'receive.txt'
        target.write_bytes(b''.join(hashlib.sha256(raw(v)).hexdigest().encode() + b' ' + raw(v) + b'\n' for v in values))
        assert call('receive-batch', target)['accepted_count'] == len(values)
    def page(kind='tag', cursor='-', direction=1, limit=100, stop=0, flag='normal', expected=0, action='entities-page', extra=()):
        return call(action, kind, cursor, direction, limit, stop, flag, *extra, expected=expected)
    def project(row, kind='tag', sort='-', expected=0):
        return call('project-remote', kind, row['entity_key'], row['id'], sort, expected=expected)
    book = rev(10000, 'book', BOOK, {'format': 'txt', 'source_sha256': 'a' * 64, 'source_bytes': 123,
                                   'title': 'E\u0301clair', 'author': '作者', 'favorite': True})
    parent = rev(10001, 'shelf', PARENT, {'name': '父书架', 'parent_id': None, 'ordinal': 0})
    child = rev(10002, 'shelf', CHILD, {'name': '子书架', 'parent_id': PARENT, 'ordinal': 2})
    series = rev(10003, 'series', CHILD, {'name': '系列'})
    membership = rev(10004, 'membership', 'shelf:' + CHILD + ':' + BOOK,
                     {'collection_kind': 'shelf', 'collection_id': CHILD, 'book_key': BOOK, 'ordinal': 7})
    location = {'mode': 'reflow_global', 'anchor_version': 2, 'parser_version': '3.40.0',
                'selector': {'exact': '', 'prefix': '', 'suffix': '', 'start': 0, 'end': 0, 'chapter': None}}
    progress = rev(10005, 'progress', BOOK, {'book_key': BOOK, 'location': location}, mode='reflow_global')
    annotation = rev(10006, 'annotation', BOOK + ':' + CHILD,
                     {'book_key': BOOK, 'annotation_id': CHILD, 'text': '书签', 'location': location}, mode='reflow_global')
    batch([rev(i) for i in range(1, 236)] + [book, parent, child, series, membership, progress, annotation])
    edit = rev(200001, key=CHILD, parents=[rev(1)['id']])
    deleted = rev(200002, key='%032x' % 2, parents=[rev(2)['id']], operation='delete')
    pending = rev(200003, key='%032x' % 3, parents=['%032x' % 999999])
    conflict = rev(200004, key='%032x' % 4)
    tombstone = rev(200005, key='%032x' % 5, parents=[rev(5)['id']], operation='delete')
    blocked = rev(300005, key='%032x' % 5, parents=[tombstone['id']])
    batch([edit, deleted, pending, conflict, tombstone, blocked])
    with sqlite3.connect(db) as c: before = list(c.iterdump())
    def traverse(direction):
        cursor = '-'; rows = []; sizes = []
        while True:
            part = page(cursor=cursor, direction=direction)['entities']; sizes.append(len(part))
            if not part: break
            rows.extend(part); cursor = part[-1]['entity_key']
        return rows, sizes
    forward, sizes = traverse(1); reverse, reverse_sizes = traverse(-1)
    assert sizes == reverse_sizes == [100, 100, 35, 0] and reverse == forward[::-1]
    assert [r['entity_key'] for r in forward] == ['%032x' % i for i in range(1, 236)]
    record('235_distinct_entities_cross_both_keyset_directions_without_kind_leakage')
    expected_sizes = {'book': 1, 'shelf': 2, 'tag': 100, 'series': 1, 'membership': 1, 'progress': 1, 'annotation': 1}
    for kind, size in expected_sizes.items():
        rows = page(kind)['entities']; assert len(rows) == size
        assert all(not r['wire'] or json.loads(r['wire'])['entity_kind'] == kind for r in rows)
    record('all_seven_kinds_are_discoverable_without_product_projection')
    assert forward[0]['id'] == edit['id'] and forward[0]['revisions'] == 2 and forward[0]['wire'] == raw(edit).decode()
    assert forward[1]['deleted'] == 1 and forward[1]['wire'] == raw(deleted).decode()
    for offset, selection in [(2, 1), (3, 2), (4, 3)]:
        row = forward[offset]; assert row['selection_kind'] == selection and row['wire'] is None and row['id'] == '' and row['bytes'] == 0
    record('safe_bytes_tombstones_and_all_unresolved_states_remain_distinct')
    assert page(stop=3)['entities'] == forward[:3]
    assert page(cursor=forward[2]['entity_key'], limit=1)['entities'] == forward[3:4]
    assert page(cursor='0' * 32, direction=-1)['entities'] == [] and page(cursor='f' * 32)['entities'] == []
    record('callback_stop_and_boundary_cursors_do_not_skip_entities')
    for change in [dict(kind='NULL'), dict(kind='unknown'), dict(direction=0), dict(direction=2), dict(limit=0), dict(limit=101), dict(flag='null-callback')]:
        assert page(**change, expected=1)['entities'] == []
    for kind, cursor in [('tag', ''), ('tag', 'A' * 32), ('book', 'txt:bad'), ('progress', '0' * 32),
                         ('annotation', BOOK), ('membership', 'shelf:bad:' + BOOK)]:
        assert page(kind=kind, cursor=cursor, expected=4)['entities'] == []
    record('typed_cursor_and_page_arguments_are_strict')
    assert page(limit=1, flag='reentry')['nested_status'] == 11
    assert page(action='entities-wrong-thread', expected=11)['entities'] == []
    assert call('book-title-wrong-thread', book['id'], expected=11)['title'] is None
    record('page_and_title_respect_owner_and_callback_reentry')
    assert call('book-title', book['id'])['title'] == book['payload']['title']
    assert call('book-title', edit['id'], expected=1)['title'] is None
    assert call('book-title', 'a' * 32, expected=12)['title'] is None
    assert call('book-title', 'bad', expected=4)['title'] is None
    record('book_title_copy_preserves_exact_unormalized_wire_and_clears_errors')
    with sqlite3.connect(db) as c:
        assert list(c.iterdump()) == before
        assert c.execute('SELECT count(*) FROM reader_books').fetchone() == (0,)
        for op, order in [('>', ''), ('<', ' DESC')]:
            query = 'EXPLAIN QUERY PLAN SELECT DISTINCT entity_key FROM reader_revisions WHERE entity_kind=?1 AND entity_key' + op + '?2 ORDER BY entity_key' + order + ' LIMIT ?3'
            detail = ' '.join(row[3] for row in c.execute(query, ('tag', '', 100)))
            assert 'SEARCH' in detail and 'reader_revisions_entity' in detail and 'TEMP B-TREE' not in detail, detail
        assert c.execute('PRAGMA user_version').fetchone() == (1,)
    record('discovery_is_read_only_and_uses_existing_index_range_in_both_directions')
    with sqlite3.connect(db) as c: assert c.execute('PRAGMA journal_mode=WAL').fetchone()[0] == 'wal'
    restored = rev(500002, key='%032x' % 2, operation='restore', parents=[deleted['id']])
    snapshot = page(flag='mutate', extra=(file(restored),))
    assert snapshot['nested_status'] == 0 and snapshot['entities'] == forward[:100]
    assert page()['entities'][1]['id'] == restored['id']
    record('discovery_snapshot_survives_real_concurrent_other_connection_commit')
    book_row = page('book')['entities'][0]
    title = call('book-title', book_row['id'])['title']; project(book_row, 'book', unicodedata.normalize('NFC', title))
    with sqlite3.connect(db) as c:
        assert c.execute('SELECT title,sort_title,favorite FROM reader_books').fetchone() == ('E\u0301clair', '\u00c9clair', 1)
        assert c.execute('SELECT count(*) FROM reader_outbox').fetchone() == (0,)
    record('host_can_project_discovered_remote_book_with_explicit_nfc_without_new_history_or_ack')
    shelves = page('shelf')['entities']; assert shelves[0]['entity_key'] == CHILD
    project(shelves[0], 'shelf', expected=10); project(shelves[1], 'shelf'); project(shelves[0], 'shelf')
    project(page('membership')['entities'][0], 'membership')
    with sqlite3.connect(db) as c:
        assert c.execute('SELECT parent_id FROM reader_shelves WHERE shelf_id=?', (CHILD,)).fetchone() == (PARENT,)
        assert c.execute('SELECT ordinal FROM reader_book_shelves').fetchone() == (7,)
    record('child_dependencies_remain_pending_until_host_explicitly_projects_safe_parent')
    book2 = copy.deepcopy(book); book2.update(id='%032x' % 20000, parents=[book['id']]); book2['payload']['title'] = 'new title'
    batch([book2]); project(book_row, 'book', unicodedata.normalize('NFC', title), expected=10)
    new_row = page('book')['entities'][0]; project(new_row, 'book', call('book-title', new_row['id'])['title'])
    for kind in ('progress', 'annotation'): project(page(kind)['entities'][0], kind, expected=1)
    with sqlite3.connect(db) as c:
        assert c.execute('SELECT title FROM reader_books').fetchone() == ('new title',)
        assert c.execute('SELECT count(*) FROM reader_outbox').fetchone() == (0,)
    record('changed_head_is_fenced_and_reading_entities_never_project_into_metadata')
    assert len(checks) == 12
    report = {'accepted': True, 'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
              'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'checks': checks, 'count': len(checks),
              'tag_entities': 235, 'kinds': 7, 'sdk_changed': False, 'schema_changed': False, 'host_ui_accepted': False}
    (root / 'result.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8'); print(json.dumps(report), flush=True)


if __name__ == '__main__': main()
