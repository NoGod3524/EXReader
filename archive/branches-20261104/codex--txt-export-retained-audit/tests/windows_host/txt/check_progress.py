"""Actions-only native acceptance for product TXT reading positions.

The real Win32 host (EXReaderProduct.exe) is driven through its own controls and
UI Automation: a 16,792,975-byte product original, page turns, close and restart,
a font-size relayout, a second book identity, a refused write while the product
database is write-locked, and the existing SDK book path. Nothing here weakens an
assertion: every step either produces the declared observation or reports a
failure with the host status text and the retained record.
"""
import ctypes as C
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import struct
import subprocess
import sys
import time
import traceback

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tests/reader_windows_compact'))
spec = importlib.util.spec_from_file_location("compact_ui", ROOT / "tests/reader_windows_compact/check_ui.py")
ui = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ui)
sys.path.insert(0, str(ROOT / 'tests/reader_perf_windows'))
from perf_windows import make_txt_fixture
sys.path.insert(0, str(ROOT / 'tests/reader_a11y_windows'))
from uia_layer import Uia
sys.path.insert(0, str(ROOT / 'tests/reader_wave3_c09'))
wave3_spec = importlib.util.spec_from_file_location("wave3_ui", ROOT / "tests/reader_wave3_c09/check_ui.py")
wave3 = importlib.util.module_from_spec(wave3_spec)
wave3_spec.loader.exec_module(wave3)

FONT_INC = 114
FONT_DEC = 113


def digest(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def rows(app):
    books = app.control('books')
    found = []
    for index in range(ui.send(books, 0x18B)):
        buffer = C.create_unicode_buffer(2048)
        ui.send(books, 0x189, index, C.addressof(buffer))
        found.append(buffer.value)
    return found


def page_text(app, automation):
    return automation.control(app.control('page')).GetValuePattern().Value or ''


def clipboard_text(app):
    from ctypes import wintypes as W
    user = C.WinDLL('user32', use_last_error=True)
    kernel = C.WinDLL('kernel32', use_last_error=True)
    user.OpenClipboard.argtypes = [W.HWND]
    user.GetClipboardData.argtypes = [W.UINT]
    user.GetClipboardData.restype = W.HANDLE
    kernel.GlobalLock.argtypes = [W.HANDLE]
    kernel.GlobalLock.restype = C.c_void_p
    kernel.GlobalUnlock.argtypes = [W.HANDLE]
    assert user.OpenClipboard(app.window)
    try:
        handle = user.GetClipboardData(13)
        assert handle
        pointer = kernel.GlobalLock(handle)
        assert pointer
        try:
            return C.wstring_at(pointer)
        finally:
            kernel.GlobalUnlock(handle)
    finally:
        user.CloseClipboard()


def selected_text_drag_points(window, before, selected):
    from ctypes import wintypes as W
    first, second = Path(before).read_bytes(), Path(selected).read_bytes()
    width, height = struct.unpack_from('<ii', first, 18)
    assert width > 0 and height > 0
    assert struct.unpack_from('<ii', second, 18) == (width, height)
    offset = struct.unpack_from('<I', first, 10)[0]
    assert offset == struct.unpack_from('<I', second, 10)[0]
    rect, client = W.RECT(), W.POINT(0, 0)
    assert ui.U.GetWindowRect(window, C.byref(rect))
    assert ui.U.ClientToScreen(window, C.byref(client))
    border_x, border_y = client.x - rect.left, client.y - rect.top
    for y in range(20, height - 20):
        row = offset + (height - y - 1) * width * 4
        changed = [x for x in range(20, width - 20)
                   if first[row + x * 4:row + x * 4 + 3] != second[row + x * 4:row + x * 4 + 3]]
        if len(changed) >= 30 and changed[-1] - changed[0] >= 100:
            left = changed[0] + 2 - border_x
            right = min(changed[-1] - 2, changed[0] + 160) - border_x
            return (left, y - border_y), (right, y - border_y)
    raise AssertionError('highlight has no selectable text span in the page screenshot')


def first_line(text):
    lines = [line for line in text.splitlines() if line.strip()]
    return lines[0] if lines else ''


def close_cleanly(app):
    app.close()
    assert app.process.returncode == 0, f"Host did not exit cleanly: {app.process.returncode}"


def main():
    assert os.name == 'nt' and os.environ.get('GITHUB_ACTIONS') == 'true'
    exe, font, out, pdf, injector = map(lambda value: Path(value).resolve(), sys.argv[1:6])
    family = sys.argv[6]
    out.mkdir(parents=True, exist_ok=False)
    fixture = make_txt_fixture(out, 0)
    expected = '4f45393b25817f506a51b56cc5d61599556e4dd5b0bd59aa00f7eb43cbfc0a86'
    assert fixture.stat().st_size == 16792975 and digest(fixture) == expected
    # A second, independent identity: same shape, different bytes and size.
    isolated = out / 'Isolated.txt'
    lines = ['Isolated Book %04d keeps its own reading position line %04d. \u4e66\u9875\u4f4d\u7f6e' % (index, index) for index in range(1200)]
    isolated.write_text(('\n'.join(lines) + '\n') * 256, encoding='utf-8')
    assert isolated.stat().st_size > 16 * 1024 * 1024

    report = dict(source_sha=os.environ['GITHUB_SHA'], host_sha256=digest(exe), checks=[],
                  scope='native Windows host: product TXT position save/restore, relayout, identity isolation, refused write and SDK book regression',
                  accepted=False)
    app = None
    product_db = None

    def record(name, detail=''):
        report['checks'].append(dict(name=name, passed=True, detail=str(detail)))
        print('CHECK ' + name + ' :: ' + str(detail), flush=True)

    def progress_heads(key):
        with sqlite3.connect(product_db, timeout=20) as db:
            found = db.execute('SELECT revision_id, body_json, body_sha256 FROM reader_revisions '
                               "WHERE entity_kind='progress' AND entity_key=?", (key,)).fetchall()
        parents = {parent for _, body, _ in found for parent in json.loads(body)['parents']}
        return {row[0]: row[2] for row in found if row[0] not in parents}, len(found)

    def observe_search_restore(stage, include_progress=True):
        # Evidence only: keep the existing driver order and assertions intact.
        text = page_text(app, automation)
        read_font = C.WinDLL('kernel32', use_last_error=True).GetPrivateProfileIntW
        read_font.argtypes = [C.c_wchar_p, C.c_wchar_p, C.c_int, C.c_wchar_p]
        read_font.restype = C.c_uint
        item = dict(stage=stage, page_label=ui.P.text(ui.U.GetDlgItem(app.window, 124)),
                    font_percent=read_font('Host', 'FontPercent', 0, str(app.profile / 'host.ini')),
                    page_text_sha256=hashlib.sha256(text.encode('utf-8')).hexdigest(),
                    page_text_chars=len(text), page_start=text[:300])
        if include_progress:
            with sqlite3.connect(product_db, timeout=20) as db:
                found = db.execute('SELECT revision_id, body_json, body_sha256 FROM reader_revisions '
                                   "WHERE entity_kind='progress' AND entity_key=?", ('txt:' + expected,)).fetchall()
            parents = {parent for _, body, _ in found for parent in json.loads(body)['parents']}
            item['revision_count'] = len(found)
            item['heads'] = [dict(revision_id=rid, body=json.loads(body), body_sha256=sha)
                             for rid, body, sha in found if rid not in parents]
        report.setdefault('search_restore_observations', []).append(item)

    def select_row(fragment):
        found = rows(app)
        index = [n for n, line in enumerate(found) if fragment in line]
        assert index, (fragment, found)
        ui.send(app.control('books'), 0x186, index[0])
        return index[0]

    def open_row(fragment):
        select_row(fragment)
        app.click('open')
        app.wait(lambda: ui.visible(app, 123) and not ui.visible(app, 119), timeout=240)
        app.wait_idle()

    def press_font_increase():
        ui.send(ui.U.GetDlgItem(app.window, FONT_INC), 0xF5)  # BM_CLICK

    def search_dialog():
        ui.command(app, 170)
        return app.wait(lambda: ui.owned_dialog(app, 171), timeout=30)

    def search_rows(dialog):
        box = ui.U.GetDlgItem(dialog, 174)
        result = []
        for index in range(ui.send(box, 0x18B)):
            value = C.create_unicode_buffer(2048)
            ui.send(box, 0x189, index, C.addressof(value))
            result.append(value.value)
        return result

    def search_query(dialog, value):
        ui.P.set_text(ui.U.GetDlgItem(dialog, 171), value)
        ui.send(dialog, 0x111, 172)
        app.wait(lambda: ui.U.IsWindowEnabled(ui.U.GetDlgItem(dialog, 172)), timeout=240)

    try:
        profile = out / 'profile'
        app = ui.P.App(exe, font, profile)
        product_db = str(app.db) + '.product.sqlite'
        app.wait_idle()
        automation = Uia()
        assert automation.available, automation.error

        ui.picker(app, pdf)
        app.wait(lambda: len(rows(app)) == 1, timeout=180)
        ui.picker(app, fixture)
        assert 'TXT 原书已保存' in app.status(), app.status()
        app.wait(lambda: len(rows(app)) == 2, timeout=300)
        record('native TXT import adds one product original after the SDK book', app.status())

        open_row(fixture.name)
        assert 'Perf Import 0000' in page_text(app, automation), page_text(app, automation)[:200]
        record('shelf selection opens the 16792975-byte original at its first page')
        export_dir = out / 'mixed-original-exports'
        export_dir.mkdir()
        dialog = wave3.open_feature(app, wave3.ORIGINALS)
        export_rows = wave3.rows(dialog)
        txt_matches = [i for i, row in enumerate(export_rows) if fixture.name in row]
        pdf_matches = [i for i, row in enumerate(export_rows) if pdf.stem in row]
        assert len(txt_matches) == len(pdf_matches) == 1, export_rows
        for index in (txt_matches[0], pdf_matches[0]):
            ui.send(ui.U.GetDlgItem(dialog, wave3.ROWS), 0x185, 1, index)
        wave3.post_click(dialog, wave3.B1)
        wave3.fill_system_dialog(app, export_dir)
        wave3.wait_message(app, dialog, wave3.N.ORIGINALS_DONE, 240)
        files = sorted(p.name for p in export_dir.iterdir())
        expected_files = sorted([expected + '.txt', digest(pdf) + '.pdf'])
        assert files == expected_files, (files, expected_files)
        assert digest(export_dir / (expected + '.txt')) == expected
        assert digest(export_dir / (digest(pdf) + '.pdf')) == digest(pdf)
        assert len(wave3.rows(dialog)) == 2
        for index in range(2):
            ui.send(ui.U.GetDlgItem(dialog, wave3.ROWS), 0x185, 1, index)
        wave3.post_click(dialog, wave3.B1)
        wave3.fill_system_dialog(app, export_dir)
        wave3.wait_message(app, dialog, wave3.N.ORIGINALS_DONE, 240)
        assert all(wave3.N.EXISTING in row for row in wave3.rows(dialog)), wave3.rows(dialog)
        assert sorted(p.name for p in export_dir.iterdir()) == expected_files
        wave3.close_feature(app, dialog)
        app.wait_idle()
        record('mixed SDK and large TXT original export preserves exact bytes and reports duplicates')
        first_page = page_text(app, automation)
        before_selection = out / 'txt-page-before-selection.bmp'
        after_selection = out / 'txt-page-selected.bmp'
        ui.P.M.screenshot(app.control('page'), before_selection)
        assert ui.U.IsWindowEnabled(app.control('select')) and ui.U.IsWindowEnabled(app.control('copy'))
        ui.command(app, 107)
        ui.P.M.screenshot(app.control('page'), after_selection)
        assert digest(before_selection) != digest(after_selection), 'selected TXT page has no visible highlight'
        ui.command(app, 108)
        assert ' '.join(clipboard_text(app).split()) == ' '.join(first_page.split())
        record('select and copy the first TXT page through native commands')
        app.focus()
        drag_start, drag_end = selected_text_drag_points(app.control('page'), before_selection, after_selection)
        app.drag(app.control('page'), drag_start, drag_end)
        app.wait_idle()
        drag_status = app.status()
        ui.P.M.screenshot(app.control('page'), out / 'txt-page-after-drag.bmp')
        ui.command(app, 108)
        copy_status = app.status()
        selected = ' '.join(clipboard_text(app).split())
        whole_page = ' '.join(first_page.split())
        assert 0 < len(selected) < len(whole_page) and selected in whole_page, {
            'selected_length': len(selected), 'page_length': len(whole_page),
            'selection_in_page': selected in whole_page, 'drag_status': drag_status,
            'copy_status': copy_status, 'start': drag_start, 'end': drag_end}
        record('drag and copy a partial TXT selection using actual mouse input')
        ui.command(app, 137)  # IDC_ACCOUNT_BUTTON, the native account command
        account_dialog = app.wait(lambda: ui.owned_dialog(app, 138), timeout=30)
        assert account_dialog, 'account dialog unavailable while reading TXT'
        ui.send(account_dialog, 0x10)  # WM_CLOSE
        app.wait(lambda: not ui.U.IsWindow(account_dialog), timeout=30)
        app.wait_idle()
        assert page_text(app, automation) == first_page
        record('account dialog opens and closes while preserving the TXT page')
        for command_id, name in ((240, 'cloud import'), (241, 'bulk organization')):
            ui.command(app, command_id)
            dialog = app.wait(lambda: ui.owned_dialog(app, 242), timeout=30)
            assert dialog, name + ' dialog unavailable while reading TXT'
            ui.send(dialog, 0x10)  # WM_CLOSE cancels an active inspection if necessary
            app.wait(lambda: not ui.U.IsWindow(dialog), timeout=60)
            app.wait_idle()
            assert page_text(app, automation) == first_page
            record(name + ' dialog opens and closes while preserving the TXT page')
        heads, count = progress_heads('txt:' + expected)
        assert count >= 1 and heads, (count, heads)
        record('first open saves a new reading position', 'revisions=%d heads=%d' % (count, len(heads)))

        source_text = fixture.read_text(encoding='utf-8')
        current = page_text(app, automation)
        position = source_text.find(current) if current else -1
        assert position >= 0, current[:200]
        end = position + len(current)
        for _ in range(6):
            app.click('next')
            app.wait_idle()
            current = page_text(app, automation)
            position = source_text.find(current, end) if current else -1
            assert position >= end, (position, end, current[:200])
            end = position + len(current)
        record('six forward page turns show consecutive source content', first_line(current))
        ui.command(app, 107)
        ui.command(app, 108)
        assert ' '.join(clipboard_text(app).split()) == ' '.join(current.split())
        record('select and copy a later TXT page using its nonzero source offset')

        before_font = page_text(app, automation)
        label_before_font = app.label()
        press_font_increase()
        app.wait_idle()
        assert app.label() != label_before_font, app.label()
        after_font = page_text(app, automation)
        marker = first_line(before_font)
        assert marker and marker in after_font, (marker, after_font[:300])
        position_line = first_line(after_font)
        position_marker = '\n'.join([line for line in after_font.splitlines() if line.strip()][:2])
        assert position_marker
        record('font increase relayouts and keeps the content position', marker)
        app.click('next'); app.wait_idle()
        after_relayout_next = page_text(app, automation)
        assert after_relayout_next and after_relayout_next != after_font
        assert after_relayout_next in source_text
        app.click('previous'); app.wait_idle()
        assert page_text(app, automation) == after_font
        record('page turns continue after TXT relayout')

        heads, count = progress_heads('txt:' + expected)
        assert count >= 1 and heads, (count, heads)
        record('product progress history exists for the content identity',
               'revisions=%d heads=%d' % (count, len(heads)))

        close_cleanly(app); app = None
        app = ui.P.App(exe, font, profile, existing=True)
        app.wait_idle()
        automation = Uia()
        assert automation.available, automation.error
        app.wait(lambda: len(rows(app)) == 2, timeout=180)
        app.wait(lambda: ui.visible(app, 123) and not ui.visible(app, 119), timeout=240)
        app.wait_idle()
        restored = page_text(app, automation)
        assert '已按内容位置恢复' in app.status(), app.status()
        assert first_line(restored) == position_line, (first_line(restored), position_line)
        record('close and restart restore the same content position', position_line)

        ui.picker(app, isolated)
        app.wait(lambda: len(rows(app)) == 3, timeout=300)
        open_row(isolated.name)
        isolated_text = page_text(app, automation)
        assert 'Isolated Book 0000' in isolated_text, isolated_text[:200]
        assert '还没有保存过阅读位置' in app.status(), app.status()
        record('a different book identity starts at its own first page', app.status())
        dialog = search_dialog()
        search_query(dialog, '\u4e66\u9875\u4f4d\u7f6e')
        assert len(search_rows(dialog)) == 32
        ui.send(dialog, 0x10)
        app.wait(lambda: not ui.U.IsWindow(dialog), timeout=30)
        app.wait_idle()
        record('TXT search handles UTF-8 text on the independent original')

        close_cleanly(app); app = None
        app = ui.P.App(exe, font, profile, existing=True)
        app.wait_idle()
        automation = Uia()
        assert automation.available, automation.error
        app.wait(lambda: len(rows(app)) == 3, timeout=180)
        app.wait(lambda: ui.visible(app, 123) and not ui.visible(app, 119), timeout=240)
        app.wait_idle()
        assert 'Isolated Book 0000' in page_text(app, automation), page_text(app, automation)[:200]
        open_row(fixture.name)
        assert first_line(page_text(app, automation)) == position_line, page_text(app, automation)[:200]
        record('restart keeps both content identities independent')

        heads_before, count_before = progress_heads('txt:' + expected)
        lock = sqlite3.connect(str(app.db) + '.product.sqlite', isolation_level=None, timeout=0.2)
        lock.execute('PRAGMA busy_timeout=200')
        locked = False
        for _ in range(60):
            try:
                lock.execute('BEGIN EXCLUSIVE')
                locked = True
                break
            except sqlite3.OperationalError:
                time.sleep(0.2)
        assert locked, 'could not hold the product database write lock'
        press_font_increase()
        app.wait_idle()
        app.wait(lambda: '阅读位置未保存' in app.status(), timeout=120)
        refused = app.status()
        # A refused write must not trap the exit either: the window still closes.
        close_cleanly(app); app = None
        lock.execute('ROLLBACK')
        lock.close()
        heads_after, count_after = progress_heads('txt:' + expected)
        assert heads_after == heads_before, (heads_before, heads_after)
        assert count_after == count_before, (count_before, count_after)
        record('a refused write keeps the retained record and still exits', refused)

        app = ui.P.App(exe, font, profile, existing=True)
        app.wait_idle()
        automation = Uia()
        assert automation.available, automation.error
        app.wait(lambda: len(rows(app)) == 3, timeout=180)
        open_row(fixture.name)
        assert position_marker in page_text(app, automation), page_text(app, automation)[:200]
        record('restart after the refused write restores the durable position', position_marker)

        before_missing = page_text(app, automation)
        dialog = search_dialog()
        search_query(dialog, 'query absent from the complete TXT original')
        assert not search_rows(dialog)
        assert '\u6ca1\u6709\u5339\u914d\u7ed3\u679c' in ui.P.text(ui.U.GetDlgItem(dialog, 178))
        assert page_text(app, automation) == before_missing
        record('TXT search reports a missing query without changing the page')
        search_query(dialog, 'line 0100')
        first_hits = search_rows(dialog)
        assert len(first_hits) == 32, first_hits
        ui.send(ui.U.GetDlgItem(dialog, 174), 0x186, 0)
        ui.send(dialog, 0x111, 175)
        app.wait(lambda: '\u5df2\u72ec\u7acb\u6838\u5bf9' in ui.P.text(ui.U.GetDlgItem(dialog, 178)), timeout=240)
        app.wait_idle()
        assert 'line 0100' in page_text(app, automation), page_text(app, automation)[:200]
        record('TXT search independently verifies and locates the selected match')
        ui.send(dialog, 0x111, 173)
        app.wait(lambda: ui.U.IsWindowEnabled(ui.U.GetDlgItem(dialog, 172)), timeout=240)
        next_hits = search_rows(dialog)
        assert len(next_hits) == 32, next_hits
        assert int(next_hits[0].split()[0]) > int(first_hits[-1].split()[0]), (first_hits[-1], next_hits[0])
        ui.send(dialog, 0x10)
        app.wait(lambda: not ui.U.IsWindow(dialog), timeout=30)
        app.wait_idle()
        record('TXT search resumes at the next batch without repeating hits')
        current = page_text(app, automation)

        # Reproduce the search, relayout and refused-save sequence from
        # run 40575156438 using the same font on both sides of the restart.
        close_cleanly(app); app = None
        app = ui.P.App(exe, font, profile, existing=True)
        app.wait_idle()
        automation = Uia()
        assert automation.available, automation.error
        app.wait(lambda: ui.visible(app, 123) and not ui.visible(app, 119), timeout=240)
        app.wait_idle()
        assert 'line 0100' in page_text(app, automation), page_text(app, automation)[:200]
        search_heads, search_count = progress_heads('txt:' + expected)
        observe_search_restore('before_locked_relayout')
        lock = sqlite3.connect(str(app.db) + '.product.sqlite', isolation_level=None, timeout=0.2)
        lock.execute('PRAGMA busy_timeout=200')
        locked = False
        for _ in range(60):
            try:
                lock.execute('BEGIN EXCLUSIVE')
                locked = True
                break
            except sqlite3.OperationalError:
                time.sleep(0.2)
        assert locked, 'could not hold the product database write lock after search'
        press_font_increase()
        app.wait_idle()
        app.wait(lambda: '\u9605\u8bfb\u4f4d\u7f6e\u672a\u4fdd\u5b58' in app.status(), timeout=120)
        after_locked_relayout = page_text(app, automation)
        observe_search_restore('after_locked_relayout', include_progress=False)
        close_cleanly(app); app = None
        lock.execute('ROLLBACK')
        lock.close()
        assert progress_heads('txt:' + expected) == (search_heads, search_count)
        report['search_refused_write_progress'] = dict(
            before_heads=search_heads, before_count=search_count,
            after_heads=progress_heads('txt:' + expected)[0],
            after_count=progress_heads('txt:' + expected)[1])
        app = ui.P.App(exe, font, profile, existing=True)
        app.wait_idle()
        automation = Uia()
        assert automation.available, automation.error
        app.wait(lambda: ui.visible(app, 123) and not ui.visible(app, 119), timeout=240)
        app.wait_idle()
        restored_after_search = page_text(app, automation)
        observe_search_restore('after_same_font_restart')
        assert restored_after_search == after_locked_relayout, (after_locked_relayout, restored_after_search)
        record('search position survives relayout and a refused save at the same font')

        open_row(pdf.stem)
        sdk_first = page_text(app, automation)
        app.click('next')
        app.wait_idle()
        sdk_second = page_text(app, automation)
        close_cleanly(app); app = None
        app = ui.P.App(exe, font, profile, existing=True)
        app.wait_idle()
        automation = Uia()
        assert automation.available, automation.error
        app.wait(lambda: len(rows(app)) == 3, timeout=180)
        open_row(pdf.stem)
        sdk_restored = page_text(app, automation)
        if sdk_second and sdk_second != sdk_first:
            assert sdk_restored == sdk_second, (sdk_restored[:120], sdk_second[:120])
            record('existing SDK fixed-page book restores its own position', sdk_restored[:80])
        else:
            assert sdk_restored == sdk_first, (sdk_restored[:120], sdk_first[:120])
            record('existing SDK fixed-page book reopens with its single page', sdk_restored[:80])

        # A valid but mismatching capture must remain untouched through page
        # turns and relayout, using the installed module to create the fixture.
        close_cleanly(app); app = None
        subprocess.run([str(injector), product_db, family, 'txt:' + expected],
                       check=True, capture_output=True, timeout=60)
        mismatch_heads, mismatch_count = progress_heads('txt:' + expected)
        assert mismatch_heads
        app = ui.P.App(exe, font, profile, existing=True)
        app.wait_idle()
        automation = Uia()
        assert automation.available, automation.error
        app.wait(lambda: len(rows(app)) == 3, timeout=180)
        open_row(fixture.name)
        assert '不一致' in app.status(), app.status()
        app.click('next'); app.wait_idle()
        press_font_increase(); app.wait_idle()
        close_cleanly(app); app = None
        after_heads, after_count = progress_heads('txt:' + expected)
        assert (after_heads, after_count) == (mismatch_heads, mismatch_count)
        record('mismatched position remains intact across page turn and relayout')
        report['accepted'] = True
    except Exception:
        report['error'] = traceback.format_exc()
        if app:
            report['host_exit_code'] = app.process.poll()
            if not app.log.closed:
                app.log.flush()
            log_path = app.profile / 'application.log'
            if log_path.exists():
                report['host_log_tail'] = log_path.read_text(encoding='utf-8', errors='replace')[-8000:]
    finally:
        if app:
            try:
                app.close()
            except Exception:
                pass
        (out / 'report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False), flush=True)
    assert report['accepted']


if __name__ == '__main__':
    main()
