# SPDX-License-Identifier: MIT
"""Actions-only installed desktop adapter and actual process-death recovery."""
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

OK, NONE, BOOTSTRAP, CONFLICT, PENDING, IO, ARG, OWNER = range(8)
BOOK = 'txt:' + 'a' * 64


def main():
    p = argparse.ArgumentParser()
    for name in ('consumer', 'c-consumer', 'command-consumer', 'product-prefix', 'link-map', 'build-log', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    a = p.parse_args()
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip() == os.environ['GITHUB_SHA']
    folder = a.output.resolve();folder.mkdir(parents=True)
    consumer = a.consumer.resolve();command = a.command_consumer.resolve()
    db = folder / '产品.sqlite';journal = folder / 'typed.pending'
    checks = []

    def record(name):
        assert name not in checks
        checks.append(name)
        print(json.dumps({'check': name, 'pass': True}), flush=True)

    def invoke(action, *args, expected=OK, database=db, pending=journal):
        result = subprocess.run([str(consumer), action, str(database), str(pending), *map(str, args)], capture_output=True, encoding='utf-8', errors='strict', timeout=60)
        assert result.returncode == 0, (action, result.stderr)
        value = json.loads(result.stdout)
        assert value['status'] == expected, (expected, value)
        return value

    def sql(query, args=(), database=db):
        with sqlite3.connect(database) as connection:
            return connection.execute(query, args).fetchall()

    def counts(database=db):
        return sql('SELECT (SELECT count(*) FROM reader_revisions),(SELECT count(*) FROM reader_outbox)', database=database)[0]

    def group(kind=1, key='-', name='标签😀', parent='-', ordinal=0, operation=0, mode='finish', **kwargs):
        return invoke('group', kind, key, name, parent, ordinal, operation, mode, **kwargs)

    def raw_group(key, parent_revision, name, number, kind=1, parent='-', ordinal=0):
        path = folder / ('name-' + str(number) + '.txt');path.write_text(name, encoding='utf-8')
        result = subprocess.run([str(command), 'group', str(db), '%032x' % number, parent_revision, str(kind), '0', key, str(path), parent, str(ordinal)], capture_output=True, encoding='utf-8', timeout=60)
        assert result.returncode == 0 and json.loads(result.stdout)['status'] == 0, result.stdout
        return '%032x' % number

    identity = invoke('seed')
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
    record('installed_adapter_uses_the_same_single_verified_product_sqlite')

    cdb = folder / 'c-api.sqlite';cjournal = folder / 'c-api.pending'
    subprocess.run([str(a.c_consumer.resolve()), str(cdb), str(cjournal)], check=True, timeout=60)
    assert counts(cdb) == (3, 3) and not cjournal.exists()
    record('independent_installed_c_consumer_bootstraps_and_calls_all_three_typed_producers')
    invoke('wrong-thread', expected=OWNER)
    record('native_metadata_owner_rejects_wrong_thread_calls')
    invoke('second-owner', expected=OWNER)
    record('a_second_owner_cannot_share_the_pending_profile')
    view = invoke('book', expected=BOOTSTRAP)
    assert view['title'] == view['sort'] == '用户已编辑标题😀' and view['author'] == '用户作者' and view['favorite'] == 1 and view['heads'] == 0
    record('catalog_only_prepare_preserves_current_product_metadata_and_reports_bootstrap')
    before = counts()
    invoke('bootstrap', 124, 'finish', expected=ARG)
    assert counts() == before and not journal.exists()
    record('verified_source_mismatch_cannot_stage_or_write_any_revision')
    invoke('favorite', 0, 'finish', expected=BOOTSTRAP)
    assert counts() == before and not journal.exists()
    record('ordinary_book_edit_cannot_silently_bootstrap_legacy_metadata')
    tag = group()
    before = counts()
    invoke('member', 1, tag['key'], 0, 0, 'finish', expected=BOOTSTRAP)
    assert counts() == before and not journal.exists()
    record('membership_reports_needs_bootstrap_before_staging_or_writing')
    bootstrap = invoke('bootstrap', 123, 'finish')
    assert bootstrap['committed'] == bootstrap['created'] == bootstrap['applied'] == 1 and bootstrap['pending'] == 0
    assert sql('SELECT title,author,sort_title,favorite FROM reader_books') == [('用户已编辑标题😀', '用户作者', '用户已编辑标题😀', 1)]
    assert sql('SELECT sdk_book_id FROM reader_local_books') == [(777,)]
    record('explicit_verified_bootstrap_retains_edited_fields_and_existing_sdk_local_mapping')
    favorite = invoke('favorite', 0, 'finish')
    raw = sql('SELECT body_json FROM reader_revisions WHERE revision_id=?', (favorite['id'],))[0][0]
    wire = json.loads(raw)
    assert wire['parents'] == [bootstrap['id']] and wire['payload']['favorite'] is False
    assert wire['payload']['title'] == '用户已编辑标题😀' and 'sdk_book_id' not in raw
    record('favorite_produces_only_native_schema1_with_the_complete_original_snapshot')

    before = counts();staged = group(name='先持久化😀', mode='stage')
    saved = journal.read_bytes()
    assert counts() == before and 0 < len(saved) <= 131072 and staged['id'].encode() in saved and staged['key'].encode() in saved and '先持久化😀'.encode() in saved
    assert staged['pending'] == 1 and not staged['committed'] and not staged['created']
    record('complete_bounded_typed_intent_and_both_ids_are_durable_before_any_mutation')
    applied = invoke('apply');assert applied['created'] == applied['applied'] == applied['committed'] == applied['pending'] == 1
    newer = raw_group(staged['key'], staged['id'], '之后的新标题', 900)
    before = counts();replayed = invoke('apply')
    assert replayed['id'] == staged['id'] and replayed['created'] == replayed['applied'] == 0 and replayed['committed'] == 1
    assert counts() == before and sql('SELECT name FROM reader_tags WHERE tag_id=?', (staged['key'],)) == [('之后的新标题',)]
    record('exact_old_intent_retry_never_requeues_or_replays_newer_metadata')
    invoke('abandon', expected=CONFLICT);assert journal.read_bytes() == saved
    record('a_committed_pending_intent_cannot_be_abandoned')
    group(name='禁止覆盖', mode='stage', expected=PENDING)
    assert journal.read_bytes() == saved and counts() == before
    record('a_new_staged_action_cannot_replace_an_existing_pending_intent')
    done = invoke('finish');assert done['committed'] == 1 and not done['pending'] and not journal.exists()
    staged = group(key=staged['key'], name='过期编辑', mode='stage');saved = journal.read_bytes()
    latest = raw_group(staged['key'], newer, '并发提交保留', 901)
    before = counts();refused = invoke('finish', expected=CONFLICT)
    assert refused['revision_status'] == 10 and not refused['committed'] and counts() == before and journal.read_bytes() == saved
    assert not sql('SELECT 1 FROM reader_revisions WHERE revision_id=?', (staged['id'],))
    assert sql('SELECT name FROM reader_tags WHERE tag_id=?', (staged['key'],)) == [('并发提交保留',)]
    record('stale_expected_heads_refuse_all_writes_and_keep_the_exact_original_intent')
    invoke('abandon');assert not journal.exists() and counts() == before
    record('explicit_abandonment_only_clears_an_uncommitted_intent')

    shelf = group(kind=0, name='父书架', ordinal=10)
    child = group(kind=0, name='子书架', parent=shelf['key'], ordinal=5)
    series = group(kind=2, name='系列😀')
    child_view = invoke('inspect-group', 0, child['key'])
    assert child_view['name'] == '子书架' and child_view['parent'] == shelf['key'] and child_view['ordinal'] == 5 and child_view['heads'] == 1
    record('shelves_subshelves_tags_and_series_share_the_installed_native_adapter')
    for kind, entity, ordinal in ((0, child, 7), (1, tag, 0), (2, series, 2)):
        joined = invoke('member', kind, entity['key'], ordinal, 0, 'finish')
        assert joined['committed'] and joined['created'] and joined['applied']
    assert sql('SELECT ordinal FROM reader_book_shelves') == [(7,)] and sql('SELECT ordinal FROM reader_book_series') == [(2,)] and len(sql('SELECT * FROM reader_book_tags')) == 1
    record('all_three_membership_kinds_preserve_existing_ordinal_contracts')
    group(key=tag['key'], name='unused', operation=1)
    deleted = invoke('inspect-group', 1, tag['key']);assert deleted['deleted'] == 1 and deleted['present'] == 1
    group(key=tag['key'], name='恢复😀', operation=2)
    assert invoke('inspect-group', 1, tag['key'])['name'] == '恢复😀'
    record('deleted_group_metadata_remains_visible_for_explicit_restore')
    utf8 = sql('SELECT body_json FROM reader_revisions WHERE revision_id=?', (series['id'],))[0][0].encode()
    assert '系列😀'.encode() in utf8 and b'\\ud83d' not in utf8
    record('typed_group_names_remain_standard_utf8_with_supplementary_characters')

    for phase in ('stage', 'apply'):
        marker = folder / (phase + '-ready');before = counts()
        proc = subprocess.Popen([str(consumer), 'group', str(db), str(journal), '1', '-', phase + '-kill', '-', '0', '0', phase + '-wait', str(marker)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 30
            while not marker.exists():
                assert proc.poll() is None, proc.communicate()
                assert time.monotonic() < deadline
                time.sleep(.05)
            invoke('pending', expected=OWNER)
            assert counts() == (before if phase == 'stage' else (before[0] + 1, before[1] + 1))
        finally:
            proc.kill();proc.communicate(timeout=10)
        recovered = invoke('pending');assert re.fullmatch('[0-9a-f]{32}', recovered['key']) and re.fullmatch('[0-9a-f]{32}', recovered['id'])
        if phase == 'apply':
            raw_group(recovered['key'], recovered['id'], 'kill后另一编辑', 902)
            before_replay = counts()
        finished = invoke('finish')
        assert finished['id'] == recovered['id'] and finished['key'] == recovered['key'] and finished['committed'] and not finished['pending']
        if phase == 'stage':assert finished['created'] == finished['applied'] == 1 and counts() == (before[0] + 1, before[1] + 1)
        else:assert finished['created'] == finished['applied'] == 0 and counts() == before_replay and sql('SELECT name FROM reader_tags WHERE tag_id=?', (recovered['key'],)) == [('kill后另一编辑',)]
        record('actual_process_kill_' + phase + '_recovers_exact_ids_payload_heads_and_releases_owner_lock')

    before = counts();denied = invoke('cleanup-denied', expected=9)
    assert denied['committed'] == denied['pending'] == 1 and counts() == (before[0] + 1, before[1] + 1) and journal.exists()
    invoke('finish');assert not journal.exists()
    record('real_cleanup_refusal_reports_committed_and_retains_safe_retry_intent')
    group(name='完整性检查', mode='stage');saved = journal.read_bytes();before = counts()
    damaged = bytearray(saved);damaged[len(damaged) // 2] ^= 1;journal.write_bytes(damaged)
    invoke('finish', expected=IO);assert counts() == before
    journal.write_bytes(saved[:-1]);invoke('pending', expected=IO);assert counts() == before
    journal.write_bytes(saved)
    record('changed_or_truncated_pending_bytes_are_refused_without_product_writes')
    journal.write_bytes(b'x' * 131073);invoke('pending', expected=IO);assert counts() == before;journal.write_bytes(saved)
    record('oversized_pending_intent_is_refused_before_unbounded_allocation')
    other = folder / 'wrong-product.sqlite';invoke('pending', expected=IO, database=other)
    assert not other.exists() and counts() == before
    record('pending_database_binding_is_checked_before_opening_another_product_database')
    invoke('abandon');Path(str(journal) + '.tmp').write_bytes(b'incomplete prepublication')
    group(name='遗留tmp之后');assert not journal.exists() and not Path(str(journal) + '.tmp').exists()
    record('orphan_prepublication_temporary_file_cannot_replay_or_block_a_new_intent')
    before = counts();group(name='a' * 257, mode='finish', expected=8)
    assert counts() == before and journal.exists();invoke('abandon')
    record('producer_validation_failure_preserves_the_intent_and_zero_transaction_effects')
    assert len(checks) == 28, len(checks)
    result = {'accepted': True, 'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
              'attempt': int(os.environ['GITHUB_RUN_ATTEMPT']), 'platform': sys.platform, 'count': len(checks), 'checks': checks,
              'sdk_database_writes': False, 'schema1_changed': False, 'wire_changed': False, 'network_used': False,
              'native_adapter_only': True, 'desktop_ui_accepted': False, 'sdk_source_verification_accepted': False,
              'consumer_sha256': hashlib.sha256(consumer.read_bytes()).hexdigest()}
    (folder / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
