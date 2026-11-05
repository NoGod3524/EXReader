#!/usr/bin/env python3
"""Diagnose old observer compatibility against a retained packaged Windows executable."""
import ctypes as c
import hashlib
import json
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path('tests/reader_perf_windows').resolve()))
import perf_windows as perf

package = Path(os.environ['RETAINED_PACKAGE']).resolve()
out = Path('build/full-perf-inspection'); out.mkdir(parents=True, exist_ok=True)
host = perf.Host(package / 'EXReader.exe', package / 'Reader.otf', out / 'profile', out / 'application.log')
result = {'tested_source': '378bad2d', 'tested_run': 40395267422,
          'exe_sha256': hashlib.sha256((package / 'EXReader.exe').read_bytes()).hexdigest(),
          'observer': 'legacy first-screen probe; empty diagnostic profile', 'error': None, 'windows': []}
try:
    time.sleep(8)
    def describe(hwnd):
        name, title = c.create_unicode_buffer(256), c.create_unicode_buffer(1024)
        perf.U.GetClassNameW(hwnd, name, 256)
        perf.U.GetWindowTextW(hwnd, title, 1024)
        return {'class': name.value, 'title': title.value, 'id': perf.U.GetDlgCtrlID(hwnd),
                'visible': bool(perf.U.IsWindowVisible(hwnd)), 'enabled': bool(perf.U.IsWindowEnabled(hwnd))}
    @perf.ENUM
    def top(hwnd, _):
        pid = perf.W.DWORD()
        perf.U.GetWindowThreadProcessId(hwnd, c.byref(pid))
        if pid.value == host.process.pid:
            entry = describe(hwnd); entry['children'] = []
            @perf.ENUM
            def child(window, unused):
                entry['children'].append(describe(window)); return True
            perf.U.EnumChildWindows(hwnd, child, 0)
            result['windows'].append(entry)
        return True
    perf.U.EnumWindows(top, 0)
    try:
        result['first_screen'] = perf.op_first_screen(host, deadline=20)
    except Exception as exc:
        result['error'] = type(exc).__name__ + ': ' + str(exc)
    result['process_exit_before_close'] = host.process.poll()
finally:
    host.close()
    (out / 'inspection.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))
if result['error']:
    raise SystemExit('legacy observer failed; original error and window inventory retained')
