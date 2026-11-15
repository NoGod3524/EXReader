# SPDX-License-Identifier: MIT
"""Summarize run 43769173285: per-surface Tab/Shift+Tab focus order and the keyboard trap.

Reads only the archived artifact files; prints a deterministic text summary.
"""
import json, sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')
root = Path(sys.argv[1])
result = json.loads((root / 'all-controls.json').read_text(encoding='utf-8'))
events = [json.loads(line) for line in (root / 'key-trace.jsonl').read_text(encoding='utf-8').splitlines() if line]
keys = [e for e in events if e['kind'] == 'keyboard_focus_observed']
print('platform=%s input_mode=%s keyboard_events=%d audit_completed=%s name_role_passed=%s errors=%s' % (
    result['platform'], result['input_mode'], len(keys), result['audit_completed'],
    result['name_role_passed'], result['errors']))
print('collected=%s missing_surfaces=%s' % (list(result['captures']),
      [s for s in result['expected_surfaces'] if s not in result['captures']]))
for label, capture in result['captures'].items():
    rows = capture['controls']
    focusable = [r for r in rows if r['keyboard_focusable']]
    reached = [r for r in rows if r['observed_keyboard_steps']]
    order = [r['name'] for r in sorted(reached, key=lambda r: min(s['seq'] for s in r['observed_keyboard_steps']))]
    print('%s: controls=%d focusable=%d observed=%d order=%s' % (label, len(rows), len(focusable), len(reached), order))
    print('  focusable_not_reached=%s' % [r['name'] for r in focusable if not r['observed_keyboard_steps']])
run, last = 0, None
for e in keys:
    name = (e['payload'].get('element') or {}).get('name')
    run = run + 1 if e['payload']['key'] == 'tab' and name == last else 1
    last = name
print('final consecutive Tab or Shift+Tab presses on the same element: %d (%s)' % (run, last))
