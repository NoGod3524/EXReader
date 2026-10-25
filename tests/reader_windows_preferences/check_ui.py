"""Actions-only real Win32 F3 reading preferences and page theme checks.

Every observation is a real native input (SendInput), a real control message, an
independent capture of the running window, the public F3 document on disk or an
independent SQLite read. No private host function is called and no host success
flag is trusted.
"""
import argparse
import ctypes as C
from ctypes import wintypes as W
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import struct
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests/windows_host'))
import check_metadata_ui as M
from check_metadata_ui import U, ENUM, send, set_text, text
sys.path.insert(0, str(ROOT / 'tests/reader_windows_account'))
import check_a11y_ui as A

MESSAGE, TOGGLE = 278, 279
PAGE, STATUS = 123, 125
FONT, LINE, PARAGRAPH, MARGIN, THEME, DIRECTION, INPUT, ZOOM = 261, 262, 263, 264, 265, 266, 267, 268
LIGHT_FG, LIGHT_BG, DARK_FG, DARK_BG = 269, 270, 271, 272
APPLY, DEFAULTS, IMPORT, REBUILD, CLOSE = 273, 274, 275, 276, 277

REQUIRED = [
    'native-shortcut-opens-settings-dialog', 'one-native-menu-entry-and-collapsible-controls',
    'default-start-keeps-original-page-pixels', 'explicit-apply-writes-public-f3-document',
    'light-theme-page-corner-and-ink', 'dark-theme-uses-actual-sdk-background',
    'authored-image-interior-preserved', 'fixed-page-content-and-colours-untouched',
    'fixed-page-zoom-uses-real-renderer', 'fixed-page-zoom-refusal-is-explicit',
    'system-theme-notification-repaints', 'rapid-changes-end-in-one-accepted-state',
    'close-and-reopen-generations', 'unknown-version-file-not-overwritten',
    'corrupt-file-not-overwritten', 'explicit-rebuild-of-unreadable-file',
    'failed-save-keeps-accepted-frame', 'legacy-import-is-explicit',
    'hardware-keys-follow-selected-mode', 'tap-mode-turns-pages',
    'rtl-direction-reverses-tap', 'swipe-mode-turns-pages',
    'reading-position-and-notes-survive-settings', 'restart-reopens-accepted-persistence',
    'close-during-settings-job-keeps-one-consistent-state']

U.GetClientRect.argtypes = [W.HWND, C.POINTER(W.RECT)]
U.GetClientRect.restype = W.BOOL
U.GetDC.argtypes = [W.HWND]
U.GetDC.restype = W.HDC
U.SetForegroundWindow.argtypes = [W.HWND]
U.SetForegroundWindow.restype = W.BOOL
U.GetForegroundWindow.restype = W.HWND
U.GetMenu.argtypes = [W.HWND]
U.GetMenu.restype = W.HANDLE
U.GetMenuItemCount.argtypes = [W.HANDLE]
U.GetMenuItemCount.restype = C.c_int
U.SetWindowPos.argtypes = [W.HWND, W.HWND, C.c_int, C.c_int, C.c_int, C.c_int, W.UINT]
U.SetWindowPos.restype = W.BOOL
U.SetCursorPos.argtypes = [C.c_int, C.c_int]
U.SetCursorPos.restype = W.BOOL
U.ClientToScreen.argtypes = [W.HWND, C.POINTER(W.POINT)]
U.ClientToScreen.restype = W.BOOL
U.GetSystemMetrics.argtypes = [C.c_int]
U.GetSystemMetrics.restype = C.c_int
G = C.WinDLL('gdi32', use_last_error=True)
G.CreateCompatibleDC.argtypes = [W.HDC]
G.CreateCompatibleDC.restype = W.HDC
G.CreateCompatibleBitmap.argtypes = [W.HDC, C.c_int, C.c_int]
G.CreateCompatibleBitmap.restype = W.HBITMAP
G.SelectObject.argtypes = [W.HDC, W.HANDLE]
G.SelectObject.restype = W.HANDLE
G.BitBlt.argtypes = [W.HDC, C.c_int, C.c_int, C.c_int, C.c_int, W.HDC, C.c_int, C.c_int, W.DWORD]
G.GetDIBits.argtypes = [W.HDC, W.HBITMAP, W.UINT, W.UINT, C.c_void_p, C.c_void_p, W.UINT]
G.DeleteObject.argtypes = [W.HANDLE]
G.DeleteDC.argtypes = [W.HDC]
KERNEL = C.WinDLL('kernel32', use_last_error=True)
KERNEL.CreateFileW.argtypes = [W.LPCWSTR, W.DWORD, W.DWORD, W.LPVOID, W.DWORD, W.DWORD, W.HANDLE]
KERNEL.CreateFileW.restype = W.HANDLE
KERNEL.CloseHandle.argtypes = [W.HANDLE]
KERNEL.CloseHandle.restype = W.BOOL

MOUSEEVENTF_MOVE, MOUSEEVENTF_ABSOLUTE = 0x0001, 0x8000
MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x0002, 0x0004
WM_CLOSE, WM_SETTINGCHANGE = 0x0010, 0x001A


class MOUSEINPUT(C.Structure):
    _fields_ = [('dx', C.c_long), ('dy', C.c_long), ('mouseData', C.c_ulong), ('dwFlags', C.c_ulong),
                ('time', C.c_ulong), ('dwExtraInfo', C.POINTER(C.c_ulong))]


class INPUTUNION(C.Union):
    _fields_ = [('mi', MOUSEINPUT)]


class INPUT(C.Structure):
    _fields_ = [('type', C.c_ulong), ('u', INPUTUNION)]


def shot(hwnd, path=None):
    """Independent capture of one window client area, returned top-down BGRA."""
    rect = W.RECT()
    assert U.GetClientRect(hwnd, C.byref(rect))
    width, height = rect.right, rect.bottom
    assert 16 <= width <= 4096 and 16 <= height <= 4096, (width, height)
    source = U.GetDC(hwnd)
    memory = G.CreateCompatibleDC(source)
    bitmap = G.CreateCompatibleBitmap(source, width, height)
    old = G.SelectObject(memory, bitmap)
    try:
        time.sleep(.2)
        assert G.BitBlt(memory, 0, 0, width, height, source, 0, 0, 0x00CC0020)
        G.SelectObject(memory, old)
        header = struct.pack('<IiiHHIIiiII', 40, width, height, 1, 32, 0, width * height * 4, 0, 0, 0, 0)
        info = C.create_string_buffer(header)
        raw = C.create_string_buffer(width * height * 4)
        assert G.GetDIBits(memory, bitmap, 0, height, raw, info, 0) == height
        body = raw.raw
        if path:
            Path(path).write_bytes(struct.pack('<2sIHHI', b'BM', 54 + len(body), 0, 0, 54) + header + body)
        rows = [body[row * width * 4:(row + 1) * width * 4] for row in range(height)]
        return width, height, b''.join(reversed(rows))
    finally:
        G.SelectObject(memory, old)
        G.DeleteObject(bitmap)
        G.DeleteDC(memory)
        U.ReleaseDC(hwnd, source)


def at(image, x, y):
    width, height, body = image
    x, y = int(x), int(y)
    if not (0 <= x < width and 0 <= y < height):
        raise AssertionError('sample outside the window: %s in %sx%s' % ((x, y), width, height))
    index = (y * width + x) * 4
    return body[index + 2], body[index + 1], body[index]


def near(pixel, expected, tolerance=12):
    return all(abs(pixel[index] - expected[index]) <= tolerance for index in range(3))


def inner(image, pad=6):
    """Window pixels away from the client edge (focus ring and border excluded)."""
    width, height, body = image
    return b''.join(body[(y * width + pad) * 4:(y * width + width - pad) * 4]
                    for y in range(pad, height - pad))


def layout(client, bitmap):
    width, height = client
    bw, bh = bitmap
    scale = min((width - 8.0) / bw, (height - 8.0) / bh)
    return int((width - bw * scale) / 2), int((height - bh * scale) / 2), int(bw * scale), int(bh * scale)


def page_number(label):
    found = re.search(r'\u7b2c (\d+) \u9875', label)
    return int(found.group(1)) if found else -1


def page_client(app):
    rect = W.RECT()
    assert U.GetClientRect(app.control('page'), C.byref(rect))
    return rect.right, rect.bottom


def document(profile):
    path = Path(profile) / 'preferences.json'
    if not path.exists():
        return None, b''
    return json.loads(path.read_text(encoding='utf-8')), path.read_bytes()


class App(M.MetadataApp):
    def find_dialog(self):
        found = []

        @ENUM
        def visit(window, unused):
            pid = W.DWORD()
            U.GetWindowThreadProcessId(window, C.byref(pid))
            if pid.value == self.process.pid and U.IsWindowVisible(window) and U.GetDlgItem(window, MESSAGE):
                found.append(window)
            return True
        U.EnumWindows(visit, 0)
        return found[-1] if found else None

    def wait_idle(self, timeout=180):
        # While the settings dialog owns the input the owner window stays
        # disabled, so the dialog's own Apply button is the idle signal.
        def ready():
            handle = self.find_dialog()
            if handle:
                return bool(U.IsWindowEnabled(U.GetDlgItem(handle, APPLY)))
            return bool(U.IsWindowEnabled(self.control('import')))
        self.wait(ready, timeout=timeout)
        time.sleep(.2)
        self.wait(ready, timeout=timeout)

    def focus(self):
        def ready():
            A.USER32.BringWindowToTop(self.window)
            U.SetForegroundWindow(self.window)
            return U.GetForegroundWindow() == self.window
        self.wait(ready, timeout=10)

    def settle(self, size=(1100, 720)):
        U.SetWindowPos(self.window, 0, 0, 0, size[0], size[1], 0x0002 | 0x0004 | 0x0040)
        time.sleep(.6)
        return page_client(self)

    def dialog(self):
        return self.wait(self.find_dialog, timeout=20)

    def open_dialog(self):
        self.focus()
        A.tap(0xBC, (A.VK_CONTROL,))
        return self.dialog()

    def field(self, identifier):
        return U.GetDlgItem(self.dialog(), identifier)

    def message(self):
        return text(U.GetDlgItem(self.dialog(), MESSAGE))

    def label(self):
        return text(self.control('page'))

    def status(self):
        return text(self.control('status'))

    def page_shot(self, name=None, output=None):
        if name and output:
            return shot(self.control('page'), Path(output) / name)
        return shot(self.control('page'))

    def fit_page(self, target):
        target = tuple(target)
        for _ in range(5):
            current = page_client(self)
            if current == target:
                return
            bounds = W.RECT()
            assert U.GetWindowRect(self.window, C.byref(bounds))
            width = bounds.right - bounds.left + (target[0] - current[0])
            height = bounds.bottom - bounds.top + (target[1] - current[1])
            U.SetWindowPos(self.window, 0, 0, 0, width, height, 0x0002 | 0x0004)
            time.sleep(.4)
        assert page_client(self) == target, (page_client(self), target)

    def click_client(self, hwnd, x, y, hold=.05):
        point = W.POINT(int(x), int(y))
        assert U.ClientToScreen(hwnd, C.byref(point))
        absolute = self.absolute(point.x, point.y)
        self.inject(absolute, MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE)
        time.sleep(hold)
        self.inject(absolute, MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_LEFTDOWN)
        time.sleep(hold)
        self.inject(absolute, MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_LEFTUP)
        time.sleep(.3)

    def drag(self, hwnd, start, end, steps=6):
        a, b = W.POINT(int(start[0]), int(start[1])), W.POINT(int(end[0]), int(end[1]))
        assert U.ClientToScreen(hwnd, C.byref(a)) and U.ClientToScreen(hwnd, C.byref(b))
        self.inject(self.absolute(a.x, a.y), MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE)
        time.sleep(.05)
        self.inject(self.absolute(a.x, a.y), MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_LEFTDOWN)
        for step in range(1, steps + 1):
            x = a.x + (b.x - a.x) * step // steps
            y = a.y + (b.y - a.y) * step // steps
            self.inject(self.absolute(x, y), MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE)
            time.sleep(.06)
        self.inject(self.absolute(b.x, b.y), MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_LEFTUP)
        time.sleep(.35)

    @staticmethod
    def absolute(x, y):
        left, top = U.GetSystemMetrics(76), U.GetSystemMetrics(77)
        width, height = U.GetSystemMetrics(78), U.GetSystemMetrics(79)
        return (int((x - left) * 65535 / (width - 1)), int((y - top) * 65535 / (height - 1)))

    @staticmethod
    def inject(absolute, flags):
        item = INPUT(type=0)
        item.u.mi = MOUSEINPUT(dx=absolute[0], dy=absolute[1], mouseData=0, dwFlags=flags, time=0,
                               dwExtraInfo=None)
        assert A.USER32.SendInput(1, C.byref(item), C.sizeof(INPUT)) == 1

    def choose(self, identifier, index):
        send(U.GetDlgItem(self.dialog(), identifier), 0x14E, index, 0)

    def press(self, identifier):
        send(U.GetDlgItem(self.dialog(), identifier), 0xF5, timeout=5000)

    def apply(self):
        self.press(APPLY)
        self.wait_idle(timeout=180)

    def close_dialog(self):
        dialog = self.dialog()
        self.press(CLOSE)
        self.wait(lambda: not U.IsWindow(dialog), timeout=20)

    def wait_enabled(self, identifier):
        self.wait(lambda: U.IsWindowEnabled(U.GetDlgItem(self.dialog(), identifier)), timeout=180)
        self.wait_idle(timeout=180)

    def close_app(self):
        send(self.window, WM_CLOSE)
        try:
            self.process.wait(timeout=90)
        except Exception:
            self.process.kill()
            self.process.wait()
        self.log.close()


def immutable(app):
    with sqlite3.connect(app.db) as db:
        return tuple(db.execute('SELECT * FROM ' + name).fetchall()
                     for name in ('notes', 'epub_notes', 'fixed_notes'))


def main():
    assert os.name == 'nt' and os.environ.get('GITHUB_ACTIONS') == 'true'
    parser = argparse.ArgumentParser()
    for name in ('candidate', 'baseline', 'font', 'fixtures', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    probes = output / 'captures'
    probes.mkdir()
    profile = output / 'profile'
    baseline_profile = output / 'baseline-profile'
    checks, problems = [], []
    app = None
    restore = None
    report = dict(accepted=False, source_sha=os.environ['GITHUB_SHA'], run_id=os.environ['GITHUB_RUN_ID'],
                  attempt=os.environ['GITHUB_RUN_ATTEMPT'], checks=checks, problems=problems,
                  transport='SendInput+UIAutomation+Win32', complete_product=False,
                  performance_accepted=False, screen_reader_accepted=False,
                  scope='native Windows UI only; not device, performance or screen-reader acceptance')
    target = [0, 0]

    def record(name, condition, detail=None):
        if not condition:
            raise AssertionError('failed check: ' + name)
        assert name not in checks, name
        checks.append(name)
        print(json.dumps({'check': name, 'pass': True, 'detail': detail}, ensure_ascii=True), flush=True)

    def launch(exe, where, existing=False):
        nonlocal app
        app = App(exe.resolve(), args.font.resolve(), where, existing=existing)
        app.wait_idle()
        app.settle()
        if target[0]:
            app.fit_page(target)
        return app

    try:
        import winreg

        launch(args.candidate, profile)
        app.import_file(args.fixtures / 'Reading sample.txt')
        app.open('Reading sample')
        app.wait_idle()
        dialog = app.open_dialog()
        record('native-shortcut-opens-settings-dialog', bool(dialog) and bool(U.IsWindowVisible(dialog)))
        hidden = not U.IsWindowVisible(U.GetDlgItem(dialog, LIGHT_FG))
        app.press(TOGGLE)
        shown = bool(U.IsWindowVisible(U.GetDlgItem(dialog, LIGHT_FG)))
        menu = U.GetMenu(app.window)
        record('one-native-menu-entry-and-collapsible-controls',
               hidden and shown and menu and U.GetMenuItemCount(menu) == 1)
        app.close_dialog()

        # ---- an untouched installation renders exactly like the option-off host
        candidate_page = page_client(app)
        baseline = launch(args.baseline, baseline_profile)
        baseline.import_file(args.fixtures / 'Reading sample.txt')
        baseline.open('Reading sample')
        baseline.wait_idle()
        baseline_page = page_client(baseline)
        target[0] = min(candidate_page[0], baseline_page[0]) - 2
        target[1] = min(candidate_page[1], baseline_page[1]) - 2
        baseline.fit_page(target)
        right = baseline.page_shot('default-off.bmp', probes)
        baseline.close_app()
        launch(args.candidate, profile, existing=True)
        app.open('Reading sample')
        app.wait_idle()
        app.fit_page(target)
        left = app.page_shot('default-on.bmp', probes)
        record('default-start-keeps-original-page-pixels', inner(left) == inner(right))

        # ---- explicit light selection ----------------------------------------
        dialog = app.open_dialog()
        set_text(app.field(FONT), '24')
        set_text(app.field(LINE), '1.60')
        set_text(app.field(PARAGRAPH), '12')
        set_text(app.field(MARGIN), '48')
        app.choose(THEME, 0)
        app.apply()
        value, raw = document(profile)
        record('explicit-apply-writes-public-f3-document',
               value is not None and len(value) == 14 and value['format'] == 'exreader-preferences' and
               value['format_version'] == 1 and abs(value['font_size'] - 24) < .01 and
               value['theme'] == 'light' and value['page_turn_input'] == 'tap')
        app.close_dialog()
        image = app.page_shot('light.bmp', probes)
        dx, dy, width, height = layout(page_client(app), (720, 1040))
        corner = at(image, dx + 6, dy + 6)
        surround = at(image, max(dx - 4, 1), max(dy - 4, 1))
        ink = [at(image, x, y) for x in range(dx + 40, dx + width - 40, 7)
               for y in range(dy + 40, dy + min(height, 500) - 10, 5)]
        ink = [pixel for pixel in ink if not near(pixel, corner, 16)]
        record('light-theme-page-corner-and-ink',
               near(corner, (255, 255, 255), 2) and near(surround, (255, 255, 255), 2) and
               bool(ink) and min(sum(pixel) for pixel in ink) < 260,
               dict(corner=corner, ink=len(ink)))

        # ---- the actual SDK canvas really is the page background -------------
        dialog = app.open_dialog()
        app.choose(THEME, 1)
        app.apply()
        app.close_dialog()
        image = app.page_shot('dark.bmp', probes)
        dark_corner = at(image, dx + 6, dy + 6)
        bright = [at(image, x, y) for x in range(dx + 40, dx + width - 40, 7)
                  for y in range(dy + 40, dy + min(height, 500) - 10, 5)]
        bright = [pixel for pixel in bright if not near(pixel, dark_corner, 16)]
        record('dark-theme-uses-actual-sdk-background',
               near(dark_corner, (16, 16, 16), 3) and bool(bright) and
               max(sum(pixel) for pixel in bright) > 500,
               dict(corner=dark_corner, ink=len(bright)))

        # ---- authored image interiors keep their real coordinates ------------
        app.import_file(args.fixtures / 'Picture book.epub')
        app.open('Picture book')
        app.wait_idle()
        app.fit_page(target)
        dx, dy, width, height = layout(page_client(app), (720, 1040))
        light = app.page_shot('picture-light.bmp', probes)
        dialog = app.open_dialog()
        app.choose(THEME, 0)
        app.apply()
        app.close_dialog()
        light = app.page_shot('picture-light.bmp', probes)
        dialog = app.open_dialog()
        app.choose(THEME, 1)
        app.apply()
        app.close_dialog()
        dark = app.page_shot('picture-dark.bmp', probes)

        def authored(image):
            return {(x, y) for x in range(dx + 2, dx + width - 2, 2)
                    for y in range(dy + 2, dy + height - 2, 2)
                    if near(at(image, x, y), (51, 102, 204), 26)}

        picture_light, picture_dark = authored(light), authored(dark)
        same = all(near(at(light, x, y), at(dark, x, y), 10) for x, y in list(picture_light)[:300])
        record('authored-image-interior-preserved',
               len(picture_light) > 40 and picture_light == picture_dark and same,
               dict(pixels=len(picture_light)))

        # ---- fixed pages keep their own content and colours ------------------
        app.import_file(args.fixtures / 'Fixed page.pdf')
        app.open('Fixed page')
        app.wait_idle()
        app.fit_page(target)
        dialog = app.open_dialog()
        app.choose(THEME, 0)
        app.apply()
        app.close_dialog()
        fixed_light = app.page_shot('fixed-light.bmp', probes)
        dialog = app.open_dialog()
        app.choose(THEME, 1)
        app.apply()
        app.close_dialog()
        fixed_dark = app.page_shot('fixed-dark.bmp', probes)
        record('fixed-page-content-and-colours-untouched', inner(fixed_light) == inner(fixed_dark))

        # ---- the installed fixed renderer owns the zoom ----------------------
        dialog = app.open_dialog()
        set_text(app.field(ZOOM), '150')
        app.apply()
        app.close_dialog()
        zoomed = app.page_shot('fixed-zoom150.bmp', probes)
        value, _ = document(profile)
        record('fixed-page-zoom-uses-real-renderer',
               zoomed != fixed_dark and value is not None and value['fixed_page_zoom'] == 150)

        # ---- one valid F3 zoom the host cannot honour is reported ------------
        app.import_file(args.fixtures / 'Large comic.cbz')
        app.open('Large comic')
        app.wait_idle()
        app.fit_page(target)
        before, before_raw = document(profile)
        comic_before = app.page_shot('comic.bmp', probes)
        dialog = app.open_dialog()
        set_text(app.field(ZOOM), '400')
        app.press(APPLY)
        app.wait_enabled(APPLY)
        after, after_raw = document(profile)
        comic_after = app.page_shot('comic-refused.bmp', probes)
        record('fixed-page-zoom-refusal-is-explicit',
               before_raw == after_raw and before['fixed_page_zoom'] == 150 and
               inner(comic_before) == inner(comic_after),
               dict(status=app.status()))
        app.close_dialog()

        # ---- a real system appearance notification ---------------------------
        app.open('Reading sample')
        app.wait_idle()
        app.fit_page(target)
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize', 0,
                             winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE)
        previous, _ = winreg.QueryValueEx(key, 'AppsUseLightTheme')
        restore = (key, previous)

        def system(value):
            winreg.SetValueEx(key, 'AppsUseLightTheme', 0, winreg.REG_DWORD, value)
            send(app.window, WM_SETTINGCHANGE)

        system(1)
        dialog = app.open_dialog()
        app.choose(THEME, 2)
        app.apply()
        app.close_dialog()
        app.wait(lambda: near(at(app.page_shot(), dx + 6, dy + 6), (255, 255, 255), 4), timeout=90)
        system(0)
        app.wait(lambda: near(at(app.page_shot(), dx + 6, dy + 6), (16, 16, 16), 4), timeout=180)
        record('system-theme-notification-repaints',
               near(at(app.page_shot(), dx + 6, dy + 6), (16, 16, 16), 4))
        system(1)
        app.wait(lambda: near(at(app.page_shot(), dx + 6, dy + 6), (255, 255, 255), 4), timeout=180)

        # ---- rapid selections end in exactly one accepted state --------------
        for index in (1, 0, 1, 0, 1):
            if not app.dialog():
                app.open_dialog()
            app.choose(THEME, index)
            app.press(APPLY)
            time.sleep(.05)
        app.wait_enabled(APPLY)
        app.close_dialog()
        time.sleep(1.0)
        value, _ = document(profile)
        observed = at(app.page_shot('rapid.bmp', probes), dx + 6, dy + 6)
        record('rapid-changes-end-in-one-accepted-state',
               (value['theme'] == 'dark') == near(observed, (16, 16, 16), 4),
               dict(theme=value['theme'], corner=observed))

        # ---- dialog generations ----------------------------------------------
        seen = []
        for _ in range(3):
            dialog = app.open_dialog()
            seen.append(dialog)
            assert text(app.field(FONT)).startswith('24'), text(app.field(FONT))
            A.tap(0x1B)
            app.wait(lambda: not U.IsWindow(dialog), timeout=20)
        record('close-and-reopen-generations', len(set(seen)) == 3 and 0 not in seen)

        # ---- accepted settings survive a real restart ------------------------
        dialog = app.open_dialog()
        app.choose(THEME, 1)
        set_text(app.field(FONT), '30')
        app.apply()
        app.close_dialog()
        app.close_app()
        launch(args.candidate, profile, existing=True)
        app.open('Reading sample')
        app.wait_idle()
        app.fit_page(target)
        image = app.page_shot('restart.bmp', probes)
        record('restart-reopens-accepted-persistence',
               near(at(image, dx + 6, dy + 6), (16, 16, 16), 3) and '30' in app.label(),
               dict(label=app.label()))

        # ---- notes and the accepted position survive later selection ---------
        app.note('F3 note kept')
        app.wait_idle()
        notes_before = immutable(app)
        label_before = app.label()

        (profile / 'host.ini').write_text('[Host]\nFontPercent=200\nZoomPercent=125\n', encoding='ascii')
        dialog = app.open_dialog()
        app.press(IMPORT)
        app.wait(lambda: text(app.field(FONT)).startswith('56'), timeout=30)
        record('legacy-import-is-explicit',
               text(app.field(ZOOM)) == '125' and text(app.field(FONT)).startswith('56'))
        app.apply()
        app.close_dialog()
        value, _ = document(profile)
        # A larger point size re-paginates the book, so the same text keeps its
        # page through the anchor while the page number legitimately changes.
        record('reading-position-and-notes-survive-settings',
               abs(value['font_size'] - 56) < .01 and value['fixed_page_zoom'] == 125 and
               immutable(app) == notes_before and page_number(app.label()) > 0,
               dict(label=app.label(), before=label_before))

        # ---- an unreadable document is never overwritten ---------------------
        app.close_app()
        target_file = profile / 'preferences.json'
        good = json.loads(target_file.read_text(encoding='utf-8'))
        for name, payload in (
                ('unknown-version-file-not-overwritten',
                 (json.dumps(dict(good, format_version=99), indent=2) + '\n').encode()),
                ('corrupt-file-not-overwritten', b'{"format":"exreader-preferences",\n')):
            target_file.write_bytes(payload)
            launch(args.candidate, profile, existing=True)
            dialog = app.open_dialog()
            set_text(app.field(FONT), '22')
            app.press(APPLY)
            app.wait(lambda: '\u6ca1\u6709' in app.message() or '\u65e0\u6cd5' in app.message(), timeout=30)
            assert target_file.read_bytes() == payload, name
            record(name, target_file.read_bytes() == payload, dict(message=app.message()))
            app.close_dialog()
            app.close_app()

        target_file.write_bytes(b'not a settings document\n')
        launch(args.candidate, profile, existing=True)
        dialog = app.open_dialog()
        app.press(REBUILD)
        app.wait_enabled(APPLY)
        rebuilt, _ = document(profile)
        record('explicit-rebuild-of-unreadable-file',
               rebuilt is not None and rebuilt['theme'] == 'light' and abs(rebuilt['font_size'] - 24) < .01)
        app.close_dialog()
        app.close_app()

        # ---- a refused save keeps the accepted frame -------------------------
        launch(args.candidate, profile, existing=True)
        app.open('Reading sample')
        app.wait_idle()
        app.fit_page(target)
        accepted, accepted_raw = document(profile)
        before_image = app.page_shot('save-before.bmp', probes)
        handle = None
        try:
            # Read sharing only: the independent read stays possible while the
            # atomic replace is refused by the running system.
            handle = KERNEL.CreateFileW(str(profile / 'preferences.json'), 0x80000000, 0x00000001,
                                        None, 3, 0x80, None)
            assert handle and handle != W.HANDLE(-1).value
            dialog = app.open_dialog()
            app.choose(THEME, 1)
            app.press(APPLY)
            app.wait_enabled(APPLY)
            after, after_raw = document(profile)
            after_image = app.page_shot('save-refused.bmp', probes)
            record('failed-save-keeps-accepted-frame',
                   accepted_raw == after_raw and inner(before_image) == inner(after_image),
                   dict(status=app.status()))
            app.close_dialog()
        finally:
            if handle and handle != W.HANDLE(-1).value:
                KERNEL.CloseHandle(handle)

        # ---- F3 navigation modes --------------------------------------------
        def set_mode(theme, direction, mode):
            dialog = app.open_dialog()
            app.choose(THEME, theme)
            app.choose(DIRECTION, direction)
            app.choose(INPUT, mode)
            app.apply()
            app.close_dialog()

        def reopen():
            app.open('Reading sample')
            app.wait_idle()
            app.fit_page(target)
            app.focus()
            return page_number(app.label())

        page = app.control('page')
        width, height = page_client(app)
        set_mode(1, 0, 3)
        base = reopen()
        A.tap(0x27)
        app.wait_idle()
        keyed = page_number(app.label())
        app.click_client(page, width - 40, height // 2)
        app.wait_idle()
        record('hardware-keys-follow-selected-mode',
               keyed == base + 1 and page_number(app.label()) == keyed,
               dict(base=base, keyed=keyed, tap=page_number(app.label())))

        set_mode(1, 0, 0)
        base = reopen()
        app.click_client(page, width - 40, height // 2)
        app.wait_idle()
        forward = page_number(app.label())
        app.click_client(page, 40, height // 2)
        app.wait_idle()
        record('tap-mode-turns-pages',
               forward == base + 1 and page_number(app.label()) == base,
               dict(base=base, forward=forward, back=page_number(app.label())))

        set_mode(1, 0, 0)
        base = reopen()
        app.click_client(page, width - 40, height // 2)
        app.wait_idle()
        app.click_client(page, width - 40, height // 2)
        app.wait_idle()
        forward = page_number(app.label())
        set_mode(1, 1, 0)
        current = reopen()
        app.click_client(page, width - 40, height // 2)
        app.wait_idle()
        record('rtl-direction-reverses-tap',
               forward >= base + 2 and current > 1 and page_number(app.label()) == current - 1,
               dict(base=base, forward=forward, current=current, after=page_number(app.label())))

        set_mode(1, 0, 1)
        base = reopen()
        app.drag(page, (width - 120, height // 2), (120, height // 2))
        app.wait_idle()
        record('swipe-mode-turns-pages', page_number(app.label()) == base + 1,
               dict(base=base, after=page_number(app.label())))

        # ---- closing during an in-flight settings job ------------------------
        dialog = app.open_dialog()
        set_text(app.field(FONT), '180')
        app.press(APPLY)
        send(app.window, WM_CLOSE)
        try:
            app.process.wait(timeout=180)
        except Exception:
            app.process.kill()
            app.process.wait()
        app.log.close()
        launch(args.candidate, profile, existing=True)
        app.open('Reading sample')
        app.wait_idle()
        final, _ = document(profile)
        label = app.label()
        shown = float(label.split('\u5b57\u53f7')[1].split('\u78c5')[0]) if '\u5b57\u53f7' in label else -1
        leftovers = sorted(item.name for item in profile.iterdir() if '.tmp-' in item.name)
        record('close-during-settings-job-keeps-one-consistent-state',
               final is not None and abs(final['font_size'] - shown) < .01 and not leftovers,
               dict(font=final['font_size'], label=label, leftovers=leftovers))
        app.close_app()
        report.update(accepted=True, transport_checks=len(checks))
    except Exception as error:
        problems.append(type(error).__name__ + ': ' + str(error))
        report['traceback'] = traceback.format_exc()
        try:
            if app and app.process.poll() is None:
                app.process.kill()
                app.process.wait()
        except Exception:
            pass
    finally:
        if restore:
            try:
                winreg.SetValueEx(restore[0], 'AppsUseLightTheme', 0, winreg.REG_DWORD, restore[1])
                winreg.CloseKey(restore[0])
            except Exception:
                pass
    report['captures'] = sorted(item.name for item in probes.iterdir())
    report['count'] = len(checks)
    report['consumer_sha256'] = hashlib.sha256(args.candidate.read_bytes()).hexdigest()
    report['baseline_sha256'] = hashlib.sha256(args.baseline.read_bytes()).hexdigest()
    (output / 'preferences-ui.json').write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False), flush=True)
    assert report['accepted'] and not problems, 'F3 native checks rejected'


if __name__ == '__main__':
    main()
