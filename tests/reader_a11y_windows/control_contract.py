#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Exhaustive assertions over captured UIA controls, independent of control IDs."""
import argparse
import json
from pathlib import Path

ACTIONABLE = {50000, 50001, 50002, 50003, 50004, 50005, 50007, 50008, 50009,
              50010, 50011, 50013, 50014, 50015, 50016, 50018, 50019,
              50020, 50021, 50023, 50024, 50025, 50027, 50028, 50029,
              50030, 50031, 50035, 50039, 50040}
ACTION_PATTERNS = {'InvokePattern', 'ValuePattern', 'RangeValuePattern',
                   'SelectionItemPattern', 'TogglePattern', 'ExpandCollapsePattern'}


def audit(payload, focus_events=()):
    rows, errors = [], []

    def visit(node, address):
        if not isinstance(node, dict):
            errors.append(address + ': invalid node')
            return
        children = node.get('children', [])
        if not isinstance(children, list):
            errors.append(address + ': invalid children')
            children = []
        count = node.get('child_count', len(children))
        if type(count) is not int or count < 0 or count != len(children):
            errors.append(address + ': inconsistent child count')
        if node.get('error') or node.get('truncated') or node.get('children_truncated'):
            errors.append(address + ': incomplete UIA tree')
        role = node.get('control_type_id', node.get('type_id'))
        if type(role) is not int or not 50000 <= role <= 50040:
            errors.append(address + ': missing or invalid UIA role')
        focusable = node.get('keyboard_focusable', node.get('focusable', False))
        if type(focusable) is not bool:
            errors.append(address + ': invalid keyboard focusability')
        patterns = node.get('patterns', [])
        if not isinstance(patterns, list) or not all(isinstance(p, str) for p in patterns):
            errors.append(address + ': invalid control patterns')
            patterns = []
        # The system title-bar container is unnamed on Windows; its individual
        # minimize/maximize/close Buttons are still checked below it.
        if role != 50037 and (role in ACTIONABLE or ACTION_PATTERNS.intersection(patterns) or focusable):
            raw_name = node.get('name')
            name = raw_name.strip() if isinstance(raw_name, str) else ''
            observed = []
            for event in focus_events:
                if event.get('kind') != 'keyboard_focus_observed':
                    continue
                value = event.get('payload', {})
                focused = value.get('element') or {}
                # Match the raw observed element, never an ID/name alone. Posted
                # modifier keys and harness focus recovery are not keyboard proof.
                identity = ('native_hwnd', 'process_id', 'automation_id', 'control_type_id', 'name')
                if (value.get('transport') == 'sendinput' and node.get('native_hwnd')
                        and all(node.get(k) == focused.get(k) for k in identity)):
                    observed.append({'seq': event.get('seq'), 'key': value.get('key'),
                                     'modifiers': value.get('modifiers', [])})
            rows.append({'address': address, 'id': node.get('automation_id', node.get('id')),
                         'name': name, 'role': role, 'name_ok': bool(name),
                         'role_ok': type(role) is int and 50000 <= role <= 50040,
                         'keyboard_focusable': focusable,
                         'enabled': node.get('enabled'), 'offscreen': node.get('offscreen'),
                         'action_patterns': sorted(ACTION_PATTERNS.intersection(patterns)),
                         'observed_keyboard_steps': observed,
                         'focus_order': 'observed steps only; complete order missing' if observed else 'missing measured Tab/arrow-key trace',
                         'screen_reader': 'missing speech evidence'})
        for index, child in enumerate(children):
            visit(child, address + '/' + str(index))

    tree = payload.get('tree', payload) if isinstance(payload, dict) else payload
    for index, root in enumerate(tree if isinstance(tree, list) else [tree]):
        visit(root, str(index))
    if not rows:
        errors.append('no interactive controls captured')
    return {'controls': rows, 'errors': errors,
            'name_role_passed': bool(rows) and not errors and all(r['name_ok'] and r['role_ok'] for r in rows),
            'complete_keyboard_verified': False, 'screen_reader_verified': False}


def self_test():
    base = {'name': 'Search', 'type_id': 50004, 'focusable': True}
    assert audit([base])['name_role_passed']
    assert not audit([dict(base, name='')])['name_role_passed']
    assert not audit([dict(base, name=None)])['name_role_passed']
    assert not audit([dict(base, type_id=0)])['name_role_passed']
    assert not audit([base, {'type_id': 0, 'focusable': False}])['name_role_passed']
    assert not audit([dict(base, type_id=50031, name='', focusable=False)])['name_role_passed']
    assert not audit([dict(base, child_count=2, children=[])])['name_role_passed']
    for bad in ({'children': None}, {'child_count': '0'}, {'child_count': -1},
                {'child_count': 0, 'children': [base]}, {'name': 123},
                {'focusable': 'false'}, {'patterns': None}, {'patterns': [42]}):
        assert not audit([dict(base, **bad)])['name_role_passed'], bad
    # A custom image/pane can act through a pattern without a Tab stop.
    assert not audit([{'type_id': 50006, 'name': '', 'patterns': ['InvokePattern']}])['name_role_passed']
    assert not audit([])['name_role_passed']
    assert audit([base, {'type_id': 50037, 'name': None, 'focusable': True}])['name_role_passed']
    assert audit([base, {'type_id': 50037, 'name': None, 'patterns': ['ValuePattern']}])['name_role_passed']
    # A newly added nested control is included without extending an ID whitelist.
    result = audit({'tree': dict(base, children=[dict(base, name='')])})
    assert len(result['controls']) == 2 and not result['name_role_passed']
    current = dict(base, native_hwnd=17, process_id=21, automation_id='search', control_type_id=50004)
    event = {'kind': 'keyboard_focus_observed', 'seq': 7,
             'payload': {'transport': 'sendinput', 'key': 'tab', 'modifiers': [], 'element': current}}
    assert audit([current], [event])['controls'][0]['observed_keyboard_steps'] == [{'seq': 7, 'key': 'tab', 'modifiers': []}]
    for changed in ({'transport': 'postmessage'}, {'element': dict(current, process_id=22)},
                    {'element': dict(current, native_hwnd=18)}):
        bad = dict(event, payload=dict(event['payload'], **changed))
        assert not audit([current], [bad])['controls'][0]['observed_keyboard_steps']
    assert not audit([current], [event])['complete_keyboard_verified']
    from uia_layer import Uia
    collector = object.__new__(Uia)
    collector.describe = lambda control, patterns: dict(base)

    class BrokenChildren:
        def GetChildren(self):
            raise RuntimeError('provider disconnected')

    broken_tree = collector._dump(BrokenChildren(), 0, 4, 600, 1, 60, {'nodes': 0})
    assert 'child enumeration failed' in broken_tree['error']
    assert not audit(broken_tree)['name_role_passed']
    print('PASS UIA contract: nested/action-pattern controls; malformed/incomplete trees rejected; exact observed focus identity only; complete keyboard/speech remain missing')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('captures', nargs='*', type=Path)
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    self_test()
    results = {str(p): audit(json.loads(p.read_text(encoding='utf-8'))) for p in args.captures}
    if args.out:
        args.out.write_text(json.dumps(results, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    for path, result in results.items():
        print(f"{path}: controls={len(result['controls'])} name_role_passed={result['name_role_passed']} errors={len(result['errors'])}; keyboard/speech=missing")
    return int(any(not result['name_role_passed'] for result in results.values()))


if __name__ == '__main__':
    raise SystemExit(main())
