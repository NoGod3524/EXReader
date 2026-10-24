# SPDX-License-Identifier: MIT
"""Actions-only installed typed producers; inspect actual native transaction effects."""
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

OK, ARG, BOOTSTRAP, REVISION = range(4)
REV_DATABASE, REV_FORMAT, REV_LIMIT, REV_COLLISION, REV_UNSAFE, REV_OWNER = 3, 4, 5, 7, 10, 11
BOOK = 'txt:' + 'a' * 64
TAG = '1' * 32


def main():
    p = argparse.ArgumentParser()
    for name in ('consumer', 'c-consumer', 'revision-consumer', 'product-prefix', 'link-map', 'build-log', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    a = p.parse_args()
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip() == os.environ['GITHUB_SHA']
    folder = a.output.resolve();folder.mkdir(parents=True)
    consumer, revision_consumer = a.consumer.resolve(), a.revision_consumer.resolve()
    checks = []

    def record(name):
        assert name not in checks
        checks.append(name)
        print(json.dumps({'check': name, 'pass': True}), flush=True)

    def invoke(db, action, *args, expected=OK, rev=None):
        result = subprocess.run([str(consumer), action, str(db), *map(str, args)], capture_output=True, encoding='utf-8', errors='strict', timeout=60)
        assert result.returncode == 0, (action, result.stderr)
        value = json.loads(result.stdout)
        assert value['status'] == expected, (expected, value)
        if rev is not None:
            assert value['revision_status'] == rev, value
        if expected != OK and 'created' in value:
            assert value['created'] == value['applied'] == 0
        return value

    def rid(number):
        return '%032x' % number

    def text(value):
        raw = value if isinstance(value, bytes) else value.encode('utf-8')
        path = folder / (hashlib.sha256(raw).hexdigest() + '.txt')
        path.write_bytes(raw)
        return path

    def group_args(number, heads=(), kind=1, op=0, key=TAG, name='书架😀', parent='-', ordinal=0):
        return (rid(number) if number is not None else '-', ','.join(heads) or '-', kind, op, key, text(name), parent, ordinal)

    def group(db, number, heads=(), *, expected=OK, rev=None, **kwargs):
        return invoke(db, 'group', *group_args(number, heads, **kwargs), expected=expected, rev=rev)

    def book(db, number, heads=(), *, title='用户标题😀', author='作者', sort='用户标题😀', length=123, op=0, key=BOOK, format='txt', sha='a' * 64, favorite=0, expected=OK, rev=None):
        return invoke(db, 'book', rid(number), ','.join(heads) or '-', op, key, format, sha, length, favorite,
                      text(title), text(author), text(sort), expected=expected, rev=rev)

    def member(db, number, heads=(), *, kind=1, op=0, key=TAG, ordinal=0, expected=OK, rev=None):
        return invoke(db, 'member', rid(number), ','.join(heads) or '-', kind, op, key, BOOK, ordinal, expected=expected, rev=rev)

    def sql(db, query, args=()):
        with sqlite3.connect(db) as connection:
            return connection.execute(query, args).fetchall()

    def counts(db):
        return sql(db, 'SELECT (SELECT count(*) FROM reader_revisions),(SELECT count(*) FROM reader_outbox)')[0]

    def retained(db, number):
        raw = sql(db, 'SELECT body_json FROM reader_revisions WHERE revision_id=?', (rid(number),))[0][0].encode('utf-8')
        value = json.loads(raw)
        assert value['id'] == rid(number) and value['version'] == 1
        assert 'sdk_book_id' not in value
        if isinstance(value['payload'], dict):
            assert 'sdk_book_id' not in value['payload']
        return value, raw

    def remote(db, value):
        raw = json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        result = subprocess.run([str(revision_consumer), 'receive', str(db), str(text(raw)), hashlib.sha256(raw).hexdigest()], capture_output=True, encoding='utf-8', timeout=60)
        assert result.returncode == 0 and json.loads(result.stdout)['status'] == 0, result.stdout

    db = folder / '产品.sqlite'
    identity = invoke(db, 'identity')
    header = (a.product_prefix / 'include/exreader-product/sqlite3.h').read_text(encoding='utf-8')
    source = re.search(r'#define SQLITE_SOURCE_ID\s+"([^"]+)"', header)[1]
    assert identity['sqlite_version'] == '3.54.0' and identity['sqlite_source_id'] == identity['header_source_id'] == source
    mapping = a.link_map.read_text(errors='replace')
    if os.name == 'nt':
        providers = [line.strip() for line in mapping.splitlines() if re.search(r'^\s*[0-9a-fA-F]+:[0-9a-fA-F]+\s+sqlite3_open_v2\s+', line)]
        assert len(providers) == 1 and re.search(r'\breader_catalog_sqlite:sqlite3\.c\.obj\s*$', providers[0]), providers
    else:
        providers = re.findall(r'(\S+\.a\([^)]+\)): definition of sqlite3_open_v2\b', a.build_log.read_text())
        assert len(providers) == 1 and providers[0].endswith('libreader_catalog_sqlite.a(sqlite3.c.o)'), providers
    assert 'exr_vendor_exr_sqlite' not in mapping
    record('installed_cpp_uses_one_verified_product_sqlite_provider')
    cdb = folder / 'c-api.sqlite'
    subprocess.run([str(a.c_consumer.resolve()), str(cdb)], check=True, timeout=30)
    assert counts(cdb) == (3, 3) and len(sql(cdb, 'SELECT * FROM reader_book_tags')) == 1
    record('installed_c_header_calls_all_three_typed_producers_and_utf16')

    generated = group(db, None, key='-')
    assert re.fullmatch('[0-9a-f]{32}', generated['id']) and re.fullmatch('[0-9a-f]{32}', generated['key'])
    assert generated['created'] == generated['applied'] == 1
    record('native_os_random_revision_and_group_ids_are_returned_after_create')
    group(db, 1)
    value, raw = retained(db, 1)
    assert value == {'version': 1, 'id': rid(1), 'entity_kind': 'tag', 'entity_key': TAG, 'operation': 'put', 'location_kind': 'none', 'parents': [], 'payload': {'name': '书架😀'}}
    assert '😀'.encode() in raw
    record('native_only_wire_producer_preserves_chinese_and_standard_utf8_emoji')
    group(db, 2, [rid(1)], name='Renamed')
    before = counts(db)
    result = group(db, 1)
    assert result['created'] == result['applied'] == 0 and counts(db) == before
    assert sql(db, 'SELECT name FROM reader_tags WHERE tag_id=?', (TAG,)) == [('Renamed',)]
    record('stable_old_command_retry_never_reapplies_metadata')
    group(db, 1, name='Collision', expected=REVISION, rev=REV_COLLISION)
    assert counts(db) == before
    record('same_stable_revision_id_different_typed_payload_is_collision')
    group(db, 3, [rid(1)], expected=REVISION, rev=REV_UNSAFE)
    assert counts(db) == before
    record('stale_ui_expected_heads_cannot_commit_any_part')
    group(db, 3, [rid(2), rid(2)], expected=ARG)
    group(db, 3, [rid(2)] * 33, expected=ARG)
    group(db, 3, ['z' * 32], expected=ARG)
    assert counts(db) == before
    record('duplicate_invalid_and_over_budget_expected_head_sets_are_refused')
    group(db, 3, op=1, expected=ARG)
    group(db, 3, op=2, expected=ARG)
    assert counts(db) == before
    record('delete_and_restore_need_explicit_observed_history')
    group(db, 3, [rid(2)], op=1)
    assert sql(db, 'SELECT deleted FROM reader_tags WHERE tag_id=?', (TAG,)) == [(1,)]
    group(db, 4, [rid(3)], expected=REVISION, rev=REV_UNSAFE)
    group(db, 4, [rid(3)], op=2, name='Restored')
    assert sql(db, 'SELECT name,deleted FROM reader_tags WHERE tag_id=?', (TAG,)) == [('Restored', 0)]
    record('typed_tombstone_and_explicit_restore_preserve_graph_rules')
    for kwargs in ({'kind': 9}, {'op': 9}, {'key': 'sdk:123'}, {'parent': '2' * 32}, {'ordinal': 1}, {'name': ''}):
        group(db, 5, [rid(4)], expected=ARG, **kwargs)
    assert counts(db) == (5, 5)
    record('typed_enums_ids_empty_names_and_non_shelf_parent_order_are_checked')
    for bad in (b'\xc0\x80', b'\xed\xa0\x80', b'\xf4\x90\x80\x80', b'\xf0\x9f'):
        group(db, 5, [rid(4)], name=bad, expected=REVISION, rev=REV_FORMAT)
    group(db, 5, [rid(4)], name='😀' * 257, expected=ARG)
    group(db, 5, [rid(4)], name='a' * 257, expected=REVISION, rev=REV_LIMIT)
    assert counts(db) == (5, 5)
    record('strict_utf8_and_existing_256_scalar_1024_byte_group_bounds_remain_enforced')

    missing = folder / 'needs-bootstrap.sqlite';invoke(missing, 'identity')
    group(missing, 10)
    before = counts(missing)
    member(missing, 11, expected=BOOTSTRAP)
    assert counts(missing) == before and not sql(missing, 'SELECT * FROM reader_book_tags')
    sql(missing, "INSERT INTO reader_books(book_key,format,source_sha256,source_bytes,title,author,sort_title,favorite) VALUES(?,'txt',?,123,'Edited by user','User author','Edited by user',1)", (BOOK, 'a' * 64))
    sql(missing, "INSERT INTO reader_local_books VALUES(?,777,'reflow_global')", (BOOK,))
    member(missing, 11, expected=BOOTSTRAP)
    assert counts(missing) == before and not sql(missing, 'SELECT * FROM reader_book_tags')
    record('catalog_only_or_absent_book_returns_needs_bootstrap_with_zero_writes')
    book(missing, 12, title='Edited by user', author='User author', sort='Edited by user', favorite=1)
    assert sql(missing, 'SELECT title,author,favorite FROM reader_books') == [('Edited by user', 'User author', 1)]
    assert sql(missing, 'SELECT sdk_book_id FROM reader_local_books') == [(777,)]
    assert retained(missing, 12)[0]['payload'] == {'format': 'txt', 'source_sha256': 'a' * 64, 'source_bytes': 123, 'title': 'Edited by user', 'author': 'User author', 'favorite': True}
    member(missing, 11)
    assert len(sql(missing, 'SELECT * FROM reader_book_tags')) == 1
    record('explicit_verified_book_bootstrap_preserves_current_user_metadata_and_local_mapping')
    before = counts(missing)
    book(missing, 13, [rid(12)], length=124, expected=REVISION, rev=REV_FORMAT)
    for kwargs in ({'length': 0}, {'length': 2 ** 63}, {'format': 'epub'}, {'sha': 'b' * 64}, {'favorite': 2}, {'key': 'sdk:777'}):
        book(missing, 13, [rid(12)], expected=ARG, **kwargs)
    assert counts(missing) == before
    record('verified_original_format_sha_length_and_favorite_cannot_be_forged_or_changed')
    book(missing, 13, [rid(12)], title='😀' * 4096, sort='😀' * 4096)
    before = counts(missing)
    book(missing, 14, [rid(13)], title='a' * 4097, expected=REVISION, rev=REV_LIMIT)
    book(missing, 14, [rid(13)], sort=b'\xed\xa0\x80', expected=REVISION, rev=REV_FORMAT)
    assert counts(missing) == before
    record('book_metadata_and_host_sort_obey_existing_scalar_byte_and_utf8_limits')
    for kind, key in ((0, '2' * 32), (2, '3' * 32)):
        group(missing, 20 + kind, kind=kind, key=key)
        member(missing, 23 + kind, kind=kind, key=key, ordinal=7)
    assert sql(missing, 'SELECT ordinal FROM reader_book_shelves') == [(7,)]
    assert sql(missing, 'SELECT ordinal FROM reader_book_series') == [(7,)]
    record('shelf_and_series_memberships_use_existing_ordered_joins')
    member(missing, 26, [rid(11)], ordinal=1, expected=ARG)
    member(missing, 26, [rid(11)], ordinal=2 ** 63, expected=ARG)
    member(missing, 26, [rid(11)], op=1)
    assert not sql(missing, 'SELECT * FROM reader_book_tags')
    member(missing, 27, [rid(26)], op=2)
    assert len(sql(missing, 'SELECT * FROM reader_book_tags')) == 1
    record('membership_delete_restore_and_unordered_tag_contract_are_explicit')
    group(missing, 28, [rid(10)], op=1)
    before = counts(missing)
    member(missing, 29, [rid(27)], expected=REVISION, rev=REV_UNSAFE)
    member(missing, 29, kind=2, key='f' * 32, expected=REVISION, rev=REV_UNSAFE)
    assert counts(missing) == before
    record('deleted_or_missing_collection_dependency_rolls_back_membership')
    book(missing, 30, [rid(13)], op=1)
    before = counts(missing)
    member(missing, 31, [rid(23)], kind=0, key='2' * 32, expected=REVISION, rev=REV_UNSAFE)
    assert counts(missing) == before
    record('retained_book_identity_does_not_override_active_book_dependency')

    hierarchy = folder / 'hierarchy.sqlite';invoke(hierarchy, 'identity')
    group(hierarchy, 40, kind=0, key='4' * 32)
    group(hierarchy, 41, kind=0, key='5' * 32, parent='4' * 32, ordinal=2)
    group(hierarchy, 42, [rid(40)], kind=0, key='4' * 32, parent='5' * 32, expected=REVISION, rev=REV_DATABASE)
    assert counts(hierarchy) == (2, 2)
    group(hierarchy, 42, kind=0, key='6' * 32, parent='f' * 32, expected=REVISION, rev=REV_UNSAFE)
    assert counts(hierarchy) == (2, 2)
    record('sub_shelf_parent_and_existing_schema_cycle_guards_survive_typed_commands')
    for trigger, table in (('fail_metadata', 'reader_tags'), ('fail_outbox', 'reader_outbox')):
        fault = folder / (trigger + '.sqlite');invoke(fault, 'identity')
        sql(fault, "CREATE TRIGGER " + trigger + " BEFORE INSERT ON " + table + " BEGIN SELECT RAISE(ABORT,'typed fault');END")
        failed = group(fault, None, key='-', expected=REVISION, rev=REV_DATABASE)
        assert re.fullmatch('[0-9a-f]{32}', failed['id']) and re.fullmatch('[0-9a-f]{32}', failed['key'])
        assert counts(fault) == (0, 0) and not sql(fault, 'SELECT * FROM reader_tags')
        sql(fault, 'DROP TRIGGER ' + trigger)
        number = int(failed['id'], 16)
        group(fault, number, key=failed['key'])
        assert counts(fault) == (1, 1)
        record(trigger + '_rolls_back_and_returned_generated_ids_allow_exact_retry')
    queue = sql(db, 'SELECT body_sha256 FROM reader_revisions WHERE revision_id=?', (rid(1),))[0][0]
    result = subprocess.run([str(revision_consumer), 'ack', str(db), rid(1), queue], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0 and json.loads(result.stdout)['status'] == OK
    before = counts(db);group(db, 1)
    assert counts(db) == before
    record('acknowledged_stable_command_retry_never_requeues')
    invoke(db, 'wrong-thread', rid(90), '-', expected=REVISION, rev=REV_OWNER)
    assert counts(db) == before
    record('native_product_owner_thread_rule_is_preserved')

    conflict = folder / 'conflict.sqlite';group(conflict, 50)
    first, _ = retained(conflict, 50)
    for number in (52, 51):
        remote(conflict, dict(first, id=rid(number), parents=[rid(50)], payload={'name': str(number)}))
    group(conflict, 53, [rid(52), rid(51)], name='Merged')
    assert retained(conflict, 53)[0]['parents'] == [rid(51), rid(52)] and counts(conflict) == (4, 2)
    record('explicit_conflict_resolution_covers_all_observed_heads_in_deterministic_parent_order')
    race = folder / 'race.sqlite';group(race, 60)
    processes = [subprocess.Popen([str(consumer), 'group', str(race), *map(str, group_args(n, [rid(60)], name=str(n)))], stdout=subprocess.PIPE, stderr=subprocess.PIPE) for n in (61, 62)]
    results = []
    for process in processes:
        stdout, stderr = process.communicate(timeout=40)
        assert process.returncode == 0, stderr
        results.append(json.loads(stdout))
    assert sorted(v['status'] for v in results) == [OK, REVISION]
    assert next(v for v in results if v['status'] == REVISION)['revision_status'] == REV_UNSAFE
    assert counts(race) == (2, 2)
    record('two_typed_native_processes_cannot_both_commit_one_observed_head')

    for action, number in (('group-before', 70), ('group-after', 71)):
        crash = folder / (action + '.sqlite');invoke(crash, 'identity')
        if action == 'group-before':
            sql(crash, 'CREATE TRIGGER pause_metadata BEFORE INSERT ON reader_tags BEGIN SELECT reader_test_pause();END')
        marker = folder / (action + '.ready')
        with (folder / (action + '.log')).open('wb') as log:
            process = subprocess.Popen([str(consumer), action, str(crash), *map(str, group_args(number)), str(marker)], stdout=log, stderr=subprocess.STDOUT)
            try:
                deadline = time.monotonic() + 40
                while not marker.exists():
                    assert process.poll() is None and time.monotonic() < deadline, 'Typed crash boundary not reached'
                    time.sleep(.05)
                process.kill();process.wait(timeout=20)
            finally:
                if process.poll() is None:
                    process.kill();process.wait(timeout=20)
        if action == 'group-before':
            sql(crash, 'DROP TRIGGER pause_metadata')
            assert counts(crash) == (0, 0) and not sql(crash, 'SELECT * FROM reader_tags')
        else:
            assert counts(crash) == (1, 1)
        group(crash, number)
        assert counts(crash) == (1, 1) and sql(crash, 'SELECT name FROM reader_tags') == [('书架😀',)]
        record(action + '_real_process_kill_and_stable_retry_preserve_all_or_none')

    def utf16(value, capacity=16385, expected=OK):
        raw = value.encode('utf-16-le', errors='surrogatepass')
        return invoke('-', 'utf16', text(raw), capacity, expected=expected)

    for value in ('', 'ASCII', '书架😀', 'E\u0301clair', '\U0010ffff'):
        result = utf16(value)
        assert result['text'] == value and result['bytes'] == len(value.encode('utf-8'))
    record('counted_utf16_conversion_preserves_unicode_scalars_emoji_and_decomposed_text')
    for value in ('\ud800', '\udc00', '\ud800A', 'A\udc00', '\ud800\ud800', '\udc00\ud800', 'A\x00B'):
        result = utf16(value, expected=ARG)
        assert result['bytes'] == 0 and result['text'] == ''
    record('lone_surrogates_wrong_pairs_and_embedded_nul_fail_without_partial_output')
    assert utf16('😀', 5)['bytes'] == 4
    for value, capacity in (('😀', 4), ('a', 0), ('a' * 16385, 20000), ('😀' * 4097, 20000)):
        result = utf16(value, capacity, expected=ARG)
        assert result['bytes'] == 0 and result['text'] == ''
    assert utf16('😀' * 4096)['bytes'] == 16384
    record('utf16_unit_utf8_byte_and_terminator_capacity_limits_are_bounded')
    sdk = folder / 'sdk.sqlite';sql(sdk, 'PRAGMA application_id=1163416131');sql(sdk, 'PRAGMA user_version=7')
    before = sdk.read_bytes()
    group(sdk, 99, expected=REVISION, rev=REV_DATABASE)
    assert sdk.read_bytes() == before
    record('typed_producer_refuses_sdk_database_without_modification')
    report = {'accepted': True, 'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
              'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'platform': sys.platform, 'count': len(checks),
              'checks': [{'id': name, 'pass': True} for name in checks], 'native_only_wire_producer': True,
              'schema1_changed': False, 'sdk_database_writes': False, 'mobile_accepted': False, 'complete_product': False}
    (folder / 'result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'accepted': True, 'checks': len(checks), 'source_sha': os.environ['GITHUB_SHA']}))


if __name__ == '__main__':
    main()
