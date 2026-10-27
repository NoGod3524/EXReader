# SPDX-License-Identifier: MIT
"""Cloud-only installed-native revision/outbox, process and protocol acceptance."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import time
import uuid

OK, ARG, MEMORY, DATABASE, FORMAT, LIMIT, HASH, COLLISION, MISSING, CYCLE, UNSAFE, OWNER, NOT_FOUND = range(13)
TAG = '00000000000000000000000000000001'
BOOK = 'epub:' + 'a' * 64


def encoded(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf-8')


def revision(number, parents=(), key=TAG, kind='tag', operation='put', payload=None, mode='none', clock=None):
    value = {'version': 1, 'id': '%032x' % number, 'entity_kind': kind, 'entity_key': key,
             'operation': operation, 'location_kind': mode, 'parents': ['%032x' % p for p in parents],
             'payload': None if operation == 'delete' else (payload if payload is not None else {'name': '旅行'})}
    if clock is not None:
        value['display_time'] = clock
    return value


def sqlite_provider(mapping, build_log):
    if os.name == 'nt':
        providers = [line.strip() for line in mapping.splitlines() if re.search(r'^\s*[0-9a-fA-F]+:[0-9a-fA-F]+\s+sqlite3_open_v2\s+', line)]
        assert len(providers) == 1 and re.search(r'\breader_catalog_sqlite:sqlite3\.c\.obj\s*$', providers[0]), providers
    elif sys.platform == 'darwin':
        objects = dict(re.findall(r'^\[\s*(\d+)\]\s+(.+)$', mapping, re.M))
        definitions = re.findall(r'^0x[0-9a-fA-F]+\s+0x[0-9a-fA-F]+\s+\[\s*(\d+)\]\s+_sqlite3_open_v2\s*$', mapping, re.M)
        assert len(definitions) == 1, definitions
        providers = [objects.get(definitions[0], '')]
        assert re.search(r'libreader_catalog_sqlite\.a(?:\[\d+\])?\(sqlite3\.c\.o\)$', providers[0]), providers
    else:
        providers = re.findall(r'(\S+\.a\([^)]+\)): definition of sqlite3_open_v2\b', build_log)
        assert len(providers) == 1 and providers[0].endswith('libreader_catalog_sqlite.a(sqlite3.c.o)'), providers
    assert 'exr_vendor_exr_sqlite' not in mapping
    return providers


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--consumer', type=Path, required=True)
    parser.add_argument('--c-consumer', type=Path, required=True)
    parser.add_argument('--product-prefix', type=Path, required=True)
    parser.add_argument('--revision-prefix', type=Path, required=True)
    parser.add_argument('--build-log', type=Path, required=True)
    parser.add_argument('--link-map', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'Cloud execution only'
    folder = args.output.resolve()
    folder.mkdir(parents=True)
    consumer = args.consumer.resolve()
    checks, processes = [], []
    source_sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    assert source_sha == os.environ['GITHUB_SHA']

    def record(name, details=None):
        assert name not in {row['id'] for row in checks}
        checks.append({'id': name, 'pass': True, 'details': details or {}})

    def invoke(action, database, *parameters, expected=OK):
        result = subprocess.run([str(consumer), action, str(database), *map(str, parameters)],
                                capture_output=True, encoding='utf-8', errors='strict', timeout=180)
        assert result.returncode == 0, (action, result.returncode, result.stderr)
        value = json.loads(result.stdout)
        assert value['status'] == expected, (action, expected, value)
        processes.append({'pid_identity': len(processes) + 1, 'action': action, 'exit_code': result.returncode,
                          'status': value['status'], 'created': value['created']})
        return value

    def wire(name, value):
        path = folder / (name + '.json')
        path.write_bytes(value if isinstance(value, bytes) else encoded(value))
        return path

    def put(database, path, remote=False, expected=OK, digest=None):
        if remote:
            return invoke('receive', database, path, digest or hashlib.sha256(path.read_bytes()).hexdigest(), expected=expected)
        return invoke('local', database, path, expected=expected)

    def heads(database, key=TAG, kind='tag'):
        return invoke('heads', database, kind, key)

    def counts(database):
        # Fixture inspection only. JSON is validated by the installed native
        # product provider in the consumer, never by this runner Python SQLite.
        with sqlite3.connect(database) as db:
            return tuple(db.execute('SELECT (SELECT count(*) FROM reader_revisions),(SELECT count(*) FROM reader_outbox)').fetchone())

    a, b = folder / '设备A.sqlite', folder / '设备B.sqlite'
    identity = invoke('identity', a)
    header = (args.product_prefix / 'include/exreader-product/sqlite3.h').read_text(encoding='utf-8')
    expected_source = re.search(r'#define SQLITE_SOURCE_ID\s+"([^"]+)"', header)[1]
    assert identity['sqlite_version'] == '3.54.0'
    assert identity['sqlite_source_id'] == identity['header_source_id'] == expected_source
    assert identity['json_smoke'] == 1
    options = set(identity['compile_options'])
    assert {'THREADSAFE=1', 'DQS=0', 'OMIT_LOAD_EXTENSION', 'MAX_LENGTH=2147483647'} <= options
    assert 'OMIT_JSON' not in options
    record('installed_product_sqlite_identity_compile_options_and_actual_json_smoke', identity)
    subprocess.run([str(args.c_consumer.resolve())], check=True, timeout=30)
    record('installed_public_c_header_and_c_consumer')
    mapping = args.link_map.read_text(errors='replace')
    providers = sqlite_provider(mapping, args.build_log.read_text())
    record('single_installed_product_sqlite_provider_no_sdk_vendor_or_system_fallback', {'provider': providers})

    first = wire('first', revision(101))
    result = put(a, first)
    assert result['created'] == 1 and result['sha256'] == hashlib.sha256(first.read_bytes()).hexdigest() and counts(a) == (1, 1)
    record('local_revision_and_outbox_committed_together')
    assert put(a, first)['created'] == 0 and counts(a) == (1, 1)
    record('same_id_exact_bytes_is_idempotent')
    # Upgrade a real v1 catalog containing committed revision/outbox rows, then
    # exercise the installed adapter against it for the rest of this suite.
    with sqlite3.connect(a) as db:
        assert db.execute('PRAGMA user_version').fetchone()[0] == 1
        db.executescript(Path('apps/reader/store/002_originals.sql').read_text(encoding='utf-8'))
        assert db.execute('PRAGMA user_version').fetchone()[0] == 2
    assert counts(a) == (1, 1)
    assert put(a, first)['created'] == 0
    record('migrated_v2_catalog_preserves_revision_and_outbox')
    queue = invoke('outbox', a)['outbox']
    assert len(queue) == 1 and queue[0]['wire'].encode() == first.read_bytes() and queue[0]['attempts'] == 0
    transport = wire('transport-a-to-b', queue[0]['wire'].encode())
    assert put(b, transport, remote=True)['created'] == 1 and counts(b) == (1, 0)
    exported = folder / 'exported-b.json'
    invoke('get', b, revision(101)['id'], exported)
    assert exported.read_bytes() == first.read_bytes()
    record('two_independent_process_databases_transfer_exact_original_bytes_without_remote_outbox')
    invoke('ack', a, revision(101)['id'], '0' * 64, expected=HASH)
    assert counts(a) == (1, 1)
    record('ack_wrong_hash_keeps_queue_and_history')
    invoke('ack', a, revision(101)['id'], result['sha256'])
    invoke('ack', a, revision(101)['id'], result['sha256'])
    assert counts(a) == (1, 0)
    assert put(a, first)['created'] == 0 and put(a, first, remote=True)['created'] == 0 and counts(a) == (1, 0)
    record('ack_retains_history_and_acknowledged_replays_never_requeue')
    changed = wire('same-id-changed', revision(101, payload={'name': 'changed'}))
    put(a, changed, expected=COLLISION)
    whitespace = wire('same-id-whitespace', first.read_bytes() + b' ')
    put(a, whitespace, remote=True, expected=COLLISION)
    invoke('get', a, revision(101)['id'], exported)
    assert exported.read_bytes() == first.read_bytes() and counts(a) == (1, 0)
    record('same_id_different_content_or_whitespace_is_refused_without_replacement')
    put(a, wire('bad-transport-hash', revision(1000)), remote=True, digest='0' * 64, expected=HASH)
    assert counts(a) == (1, 0)
    record('transport_hash_corruption_is_refused_before_storage')

    revisions = {101: first}
    revisions[102] = wire('b-concurrent', revision(102, [101], payload={'name': 'B'}, clock='1900-01-01'))
    revisions[103] = wire('a-concurrent', revision(103, [101], payload={'name': 'A'}, clock='2999-01-01'))
    put(b, revisions[102]);put(a, revisions[103]);put(a, revisions[102], remote=True);put(b, revisions[103], remote=True)
    for database in (a, b):
        state = heads(database)
        assert {h['id'] for h in state['heads']} == {revision(102)['id'], revision(103)['id']} and not state['state']['projection_safe']
    record('concurrent_heads_survive_both_transfer_directions_and_clock_extremes')
    steps = [(104, [102], 'delete'), (105, [104], 'put'), (106, [105], 'restore'), (107, [104], 'restore'),
             (108, [106, 103, 107, 104], 'restore'), (109, [108], 'put')]
    for number, parents, operation in steps:
        revisions[number] = wire('causal-' + str(number), revision(number, parents, operation=operation))
        for database in (a, b):
            put(database, revisions[number], remote=True)
        state = heads(a)['state']
        if number == 104:
            assert state['heads'] == 2 and not state['projection_safe']
            record('concurrent_tombstone_and_live_edit_are_both_retained')
        elif number == 105:
            assert state['heads'] == 2 and state['requires_restore'] and not state['projection_safe']
            record('ordinary_put_after_delete_cannot_implicitly_restore')
        elif number == 106:
            assert state['requires_restore'] and not state['projection_safe']
            record('restore_without_direct_tombstone_parent_remains_blocked')
        elif number == 107:
            assert state['heads'] == 3 and not state['projection_safe']
            record('restore_that_misses_concurrent_heads_does_not_resolve_them')
        elif number == 108:
            assert state['heads'] == 1 and state['projection_safe'] and not state['deleted']
            record('explicit_restore_covering_tombstone_and_all_competing_heads_is_safe')
        elif number == 109:
            assert state['projection_safe'] and not state['requires_restore']
            record('normal_edits_can_follow_a_valid_restore')
    for number, parents, operation in ((110, [109], 'delete'), (111, [101], 'put'), (112, [110, 111], 'restore')):
        revisions[number] = wire('late-' + str(number), revision(number, parents, operation=operation))
        for database in (a, b):
            put(database, revisions[number], remote=True)
        state = heads(a)['state']
        if number == 110:
            assert state['projection_safe'] and state['deleted']
        elif number == 111:
            assert state['heads'] == 2 and not state['projection_safe']
        else:
            assert state['heads'] == 1 and state['projection_safe'] and not state['deleted']
    record('late_old_branch_after_restore_reopens_conflict_until_explicit_new_restore')
    assert counts(a)[0] == 12 and counts(b)[0] == 12
    with sqlite3.connect(a) as db:
        assert db.execute('SELECT count(*) FROM reader_tombstones').fetchone()[0] == 2
    record('all_old_branches_and_tombstones_remain_in_history')

    reverse = folder / 'reverse.sqlite'
    for number in reversed(range(101, 110)):
        put(reverse, revisions[number], remote=True)
        if number == 109:
            state = heads(reverse)['state']
            assert state['missing_parents'] == 1 and not state['projection_safe']
    assert heads(reverse)['state']['projection_safe'] and heads(reverse)['state']['heads'] == 1 and counts(reverse) == (9, 0)
    record('parents_arriving_in_reverse_order_recompute_full_ancestry_without_remote_queue')
    missing = wire('missing-local', revision(400, [999]))
    before = counts(a)
    put(a, missing, expected=MISSING)
    assert counts(a) == before
    record('unknown_local_parent_rolls_back_revision_and_outbox')
    other = wire('other-entity', revision(201, key='%032x' % 2))
    put(a, other, remote=True)
    put(a, wire('known-cross-entity', revision(202, [201])), remote=True, expected=FORMAT)
    record('known_cross_entity_parent_is_refused')
    foreign = folder / 'foreign.sqlite'
    put(foreign, wire('foreign-child', revision(501, [502])), remote=True)
    assert heads(foreign)['state']['missing_parents'] == 1
    put(foreign, wire('foreign-parent', revision(502, key='%032x' % 2)), remote=True)
    state = heads(foreign)['state']
    assert state['foreign_parents'] == 1 and state['missing_parents'] == 0 and not state['projection_safe']
    record('later_foreign_parent_does_not_rewrite_or_authorize_earlier_child')
    cycle = folder / 'cycle.sqlite'
    put(cycle, wire('cycle-one', revision(301, [302])), remote=True)
    put(cycle, wire('cycle-two', revision(302, [301])), remote=True, expected=CYCLE)
    assert counts(cycle) == (1, 0) and heads(cycle)['state']['missing_parents'] == 1
    record('out_of_order_cycle_closure_is_rejected_atomically')

    retry = invoke('outbox', a)['outbox'][0]
    invoke('retry', a, retry['id'], DATABASE)
    queued = invoke('outbox', a)['outbox'][0]
    assert queued['attempts'] == 1 and queued['last_error'] == 'revision_error_3' and queued['wire'] == retry['wire']
    invoke('retry', a, retry['id'], 999, expected=ARG)
    record('retry_preserves_original_and_records_only_a_fixed_redacted_status_token')
    invoke('outbox', a, 0, expected=ARG);invoke('outbox', a, 101, expected=ARG)
    record('outbox_pages_are_explicitly_bounded')
    for row in invoke('outbox', a)['outbox']:
        invoke('ack', a, row['id'], row['sha256'])
    assert not invoke('outbox', a)['outbox']
    put(a, wire('new-queue-after-empty', revision(1200)))
    assert len(invoke('outbox', a)['outbox']) == 1
    record('new_outbox_work_is_found_after_queue_id_reuse')
    assert invoke('reentry', a, 'tag', TAG)['nested_status'] == OWNER
    invoke('wrong-thread', a, expected=OWNER)
    record('callback_reentry_and_wrong_owner_thread_are_refused')
    ids = [invoke('newid', a)['new_id'] for _ in range(2)]
    assert ids[0] != ids[1] and all(uuid.UUID(hex=value).version == 4 for value in ids)
    record('system_random_global_revision_ids_are_uuid4')

    valid_payloads = [
        revision(2001, key=BOOK, kind='book', payload={'format': 'epub', 'source_sha256': 'a' * 64, 'source_bytes': 17, 'title': '书', 'author': '作者', 'favorite': False}),
        revision(2002, kind='shelf', payload={'name': 'Shelf', 'parent_id': None, 'ordinal': 0}),
        revision(2003, kind='series', payload={'name': 'Series'}),
        revision(2004, kind='membership', key='shelf:' + TAG + ':' + BOOK, payload={'book_key': BOOK, 'collection_kind': 'shelf', 'collection_id': TAG, 'ordinal': 1})]
    selector = {'exact': 'Reading', 'prefix': '', 'suffix': ' text', 'start': 0, 'end': 7}
    for index, mode in enumerate(('epub_chapter', 'reflow_global', 'fixed_page')):
        key = ('pdf:' + 'b' * 64) if mode == 'fixed_page' else BOOK
        location = {'mode': mode, 'parser_version': '3.40.0', 'anchor_version': 1, 'selector': selector}
        if mode == 'epub_chapter':
            location['part_path'] = 'OPS/chapter.xhtml'
        if mode == 'fixed_page':
            location.update(page_id='page-1', page=0)
        valid_payloads.append(revision(2010 + index, kind='progress', key=key, mode=mode, payload={'book_key': key, 'location': location}))
        valid_payloads.append(revision(2020 + index, kind='annotation', key=key + ':' + TAG, mode=mode,
                                       payload={'book_key': key, 'annotation_id': TAG, 'location': location, 'text': '备注\n第二行'}))
    for index, value in enumerate(valid_payloads):
        invoke('validate', a, wire('valid-entity-' + str(index), value))
    record('all_entity_payloads_and_three_explicit_location_modes_validate')
    invalid = []
    def bad(name, update, status=FORMAT):
        value = revision(3000)
        update(value)
        invalid.append((name, encoded(value), status))
    bad('unsupported_version', lambda v: v.update(version=2))
    bad('noninteger_version', lambda v: v.update(version=1.0))
    bad('sdk_local_id_field', lambda v: v.update(sdk_book_id=1))
    bad('unknown_payload_field', lambda v: v['payload'].update(extra='x'))
    bad('wrong_global_id', lambda v: v.update(id='ABC'))
    bad('parent_duplicates', lambda v: v.update(parents=['%032x' % 1] * 2))
    bad('self_parent', lambda v: v.update(parents=[v['id']]), CYCLE)
    bad('too_many_parents', lambda v: v.update(parents=['%032x' % n for n in range(33)]), LIMIT)
    bad('delete_with_payload', lambda v: v.update(operation='delete'))
    bad('nonreading_mode', lambda v: v.update(location_kind='epub_chapter'))
    bad('escaped_nul', lambda v: v['payload'].update(name='bad\0name'))
    # Build the surrogate specimen as ASCII escapes, not an invalid Python UTF-8 encode.
    invalid.append(('unpaired_unicode_surrogate', encoded(revision(3000)).replace('旅行'.encode(), b'\\ud800'), FORMAT))
    base = encoded(revision(3000))
    invalid += [('duplicate_root_key', base.replace(b'"version":1', b'"version":1,"version":1'), FORMAT),
                ('duplicate_nested_key', base.replace(b'"name":', b'"name":"first","name":'), FORMAT),
                ('trailing_json', base + b'{}', FORMAT), ('invalid_utf8', base.replace('旅行'.encode(), b'\xff'), FORMAT),
                ('over_wire_byte_limit', base + b' ' * (1048577 - len(base)), LIMIT),
                ('deep_json', base.replace(b'"payload":', b'"payload":' + b'[' * 33).replace(b'"name":"' + '旅行'.encode() + b'"}', b'"name":"' + '旅行'.encode() + b'"}' + b']' * 33), LIMIT)]
    for name, raw, expected in invalid:
        invoke('validate', a, wire('reject-' + name, raw), expected=expected)
        record('reject_' + name)
    exact = wire('exact_wire_limit', base + b' ' * (1048576 - len(base)))
    invoke('validate', a, exact)
    record('exact_wire_byte_ceiling_is_accepted_without_reencoding')
    wrong_mode = revision(3100, kind='progress', key='txt:' + 'c' * 64, operation='delete', mode='fixed_page')
    invoke('validate', a, wire('wrong-delete-mode', wrong_mode), expected=FORMAT)
    record('deleted_reading_entity_retains_format_correct_explicit_mode')
    changed_bytes = folder / 'original-size.sqlite'
    original = valid_payloads[0]
    put(changed_bytes, wire('original-size-first', original), remote=True)
    revised = json.loads(encoded(original))
    revised.update(id='%032x' % 3500, parents=[original['id']])
    revised['payload']['source_bytes'] = 18
    put(changed_bytes, wire('original-size-conflict', revised), remote=True, expected=FORMAT)
    assert counts(changed_bytes) == (1, 0)
    record('book_original_byte_length_cannot_change_across_revisions')

    fault = folder / 'fault.sqlite'
    invoke('identity', fault)
    with sqlite3.connect(fault) as db:
        db.execute("CREATE TRIGGER fail_queue BEFORE INSERT ON reader_outbox BEGIN SELECT RAISE(ABORT,'fixture failure');END")
    atomic = wire('atomic-local', revision(6001))
    put(fault, atomic, expected=DATABASE)
    assert counts(fault) == (0, 0)
    record('outbox_insert_failure_rolls_back_preceding_revision_insert')
    put(fault, atomic, remote=True)
    assert counts(fault) == (1, 0)
    record('remote_receive_does_not_touch_even_a_refusing_outbox')
    with sqlite3.connect(fault) as db:
        db.execute('DROP TRIGGER fail_queue')
    put(fault, wire('atomic-retry', revision(6002, [6001])))
    assert counts(fault) == (2, 1)
    record('fresh_process_can_retry_after_failed_local_transaction')

    def kill_at(name, action):
        database = folder / (name + '.sqlite')
        invoke('identity', database)
        if action == 'crash-before-outbox':
            with sqlite3.connect(database) as db:
                db.execute('CREATE TRIGGER pause_queue BEFORE INSERT ON reader_outbox BEGIN SELECT reader_test_pause();END')
        path = wire(name + '-wire', revision(7001 if action == 'crash-before-outbox' else 7002))
        marker = folder / (name + '.ready')
        with (folder / (name + '.log')).open('wb') as log:
            process = subprocess.Popen([str(consumer), action, str(database), str(path), str(marker)], stdout=log, stderr=subprocess.STDOUT)
            try:
                end = time.monotonic() + 40
                while not marker.exists():
                    assert process.poll() is None and time.monotonic() < end, 'Crash boundary not reached'
                    time.sleep(.05)
                process.kill()
                process.wait(timeout=20)
                assert process.returncode != 0
                processes.append({'action': action, 'pid': process.pid, 'exit_code': process.returncode, 'ready_marker': marker.name})
            finally:
                if process.poll() is None:
                    process.kill();process.wait(timeout=20)
        if action == 'crash-before-outbox':
            with sqlite3.connect(database) as db:
                db.execute('DROP TRIGGER pause_queue')
            assert counts(database) == (0, 0)
            put(database, path)
            assert counts(database) == (1, 1)
        else:
            assert counts(database) == (1, 1)
            output = folder / (name + '-retained.json')
            invoke('get', database, revision(7002)['id'], output)
            assert output.read_bytes() == path.read_bytes()
            assert put(database, path)['created'] == 0 and counts(database) == (1, 1)
        invoke('identity', database)
    kill_at('killed-between-revision-and-outbox', 'crash-before-outbox')
    record('actual_process_kill_between_revision_and_outbox_recovers_both_or_neither')
    kill_at('killed-after-commit', 'crash-after-commit')
    record('actual_process_kill_after_commit_retains_exact_history_and_retry_queue')
    with sqlite3.connect(a) as db:
        for sql in ('DELETE FROM reader_revisions', "UPDATE reader_revisions SET operation='delete'", 'INSERT OR REPLACE INTO reader_revisions SELECT * FROM reader_revisions LIMIT 1'):
            try:
                db.execute(sql)
            except sqlite3.IntegrityError:
                db.rollback()
            else:
                raise AssertionError('Immutable history operation unexpectedly succeeded')
    record('schema1_history_update_delete_and_replace_guards_remain_active')
    bound = folder / 'bounded-history.sqlite'
    invoke('identity', bound)
    with sqlite3.connect(bound) as db:
        for n in range(4096):
            value = revision(100000 + n, [100000 + n - 1] if n else [])
            raw = encoded(value)
            db.execute('INSERT INTO reader_revisions VALUES(?,?,?,?,?,?)',
                       (value['id'], 'tag', TAG, 'put', raw.decode(), hashlib.sha256(raw).hexdigest()))
    assert heads(bound)['state']['projection_safe'] and heads(bound)['state']['revisions'] == 4096
    put(bound, wire('history-overflow', revision(104096, [104095])), expected=LIMIT)
    assert counts(bound) == (4096, 0)
    record('4096_revision_chain_uses_iterative_graph_and_refuses_history_overflow_atomically')
    foreign_db = folder / 'foreign-identity.sqlite'
    with sqlite3.connect(foreign_db) as db:
        db.execute('PRAGMA application_id=1163416131')
    invoke('identity', foreign_db, expected=DATABASE)
    record('sdk_or_foreign_database_identity_is_refused')
    assert len(checks) == 59

    report = {'accepted': True, 'source_sha': source_sha, 'run_id': os.environ['GITHUB_RUN_ID'],
              'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'platform': sys.platform, 'checks': checks,
              'count': len(checks), 'processes': processes, 'sqlite_identity': identity,
              'sqlite_provider': providers, 'consumer_sha256': hashlib.sha256(consumer.read_bytes()).hexdigest(),
              'product_files': {str(p.relative_to(args.product_prefix)): hashlib.sha256(p.read_bytes()).hexdigest()
                                for p in sorted(args.product_prefix.rglob('*')) if p.is_file()},
              'revision_files': {str(p.relative_to(args.revision_prefix)): hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in sorted(args.revision_prefix.rglob('*')) if p.is_file()},
              'complete_product': False, 'network_sync_implemented': False,
              'entity_projection_or_sdk_writes_implemented': False}
    (folder / 'result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'accepted': True, 'checks': len(checks), 'source_sha': source_sha}))


if __name__ == '__main__':
    main()
