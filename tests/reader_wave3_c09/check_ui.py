"""Actions-only end-to-end native Windows UI test of the five wave-3 features on the packaged EXE.

Every feature is entered through the real native menu command ids (the ids the native menu items carry), real
common file/folder dialogs, real message boxes and the real dialog buttons. Nothing is called through a test hook.
"""
import argparse
import ctypes as C
from ctypes import wintypes as W
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests/reader_windows_preferences'))
import check_ui as P  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parent))
import needles as N  # noqa: E402

U, send, text, A = P.U, P.send, P.text, P.A
U.GetSubMenu.argtypes = [W.HANDLE, C.c_int]
U.GetSubMenu.restype = W.HANDLE
U.GetMenuItemID.argtypes = [W.HANDLE, C.c_int]
U.GetMenuItemID.restype = W.UINT
U.GetMenu.argtypes = [W.HWND]
U.GetMenu.restype = W.HANDLE
U.GetParent.argtypes = [W.HWND]
U.GetParent.restype = W.HWND
U.GetDlgCtrlID.argtypes = [W.HWND]
U.GetDlgCtrlID.restype = C.c_int
U.EnumChildWindows.argtypes = [W.HWND, P.ENUM, W.LPARAM]
U.PostMessageW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM]

ANNOTATIONS, FONTS, ORIGINALS, BACK, FORWARD, SYNC = range(47001, 47007)
ROWS, MESSAGE, B1, B2, B3, B4, B5, CLOSE = 47101, 47102, 47111, 47112, 47113, 47114, 47115, 47120
RECORDS_ROWS, RECORDS_HIGHLIGHT, RECORDS_OPEN, RECORDS_CLOSE = 211, 216, 220, 227
SELECT_ALL = 107
REQUIRED = ['native-menu-entries', 'history-back-forward-after-real-location', 'annotation-export-cancel-then-real-files',
            'originals-directory-cancel-then-per-item-results', 'originals-rerun-reports-existing',
            'font-import-failure-keeps-library-and-frame', 'font-import-and-switch-changes-page',
            'font-restore-builtin', 'font-choice-survives-restart', 'sync-status-read-only-unknown',
            'annotation-preview-writes-nothing', 'annotation-confirm-cancel-writes-nothing',
            'annotation-confirmed-commit-writes-records', 'annotation-repeat-is-duplicate',
            'annotation-tampered-file-refused']


def menu_ids(menu):
    found = set()
    for i in range(U.GetMenuItemCount(menu)):
        child = U.GetSubMenu(menu, i)
        if child:
            found.update(menu_ids(child))
        else:
            found.add(U.GetMenuItemID(menu, i))
    return found


def class_of(window):
    name = C.create_unicode_buffer(100)
    U.GetClassNameW(window, name, 100)
    return name.value


def owned(app, predicate):
    found = []

    @P.ENUM
    def visit(window, unused):
        pid = W.DWORD()
        U.GetWindowThreadProcessId(window, C.byref(pid))
        if pid.value == app.process.pid and window != app.window and U.IsWindowVisible(window) and predicate(window):
            found.append(window)
        return True
    U.EnumWindows(visit, 0)
    return found[-1] if found else None


def feature_dialog(app):
    return owned(app, lambda w: bool(U.GetDlgItem(w, ROWS)) and bool(U.GetDlgItem(w, MESSAGE)) and class_of(w) == 'EXReaderWave3')


def records_dialog(app):
    return owned(app, lambda w: bool(U.GetDlgItem(w, RECORDS_ROWS)))


def system_dialog(app):
    return owned(app, lambda w: class_of(w) == '#32770' and bool(U.GetDlgItem(w, 1)))


def rows(dialog, control=ROWS):
    box = U.GetDlgItem(dialog, control)
    out = []
    for i in range(send(box, 0x18B)):
        length = send(box, 0x18A, i)
        value = C.create_unicode_buffer(length + 2)
        send(box, 0x189, i, C.addressof(value))
        out.append(value.value)
    return out


def message(dialog):
    return text(U.GetDlgItem(dialog, MESSAGE))


def post_click(dialog, identifier):
    assert U.PostMessageW(U.GetDlgItem(dialog, identifier), 0xF5, 0, 0)


def fill_system_dialog(app, path):
    """Type a path into the native file/folder dialog and accept it, as a user would."""
    dialog = app.wait(lambda: system_dialog(app), timeout=30)
    candidates = []

    @P.ENUM
    def child(window, unused):
        if class_of(window) == 'Edit' and U.IsWindowVisible(window):
            parent = window
            for _ in range(5):
                if U.GetDlgCtrlID(parent) in (1148, 1152):
                    candidates.append(window)
                    break
                parent = U.GetParent(parent)
                if not parent or parent == dialog:
                    break
        return True
    U.EnumChildWindows(dialog, child, 0)
    assert len(candidates) == 1, ('native filename edit', len(candidates))
    P.set_text(candidates[0], str(Path(path).resolve()))
    for _ in range(4):
        if not U.IsWindow(dialog):
            break
        try:
            send(dialog, 0x111, 1)
        except TimeoutError:
            pass
        time.sleep(.4)
    app.wait(lambda: not U.IsWindow(dialog), timeout=30)


def cancel_system_dialog(app):
    dialog = app.wait(lambda: system_dialog(app), timeout=30)
    send(dialog, 0x111, 2)
    app.wait(lambda: not U.IsWindow(dialog), timeout=30)


def open_feature(app, identifier):
    app.wait_idle()
    app.focus()
    send(app.window, 0x111, identifier)
    return app.wait(lambda: feature_dialog(app), timeout=30)


def close_feature(app, dialog):
    send(dialog, 0x111, CLOSE)
    app.wait(lambda: not U.IsWindow(dialog), timeout=20)
    app.wait_idle()


def wait_message(app, dialog, needle, timeout=240):
    app.wait(lambda: needle in message(dialog), timeout=timeout)
    return message(dialog)


def record_count(app):
    app.focus()
    A.tap(ord('L'), (A.VK_CONTROL,))
    dialog = app.wait(lambda: records_dialog(app), timeout=30)
    app.wait(lambda: len(rows(dialog, RECORDS_ROWS)) >= 1 and N.READING not in text(U.GetDlgItem(dialog, 212)), timeout=60)
    count = len(rows(dialog, RECORDS_ROWS))
    return dialog, count


def close_records(app, dialog):
    send(dialog, 0x111, RECORDS_CLOSE)
    app.wait(lambda: not U.IsWindow(dialog), timeout=20)
    app.wait_idle()


def import_and_open(app, fixture):
    app.focus()
    A.tap(ord('O'), (A.VK_CONTROL,))
    fill_system_dialog(app, fixture)
    app.wait(lambda: send(app.control('books'), 0x18B) == 1, timeout=60)
    app.wait_idle()
    send(app.control('books'), 0x186, 0)
    app.click('open')
    app.wait_idle()
    app.wait(lambda: P.page_number(app.label()) >= 1, timeout=60)


def page_hash(app, folder, name):
    path = folder / name
    P.M.screenshot(app.control('page'), path)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert os.name == 'nt' and os.environ.get('GITHUB_ACTIONS') == 'true'
    parser = argparse.ArgumentParser()
    for name in ('candidate', 'font', 'fixtures', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    fixture = (args.fixtures / 'Reading sample.txt').resolve()
    original_bytes = fixture.read_bytes()
    result = dict(accepted=False, source_sha=os.environ['GITHUB_SHA'], run_id=os.environ['GITHUB_RUN_ID'],
                  attempt=os.environ['GITHUB_RUN_ATTEMPT'], consumer_sha256=hashlib.sha256(args.candidate.read_bytes()).hexdigest(),
                  checks=[], problems=[], scope='native wave-3 feature adoption on the packaged Windows EXE')
    app = None
    exports, originals = out / 'exports', out / 'originals'
    exports.mkdir()
    originals.mkdir()

    def record(name):
        result['checks'].append(dict(name=name, passed=True, pid=app.process.pid))

    try:
        app = P.App(args.candidate.resolve(), args.font.resolve(), out / 'profile-a')
        app.wait_idle()
        import_and_open(app, fixture)

        ids = menu_ids(U.GetMenu(app.window))
        assert {ANNOTATIONS, FONTS, ORIGINALS, BACK, FORWARD, SYNC} <= ids, sorted(ids)
        record('native-menu-entries')

        # --- history: only a real located jump moves the cursor ---------------------------------
        # A bookmark is a point capture and the records owner refuses to open it without
        # content; a highlight of the real page text is located, so the jump is a true one.
        first = app.label()
        app.focus()
        send(app.window, 0x111, SELECT_ALL)
        app.wait_idle()
        dialog, _ = record_count(app)
        send(U.GetDlgItem(dialog, RECORDS_HIGHLIGHT), 0xF5, timeout=5000)
        app.wait(lambda: len(rows(dialog, RECORDS_ROWS)) >= 2, timeout=60)
        close_records(app, dialog)
        app.click('next')
        app.wait_idle()
        app.click('next')
        app.wait_idle()
        third = app.label()
        assert third != first
        dialog, _ = record_count(app)
        send(U.GetDlgItem(dialog, RECORDS_ROWS), 0x186, 1)
        send(U.GetDlgItem(dialog, RECORDS_OPEN), 0xF5, timeout=5000)
        app.wait_idle()
        app.wait(lambda: app.label() == first, timeout=60)
        close_records(app, dialog)
        app.focus()
        A.tap(0xDB, (A.VK_CONTROL,))
        app.wait_idle()
        app.wait(lambda: app.label() == third, timeout=60)
        A.tap(0xDD, (A.VK_CONTROL,))
        app.wait_idle()
        app.wait(lambda: app.label() == first, timeout=60)
        record('history-back-forward-after-real-location')

        # --- export annotations ------------------------------------------------------------------
        dialog = open_feature(app, ANNOTATIONS)
        post_click(dialog, B1)
        cancel_system_dialog(app)
        assert N.EXPORT_CANCELLED in wait_message(app, dialog, N.EXPORT_CANCELLED, 30)
        assert not list(exports.iterdir())
        post_click(dialog, B1)
        fill_system_dialog(app, exports / 'a.jsonl')
        wait_message(app, dialog, N.EXPORT_DONE)
        lines = (exports / 'a.jsonl').read_text(encoding='utf-8').splitlines()
        parsed = [json.loads(line) for line in lines]
        assert 'exreader-annotation-export-raw3' in lines[0] and len(parsed) >= 3, lines[:2]
        assert (exports / 'a.md').is_file() and not [p for p in exports.iterdir() if p.suffix == '.tmp']
        close_feature(app, dialog)
        record('annotation-export-cancel-then-real-files')

        # --- export original ---------------------------------------------------------------------
        dialog = open_feature(app, ORIGINALS)
        assert len(rows(dialog)) >= 1
        send(U.GetDlgItem(dialog, ROWS), 0x185, 1, 0)
        post_click(dialog, B1)
        cancel_system_dialog(app)
        wait_message(app, dialog, N.DIRECTORY_CANCELLED, 30)
        assert not list(originals.iterdir())
        post_click(dialog, B1)
        fill_system_dialog(app, originals)
        wait_message(app, dialog, N.ORIGINALS_DONE)
        files = [p for p in originals.iterdir()]
        assert len(files) == 1 and re.fullmatch(r'[0-9a-fA-F]{64}\.txt', files[0].name), [p.name for p in files]
        assert files[0].read_bytes() == original_bytes and hashlib.sha256(original_bytes).hexdigest() == files[0].stem.lower()
        assert N.EXPORTED in rows(dialog)[0]
        record('originals-directory-cancel-then-per-item-results')
        send(U.GetDlgItem(dialog, ROWS), 0x185, 1, 0)
        post_click(dialog, B1)
        fill_system_dialog(app, originals)
        app.wait(lambda: N.EXISTING in ''.join(rows(dialog)), timeout=120)
        assert len(list(originals.iterdir())) == 1
        close_feature(app, dialog)
        record('originals-rerun-reports-existing')

        # --- fonts ---------------------------------------------------------------------------------
        before = page_hash(app, out, 'font-before.bmp')
        label_before = P.page_number(app.label())
        dialog = open_feature(app, FONTS)
        assert len(rows(dialog)) == 1
        bad = out / 'bad.ttf'
        bad.write_bytes(b'not a font ' * 64)
        post_click(dialog, B1)
        fill_system_dialog(app, bad)
        wait_message(app, dialog, N.FONT_IMPORT_FAILED, 60)
        assert len(rows(dialog)) == 1 and P.page_number(app.label()) == label_before
        record('font-import-failure-keeps-library-and-frame')
        post_click(dialog, B1)
        fill_system_dialog(app, ROOT / 'tests/fixtures/fonts/primary.ttf')
        wait_message(app, dialog, N.FONT_IMPORTED, 120)
        app.wait(lambda: len(rows(dialog)) == 2, timeout=30)
        send(U.GetDlgItem(dialog, ROWS), 0x186, 1)
        post_click(dialog, B2)
        wait_message(app, dialog, N.FONT_SWITCHED, 240)
        app.wait_idle()
        assert N.IN_USE in rows(dialog)[1]
        close_feature(app, dialog)
        changed = page_hash(app, out, 'font-after-switch.bmp')
        assert changed != before and P.page_number(app.label()) >= 1 and label_before >= 1
        record('font-import-and-switch-changes-page')
        dialog = open_feature(app, FONTS)
        post_click(dialog, B3)
        wait_message(app, dialog, N.FONT_SWITCHED, 240)
        app.wait_idle()
        assert N.IN_USE in rows(dialog)[0]
        close_feature(app, dialog)
        assert page_hash(app, out, 'font-restored.bmp') != changed
        record('font-restore-builtin')
        dialog = open_feature(app, FONTS)
        send(U.GetDlgItem(dialog, ROWS), 0x186, 1)
        post_click(dialog, B2)
        wait_message(app, dialog, N.FONT_SWITCHED, 240)
        app.wait_idle()
        close_feature(app, dialog)
        saved = (out / 'profile-a/wave3-font.txt').read_text(encoding='ascii')
        assert re.fullmatch(r'[0-9a-f]{64}', saved), saved

        # --- sync status ---------------------------------------------------------------------------
        dialog = open_feature(app, SYNC)
        listing = rows(dialog)
        assert listing and N.UNKNOWN in listing[0], listing
        assert N.NOT_SYNCED in message(dialog)
        assert U.GetDlgItem(dialog, B1) and not any(U.GetDlgItem(dialog, i) for i in (B2, B3, B4, B5))
        post_click(dialog, B1)
        time.sleep(.5)
        assert N.UNKNOWN in rows(dialog)[0]
        close_feature(app, dialog)
        record('sync-status-read-only-unknown')

        app.close_app()
        app = P.App(args.candidate.resolve(), args.font.resolve(), out / 'profile-a', existing=True)
        app.wait_idle()
        dialog = open_feature(app, FONTS)
        assert N.IN_USE in rows(dialog)[1], rows(dialog)
        close_feature(app, dialog)
        record('font-choice-survives-restart')
        app.close_app()

        # --- import into a second profile ---------------------------------------------------------
        app = P.App(args.candidate.resolve(), args.font.resolve(), out / 'profile-b')
        app.wait_idle()
        import_and_open(app, fixture)
        records, before_count = record_count(app)
        close_records(app, records)
        dialog = open_feature(app, ANNOTATIONS)
        post_click(dialog, B2)
        fill_system_dialog(app, exports / 'a.jsonl')
        summary = wait_message(app, dialog, N.PREVIEW_DONE)
        created = int(re.search(re.escape(N.WILL_ADD) + r' (\d+)', summary).group(1))
        assert created >= 1 and U.IsWindowEnabled(U.GetDlgItem(dialog, B3)) and any(N.ADDED in row for row in rows(dialog))
        records, count = record_count(app)
        assert count == before_count
        close_records(app, records)
        record('annotation-preview-writes-nothing')
        post_click(dialog, B3)
        confirm = app.wait(lambda: system_dialog(app), timeout=30)
        send(confirm, 0x111, 2)
        app.wait(lambda: not U.IsWindow(confirm), timeout=20)
        wait_message(app, dialog, N.CONFIRM_CANCELLED, 30)
        records, count = record_count(app)
        assert count == before_count
        close_records(app, records)
        record('annotation-confirm-cancel-writes-nothing')
        post_click(dialog, B3)
        confirm = app.wait(lambda: system_dialog(app), timeout=30)
        send(confirm, 0x111, 1)
        wait_message(app, dialog, N.IMPORT_DONE, 240)
        records, count = record_count(app)
        assert count > before_count, (count, before_count)
        close_records(app, records)
        record('annotation-confirmed-commit-writes-records')
        post_click(dialog, B2)
        fill_system_dialog(app, exports / 'a.jsonl')
        again = wait_message(app, dialog, N.PREVIEW_DONE)
        assert N.DUPLICATE in again and re.search(re.escape(N.WILL_ADD) + ' 0', again), again
        record('annotation-repeat-is-duplicate')
        tampered = out / 'tampered.jsonl'
        data = (exports / 'a.jsonl').read_text(encoding='utf-8')
        found = re.search(r'[0-9a-f]{64}', data[data.index('\n'):])
        assert found
        flipped = '0' if data[data.index('\n') + found.start()] != '0' else '1'
        position = data.index('\n') + found.start()
        tampered.write_text(data[:position] + flipped + data[position + 1:], encoding='utf-8', newline='')
        post_click(dialog, B2)
        fill_system_dialog(app, tampered)
        refused = wait_message(app, dialog, N.PREVIEW_REFUSED, 120)
        assert not U.IsWindowEnabled(U.GetDlgItem(dialog, B3)), refused
        records, count2 = record_count(app)
        assert count2 == count
        close_records(app, records)
        close_feature(app, dialog)
        record('annotation-tampered-file-refused')
        app.close_app()
        app = None
        result['accepted'] = [row['name'] for row in result['checks']] == REQUIRED
    except BaseException:
        result['problems'].append(traceback.format_exc())
        traceback.print_exc()
        if app is not None:
            try:
                P.M.screenshot(app.window, out / 'failure.bmp')
            except BaseException:  # noqa: BLE001
                pass
            try:
                app.process.kill()
            except BaseException:  # noqa: BLE001
                pass
    result['count'] = len(result['checks'])
    (out / 'report.json').write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if not result['accepted']:
        sys.exit(1)


if __name__ == '__main__':
    main()
