#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Exhaustive assertions over captured UIA controls, independent of control IDs."""
import argparse
import json
from pathlib import Path

ACTIONABLE = {50000, 50002, 50003, 50004, 50005, 50007, 50008, 50009,
              50010, 50011, 50013, 50014, 50015, 50016, 50018, 50019,
              50020, 50023, 50024, 50025, 50029, 50030}


def audit(payload):
    rows, errors = [], []

    def visit(node, address):
        if not isinstance(node, dict):
            errors.append(address + ': invalid node')
            return
        children = node.get('children', [])
        if node.get('error') or node.get('truncated') or node.get('children_truncated') or node.get('child_count', len(children)) > len(children):
            errors.append(address + ': incomplete UIA tree')
        role = node.get('control_type_id', node.get('type_id'))
        focusable = node.get('keyboard_focusable', node.get('focusable', False))
        # The system title-bar container is unnamed on Windows; its individual
        # minimize/maximize/close Buttons are still checked below it.
        if role in ACTIONABLE or (focusable and role != 50037):
            name = (node.get('name') or '').strip()
            rows.append({'address': address, 'id': node.get('automation_id', node.get('id')),
                         'name': name, 'role': role, 'name_ok': bool(name),
                         'role_ok': isinstance(role, int) and 50000 <= role <= 50040,
                         'keyboard_focusable': focusable,
                         'focus_order': 'missing measured Tab/arrow-key trace',
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
    assert not audit([dict(base, child_count=2, children=[])])['name_role_passed']
    assert not audit([])['name_role_passed']
    assert audit([base, {'type_id': 50037, 'name': None, 'focusable': True}])['name_role_passed']
    # A newly added nested control is included without extending an ID whitelist.
    result = audit({'tree': dict(base, children=[dict(base, name='')])})
    assert len(result['controls']) == 2 and not result['name_role_passed']
    print('PASS UIA contract: all nested controls; missing name/role, truncated/empty tree rejected; focus/speech never inferred')


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
