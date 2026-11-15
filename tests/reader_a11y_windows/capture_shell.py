#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Collect current shell UIA and measured keyboard focus, without claiming speech.

This audits a supplied production-shell binary in an isolated data directory.
Every key is bounded to the owned foreground process. Audit collection and
accessibility acceptance are separate; observed controls do not prove all UI.
"""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import time

from control_contract import audit
import evidence
from keyboard import Keyboard
from uia_layer import Uia
import w32


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', required=True, type=Path)
    parser.add_argument('--book', required=True, type=Path)
    parser.add_argument('--font', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--uia-only', action='store_true',
                        help='collect owned UIA InvokePattern surfaces without keyboard input')
    args = parser.parse_args()
    binary, book, font, output = (p.resolve() for p in
                                  (args.binary, args.book, args.font, args.output))
    output.mkdir(parents=True, exist_ok=True)
    trace = evidence.Trace(output / 'key-trace.jsonl')
    uia = Uia()
    if not uia.available:
        raise RuntimeError(uia.error)
    process = subprocess.Popen([str(binary), '--data', str(output / 'host-data'),
                                '--font', str(font), str(book)], cwd=binary.parent)
    hwnd, keyboard = None, None
    captures, errors = {}, []

    def press(key, modifiers=()):
        foreground = w32.foreground()
        if not foreground or w32.thread_id(foreground)[1] != process.pid:
            raise RuntimeError('owned process lost foreground; refusing desktop input')
        keyboard.press(key, modifiers)
        trace.event('keyboard_focus_observed', {
            'transport': keyboard.transport, 'key': key, 'modifiers': list(modifiers),
            'element': uia.focused()})

    def snapshot(label, steps):
        tree = uia.dump(hwnd, max_depth=20, max_nodes=5000, max_children=500)
        evidence.write_json(output / ('uia-' + label + '.json'), tree)
        captures[label] = audit(tree)
        start = len(trace.events)
        if keyboard:
            for _ in range(steps):
                press('tab')
            for _ in range(steps):
                press('tab', ('shift',))
        captures[label] = audit(tree, trace.events[start:])
        print('%s: controls=%d name_role_passed=%s observed_keyboard_controls=%d' % (
            label, len(captures[label]['controls']), captures[label]['name_role_passed'],
            sum(bool(r['observed_keyboard_steps']) for r in captures[label]['controls'])))

    def activate(identifier):
        targets = [child for child in w32.child_windows(hwnd)
                   if w32.ctrl_id(child) == identifier]
        if not targets:
            raise RuntimeError('missing owned control %d' % identifier)
        if args.uia_only:
            control = uia.control(targets[0])
            if 'InvokePattern' not in uia.patterns(control):
                raise RuntimeError('owned control %d has no InvokePattern' % identifier)
            control.GetInvokePattern().Invoke()
            trace.event('uia_invoke', {'control_id': identifier, 'element': uia.describe(control)})
            time.sleep(.35)
            return
        for _ in range(80):
            if keyboard.focus() in targets:
                press('space')
                time.sleep(.35)
                return
            press('tab')
        raise RuntimeError('keyboard did not reach control %d' % identifier)

    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and process.poll() is None:
            matches = [window for window in w32.top_windows()
                       if w32.thread_id(window)[1] == process.pid
                       and w32.class_name(window) == 'EXReaderHost']
            if matches:
                hwnd = matches[0]
                break
            time.sleep(.1)
        if not hwnd:
            raise RuntimeError('owned host window did not appear')
        time.sleep(2)
        if not args.uia_only:
            # Preserve a useful Name/role sample even if this host session cannot
            # foreground the app. It carries no keyboard claim.
            snapshot('closed', 0)
            if not w32.bring_to_front(hwnd):
                raise RuntimeError('owned host cannot take foreground')
            keyboard = Keyboard(hwnd, trace=trace, delay=.08)
            probe = keyboard.ensure()
            if probe.get('transport') != 'sendinput':
                raise RuntimeError('real keyboard transport unavailable: %r' % probe)
        snapshot('closed', 12)
        activate(162) if args.uia_only else press(0x46, ('ctrl',))
        snapshot('search', 20)
        activate(205) if args.uia_only else press('escape')
        activate(161)
        snapshot('settings', 60)
        activate(161) if args.uia_only else press('escape')
        activate(160)
        snapshot('toc', 16)
        activate(160) if args.uia_only else press('escape')
        activate(180) if args.uia_only else press(0x57, ('ctrl',))
        time.sleep(.3)
        snapshot('shelf', 30)
    except Exception as exc:
        errors.append('%s: %s' % (type(exc).__name__, exc))
    finally:
        if hwnd:
            w32.user32.PostMessageW(hwnd, w32.WM_CLOSE, 0, 0)
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            errors.append('owned process required termination after WM_CLOSE timeout')
        trace.close()
        result = {'kind': 'current-windows-shell-audit',
                  'generated_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                  'platform': platform.platform(), 'python': sys.version.split()[0],
                  'input_mode': 'UIA InvokePattern only; keyboard not run' if args.uia_only else 'SendInput',
                  'files': {str(p): digest(p) for p in (binary, book, font)},
                  'audit_completed': len(captures) == 5 and not errors,
                  'name_role_passed': len(captures) == 5 and not errors and all(
                      item['name_role_passed'] for item in captures.values()),
                  'captures': captures, 'errors': errors,
                  'complete_keyboard_verified': False, 'screen_reader_verified': False,
                  'missing': ['unopened dialogs and full product catalog flows',
                              'complete keyboard/arrow coverage', 'Narrator/NVDA speech',
                              'Linux/macOS/iPhone/iPad/Android runtime evidence']}
        evidence.write_json(output / 'all-controls.json', result)
        print(json.dumps({k: v for k, v in result.items() if k != 'captures'}, ensure_ascii=False, indent=2))
    return int(not result['audit_completed'])


if __name__ == '__main__':
    raise SystemExit(main())
