#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Exit surface probe: close the packaged host with the keyboard and watch it end.

The existing GTK and Windows audits only close the host as teardown.  This probe
makes the exit a recorded check: the window must be named and focused, Alt+F4
must remove it, and the process must end by itself (never killed by the probe).
Imports the existing drivers read-only; no product file is touched.
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def finish(out, platform, checks, extra):
    out.mkdir(parents=True, exist_ok=True)
    (out / ('exit-%s.json' % platform)).write_text(
        json.dumps({'platform': platform, 'checks': checks, **extra}, indent=2,
                   ensure_ascii=False) + '\n', encoding='utf-8')
    for item in checks:
        print('EXIT-CHECK %s %s' % (item.get('name') or item.get('id'),
                                    'PASS' if item.get('pass') or item.get('status') == 'pass'
                                    else 'FAIL'), flush=True)


def gtk(args):
    sys.path.insert(0, str(ROOT / 'tests/reader_a11y_gtk'))
    import driver
    payload = args.payload.resolve(strict=True)
    folder = args.output / 'exit-gtk-run'
    folder.mkdir(parents=True, exist_ok=True)
    host = driver.Host(payload / 'bin/exreader-linux', payload / 'Reader.otf', folder)
    checks, extra = [], {}
    try:
        host.launch()
        title = driver.command('xdotool', 'getwindowname', host.window).stdout.strip()
        active = driver.command('xdotool', 'getactivewindow').stdout.strip()
        host.screenshot(args.output / 'exit-gtk-before.png')
        checks.append({'name': 'exit_window_named_and_focused_before_close',
                       'pass': title == 'EXReader Linux' and active == host.window,
                       'evaluated': True, 'severity': 'blocking',
                       'expected': 'window title EXReader Linux and active', 'actual':
                       'title=%r active=%r window=%r' % (title, active, host.window)})
        host.key('alt+F4')
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline and host.process.poll() is None:
            time.sleep(0.2)
        ended = host.process.poll() is not None
        gone = not driver.command('xdotool', 'search', '--pid', str(host.process.pid)).stdout.split() \
            if ended else False
        checks.append({'name': 'exit_alt_f4_window_closed', 'pass': ended and gone,
                       'evaluated': True, 'severity': 'blocking',
                       'expected': 'Alt+F4 removes the window', 'actual':
                       'process_ended=%s window_gone=%s' % (ended, gone)})
        code = host.process.returncode if ended else None
        checks.append({'name': 'exit_process_ended_without_kill', 'pass': ended and code == 0,
                       'evaluated': True, 'severity': 'blocking',
                       'expected': 'process exits by itself with code 0',
                       'actual': 'returncode=%r' % (code,)})
        extra['returncode'] = code
    except Exception as error:  # a failed launch is evidence, not a crash of the probe
        extra['error'] = repr(error)
        for name in ('exit_window_named_and_focused_before_close', 'exit_alt_f4_window_closed',
                     'exit_process_ended_without_kill'):
            if not any(c['name'] == name for c in checks):
                checks.append({'name': name, 'pass': False, 'evaluated': False,
                               'severity': 'blocking', 'expected': 'see check', 'actual': repr(error)})
    finally:
        if host.process and host.process.poll() is None:
            host.process.kill()
            extra['probe_had_to_kill'] = True
        if host.log and not host.log.closed:
            host.log.close()
    finish(args.output, 'gtk', checks, extra)


def windows(args):
    sys.path.insert(0, str(ROOT / 'tests/reader_a11y_windows'))
    import evidence, keyboard, png, w32
    from host import Host
    payload = args.payload.resolve(strict=True)
    trace = evidence.Trace(args.output / 'exit-windows-key-trace.jsonl')
    host = Host(payload / 'EXReader.exe', args.output / 'exit-windows-data', trace=trace, workdir=payload)
    checks, extra = [], {}

    def add(identifier, ok, expected, actual, status=None):
        checks.append({'id': identifier, 'status': status or ('pass' if ok else 'fail'),
                       'severity': 'blocking', 'expected': expected, 'actual': actual})
    try:
        host.start()
        title = w32.window_text(host.hwnd)
        reader = keyboard.Keyboard(host.hwnd, trace=trace)
        probe = reader.ensure()
        shot = w32.capture_rgb(host.hwnd)
        if shot and 'error' not in shot:
            png.write_png(args.output / 'exit-windows-before.png', shot['width'], shot['height'], shot['rgb'])
        foreground = w32.foreground()
        add('EXIT-01', bool(title) and foreground == host.hwnd,
            'main window has a title and the foreground', 'title=%r foreground=%s hwnd=%s'
            % (title, hex(foreground or 0), hex(host.hwnd)))
        if probe.get('transport') != 'sendinput':
            add('EXIT-02', False, 'Alt+F4 delivered by real keyboard input',
                'transport=%r; only SendInput counts as a keyboard exit' % (probe.get('transport'),),
                status='not_verified')
        result = host.close(keyboard=reader, timeout=45)
        extra['close'] = result
        if probe.get('transport') == 'sendinput':
            add('EXIT-02', result.get('requested') == 'alt+f4' and result.get('graceful'),
                'Alt+F4 ends the host', repr(result))
        add('EXIT-03', result.get('graceful') and not result.get('killed') and result.get('exit_code') == 0,
            'process exits by itself with code 0', repr(result))
    except Exception as error:
        extra['error'] = repr(error)
        for identifier in ('EXIT-01', 'EXIT-02', 'EXIT-03'):
            if not any(c['id'] == identifier for c in checks):
                add(identifier, False, 'see check', repr(error), status='error')
    finally:
        if host.alive():
            host.process.kill()
            extra['probe_had_to_kill'] = True
        trace.close()
    finish(args.output, 'windows', checks, extra)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('platform', choices=['gtk', 'windows'])
    parser.add_argument('--payload', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    arguments = parser.parse_args()
    arguments.output.mkdir(parents=True, exist_ok=True)
    {'gtk': gtk, 'windows': windows}[arguments.platform](arguments)
