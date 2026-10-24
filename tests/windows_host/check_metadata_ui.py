# SPDX-License-Identifier: MIT
"""Actions-only real Win32 metadata controls and independent product observations."""
import argparse
import ctypes as C
from ctypes import wintypes as W
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import struct
import subprocess
import sys
import time
import unicodedata

sys.path.insert(0, str(Path(__file__).resolve().parent / 'worker_review'))
from check_worker import App, U, ENUM, send, set_text

DETAILS, TITLE, AUTHOR, FAVORITE, SAVE, CANCEL, RETRY, DISCARD, MESSAGE = range(128, 137)
U.IsWindow.argtypes = [W.HWND];U.IsWindow.restype = W.BOOL
U.IsWindowVisible.argtypes = [W.HWND];U.IsWindowVisible.restype = W.BOOL
U.IsWindowEnabled.argtypes = [W.HWND];U.IsWindowEnabled.restype = W.BOOL
U.GetWindowRect.argtypes = [W.HWND, C.POINTER(W.RECT)]
U.GetWindowDC.argtypes = [W.HWND];U.GetWindowDC.restype = W.HDC
U.ReleaseDC.argtypes = [W.HWND, W.HDC]
G = C.WinDLL('gdi32', use_last_error=True)
G.CreateCompatibleDC.argtypes = [W.HDC];G.CreateCompatibleDC.restype = W.HDC
G.CreateCompatibleBitmap.argtypes = [W.HDC, C.c_int, C.c_int];G.CreateCompatibleBitmap.restype = W.HBITMAP
G.SelectObject.argtypes = [W.HDC, W.HANDLE];G.SelectObject.restype = W.HANDLE
G.BitBlt.argtypes = [W.HDC, C.c_int, C.c_int, C.c_int, C.c_int, W.HDC, C.c_int, C.c_int, W.DWORD]
G.GetDIBits.argtypes = [W.HDC, W.HBITMAP, W.UINT, W.UINT, C.c_void_p, C.c_void_p, W.UINT]
G.DeleteObject.argtypes = [W.HANDLE];G.DeleteDC.argtypes = [W.HDC]


def text(window):
    length = send(window, 0xE)
    value = C.create_unicode_buffer(length + 1)
    send(window, 0xD, len(value), C.addressof(value))
    return value.value


class MetadataApp(App):
    def wait_idle(self):
        self.wait(lambda: U.IsWindowEnabled(self.control('import')), timeout=90)
        time.sleep(.15)
        self.wait(lambda: U.IsWindowEnabled(self.control('import')), timeout=90)

    def dialog(self, recovery=False):
        def find():
            found = []

            @ENUM
            def visit(window, unused):
                pid = W.DWORD();U.GetWindowThreadProcessId(window, C.byref(pid))
                if pid.value == self.process.pid and U.IsWindowVisible(window) and U.GetDlgItem(window, MESSAGE):
                    expected = RETRY if recovery else TITLE
                    if U.GetDlgItem(window, expected):
                        found.append(window)
                return True

            U.EnumWindows(visit, 0)
            return found[-1] if found else None

        return self.wait(find)

    def details(self):
        self.wait_idle();send(self.control('books'), 0x186, 0)
        send(U.GetDlgItem(self.window, DETAILS), 0xF5)
        return self.dialog()

    def press(self, dialog, identifier):
        send(U.GetDlgItem(dialog, identifier), 0xF5)

    def closed(self, dialog):
        self.wait(lambda: not U.IsWindow(dialog));self.wait_idle()


def screenshot(window, path):
    assert U.IsWindowVisible(window)
    bounds = W.RECT();assert U.GetWindowRect(window, C.byref(bounds))
    width, height = bounds.right - bounds.left, bounds.bottom - bounds.top
    assert 400 <= width <= 4096 and 150 <= height <= 4096
    source = U.GetWindowDC(window);memory = G.CreateCompatibleDC(source)
    bitmap = G.CreateCompatibleBitmap(source, width, height);old = G.SelectObject(memory, bitmap)
    try:
        time.sleep(.2)
        assert G.BitBlt(memory, 0, 0, width, height, source, 0, 0, 0x00CC0020)
        G.SelectObject(memory, old)
        header = struct.pack('<IiiHHIIiiII', 40, width, height, 1, 32, 0, width * height * 4, 0, 0, 0, 0)
        info = C.create_string_buffer(header)
        pixels = C.create_string_buffer(width * height * 4)
        assert G.GetDIBits(memory, bitmap, 0, height, pixels, info, 0) == height
        assert len(set(pixels.raw)) > 8
        path.write_bytes(struct.pack('<2sIHHI', b'BM', 54 + len(pixels), 0, 0, 54) + header + pixels.raw)
    finally:
        G.SelectObject(memory, old);G.DeleteObject(bitmap);G.DeleteDC(memory);U.ReleaseDC(window, source)


def main():
    parser = argparse.ArgumentParser()
    for name in ('candidate', 'package', 'command-consumer', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    assert os.name == 'nt' and os.environ.get('GITHUB_ACTIONS') == 'true'
    output = args.output.resolve();output.mkdir(parents=True, exist_ok=False)
    profile = output / 'profile';profile.mkdir()
    catalog = profile / 'library.sqlite.product.sqlite';journal = Path(str(catalog) + '.commands.pending')
    original = ('Native Windows original remains readable after product edits.\n' * 180).encode()
    source = output / 'Original title.txt';source.write_bytes(original)
    app = None;checks = [];shots = []

    def launch():
        return MetadataApp(args.candidate.resolve(), (args.package / 'Reader.otf').resolve(), profile, existing=True)

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

    def edit(dialog, title, author=None, toggle=False):
        set_text(U.GetDlgItem(dialog, TITLE), title)
        if author is not None:
            set_text(U.GetDlgItem(dialog, AUTHOR), author)
        if toggle:
            app.press(dialog, FAVORITE)

    def shot(name, window):
        screenshot(window, output / name);shots.append(name)

    def kill():
        app.process.kill();app.process.wait(timeout=20);assert app.process.returncode != 0;app.log.close()

    try:
        app = launch()
        assert all(U.GetDlgItem(app.window, identifier) for identifier in range(100, 128))
        assert U.GetDlgItem(app.window, DETAILS)
        record('original_native_control_ids_100_through_127_are_preserved_and_details_is_appended')
        app.import_file(source);app.wait(lambda: send(app.control('books'), 0x18B) == 1);app.wait_idle()
        row = book();key = row[0];sdk_id = sql('SELECT sdk_book_id FROM reader_local_books')[0][0]
        assert key == 'txt:' + hashlib.sha256(original).hexdigest() and row[5] == len(original) and counts() == (0, 0)
        app.close();assert app.process.returncode == 0
        record('actual_native_import_retains_the_independently_hashed_original_identity')
        sql("UPDATE reader_books SET title='Legacy edited title',author='旧作者',sort_title='Legacy edited title',favorite=1")
        app = launch();dialog = app.details()
        assert text(U.GetDlgItem(dialog, TITLE)) == 'Legacy edited title' and text(U.GetDlgItem(dialog, AUTHOR)) == '旧作者'
        assert send(U.GetDlgItem(dialog, FAVORITE), 0xF0) == 1 and counts() == (1, 1)
        initial_id, initial_wire = sql('SELECT revision_id,body_json FROM reader_revisions')[0]
        assert json.loads(initial_wire)['payload']['title'] == 'Legacy edited title'
        shot('01-legacy-editor.bmp', dialog)
        app.press(dialog, CANCEL);app.closed(dialog)
        record('first_editor_verifies_public_sdk_source_and_bootstraps_current_product_fields')

        dialog = app.details();edit(dialog, 'Cafe\u0301 书名😀', '作者 😀', True);app.press(dialog, SAVE);app.closed(dialog)
        row = book();assert row[1:5] == ('Cafe\u0301 书名😀', '作者 😀', unicodedata.normalize('NFC', 'Cafe\u0301 书名😀'), 0)
        shot('02-native-edited-shelf.bmp', app.window)
        record('native_unicode_entries_and_favorite_checkbox_commit_the_exact_user_fields')
        assert counts() == (2, 2) and sql('SELECT sdk_book_id FROM reader_local_books') == [(sdk_id,)]
        values = [json.loads(raw) for raw, in sql('SELECT body_json FROM reader_revisions')]
        changed = next(value for value in values if value['id'] != initial_id)
        assert changed['parents'] == [initial_id] and changed['payload']['title'] == row[1] and changed['payload']['favorite'] is False
        assert all('sdk_book_id' not in raw for raw, in sql('SELECT body_json FROM reader_revisions'))
        assert book()[0] == key and book()[5] == len(original)
        record('one_user_save_is_one_metadata_history_outbox_transaction_without_changing_original_or_local_id')
        dialog = app.details();edit(dialog, 'Cancelled title');app.press(dialog, CANCEL);app.closed(dialog)
        assert book() == row and counts() == (2, 2) and not journal.exists()
        record('cancel_closes_the_native_editor_without_creating_an_intent_or_changing_metadata')

        sql("CREATE TRIGGER metadata_test_failure BEFORE UPDATE ON reader_books BEGIN SELECT RAISE(ABORT,'test refusal');END")
        dialog = app.details();edit(dialog, 'Recovered 书名😀');app.press(dialog, SAVE);recovery = app.dialog(True)
        assert book() == row and counts() == (2, 2) and journal.is_file()
        pending = journal.read_bytes();shot('03-recoverable-refusal.bmp', recovery)
        record('actual_product_write_refusal_preserves_a_complete_intent_with_zero_partial_writes')
        kill();assert journal.read_bytes() == pending
        record('actual_host_process_termination_preserves_pending_bytes_and_releases_its_owner')
        sql('DROP TRIGGER metadata_test_failure');app = launch();app.wait_idle()
        send(app.control('books'), 0x186, 0);send(U.GetDlgItem(app.window, DETAILS), 0xF5);recovery = app.dialog(True)
        assert journal.read_bytes() == pending and counts() == (2, 2)
        record('fresh_native_host_detects_pending_without_automatically_rebinding_or_submitting_it')
        app.press(recovery, RETRY);app.closed(recovery)
        assert book()[1] == 'Recovered 书名😀' and counts() == (3, 3) and not journal.exists()
        retained_id, retained_wire = sql('SELECT revision_id,body_json FROM reader_revisions ORDER BY rowid DESC LIMIT 1')[0]
        assert retained_id.encode() in pending and json.loads(retained_wire)['payload']['title'] == 'Recovered 书名😀'
        record('retry_commits_the_same_persisted_revision_and_full_typed_payload_once')
        app.close();app = launch();dialog = app.details()
        assert text(U.GetDlgItem(dialog, TITLE)) == 'Recovered 书名😀' and counts() == (3, 3)
        app.press(dialog, CANCEL);app.closed(dialog)
        record('normal_restart_does_not_duplicate_a_completed_native_edit')

        dialog = app.details();edit(dialog, 'Stale local edit')
        head = sql('SELECT revision_id FROM reader_revisions ORDER BY rowid DESC LIMIT 1')[0][0]
        title, author = output / 'external-title.txt', output / 'external-author.txt'
        title.write_text('External native edit', encoding='utf-8');author.write_text('Native writer', encoding='utf-8')
        result = subprocess.run([str(args.command_consumer.resolve()), 'book', str(catalog), 'f' * 32, head, '0', key,
                                 'txt', key.split(':')[1], str(len(original)), '0', str(title), str(author), str(title)],
                                capture_output=True, encoding='utf-8', timeout=60)
        (output / 'external-native-writer.log').write_text(result.stdout + result.stderr, encoding='utf-8')
        assert result.returncode == 0 and json.loads(result.stdout)['status'] == 0 and counts() == (4, 4)
        record('independent_installed_native_producer_advances_the_editor_snapshot_head')
        app.press(dialog, SAVE);recovery = app.dialog(True)
        assert counts() == (4, 4) and book()[1] == 'External native edit' and journal.exists()
        shot('04-stale-edit-retained.bmp', recovery)
        record('stale_native_gui_save_cannot_overwrite_a_concurrent_native_commit')
        app.press(recovery, DISCARD);app.closed(recovery)
        assert counts() == (4, 4) and not journal.exists() and book()[1] == 'External native edit'
        record('explicit_discard_removes_only_the_uncommitted_original_intent')

        dialog = app.details();edit(dialog, 'Barrier edit')
        held = sqlite3.connect(catalog, timeout=2);held.execute('BEGIN IMMEDIATE')
        try:
            app.press(dialog, SAVE);app.wait(lambda: journal.exists() and not U.IsWindowEnabled(U.GetDlgItem(dialog, SAVE)))
            before = journal.read_bytes();U.PostMessageW(dialog, 0x111, 2, 0);U.PostMessageW(dialog, 0x10, 0, 0)
            time.sleep(.2)
            assert U.IsWindow(dialog) and journal.read_bytes() == before and app.process.poll() is None
            shot('05-dialog-close-barrier.bmp', dialog)
        finally:
            held.rollback();held.close()
        app.closed(dialog);assert book()[1] == 'Barrier edit' and counts() == (5, 5) and not journal.exists()
        record('actual_writer_lock_cancel_and_dialog_wm_close_cannot_discard_an_accepted_save')

        dialog = app.details();raw = (C.c_uint16 * 2)(0xD800, 0)
        assert send(U.GetDlgItem(dialog, TITLE), 0xC, 0, C.addressof(raw))
        app.press(dialog, SAVE)
        app.wait(lambda: U.IsWindowEnabled(U.GetDlgItem(dialog, SAVE)))
        assert U.IsWindow(dialog) and counts() == (5, 5) and not journal.exists()
        app.press(dialog, CANCEL);app.closed(dialog)
        record('native_utf16_input_refusal_keeps_saved_metadata_and_never_stages_a_partial_intent')

        dialog = app.details();edit(dialog, 'Main-close saved')
        held = sqlite3.connect(catalog, timeout=2);held.execute('BEGIN IMMEDIATE')
        try:
            app.press(dialog, SAVE);app.wait(lambda: journal.exists())
            U.PostMessageW(app.window, 0x10, 0, 0);time.sleep(.2)
            assert app.process.poll() is None and U.IsWindow(dialog)
        finally:
            held.rollback();held.close()
        assert app.process.wait(timeout=30) == 0;app.log.close()
        assert book()[1] == 'Main-close saved' and counts() == (6, 6) and not journal.exists()
        record('main_window_wm_close_waits_for_the_accepted_native_transaction_before_exiting')
        app = launch();app.open('Main-close saved');app.wait_idle()
        assert book()[1] == 'Main-close saved' and counts() == (6, 6)
        app.click('select');app.click('copy')
        U.OpenClipboard.argtypes = [W.HWND];U.GetClipboardData.argtypes = [W.UINT];U.GetClipboardData.restype = W.HANDLE
        kernel = C.WinDLL('kernel32');kernel.GlobalLock.argtypes = [W.HANDLE];kernel.GlobalLock.restype = C.c_void_p;kernel.GlobalUnlock.argtypes = [W.HANDLE]
        assert U.OpenClipboard(app.window)
        try:
            handle = U.GetClipboardData(13);pointer = kernel.GlobalLock(handle)
            assert pointer and 'Native Windows original remains readable' in ' '.join(C.wstring_at(pointer).split())
            kernel.GlobalUnlock(handle)
        finally:
            U.CloseClipboard()
        shot('06-original-still-readable.bmp', app.window)
        app.close();assert app.process.returncode == 0
        record('original_public_sdk_reading_and_native_copy_survive_all_edits_recovery_and_normal_close')
        assert len(checks) == 18, len(checks)
        report = {'accepted': True, 'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
                  'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'checks': checks, 'count': len(checks),
                  'program_sha256': hashlib.sha256(args.candidate.read_bytes()).hexdigest(), 'screenshots': shots,
                  'scope': 'Windows native book title author favorite and durable typed edit recovery',
                  'groups_ui_accepted': False, 'performance_accepted': False, 'complete_product': False,
                  'files': {str(p.relative_to(output)): hashlib.sha256(p.read_bytes()).hexdigest()
                            for p in sorted(output.rglob('*')) if p.is_file()}}
        (output / 'metadata-ui.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({'accepted': True, 'count': len(checks), 'source_sha': report['source_sha']}), flush=True)
    finally:
        if app is not None:
            if app.process.poll() is None:
                app.process.kill();app.process.wait(timeout=20)
            if not app.log.closed:
                app.log.close()


if __name__ == '__main__':
    main()
