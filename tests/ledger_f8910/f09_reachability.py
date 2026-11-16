#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""F09 Windows keyboard reachability over one capture_shell.py run.

Reads <dir>/all-controls.json and <dir>/key-trace.jsonl (real SendInput only)
and accounts for every UIA element that reports keyboard focusability:

  reached            focus was observed on it (Tab, Shift+Tab or arrow keys),
                     matched by name + control type inside the owned process,
                     because list items and MSAA children have no own HWND
  disabled           IsEnabled is false in that snapshot (not a focus stop);
                     reported in disabled_never_reached unless another snapshot
                     reached it while enabled
  container          a window/pane/group whose own descendants were reached
  part_of_reached    an offscreen internal part of a control that was reached
                     (for example a drop-down list combo box's selection text)
  window_chrome      the system menu bar/menu item reached with Alt, not Tab
  unexplained        anything else: the verdict fails

Name/role: every focusable element must have a non-empty name (audit name_ok).
Standard library only. Exit 0 when nothing is unexplained and names pass.
"""
import json
import sys
from pathlib import Path

CONTAINERS = {50032, 50033, 50026, 50021, 50008}   # Window, Pane, Group, ToolBar, List (one stop; items by arrows)
CHROME = {50010, 50011, 50037}              # MenuBar, MenuItem, TitleBar


def main(root):
    result = json.loads((root / 'all-controls.json').read_text(encoding='utf-8'))
    events = [json.loads(line) for line in (root / 'key-trace.jsonl').read_text(encoding='utf-8').splitlines() if line]
    focus = [e['payload'] for e in events if e['kind'] == 'keyboard_focus_observed']
    real = [p for p in focus if p.get('transport') == 'sendinput']
    seen = {}
    for payload in real:
        element = payload.get('element') or {}
        key = ((element.get('name') or '').strip(), element.get('control_type_id'))
        seen.setdefault(key, set()).add(payload['key'])
    arrows = {'up', 'down', 'left', 'right', 'home', 'end', 'prior', 'next'}
    report = {'keyboard_events': len(focus), 'sendinput_events': len(real), 'surfaces': {}, 'unexplained': [],
              'unnamed': []}
    disabled_rows = []
    for label, capture in result['captures'].items():
        rows = capture['controls']
        by_address = {r['address']: r for r in rows}
        reached = {r['address'] for r in rows if (r['name'].strip(), r['role']) in seen}
        surface = {'focusable': 0, 'reached': [], 'reached_by_arrow': [], 'disabled': [], 'container': [],
                   'part_of_reached': [], 'window_chrome': [], 'unexplained': []}
        for row in rows:
            if not row['keyboard_focusable']:
                continue
            surface['focusable'] += 1
            name, role, address = row['name'].strip(), row['role'], row['address']
            if not row.get('name_ok', True):
                report['unnamed'].append('%s:%s role=%s' % (label, address, role))
            if address in reached:
                keys = seen[(name, role)]
                (surface['reached_by_arrow'] if keys <= arrows else surface['reached']).append(name)
                continue
            descendants = [a for a in reached if a.startswith(address + '/')]
            ancestors = [a for a in reached if address.startswith(a + '/')]
            if not row['enabled']:
                surface['disabled'].append(name)
                disabled_rows.append((label, name, role))
            elif role in CONTAINERS and descendants:
                surface['container'].append(name)
            elif row['offscreen'] and ancestors:
                surface['part_of_reached'].append('%s (%s)' % (name, by_address[max(ancestors, key=len)]['name']))
            elif role in CHROME:
                surface['window_chrome'].append(name)
            else:
                surface['unexplained'].append('%s role=%s' % (name, role))
                report['unexplained'].append('%s:%s role=%s' % (label, name, role))
        report['surfaces'][label] = surface
    # Disabled is not a focus stop. Report each disabled control that real keys
    # never reached in any snapshot; it does not fail the verdict on its own.
    report['disabled_never_reached'] = sorted({'%s:%s' % (l, n) for l, n, r in disabled_rows if (n, r) not in seen})
    report['audit_completed'] = result['audit_completed']
    report['missing_surfaces'] = [s for s in result['expected_surfaces'] if s not in result['captures']]
    report['errors'] = result['errors']
    report['accepted'] = bool(result['audit_completed'] and not report['unexplained'] and not report['unnamed']
                              and not report['missing_surfaces']
                              and not report['errors'] and len(real) == len(focus) and focus)
    return report


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    report = main(Path(sys.argv[1]))
    for label, surface in report['surfaces'].items():
        print('%s: focusable=%d reached=%d by_arrow=%d disabled=%s container=%s part_of_reached=%s chrome=%s unexplained=%s' % (
            label, surface['focusable'], len(surface['reached']), len(surface['reached_by_arrow']), surface['disabled'],
            surface['container'], surface['part_of_reached'], surface['window_chrome'], surface['unexplained']))
    print('unnamed=%s disabled_never_reached=%s missing_surfaces=%s errors=%s' % (
        report['unnamed'], report['disabled_never_reached'], report['missing_surfaces'], report['errors']))
    print('keyboard_events=%d sendinput=%d accepted=%s' % (report['keyboard_events'], report['sendinput_events'], report['accepted']))
    if len(sys.argv) > 2:
        Path(sys.argv[2]).write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    raise SystemExit(0 if report['accepted'] else 1)
