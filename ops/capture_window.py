#!/usr/bin/env python3
"""PID-scoped, physical-pixel PrintWindow capture (also works offscreen).

Usage: python -X utf8 capture_window.py PID OUT.png [--hwnd HWND]
"""
import ctypes as C
from ctypes import wintypes as W
import json
from pathlib import Path
import sys
from PIL import Image

U, G = C.windll.user32, C.windll.gdi32
U.SetProcessDpiAwarenessContext.argtypes = [C.c_void_p]
# Set BEFORE querying geometry or allocating the bitmap. PrintWindow paints
# physical pixels even when an unaware caller receives virtualized rectangles.
U.SetProcessDpiAwarenessContext(C.c_void_p(-4))
U.GetForegroundWindow.restype = W.HWND
U.GetWindowThreadProcessId.argtypes = [W.HWND, C.POINTER(W.DWORD)]
U.GetWindowRect.argtypes = U.GetClientRect.argtypes = [W.HWND, C.POINTER(W.RECT)]
U.ClientToScreen.argtypes = [W.HWND, C.POINTER(W.POINT)]
U.GetDpiForWindow.argtypes = [W.HWND]
U.IsWindowVisible.argtypes = [W.HWND]
U.GetWindowTextW.argtypes = [W.HWND, W.LPWSTR, C.c_int]
U.GetWindowDC.argtypes = [W.HWND]
U.GetWindowDC.restype = W.HDC
U.ReleaseDC.argtypes = [W.HWND, W.HDC]
U.PrintWindow.argtypes = [W.HWND, W.HDC, W.UINT]
G.CreateCompatibleDC.argtypes = [W.HDC]
G.CreateCompatibleDC.restype = W.HDC
G.CreateCompatibleBitmap.argtypes = [W.HDC, C.c_int, C.c_int]
G.CreateCompatibleBitmap.restype = W.HBITMAP
G.SelectObject.argtypes = [W.HDC, W.HANDLE]
G.SelectObject.restype = W.HANDLE
G.DeleteObject.argtypes = [W.HANDLE]
G.DeleteDC.argtypes = [W.HDC]
G.GetDIBits.argtypes = [W.HDC, W.HBITMAP, W.UINT, W.UINT, C.c_void_p, C.c_void_p, W.UINT]
CALLBACK = C.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
U.EnumWindows.argtypes = [CALLBACK, W.LPARAM]


def window(pid):
    hits = []
    @CALLBACK
    def visit(hwnd, _):
        found = W.DWORD()
        U.GetWindowThreadProcessId(hwnd, C.byref(found))
        title = C.create_unicode_buffer(256)
        U.GetWindowTextW(hwnd, title, 256)
        if found.value == pid and U.IsWindowVisible(hwnd) and title.value:
            hits.append(hwnd)
        return True
    U.EnumWindows(visit, 0)
    assert len(hits) == 1, (pid, hits)
    return hits[0]


def capture(pid, output, hwnd=None):
    hwnd = hwnd or window(pid)
    found = W.DWORD()
    U.GetWindowThreadProcessId(hwnd, C.byref(found))
    assert found.value == pid, (pid, hwnd, found.value)
    outer, client, origin = W.RECT(), W.RECT(), W.POINT()
    assert U.GetWindowRect(hwnd, C.byref(outer))
    assert U.GetClientRect(hwnd, C.byref(client))
    assert U.ClientToScreen(hwnd, C.byref(origin))
    w, h = outer.right-outer.left, outer.bottom-outer.top
    dc = U.GetWindowDC(hwnd)
    memory = G.CreateCompatibleDC(dc)
    bitmap = G.CreateCompatibleBitmap(dc, w, h)
    previous = G.SelectObject(memory, bitmap)
    try:
        assert U.PrintWindow(hwnd, memory, 2)
        # BITMAPINFOHEADER, top-down BGRA, no colour table for BI_RGB.
        import struct
        header = struct.pack('<IiiHHIIiiII', 40, w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
        pixels = C.create_string_buffer(w*h*4)
        assert G.GetDIBits(memory, bitmap, 0, h, pixels, header, 0) == h
        Image.frombytes('RGB', (w, h), pixels.raw, 'raw', 'BGRX').save(output)
    finally:
        G.SelectObject(memory, previous)
        G.DeleteObject(bitmap)
        G.DeleteDC(memory)
        U.ReleaseDC(hwnd, dc)
    return dict(window=[w,h], client=[client.right,client.bottom],
                client_box=[origin.x-outer.left,origin.y-outer.top,client.right,client.bottom],
                position=[outer.left,outer.top], dpi=U.GetDpiForWindow(hwnd))


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pid', type=int)
    parser.add_argument('output', type=Path)
    parser.add_argument('--hwnd', type=lambda value: int(value, 0))
    args = parser.parse_args()
    print(json.dumps(capture(args.pid, args.output, args.hwnd)))
