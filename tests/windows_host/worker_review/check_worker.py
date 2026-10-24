#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Cloud-only real Win32 controls and independently observed SQLite fault cases."""
import argparse
import ctypes as C
from ctypes import wintypes as W
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from make_fixtures import epub

U, K = C.WinDLL('user32', use_last_error=True), C.WinDLL('kernel32', use_last_error=True)
U.GetDlgItem.argtypes = [W.HWND, C.c_int]
U.GetDlgItem.restype = W.HWND
U.SendMessageTimeoutW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM, W.UINT, W.UINT, C.POINTER(C.c_size_t)]
U.SendMessageTimeoutW.restype = W.LPARAM
U.PostMessageW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM]
U.GetWindowThreadProcessId.argtypes = [W.HWND, C.POINTER(W.DWORD)]
U.GetClassNameW.argtypes = [W.HWND, W.LPWSTR, C.c_int]
ENUM = C.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
U.EnumWindows.argtypes = [ENUM, W.LPARAM]
K.OpenEventW.argtypes = [W.DWORD, W.BOOL, W.LPCWSTR]
K.OpenEventW.restype = W.HANDLE
K.SetEvent.argtypes = [W.HANDLE]
K.CloseHandle.argtypes = [W.HANDLE]

REVIEW = 0x8000+30
IDS = {'path': 101, 'import': 102, 'open': 103, 'delete': 104, 'previous': 105,
       'next': 106, 'select': 107, 'copy': 108, 'add': 109, 'update': 110,
       'remove': 111, 'jump': 112, 'zoom': 116, 'cancel': 117, 'books': 119,
       'notes': 121, 'comment': 122, 'page': 123, 'status': 125}


def send(window, message, wparam=0, lparam=0, timeout=2000):
    result = C.c_size_t()
    C.set_last_error(0)
    if not U.SendMessageTimeoutW(window, message, wparam, lparam, 2, timeout, C.byref(result)):
        raise TimeoutError('UI message not serviced: message=%d wparam=%d winerror=%d' % (message, wparam, C.get_last_error()))
    return result.value


def set_text(window, text):
    # SetWindowText cannot edit another process's child control. WM_SETTEXT is
    # a system message, so Windows marshals this Unicode buffer to the reader.
    units = len(text.encode('utf-16-le'))//2+1
    value = C.create_unicode_buffer(text, units)
    assert send(window, 0xC, 0, C.addressof(value)), 'Edit rejected WM_SETTEXT'
    actual = C.create_unicode_buffer(units)
    send(window, 0xD, len(actual), C.addressof(actual))
    assert actual.value == text, 'Edit text differs from requested Unicode input'


class App:
    def __init__(self, exe, font, profile, bounded=False, existing=False):
        self.bounded = bounded
        self.note_table = 'epub_notes' if bounded else 'notes'
        self.profile = profile
        profile.mkdir(parents=True, exist_ok=existing)
        self.db = profile/'library.sqlite'
        self.log = (profile/'application.log').open('ab' if existing else 'wb')
        self.process = subprocess.Popen([str(exe), '--font', str(font), '--data', str(profile)],
                                        stdout=self.log, stderr=subprocess.STDOUT)
        self.window = None
        def found():
            @ENUM
            def visit(window, unused):
                pid = W.DWORD()
                U.GetWindowThreadProcessId(window, C.byref(pid))
                name = C.create_unicode_buffer(100)
                U.GetClassNameW(window, name, 100)
                if pid.value == self.process.pid and name.value == 'EXReaderHost':
                    self.window = window
                return True
            U.EnumWindows(visit, 0)
            return self.window
        try:
            self.wait(found)
            self.wait_idle()
        except Exception:
            self.process.kill(); self.process.wait(); self.log.close()
            raise

    def wait(self, check, timeout=30):
        end = time.monotonic()+timeout
        while time.monotonic() < end:
            if self.process.poll() is not None:
                raise RuntimeError('Host exited before the expected UI result')
            try:
                result = check()
                if result:
                    return result
            except TimeoutError:
                pass
            time.sleep(.05)
        raise TimeoutError('Expected host transition did not complete')

    def q(self, code, value=0):
        return send(self.window, REVIEW, code, value)

    def control(self, name):
        return U.GetDlgItem(self.window, IDS[name])

    def click(self, name, timeout=2000):
        send(self.control(name), 0xF5, timeout=timeout)  # BM_CLICK

    def wait_idle(self):
        self.wait(lambda: self.q(14) == 0)

    def status(self):
        value = C.create_unicode_buffer(1000)
        send(self.control('status'), 0xD, len(value), C.addressof(value))
        return value.value

    def row(self, title):
        box = self.control('books')
        for i in range(send(box, 0x18B)):
            value = C.create_unicode_buffer(1024)
            send(box, 0x189, i, C.addressof(value))
            if title in value.value:
                return i
        raise AssertionError('Expected book row missing: '+title)

    def import_file(self, path):
        set_text(self.control('path'), str(path))
        self.click('import')
        self.wait_idle()

    def open(self, title, wait=True):
        send(self.control('books'), 0x186, self.row(title))
        self.click('open')
        if wait:
            self.wait_idle()

    def note(self, comment, wait=True):
        self.click('select')
        set_text(self.control('comment'), comment)
        self.click('add')
        if wait:
            self.wait_idle()

    def gate(self, stage):
        assert self.q(100+stage) == 1

    def stage(self, stage):
        self.wait(lambda: self.q(18) == stage)

    def release(self):
        handle = K.OpenEventW(2, False, 'Local\\EXReaderWorkerReview-'+str(self.process.pid))
        if handle:
            K.SetEvent(handle)
            K.CloseHandle(handle)

    def scalar(self, sql, values=()):
        with sqlite3.connect(self.db) as db:
            return db.execute(sql, values).fetchone()[0]

    def position(self, book=None, connection=None):
        sql = 'SELECT position FROM epub_progress' if self.bounded else 'SELECT position FROM books'
        values = () if book is None else (book,)
        sql += ' LIMIT 1' if book is None else (' WHERE book_id=?' if self.bounded else ' WHERE id=?')
        if connection is not None:
            return connection.execute(sql, values).fetchone()[0]
        return self.scalar(sql, values)

    def close(self):
        self.release()
        if self.process.poll() is None:
            U.PostMessageW(self.window, 0x10, 0, 0)
            try:
                self.process.wait(timeout=12)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        self.log.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('candidate', 'baseline', 'package', 'fixtures', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        parser.error('Choose a fresh evidence directory')
    output.mkdir(parents=True)
    font = (args.package/'Reader.otf').resolve()
    sample = (args.package/'Sample-positive.epub').resolve()
    pdf = (args.fixtures/'Pages.pdf').resolve()
    extra = (args.fixtures/'Extra-Book.epub').resolve()
    seek_book = output/'Seek-Unique.epub'
    epub(seek_book, 'Worker Seek Unique', ' '.join('word%05d' % i for i in range(6000)))
    cases = []

    def run(name, test):
        for variant, exe in (('baseline', args.baseline), ('candidate', args.candidate)):
            app = None
            result = {'name': name, 'variant': variant, 'pass': False}
            try:
                app = App(exe.resolve(), font, output/(variant+'-'+name), bounded=variant == 'candidate')
                passed, observed = test(app)
                result.update({'pass': bool(passed), 'observed': observed})
            except Exception as error:
                result['error'] = type(error).__name__+': '+str(error)
            finally:
                if app:
                    app.close()
            cases.append(result)
            print(json.dumps(result, ensure_ascii=True), flush=True)

    def setup_pdf(app):
        app.import_file(pdf)
        app.open('Pages')
        assert app.q(15) == 1

    def setup_text(app):
        app.import_file(sample)
        app.open('EXReader benchmark')
        assert app.q(15) == 0

    def note_cancel(app, update=False):
        setup_pdf(app)
        if update:
            app.note('original comment')
            send(app.control('notes'), 0x186, 0)
        app.click('select')
        set_text(app.control('comment'), 'replacement comment')
        app.gate(1)
        responsive = True
        try:
            app.click('update' if update else 'add')
        except TimeoutError:
            responsive = False
            app.release()  # independent event works even while original UI is blocked
        if responsive:
            app.stage(1)
            worker = app.q(25) != app.q(26)
            app.click('cancel')
        else:
            worker = False
        app.wait_idle()
        stored = app.scalar('SELECT count(*) FROM fixed_notes')
        intact = stored == (1 if update else 0)
        if update and stored:
            intact = app.scalar('SELECT text FROM fixed_notes LIMIT 1') == 'original comment'
        return responsive and worker and intact, {'ui_responsive': responsive, 'sdk_call_on_worker': worker, 'stored_notes': stored, 'original_note_intact': intact}

    run('fixed-note-cancel', lambda a: note_cancel(a))
    run('fixed-note-update-cancel', lambda a: note_cancel(a, True))

    def late_cancel(app):
        setup_pdf(app)
        before = app.q(11)
        app.gate(2)
        app.click('next')
        app.stage(2)
        app.click('cancel')
        app.wait_idle()
        return app.q(11) == before and '取消' in app.status(), {'before_page': before, 'after_page': app.q(11), 'status': app.status()}
    run('fixed-go-late-cancel', late_cancel)

    def rollback(app):
        setup_text(app)
        app.gate(3)
        set_text(app.control('path'), str(extra))
        app.click('import')
        app.stage(3)
        lock = sqlite3.connect(app.db, timeout=1)
        try:
            lock.execute('BEGIN IMMEDIATE')
            app.click('cancel')
            app.wait_idle()
            durable = lock.execute('SELECT count(*) FROM books').fetchone()[0]
            visible, status = app.q(13), app.status()
            return durable == visible == 2 and '删除失败' in status, {'durable_books': durable, 'visible_books': visible, 'status': status}
        finally:
            lock.rollback()
            lock.close()
    run('rollback-sql-busy', rollback)

    def failed_seek(app):
        app.import_file(seek_book)
        app.open('Worker Seek Unique')
        for _ in range(8):
            app.click('next')
            app.wait_idle()
        app.note('far annotation')
        send(app.control('page'), 0x100, 0x24)  # WM_KEYDOWN / VK_HOME
        app.wait_idle()
        before = app.q(11)
        app.q(300, 3)  # fail only after real get() calls have evicted old cache entries
        send(app.control('notes'), 0x186, 0)
        app.click('jump')
        app.wait_idle()
        retained, status = app.q(11) == before, app.status()
        lookups, injected = app.q(27), app.q(28)
        app.click('select')
        # Force the actual page selection painter after the failed jump.
        send(app.control('page'), 0xF)
        selected = app.q(16)
        app.note('after failed seek')
        after_notes = app.q(12)
        return retained and '失败' in status and selected > 0 and after_notes == 2 and lookups >= 3 and injected == 1, {'retained_page': retained, 'status': status, 'selected_bytes_after_failure': selected, 'saved_notes_after_failure': after_notes, 'real_page_lookups': lookups, 'injected_public_errors': injected}
    run('seek-failure-retains-selection', failed_seek)

    def close_candidate(app):
        app.import_file(sample)
        app.import_file(pdf)
        app.open('EXReader benchmark')
        app.click('next'); app.wait_idle()
        app.click('next'); app.wait_idle()
        source = app.q(10)
        old_position = app.position(source)
        app.gate(4)
        app.open('Pages', wait=False)
        app.stage(4)
        session_still_original = app.q(19) == source
        U.PostMessageW(app.window, 0x10, 0, 0)
        app.process.wait(timeout=20)
        position = app.position(source)
        return session_still_original and old_position > 0 and position == old_position, {'candidate_not_published': session_still_original, 'before_position': old_position, 'after_position': position, 'exit_code': app.process.returncode}
    run('close-discards-open-candidate', close_candidate)

    def drag_busy(app):
        setup_text(app)
        send(app.control('page'), 0x201, 1, 220 | (240 << 16))
        if app.bounded:
            app.wait_idle()  # The bounded down hit is a serialized SDK job.
        began = app.q(17) == 1
        app.gate(2)
        app.click('next')
        app.stage(2)
        reset = app.q(17) == 0
        send(app.control('page'), 0x200, 1, 480 | (420 << 16))
        send(app.control('page'), 0x202, 0, 480 | (420 << 16))
        send(app.control('page'), 0xF)
        app.click('cancel')
        app.wait_idle()
        return began and reset and app.q(11) == 0, {'drag_started': began, 'drag_reset_at_worker_start': reset, 'page_after_cancel': app.q(11)}
    run('busy-drag-ownership', drag_busy)

    def notes_failure(app):
        setup_text(app)
        app.note('retained annotation')
        app.q(301)
        app.note('new committed annotation')
        visible, durable, status = app.q(12), app.scalar('SELECT count(*) FROM '+app.note_table), app.status()
        first = visible == 1 and durable == 2 and '读取标注失败' in status
        app.open('EXReader benchmark')
        return first and app.q(12) == 2, {'visible_during_failure': visible, 'durable_notes': durable, 'status': status, 'visible_after_retry': app.q(12)}
    run('notes-query-retains-old-list', notes_failure)

    def shelf_failure(app):
        setup_text(app)
        app.q(302)
        app.import_file(extra)
        status, durable = app.status(), app.scalar('SELECT count(*) FROM books')
        first = durable == 2 and '读取书架失败' in status
        app.import_file(extra)
        return first and app.q(13) == 2, {'durable_books': durable, 'status': status, 'visible_after_retry': app.q(13)}
    run('shelf-query-error-disclosed', shelf_failure)

    def comment_boundary(app):
        setup_text(app)
        app.note('中'*21846)  # 65538 UTF-8 bytes, valid if truncated at 65535
        count, status = app.scalar('SELECT count(*) FROM '+app.note_table), app.status()
        rejected = count == 0 and '上限' in status
        exact = '😀'*16383
        app.note(exact)
        with sqlite3.connect(app.db) as db:
            saved = db.execute('SELECT text FROM '+app.note_table+' ORDER BY id DESC LIMIT 1').fetchone()[0]
        return rejected and saved == exact, {'over_limit_inserted': count, 'over_limit_status': status, 'boundary_utf8_bytes': len(saved.encode()), 'boundary_text_exact': saved == exact}
    run('unicode-comment-byte-limit', comment_boundary)

    def progress_failure(app):
        setup_text(app)
        lock = sqlite3.connect(app.db, timeout=1)
        try:
            lock.execute('BEGIN IMMEDIATE')
            app.click('next'); app.wait_idle()
            status = app.status()
            old = app.position(connection=lock)
            U.PostMessageW(app.window, 0x10, 0, 0)
            time.sleep(4)
            refused = app.process.poll() is None
            result = old == 0 and '保存进度失败' in status and refused
        finally:
            lock.rollback(); lock.close()
        if app.process.poll() is None:
            U.PostMessageW(app.window, 0x10, 0, 0)
            app.process.wait(timeout=15)
        saved = app.position()
        return result and saved > 0, {'status': status, 'old_durable_position': old, 'close_refused_until_retry': refused, 'position_after_retry': saved}
    run('progress-failure-blocks-silent-close', progress_failure)

    candidate = [case for case in cases if case['variant'] == 'candidate']
    baseline = [case for case in cases if case['variant'] == 'baseline']
    passed = len(candidate) == 11 and all(case['pass'] for case in candidate)
    reversed_ok = len(baseline) == 11 and all(not case['pass'] and 'error' not in case for case in baseline)
    result = {'schema': 1, 'passed': passed and reversed_ok, 'source_sha': os.environ.get('GITHUB_SHA'),
              'run_id': os.environ.get('GITHUB_RUN_ID'), 'candidate_cases': len(candidate),
              'candidate_passed': sum(case['pass'] for case in candidate),
              'baseline_cases': len(baseline), 'baseline_rejected': sum(not case['pass'] for case in baseline),
              'reverse_verification': reversed_ok, 'cases': cases,
              'binaries': {name: hashlib.sha256(path.read_bytes()).hexdigest()
                           for name, path in [('candidate', args.candidate), ('baseline', args.baseline)]}}
    (output/'worker-review.json').write_text(json.dumps(result, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
    print(json.dumps({key: result[key] for key in ('passed', 'candidate_passed', 'baseline_rejected', 'reverse_verification', 'source_sha', 'run_id')}), flush=True)
    if not result['passed']:
        raise RuntimeError('Windows worker ownership regression rejected; see worker-review.json')


if __name__ == '__main__':
    main()
