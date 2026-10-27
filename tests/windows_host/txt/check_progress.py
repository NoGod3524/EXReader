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
    lines = ['Isolated Book %04d keeps its own reading position line %04d.' % (index, index) for index in range(1200)]
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
        first_page = page_text(app, automation)
        assert ui.U.IsWindowEnabled(app.control('select')) and ui.U.IsWindowEnabled(app.control('copy'))
        ui.command(app, 107)
        ui.command(app, 108)
        assert ' '.join(clipboard_text(app).split()) == ' '.join(first_page.split())
        record('select and copy the first TXT page through native commands')
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
