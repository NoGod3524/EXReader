# SPDX-License-Identifier: MIT
"""Minimal Win32 bindings for the Windows keyboard/accessibility audit.

Only what this audit needs: window/control enumeration, control identity and
geometry, GUI focus introspection, real keyboard injection through SendInput,
and window capture through PrintWindow.

Nothing here changes the host under test; every call is a read or an input
event of the kind a user produces.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import time

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

GWL_STYLE = -16
GWL_EXSTYLE = -20
WS_TABSTOP = 0x00010000
WS_DISABLED = 0x08000000
WS_VISIBLE = 0x10000000
WS_EX_CONTROLPARENT = 0x00010000

PW_CLIENTONLY = 0x1
PW_RENDERFULLCONTENT = 0x2
DIB_RGB_COLORS = 0

SW_RESTORE = 9

VK_BACK = 0x08
VK_TAB = 0x09
VK_RETURN = 0x0D
VK_ESCAPE = 0x1B
VK_SPACE = 0x20
VK_END = 0x23
VK_HOME = 0x24
VK_LEFT = 0x25
VK_UP = 0x26
VK_RIGHT = 0x27
VK_DOWN = 0x28
VK_PRIOR = 0x21
VK_NEXT = 0x22
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12
VK_F4 = 0x73

KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
INPUT_KEYBOARD = 1

WM_CLOSE = 0x0010
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_CHAR = 0x0102
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
WM_GETTEXT = 0x000D
WM_GETTEXTLENGTH = 0x000E
CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002

SM_CXSCREEN = 0
SM_CYSCREEN = 1


class RECT(ctypes.Structure):
    _fields_ = [("left", wt.LONG), ("top", wt.LONG), ("right", wt.LONG), ("bottom", wt.LONG)]

    def as_list(self):
        return [int(self.left), int(self.top), int(self.right), int(self.bottom)]


class POINT(ctypes.Structure):
    _fields_ = [("x", wt.LONG), ("y", wt.LONG)]


class GUITHREADINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wt.DWORD),
        ("flags", wt.DWORD),
        ("hwndActive", wt.HWND),
        ("hwndFocus", wt.HWND),
        ("hwndCapture", wt.HWND),
        ("hwndMenuOwner", wt.HWND),
        ("hwndMoveSize", wt.HWND),
        ("hwndCaret", wt.HWND),
        ("rcCaret", RECT),
    ]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wt.DWORD),
        ("biWidth", wt.LONG),
        ("biHeight", wt.LONG),
        ("biPlanes", wt.WORD),
        ("biBitCount", wt.WORD),
        ("biCompression", wt.DWORD),
        ("biSizeImage", wt.DWORD),
        ("biXPelsPerMeter", wt.LONG),
        ("biYPelsPerMeter", wt.LONG),
        ("biClrUsed", wt.DWORD),
        ("biClrImportant", wt.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wt.DWORD * 3)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wt.WORD),
        ("wScan", wt.WORD),
        ("dwFlags", wt.DWORD),
        ("time", wt.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wt.LONG),
        ("dy", wt.LONG),
        ("mouseData", wt.DWORD),
        ("dwFlags", wt.DWORD),
        ("time", wt.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wt.DWORD),
        ("wParamL", wt.WORD),
        ("wParamH", wt.WORD),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wt.DWORD), ("u", _INPUTUNION)]


WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

user32.EnumWindows.argtypes = [WNDENUMPROC, wt.LPARAM]
user32.EnumWindows.restype = wt.BOOL
user32.EnumChildWindows.argtypes = [wt.HWND, WNDENUMPROC, wt.LPARAM]
user32.EnumChildWindows.restype = wt.BOOL
user32.GetWindowTextLengthW.argtypes = [wt.HWND]
user32.GetWindowTextLengthW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int
user32.GetClassNameW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
user32.GetClassNameW.restype = ctypes.c_int
user32.GetDlgCtrlID.argtypes = [wt.HWND]
user32.GetDlgCtrlID.restype = ctypes.c_int
user32.IsWindow.argtypes = [wt.HWND]
user32.IsWindow.restype = wt.BOOL
user32.IsWindowEnabled.argtypes = [wt.HWND]
user32.IsWindowEnabled.restype = wt.BOOL
user32.IsWindowVisible.argtypes = [wt.HWND]
user32.IsWindowVisible.restype = wt.BOOL
user32.GetParent.argtypes = [wt.HWND]
user32.GetParent.restype = wt.HWND
user32.GetAncestor.argtypes = [wt.HWND, ctypes.c_uint]
user32.GetAncestor.restype = wt.HWND
user32.GetWindow.argtypes = [wt.HWND, ctypes.c_uint]
user32.GetWindow.restype = wt.HWND
user32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(RECT)]
user32.GetWindowRect.restype = wt.BOOL
user32.GetClientRect.argtypes = [wt.HWND, ctypes.POINTER(RECT)]
user32.GetClientRect.restype = wt.BOOL
user32.ClientToScreen.argtypes = [wt.HWND, ctypes.POINTER(POINT)]
user32.ClientToScreen.restype = wt.BOOL
user32.GetFocus.restype = wt.HWND
user32.GetForegroundWindow.restype = wt.HWND
user32.SetForegroundWindow.argtypes = [wt.HWND]
user32.SetForegroundWindow.restype = wt.BOOL
user32.BringWindowToTop.argtypes = [wt.HWND]
user32.BringWindowToTop.restype = wt.BOOL
user32.SetActiveWindow.argtypes = [wt.HWND]
user32.SetActiveWindow.restype = wt.HWND
user32.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
user32.ShowWindow.restype = wt.BOOL
user32.SetWindowPos.argtypes = [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, ctypes.c_uint]
user32.SetWindowPos.restype = wt.BOOL
user32.AllowSetForegroundWindow.argtypes = [wt.DWORD]
user32.AllowSetForegroundWindow.restype = wt.BOOL
user32.AttachThreadInput.argtypes = [wt.DWORD, wt.DWORD, wt.BOOL]
user32.AttachThreadInput.restype = wt.BOOL
user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
user32.GetWindowThreadProcessId.restype = wt.DWORD
user32.GetGUIThreadInfo.argtypes = [wt.DWORD, ctypes.POINTER(GUITHREADINFO)]
user32.GetGUIThreadInfo.restype = wt.BOOL
user32.SendInput.argtypes = [ctypes.c_uint, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = ctypes.c_uint
user32.PostMessageW.argtypes = [wt.HWND, ctypes.c_uint, wt.WPARAM, wt.LPARAM]
user32.PostMessageW.restype = wt.BOOL
user32.SendMessageW.argtypes = [wt.HWND, ctypes.c_uint, wt.WPARAM, wt.LPARAM]
user32.SendMessageW.restype = ctypes.c_ssize_t
user32.GetSystemMetrics.argtypes = [ctypes.c_int]
user32.GetSystemMetrics.restype = ctypes.c_int
user32.PrintWindow.argtypes = [wt.HWND, wt.HDC, ctypes.c_uint]
user32.PrintWindow.restype = wt.BOOL
user32.GetDC.argtypes = [wt.HWND]
user32.GetDC.restype = wt.HDC
user32.ReleaseDC.argtypes = [wt.HWND, wt.HDC]
user32.ReleaseDC.restype = ctypes.c_int
user32.OpenClipboard.argtypes = [wt.HWND]
user32.OpenClipboard.restype = wt.BOOL
user32.CloseClipboard.restype = wt.BOOL
user32.GetClipboardData.argtypes = [ctypes.c_uint]
user32.GetClipboardData.restype = wt.HANDLE
user32.IsClipboardFormatAvailable.argtypes = [ctypes.c_uint]
user32.IsClipboardFormatAvailable.restype = wt.BOOL

gdi32.CreateCompatibleDC.argtypes = [wt.HDC]
gdi32.CreateCompatibleDC.restype = wt.HDC
gdi32.CreateDIBSection.argtypes = [wt.HDC, ctypes.POINTER(BITMAPINFO), ctypes.c_uint,
                                   ctypes.POINTER(ctypes.c_void_p), wt.HANDLE, wt.DWORD]
gdi32.CreateDIBSection.restype = wt.HBITMAP
gdi32.SelectObject.argtypes = [wt.HDC, wt.HGDIOBJ]
gdi32.SelectObject.restype = wt.HGDIOBJ
gdi32.DeleteObject.argtypes = [wt.HGDIOBJ]
gdi32.DeleteObject.restype = wt.BOOL
gdi32.DeleteDC.argtypes = [wt.HDC]
gdi32.DeleteDC.restype = wt.BOOL
gdi32.BitBlt.argtypes = [wt.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                         wt.HDC, ctypes.c_int, ctypes.c_int, wt.DWORD]
gdi32.BitBlt.restype = wt.BOOL

kernel32.GlobalLock.argtypes = [wt.HANDLE]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalUnlock.argtypes = [wt.HANDLE]
kernel32.GlobalUnlock.restype = wt.BOOL
kernel32.GetCurrentThreadId.restype = wt.DWORD

try:
    _get_long = user32.GetWindowLongPtrW
    _get_long.argtypes = [wt.HWND, ctypes.c_int]
    _get_long.restype = ctypes.c_ssize_t
except AttributeError:  # 32-bit Python exposes only GetWindowLongW
    _get_long = user32.GetWindowLongW
    _get_long.argtypes = [wt.HWND, ctypes.c_int]
    _get_long.restype = ctypes.c_long

SRCCOPY = 0x00CC0020


def make_dpi_aware():
    """Match UIA rectangles to device pixels for capture and geometry."""
    for call in (
        lambda: user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)),
        lambda: user32.SetProcessDpiAware(),
        lambda: ctypes.WinDLL("shcore").SetProcessDpiAwareness(2),
    ):
        try:
            if call():
                return True
        except Exception:
            continue
    return False


def style(hwnd):
    if not hwnd:
        return 0
    return int(_get_long(hwnd, GWL_STYLE)) & 0xFFFFFFFF


def exstyle(hwnd):
    if not hwnd:
        return 0
    return int(_get_long(hwnd, GWL_EXSTYLE)) & 0xFFFFFFFF


def has_style(hwnd, bit):
    return bool(style(hwnd) & bit)


def window_text(hwnd):
    if not hwnd or not user32.IsWindow(hwnd):
        return ""
    length = user32.GetWindowTextLengthW(hwnd)
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, length + 1)
    return buffer.value


def class_name(hwnd):
    if not hwnd or not user32.IsWindow(hwnd):
        return ""
    buffer = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buffer, 256)
    return buffer.value


def ctrl_id(hwnd):
    if not hwnd:
        return 0
    return int(user32.GetDlgCtrlID(hwnd))


def window_rect(hwnd):
    rect = RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return None
    return rect.as_list()


def client_rect(hwnd):
    rect = RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
        return None
    return rect.as_list()


def client_origin(hwnd):
    point = POINT(0, 0)
    if not user32.ClientToScreen(hwnd, ctypes.byref(point)):
        return (0, 0)
    return (int(point.x), int(point.y))


def parent(hwnd):
    return user32.GetParent(hwnd) or 0


def thread_id(hwnd):
    pid = wt.DWORD(0)
    tid = user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return int(tid), int(pid.value)


def top_windows():
    found = []

    def collect(hwnd, _param):
        found.append(int(hwnd))
        return True

    user32.EnumWindows(WNDENUMPROC(collect), 0)
    return found


def child_windows(hwnd):
    found = []

    def collect(child, _param):
        found.append(int(child))
        return True

    user32.EnumChildWindows(hwnd, WNDENUMPROC(collect), 0)
    return found


def direct_children(hwnd):
    return [h for h in child_windows(hwnd) if parent(h) == hwnd]


def screen_size():
    return (int(user32.GetSystemMetrics(SM_CXSCREEN)), int(user32.GetSystemMetrics(SM_CYSCREEN)))


def foreground():
    return int(user32.GetForegroundWindow() or 0)


def gui_thread_info(tid):
    info = GUITHREADINFO()
    info.cbSize = ctypes.sizeof(GUITHREADINFO)
    if not user32.GetGUIThreadInfo(tid, ctypes.byref(info)):
        return None
    return {
        "flags": int(info.flags),
        "active": int(info.hwndActive or 0),
        "focus": int(info.hwndFocus or 0),
        "capture": int(info.hwndCapture or 0),
        "caret": int(info.hwndCaret or 0),
    }


def focus_of(hwnd):
    tid, _pid = thread_id(hwnd)
    info = gui_thread_info(tid)
    if not info:
        return 0
    return info["focus"]


def bring_to_front(hwnd):
    """Make the host the foreground window so real input is delivered to it."""
    try:
        user32.AllowSetForegroundWindow(0xFFFFFFFF)
    except Exception:
        pass
    try:
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)
    except Exception:
        pass
    for _ in range(6):
        if foreground() == hwnd:
            return True
        try:
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
        except Exception:
            pass
        time.sleep(0.12)
    return foreground() == hwnd


def send_key(vk, up=False, unicode_char=None):
    """Inject one key event with SendInput (real hardware-level input)."""
    item = INPUT()
    item.type = INPUT_KEYBOARD
    if unicode_char is not None:
        item.u.ki.wVk = 0
        item.u.ki.wScan = unicode_char
        item.u.ki.dwFlags = KEYEVENTF_UNICODE | (KEYEVENTF_KEYUP if up else 0)
    else:
        item.u.ki.wVk = vk
        item.u.ki.wScan = 0
        item.u.ki.dwFlags = KEYEVENTF_KEYUP if up else 0
    count = user32.SendInput(1, ctypes.byref(item), ctypes.sizeof(INPUT))
    return int(count) == 1


def post_key(hwnd, vk, up=False, char=None):
    """Post a WM_KEYUP/WM_KEYDOWN or WM_CHAR to a window (message-level path)."""
    if not hwnd:
        return False
    if char is not None:
        return bool(user32.PostMessageW(hwnd, WM_CHAR, char, 1))
    message = WM_KEYUP if up else WM_KEYDOWN
    scan = int(user32.MapVirtualKeyW(vk, 0)) if hasattr(user32, "MapVirtualKeyW") else 0
    lparam = 1 | ((scan & 0xFF) << 16)
    if up:
        lparam |= (1 << 30) | (1 << 31)
    return bool(user32.PostMessageW(hwnd, message, vk, lparam))


def read_clipboard_text():
    if not user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
        return None
    if not user32.OpenClipboard(0):
        return None
    try:
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return None
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            return None
        try:
            return ctypes.wstring_at(pointer)
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def capture_rgb(hwnd):
    """Capture a whole window as top-down RGB bytes plus its size.

    PrintWindow with PW_RENDERFULLCONTENT renders the window through WM_PRINT,
    so it also works when the runner desktop is smaller than the window. A
    screen BitBlt is only used when the window refuses to render. On failure the
    returned mapping carries an "error" key so the trace can explain itself.
    """
    rect = window_rect(hwnd)
    if not rect:
        return {"error": "GetWindowRect failed for %r" % (hwnd,)}
    width = rect[2] - rect[0]
    height = rect[3] - rect[1]
    if width <= 0 or height <= 0:
        return {"error": "empty window rect %r" % (rect,)}
    info = BITMAPINFO()
    info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    info.bmiHeader.biWidth = width
    info.bmiHeader.biHeight = -height
    info.bmiHeader.biPlanes = 1
    info.bmiHeader.biBitCount = 32
    info.bmiHeader.biCompression = 0
    screen = user32.GetDC(0)
    if not screen:
        return {"error": "GetDC(NULL) failed"}
    memory = gdi32.CreateCompatibleDC(screen)
    if not memory:
        user32.ReleaseDC(0, screen)
        return {"error": "CreateCompatibleDC failed"}
    bits = ctypes.c_void_p()
    bitmap = gdi32.CreateDIBSection(memory, ctypes.byref(info), DIB_RGB_COLORS,
                                    ctypes.byref(bits), None, 0)
    if not bitmap or not bits.value:
        gdi32.DeleteDC(memory)
        user32.ReleaseDC(0, screen)
        return {"error": "CreateDIBSection failed for %dx%d" % (width, height)}
    previous = gdi32.SelectObject(memory, bitmap)
    printed = bool(user32.PrintWindow(hwnd, memory, PW_RENDERFULLCONTENT))
    blitted = False
    if not printed:
        blitted = bool(gdi32.BitBlt(memory, 0, 0, width, height, screen, rect[0], rect[1],
                                    SRCCOPY))
    gdi32.SelectObject(memory, previous)
    buffer = ctypes.string_at(bits.value, width * height * 4)
    gdi32.DeleteObject(bitmap)
    gdi32.DeleteDC(memory)
    user32.ReleaseDC(0, screen)
    rgb = bytearray(width * height * 3)
    rgb[0::3] = buffer[2::4]
    rgb[1::3] = buffer[1::4]
    rgb[2::3] = buffer[0::4]
    return {"width": width, "height": height, "rgb": bytes(rgb), "print_window": printed,
            "screen_bitblt": blitted, "window_rect": rect,
            "non_white_bytes": sum(1 for value in rgb[0:30000:3] if value != 255)}
