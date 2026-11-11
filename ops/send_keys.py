#!/usr/bin/env python3
"""PID-scoped background messages. Never activates a window or injects input.

Keyboard modifiers posted here do not promise real hardware keyboard state.
Use --inspect to record the target thread's actual focus and keyboard layout.
"""
import argparse
import ctypes as C
from ctypes import wintypes as W
import json
import time

U = C.windll.user32
U.SetProcessDpiAwarenessContext.argtypes = [C.c_void_p]
U.SetProcessDpiAwarenessContext(C.c_void_p(-4))
CALLBACK = C.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
for name in ('EnumWindows', 'EnumChildWindows'):
    getattr(U, name).argtypes = ([CALLBACK, W.LPARAM] if name == 'EnumWindows'
                               else [W.HWND, CALLBACK, W.LPARAM])
U.GetWindowThreadProcessId.argtypes = [W.HWND, C.POINTER(W.DWORD)]
U.GetWindowTextW.argtypes = U.GetClassNameW.argtypes = [W.HWND, W.LPWSTR, C.c_int]
U.GetWindowRect.argtypes = [W.HWND, C.POINTER(W.RECT)]
U.IsWindowVisible.argtypes = U.IsWindowEnabled.argtypes = [W.HWND]
U.GetDlgCtrlID.argtypes = [W.HWND]
U.GetForegroundWindow.restype = W.HWND
U.GetKeyboardLayout.argtypes = [W.DWORD]
U.GetKeyboardLayout.restype = W.HANDLE
U.PostMessageW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM]
U.SendMessageW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM]
U.SendMessageW.restype = W.LPARAM
U.MapVirtualKeyW.argtypes = [W.UINT, W.UINT]


class GUIINFO(C.Structure):
    _fields_ = [('cbSize', W.DWORD), ('flags', W.DWORD),
                *[(n, W.HWND) for n in ('active', 'focus', 'capture', 'menu', 'move', 'caret')],
                ('caret_rect', W.RECT)]


U.GetGUIThreadInfo.argtypes = [W.DWORD, C.POINTER(GUIINFO)]


def windows(pid):
    result = []
    def add(hwnd, parent):
        found = W.DWORD()
        thread = U.GetWindowThreadProcessId(hwnd, C.byref(found))
        if found.value != pid:
            return
        title, cls, rect = C.create_unicode_buffer(512), C.create_unicode_buffer(128), W.RECT()
        U.GetWindowTextW(hwnd, title, 512)
        U.GetClassNameW(hwnd, cls, 128)
        U.GetWindowRect(hwnd, C.byref(rect))
        result.append(dict(hwnd=hwnd, parent=parent, thread=thread, title=title.value,
                           cls=cls.value, id=U.GetDlgCtrlID(hwnd),
                           visible=bool(U.IsWindowVisible(hwnd)), enabled=bool(U.IsWindowEnabled(hwnd)),
                           rect=[rect.left, rect.top, rect.right, rect.bottom]))
    @CALLBACK
    def top(hwnd, _):
        count = len(result)
        add(hwnd, None)
        if len(result) != count:
            @CALLBACK
            def child(h, _):
                add(h, hwnd)
                return True
            U.EnumChildWindows(hwnd, child, 0)
        return True
    U.EnumWindows(top, 0)
    return result


def state(pid):
    items = windows(pid)
    threads = []
    for tid in sorted({w['thread'] for w in items}):
        info = GUIINFO(cbSize=C.sizeof(GUIINFO))
        okay = U.GetGUIThreadInfo(tid, C.byref(info))
        threads.append(dict(thread=tid, okay=bool(okay), active=info.active, focus=info.focus,
                            caret=info.caret, caret_rect=[info.caret_rect.left, info.caret_rect.top,
                            info.caret_rect.right, info.caret_rect.bottom],
                            keyboard_layout=hex(U.GetKeyboardLayout(tid) or 0)))
    return dict(foreground=U.GetForegroundWindow(), windows=items, threads=threads)


def post(hwnd, msg, wp=0, lp=0):
    if not U.PostMessageW(hwnd, msg, wp, lp):
        raise C.WinError()


def key(hwnd, vk):
    scan = U.MapVirtualKeyW(vk, 0)
    lp = 1 | scan << 16 | ((1 << 24) if vk in (0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2e) else 0)
    post(hwnd, 0x100, vk, lp)
    post(hwnd, 0x101, vk, lp | 0xc0000000)


def point(x, y):
    return (x & 0xffff) | (y & 0xffff) << 16


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('pid', type=int)
    p.add_argument('--hwnd', type=lambda s: int(s, 0))
    p.add_argument('--inspect', action='store_true')
    p.add_argument('--key', type=lambda s: int(s, 0))
    p.add_argument('--letters', help='Post VK_KEYDOWN/UP one by one (IME attempt, not WM_CHAR)')
    p.add_argument('--text', help='Post WM_CHAR directly; never evidence of physical IME input')
    p.add_argument('--click', nargs=2, type=int)
    p.add_argument('--drag', nargs=4, type=int)
    p.add_argument('--command', type=lambda s: int(s, 0))
    p.add_argument('--message', nargs=3, type=lambda s: int(s, 0))
    p.add_argument('--set-text')
    a = p.parse_args()
    before = U.GetForegroundWindow()
    if a.hwnd:
        assert a.hwnd in {w['hwnd'] for w in windows(a.pid)}, 'HWND does not belong to PID'
        if a.command is not None: post(a.hwnd, 0x111, a.command)
        if a.key is not None: key(a.hwnd, a.key)
        if a.letters:
            for c in a.letters:
                key(a.hwnd, ord(c.upper()))
                time.sleep(.08)
        if a.text:
            encoded = a.text.encode('utf-16-le')
            for i in range(0, len(encoded), 2):
                post(a.hwnd, 0x102, int.from_bytes(encoded[i:i+2], 'little'), 1)
        if a.click or a.drag:
            coords = a.drag or a.click * 2
            x, y, endx, endy = coords
            post(a.hwnd, 0x201, 1, point(x, y))
            if a.drag:
                for i in range(1, 11):
                    post(a.hwnd, 0x200, 1, point(x+(endx-x)*i//10, y+(endy-y)*i//10))
                    time.sleep(.02)
            post(a.hwnd, 0x202, 0, point(endx, endy))
        if a.message: post(a.hwnd, *a.message)
        if a.set_text is not None:
            text = C.create_unicode_buffer(a.set_text)
            U.SendMessageW(a.hwnd, 0xc, 0, C.addressof(text))
        time.sleep(.15)
    print(json.dumps(dict(foreground_before=before, **state(a.pid)), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
