# SPDX-License-Identifier: MIT
"""Actions-only GTK collections, native producer races and durable recovery."""
import argparse
import configparser
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
from check_linux_host import Session, command


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('payload', 'command-consumer', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    folder = args.output.resolve();folder.mkdir()
    source = folder / 'Collection original.txt'
    original = ('Native shelf and collection membership.\n' * 300).encode()
    source.write_bytes(original)
    catalog = folder / 'profile/library.sqlite.product.sqlite'
    journal = Path(str(catalog) + '.commands.pending')
    host = Session((args.payload / 'bin/exreader-linux').resolve(), (args.payload / 'Reader.otf').resolve(), folder)
    checks, shots, native, recovery_evidence = [], [], [], []
    report = {'accepted': False, 'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
              'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'checks': checks, 'screenshots': shots,
              'scope': 'GTK shelves children tags series bounded membership and explicit recovery',
              'group_page_limit': 50, 'member_page_limit': 50, 'main_shelf_cache_limit': 150,
              'sdk_changed': False, 'schema_changed': False, 'sync_ui_accepted': False,
              'recovery_observations': recovery_evidence, 'performance_accepted': False, 'complete_product': False}

    def sql(query, values=()):
        with sqlite3.connect(catalog) as db:
            return db.execute(query, values).fetchall()

    def counts():
        return sql('SELECT (SELECT count(*) FROM reader_revisions),(SELECT count(*) FROM reader_outbox)')[0]

    def observation():
        state = configparser.ConfigParser();state.read(host.observe)
        return dict(state['collections']) if state.has_section('collections') else {}

    def ready(predicate=lambda state: True):
        try:
            host.wait(lambda state: not state.get('shelf_loading') and not state.get('shelf_restoring')
                      and predicate(observation()), timeout=60)
        except TimeoutError as error:
            raise TimeoutError(str(error) + '; collections=' + repr(observation())) from error
        return observation()

    def window(title, present=True):
        end = time.monotonic() + 35
        while time.monotonic() < end:
            assert host.process.poll() is None, 'actual host exited'
            found = subprocess.run(['xdotool', 'search', '--onlyvisible', '--all', '--pid', str(host.process.pid),
                                    '--name', '^' + re.escape(title) + '$'], text=True, capture_output=True, timeout=5)
            if bool(found.stdout.strip()) == present:
                if present:
                    value = found.stdout.splitlines()[-1]
                    command('xdotool', 'windowactivate', '--sync', value)
                    return value
                return None
            time.sleep(.1)
        raise TimeoutError('Native dialog visibility differs: ' + title + ' ' + repr(observation()))

    def record(name):
        assert name not in checks
        assert host.read().get('books', 0) <= 150 and host.read().get('shelf_max_cached', 0) <= 150
        current = observation()
        assert int(current.get('group_count', 0)) <= 50 and int(current.get('member_count', 0)) <= 50
        checks.append(name);print(json.dumps({'check': name, 'pass': True}), flush=True)

    def shot(name, target):
        path = folder / (name + '.png');command('import', '-window', target, path);shots.append(path.name)

    def open_collections(menu=False):
        command('xdotool', 'windowactivate', '--sync', host.window);host.key('F2')
        if menu:
            host.key('alt+m', 'Return')
        else:
            host.key('ctrl+shift+c')
        return window('Library collections')

    def close_collections():
        window('Library collections');host.key('alt+F4');window('Library collections', False)

    def kind(value):
        window('Library collections');host.key('alt+t', 'Home');ready(lambda state: state['kind'] == '0')
        for index in range(value):
            host.key('Down');ready(lambda state: state['kind'] == str(index + 1))
        host.key('Tab');ready(lambda state: state['kind'] == str(value))

    def field(mnemonic, value):
        host.key('alt+' + mnemonic, 'ctrl+a');host.paste(str(value))

    def save_editor(title='Collection details'):
        host.key('Return');window(title, False);ready(lambda state: state['editor'] == '0')

    def group(name, position=0):
        host.key('alt+n');window('Collection details');field('n', name)
        if observation()['kind'] == '0':
            field('p', position)
        before = counts();save_editor()
        assert counts() == (before[0] + 1, before[1] + 1)
        return observation()['selected_id']

    def choose_group(key):
        current = ready();ids = current['group_ids'].split(',')
        assert key in ids, (key, current)
        host.key('alt+g', 'Home');ready()
        for _ in range(ids.index(key)):
            host.key('Down');ready()
        return ready(lambda state: state['selected_id'] == key)

    def member_editor(action, ordinal=None):
        host.key('alt+' + action);window('Book classification')
        if ordinal is not None:
            field('p', ordinal)
        save_editor('Book classification')

    def text(value):
        raw = value.encode();path = folder / (hashlib.sha256(raw).hexdigest() + '.txt');path.write_bytes(raw);return path

    def invoke(action, *values):
        result = subprocess.run([str(args.command_consumer.resolve()), action, str(catalog), *map(str, values)],
                                text=True, capture_output=True, encoding='utf-8', timeout=60)
        assert result.returncode == 0, result.stderr
        value = json.loads(result.stdout);native.append({'action': action, **value})
        assert value['status'] == 0, value
        return value

    def head(kind_name, key):
        return sql('SELECT revision_id FROM reader_revisions WHERE entity_kind=? AND entity_key=? ORDER BY rowid DESC LIMIT 1',
                   (kind_name, key))[0][0]

    def native_group(kind_value, name, key='-', parents='-', op=0, parent='-', ordinal=0):
        return invoke('group', '-', parents, kind_value, op, key, text(name), parent, ordinal)

    def kill():
        host.process.kill();host.process.wait(timeout=15);assert host.process.returncode != 0;host.log.close()

    try:
        host.launch();host.dialog(source);host.wait(lambda state: state['book'] > 0 and state['books'] == 1)
        sdk_id = host.read()['book'];host.close()
        sql("UPDATE reader_books SET title='Legacy collection title',author='旧作者',favorite=1")
        book_key = sql('SELECT book_key FROM reader_books')[0][0]
        assert book_key == 'txt:' + hashlib.sha256(original).hexdigest() and counts() == (0, 0)
        host.launch();organizer = open_collections(menu=True);ready(lambda state: state['visible'] == '1')
        shot('01-native-organizer', organizer)
        record('native_more_menu_opens_bounded_shelves_tags_series_organizer')

        parent = group('Root 书架😀', 7)
        assert sql('SELECT name,ordinal,parent_id FROM reader_shelves WHERE shelf_id=?', (parent,)) == [('Root 书架😀', 7, None)]
        record('native_group_save_adds_one_revision_and_outbox_row_with_exact_unicode')
        host.key('alt+r');window('Collection details');field('n', 'Renamed root');field('p', 1);save_editor()
        assert sql('SELECT name,ordinal FROM reader_shelves WHERE shelf_id=?', (parent,)) == [('Renamed root', 1)]
        record('native_rename_and_group_position_preserve_the_group_identity')
        before = counts();host.key('alt+n');window('Collection details');field('n', 'Cancelled group')
        host.key('Escape');window('Collection details', False)
        assert ready()['selected_id'] == parent and counts() == before and not journal.exists()
        assert not sql("SELECT * FROM reader_shelves WHERE name='Cancelled group'")
        record('native_cancel_changes_no_metadata_history_outbox_or_pending_intent')
        host.key('alt+e');ready(lambda state: state['parent_id'] == parent)
        child = group('Child shelf', 3)
        assert sql('SELECT parent_id,ordinal FROM reader_shelves WHERE shelf_id=?', (child,)) == [(parent, 3)]
        record('enter_shelf_creates_a_child_with_explicit_parent_and_position')

        before = counts();host.key('alt+a');window('Book classification');ready(lambda state: state['editor'] == '1')
        assert counts() == (before[0] + 1, before[1] + 1)
        assert sql('SELECT title,author,favorite FROM reader_books WHERE book_key=?', (book_key,)) == [('Legacy collection title', '旧作者', 1)]
        assert sql('SELECT sdk_book_id FROM reader_local_books WHERE book_key=?', (book_key,)) == [(sdk_id,)]
        bootstrap = json.loads(sql("SELECT body_json FROM reader_revisions WHERE entity_kind='book'")[0][0])
        assert bootstrap['payload']['title'] == 'Legacy collection title' and bootstrap['payload']['favorite'] is True
        record('first_membership_verifies_sdk_original_and_bootstraps_preserved_legacy_fields')
        host.key('Escape');window('Book classification', False)
        assert counts() == (before[0] + 1, before[1] + 1) and not sql('SELECT * FROM reader_book_shelves') and not journal.exists()
        record('cancel_after_explicit_original_verification_keeps_book_history_without_classifying_it')
        member_editor('a', 5)
        assert counts() == (before[0] + 2, before[1] + 2)
        assert sql('SELECT ordinal FROM reader_book_shelves WHERE shelf_id=? AND book_key=?', (child, book_key)) == [(5,)]
        current = ready(lambda state: state['member_count'] == '1')
        assert current['member_keys'] == book_key and current['member_ordinals'] == '5'
        record('membership_uses_stable_global_key_while_local_sdk_mapping_is_preserved')
        host.key('alt+b', 'Home');ready(lambda state: state['selected_member_key'] == book_key and state['member_position_enabled'] == '1')
        member_editor('p', 2)
        assert sql('SELECT ordinal FROM reader_book_shelves WHERE shelf_id=? AND book_key=?', (child, book_key)) == [(2,)]
        record('native_membership_position_updates_order_without_recreating_the_book')
        host.key('alt+b', 'Home');member_editor('i');assert not sql('SELECT * FROM reader_book_shelves WHERE shelf_id=?', (child,))
        record('explicit_remove_membership_keeps_the_original_and_book_history')
        member_editor('a', 2)
        assert ready()['member_keys'] == book_key and ready()['member_ordinals'] == '2'
        assert sql('SELECT count(*) FROM reader_books') == [(1,)]
        record('adding_a_removed_membership_explicitly_restores_its_tombstone_history')

        host.key('alt+d');window('Collection details');save_editor()
        assert sql('SELECT deleted FROM reader_shelves WHERE shelf_id=?', (child,)) == [(1,)]
        host.key('alt+u');ready(lambda state: not state['parent_id'])
        choose_group(parent);host.key('alt+d');window('Collection details');save_editor()
        before = counts();host.key('alt+m');ready(lambda state: state['removed'] == '1')
        choose_group(child);host.key('alt+s');dependency = window('Collection details')
        current = ready(lambda state: state['editor'] == '1')
        assert current['editor_accept'] == '0' and current['editor_parent'] == parent and counts() == before
        shot('02-restore-parent-required', dependency)
        record('removed_child_restore_refuses_deleted_parent_without_writing_anything')
        host.key('alt+v');window('Collection details', False);ready(lambda state: state['selected_id'] == parent)
        host.key('alt+s');window('Collection details');save_editor()
        choose_group(child);host.key('alt+s');window('Collection details');save_editor()
        assert sql('SELECT deleted FROM reader_shelves ORDER BY shelf_id') == [(0,), (0,)]
        host.key('alt+m');ready(lambda state: state['removed'] == '0')
        choose_group(parent);host.key('alt+e');ready(lambda state: state['parent_id'] == parent and state['member_keys'] == book_key)
        record('view_parent_then_explicit_restore_preserves_child_hierarchy_and_membership')

        kind(1);tag = group('Tag 😀');member_editor('a')
        assert sql('SELECT tag_id,book_key FROM reader_book_tags') == [(tag, book_key)]
        record('native_tag_group_and_membership_use_the_same_typed_owner')
        kind(2);series = group('Series books');member_editor('a', 9)
        host.key('alt+b', 'Home');member_editor('p', 4)
        assert sql('SELECT series_id,book_key,ordinal FROM reader_book_series') == [(series, book_key, 4)]
        shot('03-series-order', window('Library collections'))
        record('native_series_membership_accepts_and_edits_the_reading_order')

        kind(1);choose_group(tag);host.key('alt+r');dialog = window('Collection details');field('n', 'Barrier rename')
        lock = sqlite3.connect(catalog)
        try:
            lock.execute('BEGIN IMMEDIATE');command('xdotool', 'key', '--clearmodifiers', 'Return')
            end = time.monotonic() + 4
            while not journal.exists():
                assert time.monotonic() < end, 'typed intent was not durably staged';time.sleep(.02)
            assert host.read()['busy'] == 1
            command('xdotool', 'key', '--clearmodifiers', 'alt+F4');window('Collection details')
            assert host.process.poll() is None
        finally:
            lock.rollback();lock.close()
        window('Collection details', False);ready()
        assert sql('SELECT name FROM reader_tags WHERE tag_id=?', (tag,)) == [('Barrier rename',)] and not journal.exists()
        record('actual_native_window_close_waits_for_the_collection_commit_barrier')

        sql("CREATE TRIGGER collection_test_refusal BEFORE UPDATE ON reader_tags BEGIN SELECT RAISE(ABORT,'test collection refusal');END")
        before = counts();host.key('alt+r');window('Collection details');field('n', 'Recovered tag');host.key('Return')
        recovery = window('Recover collection change');pending = hashlib.sha256(journal.read_bytes()).hexdigest()
        (folder / 'pending-refused.bin').write_bytes(journal.read_bytes())
        recovery_evidence.append({'stage': 'refused', 'sha256': pending, 'history_outbox': counts()})
        assert counts() == before and sql('SELECT name FROM reader_tags WHERE tag_id=?', (tag,)) == [('Barrier rename',)]
        shot('04-durable-refusal', recovery)
        record('actual_product_refusal_keeps_pending_bytes_and_zero_partial_effects')
        kill();assert hashlib.sha256(journal.read_bytes()).hexdigest() == pending
        recovery_evidence.append({'stage': 'after-process-death', 'sha256': hashlib.sha256(journal.read_bytes()).hexdigest(), 'history_outbox': counts()})
        record('actual_process_death_preserves_the_original_pending_collection_intent')
        sql('DROP TRIGGER collection_test_refusal');host.launch();open_collections();window('Recover collection change')
        assert hashlib.sha256(journal.read_bytes()).hexdigest() == pending and counts() == before
        recovery_evidence.append({'stage': 'fresh-host-before-retry', 'sha256': hashlib.sha256(journal.read_bytes()).hexdigest(), 'history_outbox': counts()})
        record('fresh_host_presents_recovery_without_automatic_rebinding_or_resubmission')
        host.key('alt+r');window('Recover collection change', False);ready()
        assert counts() == (before[0] + 1, before[1] + 1) and not journal.exists()
        assert sql('SELECT name FROM reader_tags WHERE tag_id=?', (tag,)) == [('Recovered tag',)]
        record('explicit_native_retry_commits_the_same_intent_once')

        kind(1);choose_group(tag);host.key('alt+r');window('Collection details');field('n', 'Stale UI name')
        external = native_group(1, 'Independent writer', tag, head('tag', tag));before = counts()
        host.key('Return');recovery = window('Recover collection change')
        assert counts() == before and sql('SELECT name FROM reader_tags WHERE tag_id=?', (tag,)) == [('Independent writer',)]
        assert host.read()['error'] != 0 and external['id'] == head('tag', tag)
        shot('05-stale-head-refused', recovery)
        record('actual_independent_native_writer_advances_heads_and_stale_gui_cannot_overwrite')
        host.key('alt+d');window('Recover collection change', False);ready()
        assert counts() == before and not journal.exists()
        record('explicit_discard_removes_only_uncommitted_pending_intent')

        seeded = [native_group(1, 'Paged tag %02d' % i) for i in range(55)]
        kind(0);kind(1)
        expected = [value[0] for value in sql('SELECT tag_id FROM reader_tags WHERE deleted=0 ORDER BY tag_id')]
        first = ready(lambda state: state['group_count'] == '50' and state['group_after'] == '1')
        assert first['group_ids'].split(',') == expected[:50] and first['group_before'] == '0'
        host.key('ctrl+Page_Down');last = ready(lambda state: state['group_after'] == '0')
        assert last['group_ids'].split(',') == expected[50:] and last['group_before'] == '1'
        host.key('ctrl+Page_Up');assert ready()['group_ids'].split(',') == expected[:50]
        record('actual_group_list_pages_forward_and_reverse_with_a_fifty_row_bound')
        close_collections();host.close()
        for item in seeded:
            native_group(1, '-', item['key'], item['id'], op=1)
        host.launch();open_collections();kind(1);host.key('alt+m')
        removed = sorted(item['key'] for item in seeded)
        first = ready(lambda state: state['removed'] == '1' and state['group_count'] == '50')
        assert first['group_ids'].split(',') == removed[:50] and first['group_after'] == '1'
        host.key('ctrl+Page_Down');assert ready(lambda state: state['group_after'] == '0')['group_ids'].split(',') == removed[50:]
        host.key('ctrl+Page_Up');assert ready()['group_ids'].split(',') == removed[:50]
        historical = removed[0];choose_group(historical);host.key('alt+s');window('Collection details');save_editor()
        assert sql('SELECT deleted FROM reader_tags WHERE tag_id=?', (historical,)) == [(0,)]
        record('removed_view_pages_historical_other_writer_tombstones_after_restart_and_restores')

        for i in range(55):
            raw = ('Cloud-only collection fixture %d' % i).encode();sha = hashlib.sha256(raw).hexdigest();key = 'txt:' + sha
            invoke('book', '-', '-', 0, key, 'txt', sha, len(raw), 0, text('Member %02d' % i), text('Fixture'), text('Member %02d' % i))
            invoke('member', '-', '-', 2, 0, series, key, i + 10)
        kind(2)
        # Switching kind also exits Removed explicitly; its toggle is global.
        if observation()['removed'] == '1':
            host.key('alt+m');ready(lambda state: state['removed'] == '0')
        choose_group(series)
        expected = sql('SELECT b.book_key,m.ordinal FROM reader_book_series m JOIN reader_books b USING(book_key) WHERE m.series_id=? ORDER BY m.ordinal,b.book_key', (series,))
        first = ready(lambda state: state['member_count'] == '50' and state['member_after'] == '1')
        assert first['member_keys'].split(',') == [key for key, _ in expected[:50]]
        assert list(map(int, first['member_ordinals'].split(','))) == [number for _, number in expected[:50]]
        host.key('alt+Right');last = ready(lambda state: state['member_after'] == '0')
        assert last['member_keys'].split(',') == [key for key, _ in expected[50:]] and last['member_before'] == '1'
        host.key('alt+Left');assert ready()['member_keys'].split(',') == [key for key, _ in expected[:50]]
        shot('06-bounded-member-page', window('Library collections'))
        record('actual_series_member_list_pages_both_directions_preserving_order_and_fifty_row_bound')

        host.key('alt+b', 'Home', 'Return');window('Library collections', False)
        host.wait(lambda state: state['reader_visible'] == 1 and state['book'] == sdk_id and state['error'] == 0)
        shot('07-original-opened-from-membership', host.window)
        assert sql('SELECT sdk_book_id FROM reader_local_books WHERE book_key=?', (book_key,)) == [(sdk_id,)]
        assert all('sdk_book_id' not in raw for raw, in sql('SELECT body_json FROM reader_revisions'))
        record('actual_member_activation_opens_downloaded_original_and_wire_keeps_local_ids_out')
        host.close();host.launch();open_collections();kind(2);choose_group(series)
        assert int(ready()['member_count']) == 50 and counts()[0] == counts()[1]
        close_collections();host.key('F2', 'Return');host.wait(lambda state: state['book'] == sdk_id and state['reader_visible'] == 1)
        record('normal_restart_preserves_collections_memberships_and_the_main_native_reading_path')
        host.close()
        assert len(checks) == 27, checks
        report['accepted'] = True
    finally:
        if not report['accepted']:
            print(json.dumps({'failed_collections_observation': observation(), 'host': host.read()}, ensure_ascii=False), flush=True)
            if host.process and host.process.poll() is None:
                shot('failure-native-desktop', 'root')
        if host.process and host.process.poll() is None:
            host.process.kill();host.process.wait(timeout=15)
        if host.log and not host.log.closed:
            host.log.close()
        (folder / 'native-writer-results.json').write_text(json.dumps(native, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        report['count'] = len(checks)
        report['program_sha256'] = hashlib.sha256(host.binary.read_bytes()).hexdigest()
        report['files'] = {str(path.relative_to(folder)): hashlib.sha256(path.read_bytes()).hexdigest()
                           for path in sorted(folder.rglob('*')) if path.is_file()}
        (folder / 'collections-ui.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({'accepted': report['accepted'], 'count': len(checks), 'source_sha': report['source_sha'],
                          'run_id': report['run_id'], 'attempt': report['attempt'], 'program_sha256': report['program_sha256'],
                          'report_sha256': hashlib.sha256((folder / 'collections-ui.json').read_bytes()).hexdigest(),
                          'screenshots': {name: report['files'][name] for name in shots}}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
