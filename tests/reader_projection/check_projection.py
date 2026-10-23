# SPDX-License-Identifier: MIT
"""Cloud-only installed native atomic metadata/history/outbox acceptance."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
import unicodedata

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'reader_sync'))
from check_sync import revision, raw

OK, ARG, DATABASE, FORMAT, LIMIT, COLLISION, UNSAFE, NOT_FOUND = 0, 1, 3, 4, 5, 7, 10, 12
TAG = '1' * 32
BOOK = 'txt:' + 'a' * 64


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--consumer', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    folder = a.output.resolve();folder.mkdir(parents=True)
    consumer = a.consumer.resolve()
    checks = []

    def record(name):
        assert name not in {x['id'] for x in checks}
        checks.append({'id': name, 'pass': True})
        print(json.dumps({'check': name, 'pass': True}), flush=True)

    def invoke(db, action, *args, expected=OK):
        result = subprocess.run([str(consumer), action, str(db), *map(str, args)],
                                capture_output=True, encoding='utf-8', errors='strict', timeout=60)
        assert result.returncode == 0, (action, result.returncode, result.stderr)
        value = json.loads(result.stdout)
        assert value['status'] == expected, (action, expected, value)
        if expected != OK:
            assert value['created'] == 0 and value['applied'] == 0
        return value

    def wire(value):
        data = raw(value)
        path = folder / (value['id'] + '-' + hashlib.sha256(data).hexdigest()[:8] + '.json')
        path.write_bytes(data)
        return path

    def local(db, value, expected_heads=(), sort='-', expected=OK):
        return invoke(db, 'project-local', wire(value), ','.join(expected_heads) or '-', sort, expected=expected)

    def receive(db, value):
        path = wire(value)
        return invoke(db, 'receive', path, hashlib.sha256(path.read_bytes()).hexdigest())

    def project(db, value, expected_head=None, sort='-', expected=OK):
        return invoke(db, 'project-remote', value['entity_kind'], value['entity_key'], expected_head or value['id'], sort, expected=expected)

    def selected(db, kind='tag', key=TAG, expected=OK):
        output = folder / 'selected-original.json'
        if output.exists():
            output.unlink()
        value = invoke(db, 'selected', kind, key, output, expected=expected)
        assert output.exists() == (expected == OK)
        return value, output.read_bytes() if output.exists() else None

    def sql(db, query, parameters=()):
        with sqlite3.connect(db) as connection:
            return connection.execute(query, parameters).fetchall()

    def counts(db):
        return tuple(sql(db, 'SELECT (SELECT count(*) FROM reader_revisions),(SELECT count(*) FROM reader_outbox)')[0])

    db = folder / '产品.sqlite'
    value, output = selected(db, expected=NOT_FOUND)
    assert value['selection_kind'] == 0 and value['state']['heads'] == 0 and output is None
    record('selected_missing_is_explicit_and_returns_no_wire')
    decomposed = 'E\u0301clair'
    book = revision(1, kind='book', key=BOOK, payload={'format': 'txt', 'source_sha256': 'a' * 64,
                    'source_bytes': 123, 'title': decomposed, 'author': '作者', 'favorite': False})
    normalized = unicodedata.normalize('NFC', decomposed)
    result = local(db, book, sort=normalized)
    assert result['created'] == result['applied'] == 1 and counts(db) == (1, 1)
    assert sql(db, 'SELECT title,sort_title,source_bytes FROM reader_books') == [(decomposed, normalized, 123)]
    assert invoke(db, 'outbox')['outbox'][0]['wire'].encode() == raw(book)
    record('local_book_metadata_history_outbox_commit_atomically_without_rewriting_wire_for_nfc_sort')
    book2 = revision(2, kind='book', key=BOOK, parents=[book['id']], payload=dict(book['payload'], title='Renamed', favorite=True))
    local(db, book2, sort='Renamed', expected=UNSAFE)
    assert counts(db) == (1, 1) and sql(db, 'SELECT title FROM reader_books') == [(decomposed,)]
    record('stale_expected_head_set_refuses_all_three_changes')
    missing_parent_set = dict(book2, parents=[])
    local(db, missing_parent_set, [book['id']], sort='Renamed', expected=UNSAFE)
    assert counts(db) == (1, 1)
    record('new_parent_set_must_equal_the_observed_current_heads')
    sql(db, "INSERT INTO reader_local_books VALUES(?,111,'reflow_global')", (BOOK,))
    local(db, book2, [book['id']], sort='Renamed')
    assert counts(db) == (2, 2) and sql(db, 'SELECT title,favorite FROM reader_books') == [('Renamed', 1)]
    assert sql(db, 'SELECT sdk_book_id,location_kind FROM reader_local_books') == [(111, 'reflow_global')]
    record('book_metadata_update_preserves_original_identity_and_device_local_sdk_mapping')
    invoke(db, 'ack', book['id'], hashlib.sha256(raw(book)).hexdigest())
    result = local(db, book, sort=normalized)
    assert result['created'] == result['applied'] == 0 and counts(db) == (2, 1)
    assert sql(db, 'SELECT title FROM reader_books') == [('Renamed',)]
    record('exact_old_id_replay_does_not_reapply_metadata_or_requeue_after_ack')
    local(db, dict(book2, payload=dict(book2['payload'], title='Collision')), [book['id']], sort='Collision', expected=COLLISION)
    assert counts(db) == (2, 1)
    record('same_id_different_original_bytes_never_replaces_product_metadata')
    book3 = revision(3, kind='book', key=BOOK, parents=[book2['id']], payload=dict(book2['payload'], title='Remote'))
    receive(db, book3)
    assert sql(db, 'SELECT title FROM reader_books') == [('Renamed',)] and counts(db) == (3, 1)
    project(db, book3, expected_head=book2['id'], sort='Remote', expected=UNSAFE)
    assert sql(db, 'SELECT title FROM reader_books') == [('Renamed',)]
    record('remote_receive_preserves_metadata_until_current_safe_head_is_explicitly_projected')
    project(db, book3, sort='Remote')
    assert counts(db) == (3, 1) and sql(db, 'SELECT title FROM reader_books') == [('Remote',)]
    value, original = selected(db, 'book', BOOK)
    assert value['selection_kind'] == 4 and original == raw(book3)
    record('remote_projection_changes_only_metadata_and_safe_selection_returns_exact_original')
    book4 = revision(4, kind='book', key=BOOK, parents=[book3['id']], payload=dict(book3['payload'], title='Bad sort'))
    local(db, book4, [book3['id']], expected=ARG)
    local(db, book4, [book3['id']], sort='x' * 16385, expected=LIMIT)
    assert counts(db) == (3, 1) and sql(db, 'SELECT title FROM reader_books') == [('Remote',)]
    record('missing_or_overlong_host_sort_key_rolls_back_history_outbox_and_metadata')
    fault = folder / 'metadata-fault.sqlite';invoke(fault, 'identity')
    sql(fault, "CREATE TRIGGER fail_metadata BEFORE INSERT ON reader_tags BEGIN SELECT RAISE(ABORT,'fixture metadata failure');END")
    tag = revision(20)
    local(fault, tag, expected=DATABASE)
    assert counts(fault) == (0, 0) and not sql(fault, 'SELECT * FROM reader_tags')
    sql(fault, 'DROP TRIGGER fail_metadata');local(fault, tag)
    assert counts(fault) == (1, 1) and sql(fault, 'SELECT name FROM reader_tags') == [('书架',)]
    record('metadata_fault_rolls_back_preceding_history_and_outbox_and_same_id_can_retry')
    queue_fault = folder / 'queue-fault.sqlite';invoke(queue_fault, 'identity')
    sql(queue_fault, "CREATE TRIGGER fail_queue BEFORE INSERT ON reader_outbox BEGIN SELECT RAISE(ABORT,'fixture queue failure');END")
    local(queue_fault, tag, expected=DATABASE)
    assert counts(queue_fault) == (0, 0) and not sql(queue_fault, 'SELECT * FROM reader_tags')
    receive(queue_fault, tag);project(queue_fault, tag)
    assert counts(queue_fault) == (1, 0) and len(sql(queue_fault, 'SELECT * FROM reader_tags')) == 1
    record('outbox_fault_rolls_back_local_metadata_while_remote_projection_never_enqueues')
    plain = folder / 'plain-existing.sqlite'
    invoke(plain, 'local', wire(tag))
    assert not sql(plain, 'SELECT * FROM reader_tags')
    result = local(plain, tag)
    assert result['created'] == result['applied'] == 0 and not sql(plain, 'SELECT * FROM reader_tags')
    project(plain, tag)
    assert counts(plain) == (1, 1) and len(sql(plain, 'SELECT * FROM reader_tags')) == 1
    record('already_retained_plain_revision_requires_explicit_remote_projection_instead_of_duplicate_replay')
    conflict = folder / 'conflict.sqlite';local(conflict, tag)
    ta = revision(21, parents=[tag['id']], payload={'name': 'A'})
    tb = revision(22, parents=[tag['id']], payload={'name': 'B'})
    receive(conflict, ta);receive(conflict, tb)
    value, _ = selected(conflict, expected=UNSAFE)
    assert value['selection_kind'] == 2 and value['state']['heads'] == 2
    project(conflict, ta, expected=UNSAFE)
    assert sql(conflict, 'SELECT name FROM reader_tags') == [('书架',)]
    record('concurrent_selection_is_explicit_and_cannot_silently_project_a_winner')
    merged = revision(23, parents=[ta['id'], tb['id']], payload={'name': 'Resolved'})
    local(conflict, merged, [tb['id'], ta['id']])
    assert counts(conflict) == (4, 2) and sql(conflict, 'SELECT name FROM reader_tags') == [('Resolved',)]
    record('explicit_local_merge_covers_the_complete_unordered_expected_head_set')
    tombstone = revision(24, parents=[merged['id']], operation='delete')
    local(conflict, tombstone, [merged['id']])
    value, original = selected(conflict)
    assert value['selection_kind'] == 4 and value['state']['deleted'] and original == raw(tombstone)
    assert sql(conflict, 'SELECT deleted FROM reader_tags') == [(1,)]
    implicit = revision(25, parents=[tombstone['id']])
    local(conflict, implicit, [tombstone['id']], expected=UNSAFE)
    assert counts(conflict) == (5, 3)
    record('soft_delete_retains_metadata_history_and_blocks_implicit_local_resurrection')
    restored = revision(26, parents=[tombstone['id']], operation='restore', payload={'name': 'Restored'})
    local(conflict, restored, [tombstone['id']])
    assert sql(conflict, 'SELECT name,deleted FROM reader_tags') == [('Restored', 0)]
    record('explicit_restore_uses_the_tombstone_parent_before_reactivating_metadata')
    waiting = folder / 'pending.sqlite'
    parent = revision(31)
    child = revision(32, parents=[parent['id']])
    receive(waiting, child)
    value, _ = selected(waiting, expected=UNSAFE)
    assert value['selection_kind'] == 1 and value['state']['missing_parents'] == 1
    receive(waiting, parent)
    assert selected(waiting)[0]['selection_kind'] == 4
    record('pending_parent_selection_is_distinct_and_becomes_safe_after_causal_completion')
    blocked = folder / 'blocked-restore.sqlite'
    receive(blocked, tombstone);receive(blocked, merged);receive(blocked, ta);receive(blocked, tb);receive(blocked, tag);receive(blocked, implicit)
    value, _ = selected(blocked, expected=UNSAFE)
    assert value['selection_kind'] == 3 and value['state']['requires_restore']
    record('implicit_remote_restore_is_an_explicit_blocked_state_without_wire_success')
    location = {'mode': 'reflow_global', 'parser_version': '3.40.0', 'anchor_version': 1,
                'selector': {'exact': 'Reading', 'prefix': '', 'suffix': ' text', 'start': 0, 'end': 7}}
    reading = folder / 'reading-authority.sqlite'
    progress = revision(40, kind='progress', key=BOOK, mode='reflow_global', payload={'book_key': BOOK, 'location': location})
    local(reading, progress, expected=ARG)
    assert counts(reading) == (0, 0)
    receive(reading, progress)
    assert selected(reading, 'progress', BOOK)[1] == raw(progress) and counts(reading) == (1, 0)
    project(reading, progress, expected=ARG)
    record('progress_is_selected_revision_authority_without_product_table_or_sdk_projection')
    note_key = BOOK + ':' + 'b' * 32
    note = revision(41, kind='annotation', key=note_key, mode='reflow_global', payload={'book_key': BOOK, 'annotation_id': 'b' * 32, 'location': location, 'text': 'note'})
    receive(reading, note)
    assert selected(reading, 'annotation', note_key)[1] == raw(note)
    project(reading, note, expected=ARG)
    record('annotation_selected_payload_retains_explicit_location_without_cross_database_writes')
    organization = folder / 'organization.sqlite'
    missing_shelf = revision(50, kind='shelf', key='5' * 32, payload={'name': 'Missing', 'parent_id': '6' * 32, 'ordinal': 0})
    local(organization, missing_shelf, expected=UNSAFE)
    assert counts(organization) == (0, 0)
    receive(organization, missing_shelf);project(organization, missing_shelf, expected=UNSAFE)
    assert counts(organization) == (1, 0) and not sql(organization, 'SELECT * FROM reader_shelves')
    record('missing_active_shelf_parent_rolls_back_local_change_but_retains_remote_history_pending')
    shelves = []
    for n in range(8):
        shelf = revision(60 + n, kind='shelf', key='%032x' % (100 + n), payload={'name': 'Level ' + str(n), 'parent_id': shelves[-1]['entity_key'] if n else None, 'ordinal': n})
        local(organization, shelf);shelves.append(shelf)
    deep = revision(70, kind='shelf', key='%032x' % 108, payload={'name': 'Too deep', 'parent_id': shelves[-1]['entity_key'], 'ordinal': 8})
    before = counts(organization);local(organization, deep, expected=DATABASE)
    assert counts(organization) == before and len(sql(organization, 'SELECT * FROM reader_shelves')) == 8
    record('schema_eight_level_limit_rejects_metadata_history_and_outbox_together')
    cyclic = revision(71, kind='shelf', key=shelves[0]['entity_key'], parents=[shelves[0]['id']], payload={'name': 'Cycle', 'parent_id': shelves[1]['entity_key'], 'ordinal': 0})
    local(organization, cyclic, [shelves[0]['id']], expected=DATABASE)
    assert counts(organization) == before and sql(organization, 'SELECT parent_id FROM reader_shelves WHERE shelf_id=?', (shelves[0]['entity_key'],)) == [(None,)]
    record('cross_entity_shelf_cycle_cannot_bypass_the_existing_schema_trigger')
    local(organization, book, sort=normalized)
    series = revision(72, kind='series', key='7' * 32, payload={'name': 'Series'})
    org_tag = revision(73, kind='tag', key='8' * 32, payload={'name': 'Tag'})
    local(organization, series);local(organization, org_tag)
    members = []
    for n, group, collection_id in ((80, 'shelf', shelves[0]['entity_key']), (81, 'series', series['entity_key']), (82, 'tag', org_tag['entity_key'])):
        member = revision(n, kind='membership', key=group + ':' + collection_id + ':' + BOOK,
                          payload={'book_key': BOOK, 'collection_kind': group, 'collection_id': collection_id, 'ordinal': 3})
        local(organization, member);members.append(member)
    assert sql(organization, 'SELECT ordinal FROM reader_book_shelves') == [(3,)]
    assert sql(organization, 'SELECT ordinal FROM reader_book_series') == [(3,)]
    assert len(sql(organization, 'SELECT * FROM reader_book_tags')) == 1
    record('shelf_series_and_tag_memberships_project_into_existing_bounded_catalog_tables')
    moved = revision(83, kind='membership', key=members[0]['entity_key'], parents=[members[0]['id']], payload=dict(members[0]['payload'], ordinal=9))
    local(organization, moved, [members[0]['id']])
    assert sql(organization, 'SELECT ordinal FROM reader_book_shelves') == [(9,)]
    deleted_member = revision(84, kind='membership', key=moved['entity_key'], parents=[moved['id']], operation='delete')
    local(organization, deleted_member, [moved['id']])
    assert not sql(organization, 'SELECT * FROM reader_book_shelves')
    assert sql(organization, 'SELECT count(*) FROM reader_tombstones WHERE revision_id=?', (deleted_member['id'],)) == [(1,)]
    record('membership_update_and_delete_change_only_derived_join_and_retain_tombstone_history')
    deleted_tag = revision(85, kind='tag', key=org_tag['entity_key'], parents=[org_tag['id']], operation='delete')
    local(organization, deleted_tag, [org_tag['id']])
    assert len(sql(organization, 'SELECT * FROM reader_book_tags')) == 1
    member_after_delete = revision(86, kind='membership', key=members[2]['entity_key'], parents=[members[2]['id']], payload=members[2]['payload'])
    before = counts(organization);local(organization, member_after_delete, [members[2]['id']], expected=UNSAFE)
    assert counts(organization) == before
    record('entity_soft_delete_never_cascades_history_and_new_membership_requires_active_dependency')
    identity = folder / 'identity-mismatch.sqlite';invoke(identity, 'identity')
    sql(identity, "INSERT INTO reader_books(book_key,format,source_sha256,source_bytes,title,sort_title) VALUES(?,'txt',?,999,'legacy','legacy')", (BOOK, 'a' * 64))
    local(identity, book, sort=normalized, expected=FORMAT)
    assert counts(identity) == (0, 0) and sql(identity, 'SELECT source_bytes FROM reader_books') == [(999,)]
    record('existing_product_original_length_cannot_be_rewritten_by_revision_projection')
    race = folder / 'two-native-writers.sqlite';local(race, tag)
    left = revision(90, parents=[tag['id']], payload={'name': 'Left'})
    right = revision(91, parents=[tag['id']], payload={'name': 'Right'})
    processes = [subprocess.Popen([str(consumer), 'project-local', str(race), str(wire(v)), tag['id'], '-'], stdout=subprocess.PIPE, stderr=subprocess.PIPE) for v in (left, right)]
    outcomes = []
    for process in processes:
        stdout, stderr = process.communicate(timeout=30)
        assert process.returncode == 0, stderr
        outcomes.append(json.loads(stdout))
    assert sorted(v['status'] for v in outcomes) == [OK, UNSAFE] and counts(race) == (2, 2)
    winner = next(v['id'] for v in outcomes if v['status'] == OK)
    assert selected(race)[0]['id'] == winner
    record('two_native_processes_cannot_both_commit_against_the_same_expected_head')

    def crash(name, action):
        database = folder / (name + '.sqlite');invoke(database, 'identity')
        if action == 'crash-project-before-metadata':
            sql(database, 'CREATE TRIGGER pause_projection BEFORE INSERT ON reader_tags BEGIN SELECT reader_test_pause();END')
        value = revision(100 if action == 'crash-project-before-metadata' else 101)
        marker = folder / (name + '.ready')
        with (folder / (name + '.log')).open('wb') as log:
            process = subprocess.Popen([str(consumer), action, str(database), str(wire(value)), '-', '-', str(marker)], stdout=log, stderr=subprocess.STDOUT)
            try:
                deadline = time.monotonic() + 40
                while not marker.exists():
                    assert process.poll() is None and time.monotonic() < deadline, 'Projection crash boundary was not reached'
                    time.sleep(.05)
                process.kill();process.wait(timeout=20)
                assert process.returncode != 0
            finally:
                if process.poll() is None:
                    process.kill();process.wait(timeout=20)
        if action == 'crash-project-before-metadata':
            sql(database, 'DROP TRIGGER pause_projection')
            assert counts(database) == (0, 0) and not sql(database, 'SELECT * FROM reader_tags')
            local(database, value)
        assert counts(database) == (1, 1) and sql(database, 'SELECT name FROM reader_tags') == [('书架',)]
        assert selected(database)[1] == raw(value)
        result = local(database, value)
        assert result['created'] == result['applied'] == 0 and counts(database) == (1, 1)
    crash('killed-before-metadata', 'crash-project-before-metadata')
    record('real_kill_after_history_outbox_before_metadata_recovers_all_three_or_none')
    crash('killed-after-atomic-commit', 'crash-project-after-commit')
    record('real_kill_after_commit_retains_exact_metadata_history_outbox_without_duplicate_projection')
    sdk = folder / 'sdk-identity.sqlite'
    sql(sdk, 'PRAGMA application_id=1163416131');sql(sdk, 'PRAGMA user_version=7')
    before_bytes = sdk.read_bytes()
    local(sdk, tag, expected=DATABASE)
    assert sdk.read_bytes() == before_bytes
    record('sdk_database_identity_is_rejected_without_modification')
    assert len(checks) == 31, len(checks)
    report = {'accepted': True, 'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
              'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'platform': sys.platform, 'count': len(checks), 'checks': checks,
              'metadata_history_outbox_same_product_transaction': True, 'wire_rewritten': False,
              'sdk_database_writes': False, 'active_reading_navigation': False, 'complete_product': False}
    (folder / 'result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'accepted': True, 'checks': len(checks), 'source_sha': os.environ['GITHUB_SHA']}))


if __name__ == '__main__':
    main()
