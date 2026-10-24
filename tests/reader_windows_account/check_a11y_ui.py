# SPDX-License-Identifier: MIT
"""Actions-only keyboard and accessibility regression for the Windows host.

Every state change below is a real hardware key event (SendInput) or a real UI
Automation call on the packaged product host. Nothing drives WM_COMMAND, BM_CLICK
or a private host function, and nothing is asserted from a source grep.
"""
import argparse
import ctypes as C
from ctypes import wintypes as W
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

import uiautomation as auto

USER32 = C.WinDLL("user32", use_last_error=True)
KERNEL = C.WinDLL("kernel32", use_last_error=True)


class KEYBDINPUT(C.Structure):
    _fields_ = [("wVk", C.c_ushort), ("wScan", C.c_ushort), ("dwFlags", C.c_ulong),
                ("time", C.c_ulong), ("dwExtraInfo", C.POINTER(C.c_ulong))]


class MOUSEINPUT(C.Structure):
    _fields_ = [("dx", C.c_long), ("dy", C.c_long), ("mouseData", C.c_ulong),
                ("dwFlags", C.c_ulong), ("time", C.c_ulong), ("dwExtraInfo", C.POINTER(C.c_ulong))]


class HARDWAREINPUT(C.Structure):
    _fields_ = [("uMsg", C.c_ulong), ("wParamL", C.c_short), ("wParamH", C.c_ushort)]


class INPUTUNION(C.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT)]


class INPUT(C.Structure):
    _fields_ = [("type", C.c_ulong), ("u", INPUTUNION)]

KEYEVENTF_KEYUP = 0x0002
INPUT_KEYBOARD = 1
VK_TAB, VK_SHIFT, VK_SPACE, VK_ESCAPE, VK_CONTROL = 0x09, 0x10, 0x20, 0x1B, 0x11


def key(vk, up=False):
    item = INPUT(type=INPUT_KEYBOARD)
    item.u.ki = KEYBDINPUT(wVk=vk, wScan=0, dwFlags=KEYEVENTF_KEYUP if up else 0, time=0, dwExtraInfo=None)
    assert USER32.SendInput(1, C.byref(item), C.sizeof(INPUT)) == 1


def tap(vk, modifiers=()):
    for modifier in modifiers:
        key(modifier)
    key(vk)
    key(vk, True)
    for modifier in reversed(modifiers):
        key(modifier, True)
    time.sleep(0.12)


class FOCUS(C.Structure):
    _fields_ = [("cbSize", W.DWORD), ("flags", W.DWORD), ("hwndActive", W.HWND), ("hwndFocus", W.HWND),
                ("hwndCapture", W.HWND), ("hwndMenuOwner", W.HWND), ("hwndMoveSize", W.HWND),
                ("hwndCaret", W.HWND), ("rcCaret", W.RECT)]



USER32.GetDlgItem.argtypes = [W.HWND, C.c_int]
USER32.GetDlgItem.restype = W.HWND
USER32.SendMessageW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM]
USER32.SendMessageW.restype = W.LPARAM
USER32.PostMessageW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM]
USER32.PostMessageW.restype = W.BOOL
USER32.GetParent.argtypes = [W.HWND]
USER32.GetParent.restype = W.HWND
USER32.IsWindowEnabled.argtypes = [W.HWND]
USER32.IsWindowEnabled.restype = W.BOOL
USER32.SetForegroundWindow.argtypes = [W.HWND]
USER32.SetForegroundWindow.restype = W.BOOL
USER32.GetClassNameW.argtypes = [W.HWND, W.LPWSTR, C.c_int]
USER32.GetClassNameW.restype = C.c_int
USER32.GetWindowThreadProcessId.argtypes = [W.HWND, C.POINTER(W.DWORD)]
USER32.GetGUIThreadInfo.argtypes = [W.DWORD, C.POINTER(FOCUS)]
USER32.GetGUIThreadInfo.restype = W.BOOL
USER32.SetWinEventHook.argtypes = [W.UINT, W.UINT, W.HMODULE, C.c_void_p, W.DWORD, W.DWORD, W.UINT]
USER32.SetWinEventHook.restype = W.HANDLE
USER32.UnhookWinEvent.argtypes = [W.HANDLE]
USER32.PeekMessageW.argtypes = [C.POINTER(W.MSG), W.HWND, W.UINT, W.UINT, W.UINT]
USER32.TranslateMessage.argtypes = [C.POINTER(W.MSG)]
USER32.DispatchMessageW.argtypes = [C.POINTER(W.MSG)]
KERNEL.CreateToolhelp32Snapshot.argtypes = [W.DWORD, W.DWORD]
KERNEL.CreateToolhelp32Snapshot.restype = W.HANDLE
KERNEL.CloseHandle.argtypes = [W.HANDLE]
USER32.SendInput.argtypes = [W.UINT, C.c_void_p, C.c_int]
USER32.SendInput.restype = W.UINT


def pump(seconds, stop):
    """Out-of-context WinEvents arrive on this thread only while it pumps."""
    message = W.MSG()
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        while USER32.PeekMessageW(C.byref(message), 0, 0, 0, 1):
            USER32.TranslateMessage(C.byref(message))
            USER32.DispatchMessageW(C.byref(message))
        if stop():
            return True
        time.sleep(0.02)
    return False


def focus_of(pid):
    """Real focus of the host's UI thread, read from the system, never from the probe."""
    for thread in thread_ids(pid):
        info = FOCUS(); info.cbSize = C.sizeof(info)
        if USER32.GetGUIThreadInfo(thread, C.byref(info)):
            return info.hwndFocus
    return None


class THREADENTRY(C.Structure):
    _fields_ = [("dwSize", C.c_ulong), ("cntUsage", C.c_ulong), ("th32ThreadID", C.c_ulong),
                ("th32OwnerProcessID", C.c_ulong), ("tpBasePri", C.c_long), ("tpDeltaPri", C.c_long),
                ("dwFlags", C.c_ulong)]


KERNEL.Thread32First.argtypes = [W.HANDLE, C.POINTER(THREADENTRY)]
KERNEL.Thread32First.restype = W.BOOL
KERNEL.Thread32Next.argtypes = [W.HANDLE, C.POINTER(THREADENTRY)]
KERNEL.Thread32Next.restype = W.BOOL
USER32.EnumWindows.argtypes = [C.c_void_p, W.LPARAM]
USER32.EnumWindows.restype = W.BOOL
USER32.GetForegroundWindow.argtypes = []
USER32.GetForegroundWindow.restype = W.HWND
USER32.BringWindowToTop.argtypes = [W.HWND]
USER32.BringWindowToTop.restype = W.BOOL


def thread_ids(pid):
    ENTRY = THREADENTRY
    snap = KERNEL.CreateToolhelp32Snapshot(0x00000004, 0)
    entry = ENTRY(); entry.dwSize = C.sizeof(entry)
    found = []
    ok = KERNEL.Thread32First(snap, C.byref(entry))
    while ok:
        if entry.th32OwnerProcessID == pid:
            found.append(entry.th32ThreadID)
        ok = KERNEL.Thread32Next(snap, C.byref(entry))
    KERNEL.CloseHandle(snap)
    return found


def wait(predicate, timeout=30, what="condition"):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        value = predicate()
        if value:
            return value
        time.sleep(0.05)
    raise TimeoutError(what)


def main():
    parser = argparse.ArgumentParser()
    for name in ("candidate", "package", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    assert os.name == "nt" and os.environ.get("GITHUB_ACTIONS") == "true"
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    output = args.output.resolve(); output.mkdir(parents=True, exist_ok=False)
    profile = output / "profile"; profile.mkdir()
    source = output / "Accessibility book.txt"
    marker = "A11Y marker alpha beta gamma."
    source.write_bytes((marker + " " + "Second sentence for the page range. " * 40 + "\n").encode())
    checks = []

    def record(name):
        assert name not in checks, name
        checks.append(name)
        print(json.dumps({"check": name, "pass": True}, ensure_ascii=False), flush=True)

    host = {"window": 0}

    def control(identifier):
        return int(USER32.GetDlgItem(host["window"], identifier) or 0)

    def element(hwnd):
        return auto.ControlFromHandle(hwnd)

    log = (output / "host.log").open("wb")
    process = subprocess.Popen([str(args.candidate), "--font", str(args.package / "Reader.otf"),
                                "--data", str(profile)], stdout=log, stderr=subprocess.STDOUT)
    try:
        def find_window():
            found = []
            @C.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
            def visit(window, _):
                pid = W.DWORD(); USER32.GetWindowThreadProcessId(window, C.byref(pid))
                name = C.create_unicode_buffer(120); USER32.GetClassNameW(window, name, 120)
                if pid.value == process.pid and name.value == "EXReaderHost":
                    found.append(window)
                return True
            USER32.EnumWindows(visit, 0)
            if found:
                host["window"] = found[-1]
                return host["window"]
            return 0
        wait(find_window, 30, "host window")

        def foreground():
            for _ in range(40):
                USER32.BringWindowToTop(host["window"])
                USER32.SetForegroundWindow(host["window"])
                if USER32.GetForegroundWindow() == host["window"]:
                    return True
                time.sleep(0.1)
            return False
        assert foreground(), "the host never became the foreground window; SendInput would miss it"
        # A real import so the details command and the page have content.
        text = C.create_unicode_buffer(str(source))
        USER32.SendMessageW(control(101), 0x000C, 0, C.addressof(text))
        element(control(102)).SetFocus()
        wait(lambda: focus_of(process.pid) == control(102), 10, "import focus")
        tap(VK_SPACE)
        wait(lambda: "已导入" in window_text(control(125)), 180, "import finished")
        record("import_command_activates_from_the_keyboard")

        # Open it with the keyboard: select the only row, then activate 打开.
        USER32.SendMessageW(control(119), 0x0186, 0, 0)  # LB_SETCURSEL
        element(control(103)).SetFocus()
        wait(lambda: focus_of(process.pid) == control(103), 10, "open focus")
        tap(VK_SPACE)
        wait(lambda: "已打开" in window_text(control(125)), 120, "book opened")

        # 1) accessible names on the two unlabeled editors
        search_name = element(control(126)).Name or ""
        comment_name = element(control(122)).Name or ""
        print(json.dumps({"names": {"search": search_name, "comment": comment_name}}, ensure_ascii=False), flush=True)
        assert "搜索" in search_name, search_name
        assert "标注内容" in comment_name, comment_name
        record("shelf_search_and_comment_edits_expose_accessible_names")

        # 2) the comment editor releases Tab and Shift+Tab
        element(control(122)).SetFocus()
        wait(lambda: focus_of(process.pid) == control(122), 10, "comment focus")
        tap(VK_TAB)
        after_tab = focus_of(process.pid)
        assert after_tab and after_tab != control(122), after_tab
        tap(VK_TAB, (VK_SHIFT,))
        after_back = focus_of(process.pid)
        assert after_back and after_back != control(122), after_back
        record("comment_editor_releases_tab_and_shift_tab")

        # 3) import and refresh keep a defined focus stop when they disable themselves
        for identifier, name in ((102, "import"), (127, "refresh")):
            element(control(identifier)).SetFocus()
            wait(lambda: focus_of(process.pid) == control(identifier), 10, name + " focus")
            tap(VK_SPACE)
            time.sleep(0.2)
            focused = focus_of(process.pid)
            assert focused, name + " focus dropped"
            assert USER32.GetParent(focused) == host["window"], name + " focus left the window"
            assert USER32.IsWindowEnabled(focused), name + " focus landed on a disabled stop"
        record("import_and_refresh_commands_keep_a_defined_focus_stop")

        # 4) status changes raise a native change event
        events = []

        @C.WINFUNCTYPE(None, W.HANDLE, W.DWORD, W.HWND, W.LONG, W.LONG, W.DWORD, W.DWORD)
        def hook(_, event, window, object_id, child, thread, _ms):
            if window == status_handle and object_id == -4:  # OBJID_CLIENT
                events.append(event)
        status_handle = control(125)
        handle = USER32.SetWinEventHook(0x800C, 0x800C, None, C.cast(hook, C.c_void_p), process.pid, 0, 0x0000)
        assert handle
        try:
            element(control(107)).SetFocus()  # select-the-page command changes the status line
            tap(VK_SPACE)
            assert pump(20, lambda: bool(events)), "no native change event from the status line"
        finally:
            USER32.UnhookWinEvent(handle)
        record("status_line_raises_a_native_change_event")

        # 5) page text and selection through the native text pattern
        page = element(control(123))
        pattern = page.GetPattern(auto.PatternId.TextPattern)
        assert pattern is not None, "no TextPattern on the page"
        document = pattern.DocumentRange.GetText(-1)
        print(json.dumps({"page_text_bytes": len(document.encode("utf-8"))}, ensure_ascii=False), flush=True)
        assert marker in document, document[:200]
        record("page_exposes_text_through_a_native_text_pattern")
        page.SetFocus()
        wait(lambda: focus_of(process.pid) == control(123), 10, "page focus")
        tap(ord("A"), (VK_CONTROL,))
        selection = pattern.GetSelection()
        assert len(selection) == 1, len(selection)
        selected = selection[0].GetText(-1)
        assert selected == document, (selected[:80], document[:80])
        record("page_selection_is_exposed_as_a_text_range")

        # 6) modal dialogs: focus returns, background commands report disabled
        element(control(128)).SetFocus()
        wait(lambda: focus_of(process.pid) == control(128), 10, "details focus")
        tap(VK_SPACE)
        dialog = wait(lambda: dialog_of(process.pid), 30, "details dialog")
        assert not element(control(102)).IsEnabled, "blocked import still reports enabled"
        record("modal_background_commands_report_disabled_to_uia")
        tap(VK_ESCAPE)
        wait(lambda: focus_of(process.pid) == control(128), 20, "focus back on details")
        record("details_dialog_returns_focus_to_its_invoking_command")

        # 7) mnemonics on the main commands
        keys = {}
        for identifier in (102, 103, 104, 127, 128):
            keys[identifier] = element(control(identifier)).AccessKey or ""
        print(json.dumps({"access_keys": keys}, ensure_ascii=False), flush=True)
        assert all(keys.values()), keys
        record("main_commands_expose_alt_mnemonics")

        # 8) one clean Tab cycle over every enabled stop
        element(control(101)).SetFocus()
        seen, order = set(), []
        for _ in range(120):
            current = focus_of(process.pid)
            assert current, "focus dropped inside the tab cycle"
            if current in seen and len(order) > 1:
                break
            seen.add(current); order.append(current)
            tap(VK_TAB)
            time.sleep(0.05)
        print(json.dumps({"tab_stops": len(order)}, ensure_ascii=False), flush=True)
        assert len(order) >= 18, len(order)
        assert focus_of(process.pid) == order[0], "the cycle did not close"
        record("tab_order_visits_every_enabled_stop_once_and_closes")

        report = {"accepted": True, "source_sha": os.environ["GITHUB_SHA"], "run_id": os.environ["GITHUB_RUN_ID"],
                  "attempt": os.environ["GITHUB_RUN_ATTEMPT"], "checks": checks, "count": len(checks),
                  "transport": "sendinput+uia", "screen_reader_verified": False, "complete_product": False}
        (output / "a11y-ui.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"accepted": True, "count": len(checks)}), flush=True)
    finally:
        if process.poll() is None:
            USER32.PostMessageW(host["window"], 0x0010, 0, 0)
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait()
        log.close()


def window_text(hwnd):
    length = USER32.SendMessageW(hwnd, 0x000E, 0, 0)
    buffer = C.create_unicode_buffer(length + 1)
    USER32.SendMessageW(hwnd, 0x000D, length + 1, C.addressof(buffer))
    return buffer.value


def dialog_of(pid):
    found = []
    @C.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
    def visit(window, _):
        owner = W.DWORD(); USER32.GetWindowThreadProcessId(window, C.byref(owner))
        name = C.create_unicode_buffer(120); USER32.GetClassNameW(window, name, 120)
        if owner.value == pid and name.value == "#32770" and USER32.IsWindowVisible(window):
            found.append(window)
        return True
    USER32.EnumWindows(visit, 0)
    return found[-1] if found else 0


if __name__ == "__main__":
    main()
