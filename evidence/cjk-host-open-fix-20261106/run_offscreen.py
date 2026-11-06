"""Run the three approved UI checks; only observe window/foreground state.

Usage: python run_offscreen.py RAW_DIRECTORY FONT
The host's --offscreen snapshot action uses PrintWindow, with no fallback.
"""
import ctypes as c
from ctypes import wintypes as w
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import time

root, font = map(Path, sys.argv[1:])
user = c.WinDLL('user32', use_last_error=True)
user.SetProcessDpiAwarenessContext.argtypes = [c.c_void_p]
assert user.SetProcessDpiAwarenessContext(c.c_void_p(-4)), c.get_last_error()
user.GetForegroundWindow.restype = w.HWND
user.GetWindowThreadProcessId.argtypes = [w.HWND, c.POINTER(w.DWORD)]
user.GetWindowRect.argtypes = [w.HWND, c.POINTER(w.RECT)]
user.GetClassNameW.argtypes = [w.HWND, w.LPWSTR, c.c_int]
callback_type = c.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
user.EnumWindows.argtypes = [callback_type, w.LPARAM]

for label in ('restore', 'fault'):
    db = root / (label + '-data') / 'library.sqlite'
    with sqlite3.connect(f'file:{db}?mode=ro', uri=True) as con:
        rows = con.execute('SELECT book_id,part,position FROM epub_progress WHERE book_id=2').fetchall()
    assert rows == [(2, 0, 0)], (label, rows)

for label in ('first', 'restore', 'fault'):
    out = root / ('ui-' + label)
    out.mkdir(exist_ok=True)
    script = root / (label + '.drive')
    allowed = {'wait_idle', 'shell', 'shell_dpi', 'shell_client', 'shell_font',
               'import', 'open', 'check', 'shell_measure', 'state', 'snapshot', 'quit'}
    assert all(line.split('|')[0] in allowed for line in script.read_text(encoding='utf-8').splitlines())
    exe = root / 'host' / ('EXReader-8m.exe' if label == 'fault' else 'EXReader.exe')
    args = [str(exe), '--offscreen', '--font', str(font), '--drive', str(script),
            '--data', str(root / (label + '-data')), '--evidence', str(out)]
    started = time.monotonic()
    process = subprocess.Popen(args, creationflags=subprocess.CREATE_NO_WINDOW,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    observations, foreground, rects = 0, 0, set()
    violations = []

    @callback_type
    def observe(hwnd, unused):
        owner = w.DWORD()
        user.GetWindowThreadProcessId(hwnd, c.byref(owner))
        if owner.value == process.pid:
            name = c.create_unicode_buffer(256)
            user.GetClassNameW(hwnd, name, len(name))
            if name.value == 'EXReaderHost':
                rect = w.RECT()
                if not user.GetWindowRect(hwnd, c.byref(rect)):
                    violations.append('GetWindowRect failed')
                else:
                    rects.add((rect.left, rect.top, rect.right, rect.bottom))
                    if (rect.left, rect.top) != (-32000, -32000):
                        violations.append('window left approved offscreen position')
        return True

    try:
        while process.poll() is None:
            observations += 1
            owner = w.DWORD()
            user.GetWindowThreadProcessId(user.GetForegroundWindow(), c.byref(owner))
            if owner.value == process.pid:
                foreground += 1
                violations.append('host became foreground')
            user.EnumWindows(observe, 0)
            if violations:
                raise RuntimeError(violations)
            if time.monotonic() - started > 240:
                raise TimeoutError(label)
            time.sleep(.02)
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait()
        result = {'command': args, 'exit': process.returncode,
                  'elapsed_seconds': round(time.monotonic() - started, 3),
                  'observations': observations, 'foreground_observations': foreground,
                  'window_rectangles': sorted(rects), 'violations': violations,
                  'executable_sha256': hashlib.sha256(exe.read_bytes()).hexdigest()}
        (out / 'process.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    log = (out / 'drive.log').read_text(encoding='utf-8')
    failures = [line for line in log.splitlines() if line.startswith('STEP\t') and '\tFAIL\t' in line]
    shots = list(out.glob('*.png'))
    assert process.returncode == 0 and not failures, (label, result, failures)
    assert rects and foreground == 0 and len(shots) == 1, (label, result, shots)
    print(json.dumps({'phase': label, **result, 'screenshots': list(map(str, shots))}), flush=True)
