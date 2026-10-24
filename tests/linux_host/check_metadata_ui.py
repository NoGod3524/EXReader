# SPDX-License-Identifier: MIT
"""Actual GTK book edits, retained intent recovery, and a concurrent native writer."""
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

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
from check_linux_host import Session, command


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--payload', type=Path, required=True)
    parser.add_argument('--command-consumer', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    folder = args.output.resolve();folder.mkdir()
    source = folder / 'Original title.txt'
    original = ('Native library metadata and durable commands.\n' * 200).encode()
    source.write_bytes(original)
    catalog = folder / 'profile/library.sqlite.product.sqlite'
    journal = Path(str(catalog) + '.commands.pending')
    host = Session((args.payload / 'bin/exreader-linux').resolve(), (args.payload / 'Reader.otf').resolve(), folder)
    checks, shots = [], []

    def record(name):
        assert name not in checks
        checks.append(name);print(json.dumps({'check': name, 'pass': True}), flush=True)

    def sql(query, values=()):
        with sqlite3.connect(catalog) as db:
            return db.execute(query, values).fetchall()

    def counts():
        return sql('SELECT (SELECT count(*) FROM reader_revisions),(SELECT count(*) FROM reader_outbox)')[0]

    def book():
        return sql('SELECT book_key,title,author,sort_title,favorite,source_bytes FROM reader_books')[0]

    def window(title, present=True):
        end = time.monotonic() + 35
        while time.monotonic() < end:
            assert host.process.poll() is None, 'actual host exited'
            result = subprocess.run(['xdotool', 'search', '--onlyvisible', '--all', '--pid', str(host.process.pid),
                                     '--name', '^' + title + '$'], text=True, capture_output=True, timeout=5)
            if bool(result.stdout.strip()) == present:
                if present:
                    value = result.stdout.splitlines()[-1]
                    command('xdotool', 'windowactivate', '--sync', value)
                    return value
                return None
            time.sleep(.1)
        raise TimeoutError('Native dialog visibility differs: ' + title)

    def shot(name, target):
        path = folder / (name + '.png');command('import', '-window', target, path);shots.append(path.name)

    def edit():
        command('xdotool', 'windowactivate', '--sync', host.window)
        host.key('F2', 'ctrl+e');return window('Book details')

    def field(mnemonic, value):
        host.key('alt+' + mnemonic, 'ctrl+a');host.paste(value)

    def title_value():
        host.key('alt+t', 'ctrl+a', 'ctrl+c')
        return command('xclip', '-selection', 'clipboard', '-o')

    def set_values(title, author=None, toggle=False):
        field('t', title)
        if author is not None:
            field('a', author)
        if toggle:
            host.key('alt+f')

    def saved_with_window_close_barrier(dialog):
        lock = sqlite3.connect(catalog)
        try:
            lock.execute('BEGIN IMMEDIATE')
            host.key('alt+t')
            command('xdotool', 'key', '--clearmodifiers', 'Return')
            end = time.monotonic() + 3
            while not journal.exists():
                assert time.monotonic() < end, 'typed intent did not reach durable staging'
                time.sleep(.02)
            assert host.read()['busy'] == 1
            # windowclose calls XDestroyWindow and bypasses WM_DELETE_WINDOW.
            # Use the same window-manager shortcut a user presses instead.
            command('xdotool', 'key', '--clearmodifiers', 'alt+F4')
            window('Book details')
            assert host.process.poll() is None
        finally:
            lock.rollback();lock.close()
        window('Book details', False);host.wait(lambda s: s['error'] == 0)

    def kill():
        host.process.kill();host.process.wait(timeout=15)
        assert host.process.returncode != 0
        host.log.close()

    try:
        host.launch();host.dialog(source);host.wait(lambda s: s['book'] > 0 and s['books'] == 1)
        sdk_id = host.read()['book'];host.close()
        sql("UPDATE reader_books SET title='Legacy edited title',author='旧作者',sort_title='Legacy edited title',favorite=1")
        key = book()[0]
        assert key == 'txt:' + hashlib.sha256(original).hexdigest() and book()[5] == len(original)
        host.launch();dialog = edit()
        assert title_value() == 'Legacy edited title' and counts() == (1, 1)
        initial_id, initial_wire = sql('SELECT revision_id,body_json FROM reader_revisions')[0]
        payload = json.loads(initial_wire)['payload']
        assert payload['title'] == 'Legacy edited title' and payload['author'] == '旧作者' and payload['favorite'] is True
        shot('01-legacy-preserved', dialog)
        host.key('Escape');window('Book details', False)
        record('actual_editor_bootstraps_verified_original_preserving_existing_product_edits')

        dialog = edit();set_values('Cafe\u0301 书名😀', '作者 😀', toggle=True);saved_with_window_close_barrier(dialog)
        record('native_dialog_window_close_waits_for_the_metadata_commit_barrier')
        row = book();assert row[1:5] == ('Cafe\u0301 书名😀', '作者 😀', unicodedata.normalize('NFC', 'Cafe\u0301 书名😀'), 0)
        record('native_entries_and_favorite_control_commit_exact_unicode_metadata')
        assert counts() == (2, 2)
        wires = [json.loads(raw) for raw, in sql('SELECT body_json FROM reader_revisions')]
        edited = next(value for value in wires if value['id'] != initial_id)
        assert edited['parents'] == [initial_id] and edited['payload']['title'] == row[1]
        assert edited['payload']['author'] == row[2] and edited['payload']['favorite'] is False
        assert all('sdk_book_id' not in raw for raw, in sql('SELECT body_json FROM reader_revisions'))
        record('one_user_save_has_one_atomic_metadata_history_and_outbox_transaction')
        assert sql('SELECT sdk_book_id FROM reader_local_books') == [(sdk_id,)] and row[0] == key and row[5] == len(original)
        record('editing_keeps_original_identity_and_device_local_mapping')

        dialog = edit();assert title_value() == row[1];set_values('Cancelled title');host.key('Escape')
        window('Book details', False);assert book() == row and counts() == (2, 2) and not journal.exists()
        record('native_cancel_leaves_metadata_history_and_outbox_unchanged')

        sql("CREATE TRIGGER metadata_test_failure BEFORE UPDATE ON reader_books BEGIN SELECT RAISE(ABORT,'test transaction refusal');END")
        dialog = edit();set_values('Recovered 书名😀');host.key('Return');recovery = window('Recover book edit')
        assert book() == row and counts() == (2, 2) and journal.is_file()
        pending = hashlib.sha256(journal.read_bytes()).hexdigest();shot('02-pending-refusal', recovery)
        record('actual_product_refusal_keeps_full_intent_and_zero_partial_transaction_effects')
        kill();assert hashlib.sha256(journal.read_bytes()).hexdigest() == pending
        record('actual_host_process_death_preserves_the_pending_intent')
        sql('DROP TRIGGER metadata_test_failure');host.launch();host.key('F2', 'ctrl+e');recovery = window('Recover book edit')
        assert hashlib.sha256(journal.read_bytes()).hexdigest() == pending and counts() == (2, 2)
        record('fresh_host_shows_recovery_without_rewriting_or_resubmitting_pending_bytes')
        host.key('alt+r');window('Recover book edit', False);host.wait(lambda s: s['error'] == 0)
        assert book()[1] == 'Recovered 书名😀' and counts() == (3, 3) and not journal.exists()
        record('native_retry_recovers_one_exact_original_intent_into_one_revision_and_outbox_row')
        host.close();host.launch();dialog = edit();assert title_value() == 'Recovered 书名😀' and counts() == (3, 3)
        host.key('Escape');window('Book details', False)
        record('normal_restart_does_not_duplicate_a_completed_edit')

        dialog = edit();set_values('Stale local edit')
        head = sql('SELECT revision_id FROM reader_revisions WHERE rowid=(SELECT max(rowid) FROM reader_revisions)')[0][0]
        title, author = folder / 'external-title.txt', folder / 'external-author.txt'
        title.write_text('External native edit', encoding='utf-8');author.write_text('Native writer', encoding='utf-8')
        result = subprocess.run([str(args.command_consumer.resolve()), 'book', str(catalog), 'f' * 32, head, '0', key,
                                 'txt', key.split(':')[1], str(len(original)), '0', str(title), str(author), str(title)],
                                text=True, capture_output=True, encoding='utf-8', timeout=60)
        (folder / 'external-native-writer.log').write_text(result.stdout + result.stderr, encoding='utf-8')
        assert result.returncode == 0 and json.loads(result.stdout)['status'] == 0 and counts() == (4, 4)
        record('actual_independent_native_producer_advances_the_prepared_book_head')
        host.key('Return');recovery = window('Recover book edit')
        assert counts() == (4, 4) and book()[1] == 'External native edit' and host.read()['error'] != 0
        shot('03-stale-head-refused', recovery)
        record('stale_gui_submission_cannot_overwrite_the_concurrent_native_edit')
        host.key('alt+d');window('Recover book edit', False)
        assert not journal.exists() and counts() == (4, 4) and book()[1] == 'External native edit'
        record('explicit_discard_removes_only_the_uncommitted_intent')
        host.key('F2', 'Return');host.wait(lambda s: s['book'] == sdk_id and s['error'] == 0 and s['reader_visible'])
        shot('04-original-still-readable', host.window)
        record('original_public_sdk_reading_still_opens_after_metadata_and_recovery_operations')
        host.close()
        assert len(checks) == 15
        report = {'accepted': True, 'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
                  'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'checks': checks, 'count': len(checks),
                  'program_sha256': hashlib.sha256(host.binary.read_bytes()).hexdigest(), 'screenshots': shots,
                  'scope': 'GTK actual book title author favorite and durable typed edit recovery',
                  'groups_ui_accepted': False, 'performance_accepted': False, 'complete_product': False,
                  'files': {str(p.relative_to(folder)): hashlib.sha256(p.read_bytes()).hexdigest()
                            for p in sorted(folder.rglob('*')) if p.is_file()}}
        (folder / 'metadata-ui.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({'accepted': True, 'count': len(checks), 'source_sha': report['source_sha']}))
    finally:
        if host.process and host.process.poll() is None:
            host.process.kill();host.process.wait(timeout=15)
        if host.log and not host.log.closed:
            host.log.close()


if __name__ == '__main__':
    main()
