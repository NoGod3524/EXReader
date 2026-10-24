# SPDX-License-Identifier: MIT
"""Actions-only v2 reading transactions with an actual legacy validator."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import time

BOOK = 'txt:' + 'a' * 64
ANNOTATION = BOOK + ':' + 'b' * 32


def main():
    p = argparse.ArgumentParser()
    for name in ('consumer', 'legacy-consumer', 'output'): p.add_argument('--' + name, required=True, type=Path)
    a = p.parse_args(); assert os.environ.get('GITHUB_ACTIONS') == 'true'
    root = a.output.resolve(); root.mkdir(parents=True)
    db, receiver, legacy = root / 'local.sqlite', root / 'receiver.sqlite', root / 'legacy.sqlite'
    checks = []
    def record(name):
        assert name not in checks; checks.append(name); print('PASS ' + name, flush=True)
    def encode(v): return json.dumps(v, ensure_ascii=False, separators=(',', ':')).encode()
    def wire(v):
        path = root / (v['id'] + '-' + hashlib.sha256(encode(v)).hexdigest()[:8] + '.json'); path.write_bytes(encode(v)); return path
    def call(action, database, *args, expected=0, old=False):
        exe = a.legacy_consumer if old else a.consumer
        done = subprocess.run([str(exe.resolve()), action, str(database), *map(str, args)], capture_output=True, text=True, encoding='utf-8', timeout=30)
        assert done.returncode == 0, (action, done.stderr)
        value = json.loads(done.stdout); assert value['status'] == expected, (action, expected, value)
        return value
    def revision(n=1, kind='annotation', version=2, mode='reflow_global'):
        book = ('epub:' if mode == 'epub_chapter' else 'pdf:' if mode == 'fixed_page' else 'txt:') + 'a' * 64
        selector = {'exact': '', 'prefix': '前文', 'suffix': '后文', 'start': 6, 'end': 6}
        if mode == 'reflow_global' and version == 2: selector['chapter'] = None
        location = {'mode': mode, 'anchor_version': version, 'parser_version': '3.40.0', 'selector': selector}
        if mode == 'epub_chapter':
            location['part_path'] = 'OPS/a.xhtml'
            if version == 2: location['part'] = 2
        if mode == 'fixed_page': location.update(page_id='page-1', page=0)
        payload = {'book_key': book, 'location': location}
        if kind == 'annotation': payload.update(annotation_id='b' * 32, text='书签')
        return {'version': 1, 'id': '%032x' % n, 'entity_kind': kind, 'entity_key': book + (':' + 'b' * 32 if kind == 'annotation' else ''),
                'operation': 'put', 'location_kind': mode, 'parents': [], 'payload': payload}
    def validate(value, expected=0, old=False):
        return call('validate', legacy if old else db, wire(value), expected=expected, old=old)
    def receive(database, value): return call('receive', database, wire(value), hashlib.sha256(encode(value)).hexdigest())
    def commit(value, expected_heads=(), expected=0):
        return call('reading-local', db, wire(value), ','.join(expected_heads) or '-', '-', expected=expected)
    def selected(database, value, expected=0):
        target = root / ('selected-' + value['id'] + '.json')
        if target.exists(): target.unlink()
        result = call('selected', database, value['entity_kind'], value['entity_key'], target, expected=expected)
        if expected == 0: assert target.read_bytes() == encode(value)
        else: assert not target.exists()
        return result
    def counts(database):
        with sqlite3.connect(database) as c: return c.execute('SELECT (SELECT count(*) FROM reader_revisions),(SELECT count(*) FROM reader_outbox)').fetchone()

    for mode in ('reflow_global', 'epub_chapter', 'fixed_page'):
        for kind in ('progress', 'annotation'):
            value = revision(kind=kind, mode=mode); validate(value); validate(value, 4, old=True)
            call('receive', legacy, wire(value), hashlib.sha256(encode(value)).hexdigest(), expected=4, old=True)
    assert counts(legacy) == (0, 0)
    record('three_v2_point_modes_validate_and_actual_old_client_refuses_every_mode')
    value = revision(mode='fixed_page'); value['payload']['location']['selector'].update(prefix='', suffix='', start=0, end=0)
    validate(value); record('textless_fixed_page_zero_point_is_representable')
    value = revision(); value['payload']['location']['selector']['chapter'] = 'OPS/b.xhtml'; validate(value)
    record('global_chapter_scope_is_explicit_and_preserved')
    for mode in ('reflow_global', 'epub_chapter', 'fixed_page'):
        value = revision(mode=mode); selector = value['payload']['location']['selector']; selector.update(exact='读🙂', start=3, end=10)
        validate(value); validate(value, 4, old=True)
    record('nonempty_quote_span_uses_utf8_bytes_in_all_three_modes')
    invalid = []
    def bad(name, change, expected=4):
        value = revision(); change(value); invalid.append((name, value, expected))
    bad('point_wrong_end', lambda v: v['payload']['location']['selector'].update(end=7))
    bad('quote_wrong_span', lambda v: v['payload']['location']['selector'].update(exact='读', end=7))
    bad('missing_chapter', lambda v: v['payload']['location']['selector'].pop('chapter'))
    bad('chapter_wrong_type', lambda v: v['payload']['location']['selector'].update(chapter=2))
    bad('chapter_empty_string', lambda v: v['payload']['location']['selector'].update(chapter=''))
    bad('unknown_selector_field', lambda v: v['payload']['location']['selector'].update(extra=True))
    bad('unknown_version', lambda v: v['payload']['location'].update(anchor_version=3))
    bad('nul_quote', lambda v: v['payload']['location']['selector'].update(exact='\0', end=7))
    bad('context_bytes', lambda v: v['payload']['location']['selector'].update(prefix='读' * 43), 5)
    bad('context_scalars', lambda v: v['payload']['location']['selector'].update(prefix='x' * 33), 5)
    for name, value, expected in invalid: validate(value, expected); record(name + '_refused')
    value = revision(kind='progress'); value['payload']['location']['selector'].update(exact='x', end=7)
    validate(value, 4); record('v2_progress_cannot_be_a_highlight')
    value = revision(mode='epub_chapter'); value['payload']['location'].pop('part'); validate(value, 4)
    value = revision(mode='epub_chapter'); value['payload']['location']['part'] = -1; validate(value, 4)
    value['payload']['location']['part'] = 1 << 63; validate(value, 4)
    record('epub_index_is_required_nonnegative_and_storage_bounded')
    value = revision(version=1); value['payload']['location']['selector'].update(exact='v1', end=8, prefix='x' * 200)
    validate(value); validate(value, old=True)
    v1_copy = root / 'v1-copy.sqlite'
    receive(v1_copy, value); selected(v1_copy, value)
    record('v1_positive_bytes_and_its_original_context_limit_are_unchanged')
    value = revision(version=1); validate(value, 4); validate(value, 4, old=True)
    record('v1_empty_quote_remains_refused_by_both_clients')
    value = revision(); commit(value, expected=12); record('local_reading_requires_retained_verified_book_history')
    book = {'version': 1, 'id': '%032x' % 100, 'entity_kind': 'book', 'entity_key': BOOK, 'operation': 'put', 'location_kind': 'none', 'parents': [],
            'payload': {'format': 'txt', 'source_sha256': 'a' * 64, 'source_bytes': 100, 'title': '书', 'author': '', 'favorite': False}}
    receive(db, book); receive(receiver, book)
    value = revision(); result = commit(value); assert result['created'] == 1
    receive(receiver, value); selected(receiver, value)
    record('reading_history_and_outbox_commit_then_other_device_selects_exact_bytes')
    edited = revision(2); edited['parents'] = [value['id']]; edited['payload']['text'] = 'edited'
    before = counts(db); commit(edited, expected=10); assert counts(db) == before
    record('stale_or_incomplete_observed_heads_refuse_without_any_write')
    commit(edited, [value['id']]); selected(db, edited)
    result = commit(value); assert result['created'] == 0; selected(db, edited)
    record('exact_old_retry_cannot_requeue_or_overwrite_the_new_head')
    other = copy.deepcopy(edited); other['id'] = '%032x' % 3; other['payload']['text'] = 'other device'
    receive(db, other); result = selected(db, edited, 10); assert result['selection_kind'] == 2
    record('concurrent_reading_heads_remain_explicit_and_unselected')
    merged = revision(4); merged['parents'] = [edited['id'], other['id']]
    commit(merged, merged['parents']); selected(db, merged)
    record('explicit_complete_head_merge_restores_a_safe_single_global_record')
    deleted = revision(5); deleted.update(parents=[merged['id']], operation='delete', payload=None)
    commit(deleted, deleted['parents']); selected(db, deleted)
    resurrect = revision(6); resurrect['parents'] = [deleted['id']]
    before = counts(db); commit(resurrect, resurrect['parents'], expected=10); assert counts(db) == before
    restored = revision(7); restored.update(parents=[deleted['id']], operation='restore')
    commit(restored, restored['parents']); selected(db, restored)
    record('delete_and_explicit_restore_preserve_one_global_identity')
    child = revision(9); child['parents'] = ['%032x' % 8]
    receive(receiver, child); selected(receiver, child, 10)
    parent = revision(8); parent['parents'] = [value['id']]
    receive(receiver, parent); selected(receiver, child)
    record('out_of_order_offline_history_blocks_until_its_parents_arrive')
    crash = revision(10); crash['parents'] = [restored['id']]
    marker = root / 'committed-marker'
    process = subprocess.Popen([str(a.consumer.resolve()), 'crash-reading-after-commit', str(db), str(wire(crash)), restored['id'], '-', str(marker)],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        deadline = time.monotonic() + 30
        while not marker.exists() and process.poll() is None and time.monotonic() < deadline: time.sleep(.02)
        assert marker.exists() and process.poll() is None
    finally:
        if process.poll() is None: process.kill()
        process.wait(timeout=5)
    selected(db, crash); before = counts(db); commit(crash, crash['parents']); assert counts(db) == before
    record('actual_kill_after_reading_commit_reopens_and_retries_without_duplicate')
    before = counts(db); commit(book, expected=1); assert counts(db) == before
    record('reading_transaction_cannot_mutate_book_metadata')
    assert len(checks) == 28
    report = {'accepted': True, 'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'], 'attempt': os.environ['GITHUB_RUN_ATTEMPT'],
              'checks': checks, 'count': len(checks), 'consumer_sha256': hashlib.sha256(a.consumer.read_bytes()).hexdigest(),
              'legacy_consumer_sha256': hashlib.sha256(a.legacy_consumer.read_bytes()).hexdigest(),
              'schema_changed': False, 'sdk_changed': False, 'sdk_resolution_accepted': False, 'host_ui_accepted': False}
    (root / 'result.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8'); print(json.dumps(report), flush=True)


if __name__ == '__main__': main()
