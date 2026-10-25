# SPDX-License-Identifier: MIT
"""Actions-only acceptance of the installed bulk organization package.

Every scenario drives the installed bulk-probe (an independent consumer) and is
judged by an independent sqlite3 reader of the product database: metadata rows,
retained history, outbox, retry IDs, observed heads and untouched books.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time

OK, CANCELLED, ARGUMENT, OWNER, IO, CORRUPT, ACTIVE, NO_JOURNAL, FOREIGN, METADATA, CAPACITY = range(11)
NOT_RUN, COMMITTED, UNCHANGED, CONFLICT, MISSING, DEPENDENCY, BOOTSTRAP, FAILED = range(8)
FAV_SET, FAV_CLEAR, SHELF_ADD, SHELF_REMOVE, TAG_ADD, TAG_REMOVE, SERIES_ADD, SERIES_REMOVE = range(8)
BOOKS = 2202
BATCH = 100


def key(i):
    return 'txt:%064x' % (i + 1)


def main():
    p = argparse.ArgumentParser()
    for name in ('probe', 'c-consumer', 'link-map', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    a = p.parse_args()
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    source = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    assert source == os.environ['GITHUB_SHA']
    folder = a.output.resolve()
    folder.mkdir(parents=True)
    probe = str(a.probe.resolve())
    db = folder / 'product.sqlite'
    pending = folder / 'typed.pending'
    journal = folder / 'bulk.journal'
    checks = []
    timings = {}

    def record(name):
        assert name not in [c['name'] for c in checks], name
        checks.append({'name': name, 'ok': True})
        print(json.dumps({'check': name, 'pass': True}), flush=True)

    def invoke(mode, *options, expect=None, timeout=900, database=db, pend=pending, jour=journal):
        result = subprocess.run([probe, mode, str(database), str(pend), str(jour), *map(str, options)],
                                capture_output=True, encoding='utf-8', errors='strict', timeout=timeout)
        assert result.returncode == 0, (mode, options, result.returncode, result.stderr)
        value = json.loads(result.stdout)
        if 'status' in value and mode != 'bad-request':
            assert value['error_code'] == value['status'], (mode, value)
        if expect is not None:
            assert value['status'] == expect, (mode, options, expect, value)
        return value

    def sql(query, args=()):
        connection = sqlite3.connect(str(db))
        try:
            return connection.execute(query, args).fetchall()
        finally:
            connection.close()

    def totals():
        return sql('SELECT (SELECT count(*) FROM reader_revisions),(SELECT count(*) FROM reader_outbox)')[0]

    def book_revisions(indices):
        wanted = set(key(i) for i in indices)
        return [r for r in sql('SELECT revision_id,entity_key,operation,body_sha256 FROM reader_revisions WHERE entity_kind=\'book\' ORDER BY revision_id')
                if r[1] in wanted]

    def fav(i):
        return sql('SELECT favorite FROM reader_books WHERE book_key=?', (key(i),))[0][0]

    def entity_revisions(kind, entity):
        return sql('SELECT revision_id,operation,body_json FROM reader_revisions WHERE entity_kind=? AND entity_key=? ORDER BY revision_id', (kind, entity))

    def membership_rows(kind, group):
        table = {'shelf': ('reader_book_shelves', 'shelf_id'), 'tag': ('reader_book_tags', 'tag_id'), 'series': ('reader_book_series', 'series_id')}[kind]
        return dict((k, o) for k, o in sql('SELECT book_key,%s FROM %s WHERE %s=?' % ('ordinal' if kind != 'tag' else '0', table[0], table[1]), (group,)))

    def batches(first, total, stride=1):
        position = 0
        while position < total:
            count = min(BATCH, total - position)
            yield first + position * stride, count
            position += count

    def run_all(action, group, first, total, ordinal_from=None, stride=1):
        results = []
        for start, count in batches(first, total, stride):
            options = ['action=' + str(action), 'start=' + str(start), 'count=' + str(count), 'stride=' + str(stride)]
            if group:
                options.append('group=' + group)
            options.append('ordinal=' + str(start if ordinal_from is None else ordinal_from + (start - first)))
            result = invoke('run', *options, expect=OK)
            s = result['summary']
            assert s['complete'] == 1 and s['total'] == count and s['not_run'] == 0, s
            assert len(result['items']) == count and count <= BATCH
            # The report survives until the host acknowledges it.
            assert journal.exists()
            inspected = invoke('inspect', expect=OK)
            assert inspected['items'] == result['items'] and inspected['summary'] == s
            invoke('ack', expect=OK)
            assert not journal.exists()
            results.extend(result['items'])
        return results

    def audit_items(items, kind, group=None, observed=None):
        """Every reported revision must exist, belong to the entity, and have exactly the observed heads as parents."""
        for item in items:
            if item['outcome'] != COMMITTED:
                continue
            rows = sql('SELECT entity_kind,entity_key,operation,body_json FROM reader_revisions WHERE revision_id=?', (item['revision'],))
            assert len(rows) == 1, item
            entity_kind, entity_key, operation, body = rows[0]
            assert entity_kind == kind and entity_key == item['entity'], (item, rows[0])
            assert sql('SELECT count(*) FROM reader_outbox WHERE revision_id=?', (item['revision'],))[0][0] == 1
            if item['heads_known']:
                parents = json.loads(body)['parents']
                assert sorted(parents) == sorted(item['heads']), (item, parents)

    # ---- seed -----------------------------------------------------------
    started = time.time()
    seeded = invoke('seed', 'count=%d' % BOOKS, 'legacy=1')
    assert seeded['books'] == BOOKS
    shelves, tags, series = seeded['shelves'], seeded['tags'], seeded['series']
    timings['seed_seconds'] = round(time.time() - started, 1)
    assert sql('PRAGMA user_version')[0][0] == 1 and sql('PRAGMA application_id')[0][0] == 1163416144
    assert sql('SELECT count(*) FROM reader_books')[0][0] == BOOKS + 1
    base_revisions = totals()
    assert base_revisions[0] == base_revisions[1] == BOOKS + 3 + 3 + 2
    record('seeded_2202_bootstrapped_books_plus_one_legacy_catalog_only_book_and_eight_groups')

    # ---- C ABI and argument bounds -------------------------------------
    c_db = folder / 'c-api.sqlite'
    c_out = subprocess.run([str(a.c_consumer.resolve()), str(c_db), str(folder / 'c-api.pending'), str(folder / 'c-api.journal')],
                           capture_output=True, encoding='utf-8', timeout=120)
    assert c_out.returncode == 0 and 'c-abi-ok' in c_out.stdout, (c_out.returncode, c_out.stdout, c_out.stderr)
    record('independent_installed_c_consumer_runs_a_batch_and_acknowledges_its_journal')
    before = totals()
    bad = invoke('bad-request', expect=OK)
    assert bad['refused'] == 8 and not journal.exists() and totals() == before
    record('duplicate_empty_oversize_group_ordinal_capacity_and_struct_size_requests_are_refused_without_a_journal')
    wrong = invoke('wrong-thread', expect=OWNER)
    assert not journal.exists() and totals() == before
    record('a_second_thread_cannot_run_a_batch_on_the_owner_worker')
    foreign = invoke('foreign', expect=FOREIGN)
    assert not journal.exists() and totals() == before and not pending.exists()
    record('an_unrelated_pending_metadata_intent_blocks_the_batch_and_is_left_for_its_owner')

    # ---- 2202 books, every batch at most 100 ---------------------------
    started = time.time()
    snapshot_unselected = book_revisions(range(1100, BOOKS))
    snapshot_unselected_flags = [fav(i) for i in range(1100, BOOKS)]
    items = run_all(SHELF_ADD, shelves[0], 0, BOOKS)
    assert len(items) == BOOKS and all(i['outcome'] == COMMITTED and i['created'] == 1 and i['replayed'] == 0 and i['heads_known'] == 1 and i['heads'] == [] for i in items)
    after = totals()
    assert after == (before[0] + BOOKS, before[1] + BOOKS)
    members = membership_rows('shelf', shelves[0])
    assert len(members) == BOOKS and all(members[key(i)] == i for i in range(BOOKS)), 'ordinals follow ordinal_base+index per batch'
    audit_items(items, 'membership')
    timings['shelf_add_2202_seconds'] = round(time.time() - started, 1)
    record('shelf_add_commits_2202_books_in_23_batches_of_at_most_100_with_metadata_history_and_outbox_each_exact')

    again = run_all(SHELF_ADD, shelves[0], 0, BOOKS)
    assert all(i['outcome'] == UNCHANGED and not i['committed'] and not i['revision'] for i in again)
    assert totals() == after
    record('repeating_the_same_2202_book_request_is_unchanged_with_no_new_revision_or_outbox_row')

    started = time.time()
    items = run_all(FAV_SET, None, 0, 1100)
    assert all(i['outcome'] == COMMITTED for i in items) and all(fav(i) == 1 for i in range(1100))
    audit_items(items, 'book')
    assert totals() == (after[0] + 1100, after[1] + 1100)
    timings['favorite_1100_seconds'] = round(time.time() - started, 1)
    assert book_revisions(range(1100, BOOKS)) == snapshot_unselected and [fav(i) for i in range(1100, BOOKS)] == snapshot_unselected_flags
    record('favorite_set_on_1100_selected_books_leaves_the_1102_unselected_books_and_their_history_unchanged')
    # Favorite metadata other than the flag is preserved exactly.
    row = sql('SELECT title,author,sort_title,source_bytes FROM reader_books WHERE book_key=?', (key(5),))[0]
    assert row == ('book-5', 'author-5', 'book-5', 105)
    record('favorite_edits_preserve_title_author_sort_title_and_original_identity')

    tag_items = run_all(TAG_ADD, tags[0], 0, 300)
    assert all(i['outcome'] == COMMITTED for i in tag_items) and len(membership_rows('tag', tags[0])) == 300
    removed = run_all(TAG_REMOVE, tags[0], 0, 120)
    assert all(i['outcome'] == COMMITTED for i in removed) and len(membership_rows('tag', tags[0])) == 180
    audit_items(removed, 'membership')
    assert all(entity_revisions('membership', 'tag:%s:%s' % (tags[0], key(i)))[-1][1] in ('delete', 'put') for i in range(120))
    ops = [r[1] for r in entity_revisions('membership', 'tag:%s:%s' % (tags[0], key(0)))]
    assert sorted(ops) == ['delete', 'put']
    absent = run_all(TAG_REMOVE, tags[0], 0, 120)
    assert all(i['outcome'] == UNCHANGED for i in absent)
    readded = run_all(TAG_ADD, tags[0], 0, 100)
    assert all(i['outcome'] == COMMITTED for i in readded), 'a deleted membership returns through an explicit restore'
    ops = sorted(r[1] for r in entity_revisions('membership', 'tag:%s:%s' % (tags[0], key(0))))
    assert ops == ['delete', 'put', 'restore'], ops
    record('tag_add_remove_and_restore_use_typed_put_delete_restore_and_remove_of_a_non_member_is_unchanged')
    series_items = run_all(SERIES_ADD, series[0], 200, 100, ordinal_from=40)
    assert all(i['outcome'] == COMMITTED for i in series_items)
    ordinals = membership_rows('series', series[0])
    assert ordinals == dict((key(200 + n), 40 + n) for n in range(100))
    record('series_add_assigns_the_documented_ordinals_and_shelf_remove_deletes_with_observed_heads')
    shelf_removed = run_all(SHELF_REMOVE, shelves[0], 0, 50)
    assert all(i['outcome'] == COMMITTED for i in shelf_removed) and len(membership_rows('shelf', shelves[0])) == BOOKS - 50
    audit_items(shelf_removed, 'membership')

    # ---- mid-batch conflict, deleted dependency, missing and legacy books
    base = totals()
    wire = json.dumps({'version': 1, 'id': 'c0' * 16, 'entity_kind': 'book', 'entity_key': key(1250), 'operation': 'put', 'location_kind': 'none',
                       'parents': [], 'payload': {'format': 'txt', 'source_sha256': '%064x' % 1251, 'source_bytes': 1350, 'title': 'concurrent-1250',
                                                  'author': 'author', 'favorite': False}}, separators=(',', ':'))
    wire_path = folder / 'remote-book.json'
    wire_path.write_bytes(wire.encode('utf-8'))
    conflict = invoke('run', 'action=%d' % FAV_SET, 'start=1200', 'count=100', 'interfere_after=10', 'fork_book=1250', 'fork_wire=' + str(wire_path), 'fork_sha=' + hashlib.sha256(wire.encode('utf-8')).hexdigest(), expect=OK)
    out = conflict['items']
    assert conflict['summary']['complete'] == 1 and conflict['summary']['conflicts'] == 1 and conflict['summary']['committed'] == 99
    assert out[50]['outcome'] == CONFLICT and out[50]['conflict'] == 1 and not out[50]['revision'] and fav(1250) == 0
    assert all(out[n]['outcome'] == COMMITTED for n in range(100) if n != 50)
    assert all(fav(1200 + n) == 1 for n in range(100) if n != 50)
    assert len(out[50]['heads']) == 2 and out[50]['heads_known'] == 1, 'the complete concurrent head set is reported'
    assert totals() == (base[0] + 100, base[1] + 99), '99 batch revisions plus one received concurrent revision (no outbox row)'
    audit_items(out, 'book')
    invoke('ack', expect=OK)
    record('a_concurrent_head_created_mid_batch_is_reported_conflict_while_neighbours_stay_committed_and_the_book_unchanged')

    base = totals()
    dependency = invoke('run', 'action=%d' % SHELF_ADD, 'group=' + shelves[2], 'start=1300', 'count=100',
                        'interfere_after=20', 'delete_group=' + shelves[2], 'delete_kind=0', expect=OK)
    out = dependency['items']
    assert [i['outcome'] for i in out[:21]] == [COMMITTED] * 21
    assert all(i['outcome'] == DEPENDENCY and i['conflict'] == 1 for i in out[21:]), [i['outcome'] for i in out[21:]]
    assert dependency['summary']['committed'] == 21 and dependency['summary']['conflicts'] == 79
    assert totals() == (base[0] + 21 + 1, base[1] + 21 + 1)
    assert len([r for r in sql('SELECT entity_key FROM reader_revisions WHERE entity_kind=\'membership\' AND entity_key LIKE ?', ('shelf:' + shelves[2] + ':%',))]) == 21
    invoke('ack', expect=OK)
    record('group_deleted_mid_batch_reports_dependency_deleted_for_the_remaining_79_and_keeps_the_21_commits')

    base = totals()
    missing_key = 'txt:' + 'f' * 64
    mixed = invoke('run', 'action=%d' % FAV_SET, 'keys=%s,%s,%s,%s' % (key(1600), missing_key, key(1601), key(BOOKS)), expect=OK)
    outcomes = [i['outcome'] for i in mixed['items']]
    assert outcomes == [COMMITTED, MISSING, COMMITTED, BOOTSTRAP], outcomes
    assert mixed['summary']['committed'] == 2 and mixed['summary']['failed'] == 2
    assert totals() == (base[0] + 2, base[1] + 2) and journal.exists()
    assert invoke('inspect', expect=OK)['summary'] == mixed['summary']
    invoke('ack', expect=OK)
    record('missing_and_legacy_books_are_reported_per_item_without_stopping_the_batch')

    # ---- cancellation: committed items stay, resume continues with same IDs
    base = totals()
    cancelled = invoke('run', 'action=%d' % TAG_ADD, 'group=' + tags[1], 'start=1400', 'count=100', 'cancel_after=30', expect=CANCELLED)
    assert cancelled['summary']['committed'] == 30 and cancelled['summary']['not_run'] == 70 and cancelled['summary']['cancelled'] == 1
    first_ids = [i['revision'] for i in cancelled['items'][:30]]
    assert totals() == (base[0] + 30, base[1] + 30) and journal.exists() and not pending.exists()
    assert len(membership_rows('tag', tags[1])) == 30
    invoke('run', 'action=%d' % TAG_ADD, 'group=' + tags[1], 'start=1400', 'count=1', expect=ACTIVE)
    resumed = invoke('resume', expect=OK)
    assert resumed['summary']['complete'] == 1 and resumed['summary']['committed'] == 100
    assert [i['revision'] for i in resumed['items'][:30]] == first_ids
    assert totals() == (base[0] + 100, base[1] + 100) and len(membership_rows('tag', tags[1])) == 100
    invoke('ack', expect=OK)
    record('cancel_keeps_30_committed_items_blocks_a_new_batch_and_resume_finishes_the_other_70_with_the_original_ids')

    base = totals()
    invoke('run', 'action=%d' % TAG_ADD, 'group=' + tags[2], 'start=1500', 'count=100', 'cancel_after=5', expect=CANCELLED)
    invoke('abandon', expect=OK)
    assert not journal.exists() and len(membership_rows('tag', tags[2])) == 5 and totals() == (base[0] + 5, base[1] + 5)
    invoke('abandon', expect=NO_JOURNAL)
    record('abandon_removes_the_journal_but_never_rolls_back_the_five_committed_items')

    # ---- actual process termination before and after the product commit
    for phase, expect_committed_at_kill in (('staged', 0), ('committed', 1)):
        base = totals()
        marker = folder / (phase + '.ready')
        marker.unlink(missing_ok=True)
        group = series[1]
        first = 1600 if phase == 'staged' else 1700
        proc = subprocess.Popen([probe, 'run', str(db), str(pending), str(journal), 'action=%d' % SERIES_ADD, 'group=' + group,
                                 'start=%d' % first, 'count=100', 'ordinal=0', 'pause=%s:7' % phase, 'marker=' + str(marker)],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        deadline = time.time() + 600
        while not marker.exists():
            assert proc.poll() is None and time.time() < deadline, proc.communicate()
            time.sleep(0.05)
        proc.kill()
        proc.communicate(timeout=30)
        entity = 'series:%s:%s' % (group, key(first + 7))
        stored = entity_revisions('membership', entity)
        assert len(stored) == expect_committed_at_kill, (phase, stored)
        assert pending.exists() and journal.exists()
        killed = invoke('inspect', expect=OK)
        assert killed['summary']['committed'] == (7 if phase == 'staged' else 7) and killed['summary']['not_run'] == 93
        assert totals() == (base[0] + 7 + expect_committed_at_kill, base[1] + 7 + expect_committed_at_kill)
        before_ids = [i['revision'] for i in killed['items'][:7]]
        resumed = invoke('resume', expect=OK)
        item = resumed['items'][7]
        assert resumed['summary']['complete'] == 1 and resumed['summary']['committed'] == 100, resumed['summary']
        assert item['outcome'] == COMMITTED and item['entity'] == entity
        if phase == 'staged':
            assert item['created'] == 1 and item['replayed'] == 0 and item['heads_known'] == 1, item
        else:
            assert item['created'] == 0 and item['replayed'] == 1 and item['heads_known'] == 1, item
        assert [i['revision'] for i in resumed['items'][:7]] == before_ids
        assert len(entity_revisions('membership', entity)) == 1 and item['revision'] == entity_revisions('membership', entity)[0][0]
        assert totals() == (base[0] + 100, base[1] + 100) and not pending.exists()
        audit_items(resumed['items'], 'membership')
        reopened = invoke('inspect', expect=OK)
        assert reopened['items'] == resumed['items']
        invoke('ack', expect=OK)
        record('actual_process_kill_%s_the_product_commit_resumes_with_exact_retry_id_and_no_duplicate_revision' % ('before' if phase == 'staged' else 'after'))

    # ---- journal damage and independent total check ---------------------
    invoke('run', 'action=%d' % TAG_ADD, 'group=' + tags[2], 'start=1500', 'count=20', 'cancel_after=2', expect=CANCELLED)
    raw = bytearray(journal.read_bytes())
    raw[len(raw) // 2] ^= 0x55
    journal.write_bytes(bytes(raw))
    totals_before = totals()
    invoke('resume', expect=CORRUPT)
    invoke('inspect', expect=CORRUPT)
    assert totals() == totals_before and journal.exists()
    invoke('abandon', expect=OK)
    assert not journal.exists()
    record('a_damaged_journal_is_refused_by_resume_and_inspect_changes_nothing_and_can_be_abandoned')

    # Real commit followed by a filesystem refusal while clearing its intent.
    # Isolate this DB so all original 2202-book expectations stay unchanged.
    recovery = folder / 'cleanup-refused'
    recovery.mkdir()
    other_db, other_pending, other_journal = recovery / 'product.sqlite', recovery / 'typed.pending', recovery / 'bulk.journal'
    invoke('seed', 'count=1', database=other_db, pend=other_pending, jour=other_journal)
    failed = invoke('run', 'action=0', 'count=1', 'block_cleanup=1', expect=METADATA,
                    database=other_db, pend=other_pending, jour=other_journal)
    assert failed['cleanup_failure_injected'] is True and failed['items'][0]['committed'] == 1, failed
    assert failed['summary']['committed'] == 1 and failed['summary']['not_run'] == 0 and failed['summary']['complete'] == 0, failed
    receipt = failed['items'][0]['revision']
    def recovery_rows():
        with sqlite3.connect(other_db) as connection:
            return connection.execute('SELECT revision_id FROM reader_revisions ORDER BY revision_id').fetchall(), connection.execute('SELECT revision_id FROM reader_outbox ORDER BY revision_id').fetchall()
    before_recovery = recovery_rows()
    assert (receipt,) in before_recovery[0] and (receipt,) in before_recovery[1]
    resumed = invoke('resume', expect=OK, database=other_db, pend=other_pending, jour=other_journal)
    assert resumed['summary']['complete'] == 1 and resumed['items'][0]['committed'] == 1 and resumed['items'][0]['replayed'] == 1, resumed
    assert resumed['items'][0]['revision'] == receipt and recovery_rows() == before_recovery, resumed
    invoke('ack', expect=OK, database=other_db, pend=other_pending, jour=other_journal)
    assert not other_pending.exists() and not other_journal.exists()
    record('apply_success_keeps_committed_receipt_when_pending_cleanup_fails_and_resume_reuses_original_revision')

    integrity = sql('PRAGMA integrity_check')
    assert integrity == [('ok',)]
    assert sql('SELECT count(*) FROM reader_outbox WHERE revision_id NOT IN (SELECT revision_id FROM reader_revisions)')[0][0] == 0
    assert sql('SELECT count(*) FROM reader_revisions WHERE revision_id NOT IN (SELECT revision_id FROM reader_outbox)')[0][0] == 1
    unselected_after = book_revisions(range(1100, 1200))
    assert sorted(r[0] for r in unselected_after) == sorted(r[0] for r in snapshot_unselected if r[1] in set(key(i) for i in range(1100, 1200))), 'books 1100..1199 were never selected by a book edit'
    assert [fav(i) for i in range(1100, 1200)] == [0] * 100
    link = a.link_map.read_text(errors='replace').lower()
    assert 'bulk.cpp' in link or 'reader_bulk' in link
    record('final_database_integrity_history_outbox_and_untouched_books_hold_after_all_scenarios')

    digest = hashlib.sha256(db.read_bytes()).hexdigest()
    report = {'ok': True, 'source': source, 'run_id': os.environ.get('GITHUB_RUN_ID'), 'attempt': os.environ.get('GITHUB_RUN_ATTEMPT'),
              'platform': sys.platform, 'books': BOOKS, 'max_batch': BATCH, 'checks': checks, 'timings': timings,
              'final_database_sha256': digest, 'revisions_outbox': list(totals())}
    report['probe_sha256'] = hashlib.sha256(a.probe.read_bytes()).hexdigest()
    (folder / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding='utf-8')
    print('bulk organization checks passed: %d' % len(checks))


if __name__ == '__main__':
    main()
