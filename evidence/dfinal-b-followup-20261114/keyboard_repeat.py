"""Diagnostic repetitions of the unchanged keyboard assertion; not acceptance retry."""
import ctypes
import json
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
USER = ctypes.WinDLL('user32', use_last_error=True)
USER.GetOpenClipboardWindow.restype = ctypes.c_void_p
USER.GetClipboardOwner.restype = ctypes.c_void_p
USER.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
USER.GetClipboardSequenceNumber.restype = ctypes.c_ulong


def snapshot():
    opened, owner = USER.GetOpenClipboardWindow(), USER.GetClipboardOwner()
    open_pid, owner_pid = ctypes.c_ulong(), ctypes.c_ulong()
    if opened:
        USER.GetWindowThreadProcessId(opened, ctypes.byref(open_pid))
    if owner:
        USER.GetWindowThreadProcessId(owner, ctypes.byref(owner_pid))
    return {'sequence': USER.GetClipboardSequenceNumber(), 'open_window': opened,
            'open_pid': open_pid.value, 'owner_window': owner, 'owner_pid': owner_pid.value,
            'physical_modifier_down': {name: bool(USER.GetAsyncKeyState(vk) & 0x8000)
                                       for name, vk in [('ctrl', 17), ('shift', 16), ('alt', 18)]}}


command = [str(ROOT / 'build/audit-msvc/exreader-shell-selection-test.exe'), 'keyboard',
           str(ROOT / 'tests/fixtures/fonts/primary.ttf')]
print('Diagnostic command:', json.dumps(command), flush=True)
results = []
for index in range(1, 41):
    before = snapshot()
    started = time.monotonic()
    process = subprocess.run(command, cwd=ROOT / 'build/audit-msvc', capture_output=True,
                             timeout=15, encoding='utf-8', errors='replace')
    result = {'attempt': index, 'exit': process.returncode,
              'seconds': round(time.monotonic()-started, 3),
              'before': before, 'after': snapshot()}
    results.append(result)
    print(json.dumps(result), flush=True)
    print(process.stdout, end='', flush=True)
    print(process.stderr, end='', flush=True)
print('Diagnostic summary:', json.dumps({'runs': len(results),
                                        'passed': sum(r['exit'] == 0 for r in results),
                                        'failed': sum(r['exit'] != 0 for r in results)}), flush=True)
