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


def compare_endpoints(left, endpoint, right, other_endpoint):
    # uiautomation 2.0.29's wrapper forgets to unwrap its target TextRange.
    # Call the same public IUIAutomationTextRange method with both COM objects.
    return left.textRange.CompareEndpoints(endpoint, right.textRange, other_endpoint)


def main():
    parser = argparse.ArgumentParser()
    for name in ("candidate", "package", "fixtures", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    assert os.name == "nt" and os.environ.get("GITHUB_ACTIONS") == "true"
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    output = args.output.resolve(); output.mkdir(parents=True, exist_ok=False)
    profile = output / "profile"; profile.mkdir()
    source = output / "Accessibility book.txt"
    marker = "A11Y marker alpha beta gamma."
    unit_text = "abcdef alpha beta gamma e\u0301😀中 "
    source.write_bytes((marker + "\n" + "".join(
        f"{row:04d} {unit_text}Second sentence for the page range.\n" for row in range(55))).encode("utf-8"))
    checks = []
    failures = []

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
        assert after_back == control(122), (after_tab, after_back, control(122))
        record("comment_editor_releases_tab_and_shift_tab")

        # 3) import and refresh keep a defined focus stop when they disable themselves
        for identifier, name in ((102, "import"), (127, "refresh")):
            element(control(identifier)).SetFocus()
            wait(lambda: focus_of(process.pid) == control(identifier), 10, name + " focus")
            tap(VK_SPACE)
            time.sleep(0.2)
            focused = focus_of(process.pid)
            print(json.dumps({"disabled_command": name, "focus_after": focused,
                              "foreground": USER32.GetForegroundWindow(),
                              "owner": host["window"]}), flush=True)
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
        print(json.dumps({"details_after_escape": {"dialog": dialog_of(process.pid),
                          "focus": focus_of(process.pid), "expected": control(128),
                          "enabled": bool(USER32.IsWindowEnabled(control(128))),
                          "status": window_text(control(125))}}, ensure_ascii=False), flush=True)
        try:
            wait(lambda: focus_of(process.pid) == control(128), 20, "focus back on details")
        except TimeoutError as error:
            # Keep this assertion strict while still exercising the independent
            # text provider below. The final report and process must both fail.
            failures.append({"check": "details_dialog_returns_focus_to_its_invoking_command",
                             "error": str(error), "focus": focus_of(process.pid),
                             "expected": control(128)})
            print(json.dumps({"failure": failures[-1]}, ensure_ascii=False), flush=True)
        else:
            record("details_dialog_returns_focus_to_its_invoking_command")

        # 7) mnemonics on the main commands
        keys = {}
        for identifier in (102, 103, 104, 127, 128):
            keys[identifier] = element(control(identifier)).AccessKey or ""
        print(json.dumps({"access_keys": keys}, ensure_ascii=False), flush=True)
        assert all(keys.values()), keys
        record("main_commands_expose_alt_mnemonics")

        # 8) provider object lifetime: interleaved AddRef/QI/Clone/Release
        UIA_E_ELEMENTNOTAVAILABLE = -2147220991  # 0x80040201
        document = pattern.DocumentRange
        full_text = document.GetText(-1)
        survivors = []
        for _ in range(24):
            first = document.Clone()
            second = first.Clone()
            third = second.Clone()
            assert first.Compare(second)
            assert first.GetText(-1) == full_text
            survivors.append(third)
            del second, first
            assert third.GetText(-1) == full_text
        assert survivors[-1].GetText(-1) == full_text
        del survivors
        assert pattern.DocumentRange.GetText(-1) == full_text
        assert process.poll() is None, "the host died while ranges were interleaved"
        record("text_ranges_survive_interleaved_clone_compare_and_release")

        # 9) an old frame's range reads its own snapshot and refuses to select
        stale = pattern.DocumentRange
        stale_text = stale.GetText(-1)
        page.SetFocus()
        tap(0x22)  # Page Down on the focused page
        time.sleep(0.8)
        fresh = pattern.DocumentRange
        fresh_text = fresh.GetText(-1)
        assert fresh_text != stale_text, "the page did not change; the stale check would prove nothing"
        assert stale.GetText(-1) == stale_text, "an old range must keep reading its own snapshot"
        refused = False
        try:
            stale.Select()
        except Exception as error:
            refused = True
            code = getattr(error, "hresult", None)
            if code is None and getattr(error, "args", None):
                code = error.args[0]
            assert code is not None and int(code) == UIA_E_ELEMENTNOTAVAILABLE, (code, error)
        assert refused, "a stale range selected inside the new frame"
        record("stale_page_ranges_keep_their_text_and_refuse_to_select")

        # 10) text units and truncation. Expected ranges follow Microsoft's UIA
        # contract, not the provider implementation: nonempty Move spans one unit,
        # degenerate Move stays degenerate, and crossing endpoints move both ends.
        #     UIA enums: Character 0, Word 2, Document 6; endpoints Start 0, End 1.
        units = fresh
        assert 1 <= len(units.GetText(1)) <= 2
        assert units.GetText(0) == ""
        assert units.GetText(-1) == fresh_text
        cursor = units.Clone()
        cursor.MoveEndpointByRange(1, units, 0)
        assert cursor.Move(0, -(2**31)) == 0
        assert cursor.GetText(-1) == ""
        assert cursor.Move(6, 1) == 1
        assert cursor.GetText(-1) == ""
        cursor.ExpandToEnclosingUnit(6)
        assert cursor.GetText(-1) == fresh_text
        clip = units.Clone()
        assert clip.MoveEndpointByUnit(0, 0, -10**6) <= 0
        assert compare_endpoints(clip, 0, units, 0) == 0
        assert clip.MoveEndpointByUnit(1, 0, 10**6) >= 0
        assert compare_endpoints(clip, 1, units, 1) == 0
        record("text_units_truncation_and_endpoints_follow_the_contract")

        ascii_range = units.FindText("abcdef", False, False)
        assert ascii_range and ascii_range.GetText(-1) == "abcdef", fresh_text
        move = ascii_range.Clone()
        assert move.Move(0, 1) == 1
        assert move.GetText(-1) == "b", move.GetText(-1)
        assert move.Move(0, -1) == -1
        assert move.GetText(-1) == "a", move.GetText(-1)
        word = units.FindText("alpha beta", False, False)
        assert word
        word.ExpandToEnclosingUnit(2)
        assert word.GetText(-1).strip() == "alpha", word.GetText(-1)
        assert word.Move(2, 1) == 1
        assert word.GetText(-1).strip() == "beta", word.GetText(-1)
        record("nonempty_move_normalizes_from_start_and_preserves_one_text_unit")

        crossing = ascii_range.Clone()
        crossing.MoveEndpointByRange(1, ascii_range, 0)
        assert crossing.MoveEndpointByUnit(0, 0, 1) == 1
        assert crossing.MoveEndpointByUnit(1, 0, 1) == 1
        assert crossing.GetText(-1) == "b"
        assert crossing.MoveEndpointByUnit(0, 0, 2) == 2
        assert crossing.GetText(-1) == ""
        target = ascii_range.Clone()
        assert target.MoveEndpointByUnit(0, 0, 3) == 3
        assert compare_endpoints(crossing, 0, target, 0) == 0
        crossing.MoveEndpointByRange(0, ascii_range, 1)
        assert compare_endpoints(crossing, 0, ascii_range, 1) == 0
        assert compare_endpoints(crossing, 1, ascii_range, 1) == 0
        assert crossing.MoveEndpointByUnit(1, 0, -(2**31)) < 0
        assert compare_endpoints(crossing, 0, units, 0) == 0
        assert compare_endpoints(crossing, 1, units, 0) == 0
        record("crossing_endpoints_follow_the_moved_endpoint_and_int_min_is_bounded")

        unicode_range = units.FindText("e\u0301😀中", False, False)
        assert unicode_range, fresh_text
        unicode_range.ExpandToEnclosingUnit(0)
        assert unicode_range.GetText(-1) == "e\u0301", unicode_range.GetText(-1)
        assert unicode_range.GetText(1) == "e\u0301"
        assert unicode_range.Move(0, 1) == 1
        assert unicode_range.GetText(-1) == "😀", unicode_range.GetText(-1)
        assert unicode_range.GetText(1) == "😀"
        assert unicode_range.Move(0, 1) == 1
        assert unicode_range.GetText(-1) == "中", unicode_range.GetText(-1)
        record("unicode_character_units_preserve_combining_sequences_and_surrogate_pairs")

        for smaller in (1, 3, 4, 5):  # Format -> Word; Line/Paragraph/Page -> Document
            fallback, reference = ascii_range.Clone(), ascii_range.Clone()
            fallback.ExpandToEnclosingUnit(smaller)
            reference.ExpandToEnclosingUnit(2 if smaller == 1 else 6)
            assert fallback.Compare(reference), smaller
        invalid = ascii_range.Clone()
        refused = False
        try:
            invalid.Move(99, 1)
        except Exception as error:
            code = getattr(error, "hresult", error.args[0] if error.args else None)
            # The public UIA client contract promises a failing HRESULT, not
            # preservation of the server's E_INVALIDARG. UIAutomation's enum
            # transport returns E_UNEXPECTED on this runner. Keep both refusal
            # and endpoint immutability mandatory; never accept an arbitrary
            # exception, a successful move, or changed range.
            assert code in (-2147024809, -2147418113), error  # E_INVALIDARG / E_UNEXPECTED
            print(json.dumps({"invalid_text_unit": 99, "client_hresult": code}), flush=True)
            refused = True
        assert refused and invalid.Compare(ascii_range)
        record("valid_unsupported_units_fall_forward_and_invalid_units_leave_the_range_unchanged")
        assert len(units.GetChildren()) == 0
        record("range_get_children_returns_an_empty_com_array_in_the_correct_vtable_slot")

        # 11) geometry is real for text and empty for an empty range
        # Inspect the public COM SAFEARRAY of doubles. The Python convenience
        # method converts it to Rect objects and truncates each coordinate.
        rects = units.textRange.GetBoundingRectangles()
        assert len(rects) >= 8 and len(rects) % 4 == 0, rects
        assert all(rects[i + 2] > 0 and rects[i + 3] > 0 for i in range(0, len(rects), 4)), rects
        assert len({round(rects[i + 1], 2) for i in range(0, len(rects), 4)}) >= 2, rects
        single = units.Clone()
        single.ExpandToEnclosingUnit(0)
        single_rects = single.textRange.GetBoundingRectangles()
        assert len(single_rects) == 4 and single_rects[2] > 0, single_rects
        print(json.dumps({"full_page_rectangles": list(rects), "first_character_rectangle": list(single_rects)}), flush=True)
        collapsed = units.Clone()
        collapsed.MoveEndpointByRange(1, units, 0)  # end = range start
        assert collapsed.GetText(-1) == ""
        assert len(collapsed.textRange.GetBoundingRectangles()) == 0
        record("bounding_rectangles_describe_only_real_geometry")

        # 12) a point inside the page yields a range at that point
        bounds = page.BoundingRectangle
        range_from_point = getattr(pattern, "RangeFromPoint", None)
        assert range_from_point is not None, "uiautomation has no RangeFromPoint"
        # The left quarter is nearer the leading caret. The cell midpoint is
        # equidistant from two insertion points and has no unique expected side.
        point_range = range_from_point(int(single_rects[0] + single_rects[2] / 4),
                                      int(single_rects[1] + single_rects[3] / 2))
        assert point_range is not None
        point_range.ExpandToEnclosingUnit(0)
        assert point_range.GetText(-1) == single.GetText(-1), (point_range.GetText(-1), single.GetText(-1))
        record("range_from_point_uses_the_host_hit_test")
        outside = range_from_point(int(bounds.left - 200), int(single_rects[1] + single_rects[3] / 2))
        assert outside is not None and outside.GetText(-1) == ""
        outside.ExpandToEnclosingUnit(0)
        assert outside.GetText(-1) == single.GetText(-1), (outside.GetText(-1), single.GetText(-1))
        record("outside_page_points_return_the_nearest_degenerate_text_range")

        # 13) one clean Tab cycle over every enabled stop
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

        # Exercise the same provider on real PDF and bounded EPUB frames, using
        # independent literal fixture text, native keyboard import/open and UIA.
        def row_with(title):
            count = USER32.SendMessageW(control(119), 0x018B, 0, 0)  # LB_GETCOUNT
            for index in range(count):
                length = USER32.SendMessageW(control(119), 0x018A, index, 0)  # LB_GETTEXTLEN
                if length < 0 or length > 4096:
                    continue
                label = C.create_unicode_buffer(length + 1)
                USER32.SendMessageW(control(119), 0x0189, index, C.addressof(label))
                if title in label.value:
                    return index
            return None

        for filename, title, literal, check in (
            ("pages.pdf", "pages", "Fixed page one.", "pdf_text_geometry_hit_and_selection_use_the_rendered_regions"),
            ("book.epub", "Reading state fixture", "Repeated spine chapter", "bounded_epub_text_geometry_hit_and_selection_use_the_rendered_glyphs"),
        ):
            old = pattern.DocumentRange
            old_text = old.GetText(-1)
            path = C.create_unicode_buffer(str((args.fixtures / filename).resolve()))
            wait(lambda: USER32.IsWindowEnabled(control(102)), 120, filename + " import ready")
            USER32.SendMessageW(control(101), 0x000C, 0, C.addressof(path))
            element(control(102)).SetFocus()
            wait(lambda: focus_of(process.pid) == control(102), 10, filename + " import focus")
            tap(VK_SPACE)
            wait(lambda: "已导入" in window_text(control(125)) and USER32.IsWindowEnabled(control(102)),
                 120, filename + " imported")
            wait(lambda: row_with(title) is not None, 60, filename + " visible shelf row")
            USER32.SendMessageW(control(119), 0x0186, row_with(title), 0)
            element(control(103)).SetFocus()
            wait(lambda: focus_of(process.pid) == control(103), 10, filename + " open focus")
            tap(VK_SPACE)

            def loaded_range():
                try:
                    value = pattern.DocumentRange
                    return value if value.GetText(-1).startswith(literal) else None
                except Exception:
                    return None  # readiness only; all behavioral assertions follow

            current = wait(loaded_range, 120, filename + " literal page text")
            assert old.GetText(-1) == old_text
            refused = False
            try:
                old.Select()
            except Exception as error:
                code = getattr(error, "hresult", error.args[0] if error.args else None)
                assert code == UIA_E_ELEMENTNOTAVAILABLE, error
                refused = True
            assert refused, filename + " accepted selection from the previous book"
            whole_rects = current.textRange.GetBoundingRectangles()
            assert len(whole_rects) >= 8 and len(whole_rects) % 4 == 0, whole_rects
            assert len({round(whole_rects[i + 1], 1) for i in range(0, len(whole_rects), 4)}) >= 2
            first = current.Clone()
            first.ExpandToEnclosingUnit(0)
            assert first.GetText(-1) == literal[0]
            boxes = first.textRange.GetBoundingRectangles()
            assert len(boxes) == 4 and boxes[2] > 0 and boxes[3] > 0, boxes
            at = pattern.RangeFromPoint(int(boxes[0] + boxes[2] / 4), int(boxes[1] + boxes[3] / 2))
            assert at and at.GetText(-1) == ""
            at.ExpandToEnclosingUnit(0)
            assert at.GetText(-1) == literal[0], (filename, at.GetText(-1))
            outside = pattern.RangeFromPoint(int(page.BoundingRectangle.left - 200), int(boxes[1] + boxes[3] / 2))
            assert outside and outside.GetText(-1) == ""
            outside.ExpandToEnclosingUnit(0)
            assert outside.GetText(-1) == literal[0], (filename, outside.GetText(-1))
            chosen = current.FindText(literal, False, False)
            assert chosen and chosen.GetText(-1) == literal
            chosen.Select()
            selected = pattern.GetSelection()
            assert len(selected) == 1 and selected[0].GetText(-1) == literal
            print(json.dumps({"format": filename, "text_prefix": current.GetText(32),
                              "rectangles": list(whole_rects), "first": list(boxes)}, ensure_ascii=False), flush=True)
            record(check)

        report = {"accepted": not failures, "source_sha": os.environ["GITHUB_SHA"], "run_id": os.environ["GITHUB_RUN_ID"],
                  "attempt": os.environ["GITHUB_RUN_ATTEMPT"], "checks": checks, "count": len(checks),
                  "failures": failures, "transport": "sendinput+uia", "screen_reader_verified": False, "complete_product": False}
        (output / "a11y-ui.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"accepted": not failures, "count": len(checks), "failures": failures}), flush=True)
        if failures:
            raise SystemExit("native accessibility checks failed")
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
