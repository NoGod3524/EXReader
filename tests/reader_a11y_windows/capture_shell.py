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


def verdict(captures, expected, errors, child_exit):
    """A complete collection with a failed control assertion must fail the CLI."""
    completed = set(captures) == set(expected) and not errors and child_exit == 0
    return {'audit_completed': completed,
            'name_role_passed': completed and all(
                item['name_role_passed'] for item in captures.values()),
            'child_exit_code': child_exit,
            'complete_keyboard_verified': False, 'screen_reader_verified': False}


def self_check():
    good = audit([{'name': 'Search', 'type_id': 50004, 'focusable': True}])
    bad = audit([{'name': '', 'type_id': 50004, 'focusable': True}])
    assert verdict({'reader': good}, ['reader'], [], 0)['name_role_passed']
    failed = verdict({'reader': bad}, ['reader'], [], 0)
    assert failed['audit_completed'] and not failed['name_role_passed']
    assert not verdict({'reader': good}, ['reader', 'sync'], [], 0)['audit_completed']
    assert not verdict({'reader': good, 'extra': good}, ['reader'], [], 0)['audit_completed']
    assert not verdict({'reader': good}, ['reader'], ['provider disconnected'], 0)['name_role_passed']
    assert not verdict({'reader': good}, ['reader'], [], 77)['name_role_passed']
    assert not verdict({'reader': good}, ['reader'], [], None)['name_role_passed']
    assert not failed['complete_keyboard_verified'] and not failed['screen_reader_verified']
    print('PASS shell audit gate: unnamed controls, missing/extra surfaces, collection errors and abnormal child exits fail; keyboard/speech remain missing')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-check', action='store_true')
    parser.add_argument('--binary', type=Path)
    parser.add_argument('--book', type=Path)
    parser.add_argument('--font', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--extended', action='store_true',
                        help='also collect dictionary settings, vocabulary and WebDAV account panels')
    parser.add_argument('--reach', action='store_true',
                        help='also drive conditional controls into reach: a real search with results, '
                             'a saved style preset and arrow keys through the table of contents')
    parser.add_argument('--uia-only', action='store_true',
                        help='collect owned UIA InvokePattern surfaces without keyboard input')
    args = parser.parse_args()
    if args.self_check:
        self_check()
        return 0
    if any(p is None for p in (args.binary, args.book, args.font, args.output)):
        parser.error('--binary, --book, --font and --output are required for collection')
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
    expected = ['closed', 'search', 'settings', 'toc', 'shelf']
    if args.extended:
        expected += ['dictionary-settings', 'vocabulary', 'webdav-account']
    if args.reach:
        expected += ['search-results', 'settings-preset', 'toc-arrows']

    def press(key, modifiers=()):
        foreground = w32.foreground()
        if not foreground or w32.thread_id(foreground)[1] != process.pid:
            raise RuntimeError('owned process lost foreground; refusing desktop input')
        keyboard.press(key, modifiers)
        trace.event('keyboard_focus_observed', {
            'transport': keyboard.transport, 'key': key, 'modifiers': list(modifiers),
            'element': uia.focused()})

    def snapshot(label, steps, extra=()):
        tree = uia.dump(hwnd, max_depth=20, max_nodes=5000, max_children=500)
        evidence.write_json(output / ('uia-' + label + '.json'), tree)
        captures[label] = audit(tree)
        start = len(trace.events)
        if keyboard:
            for key, modifiers in extra:
                press(key, modifiers)
            for _ in range(steps):
                press('tab')
            for _ in range(steps):
                press('tab', ('shift',))
        captures[label] = audit(tree, trace.events[start:])
        print('%s: controls=%d name_role_passed=%s observed_keyboard_controls=%d' % (
            label, len(captures[label]['controls']), captures[label]['name_role_passed'],
            sum(bool(r['observed_keyboard_steps']) for r in captures[label]['controls'])))

    def activate(identifier, panel_title=None):
        targets = [child for child in w32.child_windows(hwnd)
                   if w32.ctrl_id(child) == identifier
                   and w32.user32.IsWindowVisible(child)
                   and w32.user32.IsWindowEnabled(child)
                   and (panel_title is None or w32.window_text(w32.parent(child)) == panel_title)]
        if len(targets) != 1:
            raise RuntimeError('expected one visible enabled owned control %d, found %d' %
                               (identifier, len(targets)))
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
        if args.reach and not args.uia_only:
            # Focus is back in the query field after the balanced walk: type a
            # query with matches so the previous/next result buttons enable.
            for virtual_key in (0x41, 0x4C, 0x49, 0x43, 0x45):  # a l i c e
                press(virtual_key)
            press('enter')
            time.sleep(1.5)
            snapshot('search-results', 24)
        activate(205) if args.uia_only else press('escape')
        activate(161)
        snapshot('settings', 60)
        if args.reach and not args.uia_only:
            activate(1841)  # 保存为预设: a saved preset enables the preset list button
            time.sleep(.5)
            snapshot('settings-preset', 62)
        activate(161) if args.uia_only else press('escape')
        activate(160)
        snapshot('toc', 16)
        if args.reach and not args.uia_only:
            # One Tab stop for the list; chapters are reached with the arrow keys.
            snapshot('toc-arrows', 0, [('down', ())] * 24 + [('home', ()), ('end', ()), ('up', ())])
        activate(160) if args.uia_only else press('escape')
        if args.extended:
            activate(161)
            activate(183)
            snapshot('dictionary-settings', 20)
            activate(813, '词典设置')
            snapshot('vocabulary', 20)
            activate(815, '生词本')
            activate(161)
            activate(184)
            snapshot('webdav-account', 24)
            activate(846)
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
                  'collector_sha256': digest(Path(__file__).resolve()),
                  'control_contract_sha256': digest(Path(__file__).resolve().with_name('control_contract.py')),
                  'expected_surfaces': expected,
                  **verdict(captures, expected, errors, process.returncode),
                  'captures': captures, 'errors': errors,
                  'missing': ['unopened dialogs and full product catalog flows',
                              'complete keyboard/arrow coverage', 'Narrator/NVDA speech',
                              'Linux/macOS/iPhone/iPad/Android runtime evidence']}
        evidence.write_json(output / 'all-controls.json', result)
        print(json.dumps({k: v for k, v in result.items() if k != 'captures'}, ensure_ascii=False, indent=2))
    return int(not result['name_role_passed'])


if __name__ == '__main__':
    raise SystemExit(main())
