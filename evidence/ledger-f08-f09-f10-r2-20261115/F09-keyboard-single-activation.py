# SPDX-License-Identifier: MIT
"""Run tests/reader_a11y_windows/capture_shell.py with real SendInput keys and
at most one SetForegroundWindow call per run (owner rule 2026-11-05).

w32.bring_to_front normally retries up to six times and Keyboard.ready() would
re-grab foreground mid-run. Both are replaced here: the first call logs
"activating window for focus checks" and calls SetForegroundWindow once; every
later call only reports whether the host still owns the foreground. If the
foreground is refused the collector fails with "owned host cannot take
foreground" (reported as 无法获得前台) and no further grab is attempted.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tests' / 'reader_a11y_windows'))
import w32  # noqa: E402
import keyboard  # noqa: E402
import capture_shell  # noqa: E402

state = {'activations': 0}


def bring_to_front_once(hwnd):
    if state['activations'] == 0:
        state['activations'] += 1
        print('activating window for focus checks', flush=True)
        w32.user32.SetForegroundWindow(hwnd)
        import time
        time.sleep(0.3)
        if w32.foreground() != hwnd:
            print('无法获得前台', flush=True)
    return w32.foreground() == hwnd


w32.bring_to_front = bring_to_front_once
keyboard.Keyboard.ready = lambda self: (self.note_dialog(), True)[1]

if __name__ == '__main__':
    code = capture_shell.main()
    print('set_foreground_calls=%d' % state['activations'])
    raise SystemExit(code)
