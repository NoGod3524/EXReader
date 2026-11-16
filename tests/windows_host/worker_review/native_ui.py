# SPDX-License-Identifier: MIT
"""Public keyboard/file-picker actions shared by the retained Win32 suites."""
import ctypes as C
from ctypes import wintypes as W
import json
import time

U = C.WinDLL('user32', use_last_error=True)
U.GetDlgItem.argtypes = [W.HWND, C.c_int]
U.GetDlgItem.restype = W.HWND
U.GetWindowThreadProcessId.argtypes = [W.HWND, C.POINTER(W.DWORD)]
U.SetForegroundWindow.argtypes = [W.HWND]
U.GetForegroundWindow.restype = W.HWND
U.SetFocus.argtypes = [W.HWND]
U.SetFocus.restype = W.HWND
U.AttachThreadInput.argtypes = [W.DWORD, W.DWORD, W.BOOL]
U.IsWindow.argtypes = [W.HWND]
U.IsWindowVisible.argtypes = [W.HWND]
U.IsWindowEnabled.argtypes = [W.HWND]
U.GetClassNameW.argtypes = [W.HWND, W.LPWSTR, C.c_int]
U.SendMessageW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM]
U.SendMessageW.restype = W.LPARAM
ENUM = C.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
U.EnumWindows.argtypes = [ENUM, W.LPARAM]
U.EnumChildWindows.argtypes = [W.HWND, ENUM, W.LPARAM]
U.GetDlgCtrlID.argtypes = [W.HWND]


class Keyboard(C.Structure):
    _fields_ = [('vk', W.WORD), ('scan', W.WORD), ('flags', W.DWORD),
                ('time', W.DWORD), ('extra', C.c_size_t)]


class Mouse(C.Structure):
    _fields_ = [('x', W.LONG), ('y', W.LONG), ('data', W.DWORD),
                ('flags', W.DWORD), ('time', W.DWORD), ('extra', C.c_size_t)]


class Payload(C.Union):
    _fields_ = [('keyboard', Keyboard), ('mouse', Mouse)]


class Input(C.Structure):
    _fields_ = [('type', W.DWORD), ('payload', Payload)]


U.SendInput.argtypes = [W.UINT, C.POINTER(Input), C.c_int]


def wait(check, timeout=30, what='native UI transition'):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        result = check()
        if result:
            return result
        time.sleep(.05)
    raise TimeoutError(what)


def focus(window, child):
    assert window and child, 'missing native focus target'
    U.SetForegroundWindow(window)
    wait(lambda: U.GetForegroundWindow() == window, 10, 'foreground host')
    current = C.windll.kernel32.GetCurrentThreadId()
    target = U.GetWindowThreadProcessId(child, None)
    assert U.AttachThreadInput(current, target, True)
    try:
        U.SetFocus(child)
    finally:
        U.AttachThreadInput(current, target, False)


def tap(vk, modifiers=()):
    events = [(key, 0) for key in modifiers] + [(vk, 0), (vk, 2)]
    events += [(key, 2) for key in reversed(modifiers)]
    inputs = (Input * len(events))()
    for item, (key, flags) in zip(inputs, events):
        item.type = 1
        item.payload.keyboard = Keyboard(vk=key, flags=flags)
    assert U.SendInput(len(inputs), inputs, C.sizeof(Input)) == len(inputs)
    time.sleep(.12)


def page_key(window, vk, modifiers=()):
    focus(window, U.GetDlgItem(window, 123))
    tap(vk, modifiers)


def inventory(window, output):
    controls = []

    @ENUM
    def visit(child, unused):
        name = C.create_unicode_buffer(100)
        U.GetClassNameW(child, name, len(name))
        controls.append({'id': U.GetDlgCtrlID(child), 'class': name.value,
                         'visible': bool(U.IsWindowVisible(child)),
                         'enabled': bool(U.IsWindowEnabled(child))})
        return True

    U.EnumChildWindows(window, visit, 0)
    output.write_text(json.dumps(controls, indent=2) + '\n', encoding='utf-8')


def file_dialog(pid):
    found = []

    @ENUM
    def visit(window, unused):
        owner = W.DWORD()
        U.GetWindowThreadProcessId(window, C.byref(owner))
        name = C.create_unicode_buffer(100)
        U.GetClassNameW(window, name, len(name))
        if owner.value == pid and name.value == '#32770' and U.IsWindowVisible(window):
            # edt1 is the documented filename edit in OPENFILENAME's template.
            if U.GetDlgItem(window, 0x480):
                found.append(window)
        return True

    U.EnumWindows(visit, 0)
    return found[-1] if found else 0


def begin_import(window, pid, path):
    wait(lambda: U.IsWindowEnabled(U.GetDlgItem(window, 127)), 120, 'import ready')
    page_key(window, ord('I'), (0x11,))
    dialog = wait(lambda: file_dialog(pid), what='native import file picker')
    edit = U.GetDlgItem(dialog, 0x480)
    text = C.create_unicode_buffer(str(path))
    assert U.SendMessageW(edit, 0xC, 0, C.addressof(text)), 'filename edit rejected path'
    # Submit with a real keyboard event; a synchronous click would block in the modal loop.
    focus(dialog, edit)
    tap(0x0D)
    wait(lambda: not U.IsWindow(dialog), what='file picker accepted the source')
    return dialog
