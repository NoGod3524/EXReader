#!/usr/bin/env python3
"""Typography evidence on original books; HWNDs never activate.

All PNGs are captured by the owner's DPI-aware capture_window.py, not by the
reader's snapshot action. Call run() with shell_measure checkpoints followed
by probe_wait|1800 to allow the external capture to finish.
"""
import ctypes as C
from ctypes import wintypes as W
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

U = C.windll.user32
U.SetProcessDpiAwarenessContext(C.c_void_p(-4))
U.GetForegroundWindow.restype = W.HWND
U.GetWindowThreadProcessId.argtypes = [W.HWND, C.POINTER(W.DWORD)]
HIDDEN = subprocess.CREATE_NO_WINDOW


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(exe, script, out, capture, shots=(), font=None, timeout=240):
    out = Path(out).resolve(); out.mkdir(parents=True, exist_ok=True)
    profile = out/'profile'; profile.mkdir(exist_ok=True)
    drive = out/'run.drive'; drive.write_text(script, encoding='utf-8')
    cmd = [str(exe), '--offscreen', '--drive', str(drive), '--data', str(profile), '--evidence', str(out)]
    if font: cmd += ['--font', str(font)]
    process = subprocess.Popen(cmd, creationflags=HIDDEN, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    captured = set(); foreground = 0; start = time.monotonic()
    try:
        while process.poll() is None:
            pid = W.DWORD(); U.GetWindowThreadProcessId(U.GetForegroundWindow(), C.byref(pid))
            foreground += pid.value == process.pid
            for name in shots:
                meta = out/(name+'.json')
                if name in captured or not meta.exists(): continue
                try: json.loads(meta.read_text(encoding='utf-8'))
                except (ValueError, PermissionError): continue
                result = subprocess.run([sys.executable, '-X', 'utf8', str(capture), str(process.pid), str(out/(name+'.png'))],
                                        capture_output=True, creationflags=HIDDEN, timeout=20)
                assert result.returncode == 0, result.stdout + result.stderr
                captured.add(name)
            if time.monotonic()-start > timeout: raise TimeoutError(str(out))
            time.sleep(.03)
        stdout, stderr = process.communicate()
        result = dict(exit=process.returncode, foreground_observations=foreground,
                      elapsed_seconds=time.monotonic()-start, screenshots=sorted(captured),
                      stderr=stderr.decode(errors='replace'), command=cmd)
        dump(out/'process.json', result)
        assert process.returncode == 0 and foreground == 0 and captured == set(shots), result
        return result
    finally:
        if process.poll() is None: process.terminate(); process.wait(timeout=10)


def checkpoint(name):
    return f'wait_idle\nshell_measure|{name}\nprobe_wait|1800\n'


if __name__ == '__main__':
    # A small reusable runner for a reviewed drive file and named checkpoints.
    exe, drive, dest, capture, *shots = sys.argv[1:]
    run(Path(exe).resolve(), Path(drive).read_text(encoding='utf-8'), dest, capture, shots)
