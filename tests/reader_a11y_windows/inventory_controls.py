#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Inventory every native control creation site, including unnamed/dynamic sites.

This is a source coverage audit, never a UIA or speech acceptance result.
Repeated loop constructors are sites, not a count of runtime controls.
"""
import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CALL = re.compile(r'\b(CreateWindow(?:Ex)?W|shell_make_button)\s*\(')


def calls(source):
    # Mask comments while keeping offsets, strings and newlines intact.
    source = re.sub(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"',
                    lambda m: m[0] if m[0].startswith('"') else
                    re.sub(r'[^\n]', ' ', m[0]), source, flags=re.S)
    rows = []
    for match in CALL.finditer(source):
        depth, end = 1, match.end()
        for token in re.finditer(r'"(?:\\.|[^"\\])*"|[()]', source[end:]):
            if token[0] == '(':
                depth += 1
            elif token[0] == ')':
                depth -= 1
                if not depth:
                    end += token.end()
                    break
        expression = source[match.start():end]
        # Function declarations have no semicolon after the closing paren.
        if source[end:].lstrip().startswith('{'):
            continue
        rows.append({'line': source.count('\n', 0, match.start()) + 1,
                     'constructor': match[1], 'expression': expression,
                     'native_role_hint': re.findall(r'L"(BUTTON|EDIT|LISTBOX|COMBOBOX|STATIC|EXReaderPage)"', expression),
                     'tabstop_declared': 'WS_TABSTOP' in expression,
                     'name_role_focus_verified': False,
                     'missing': 'external UIA Name/ControlType and keyboard traversal for this site'})
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    # Negative controls: an unnamed control must remain visible in the audit.
    probe = calls('x=CreateWindowW(L"EDIT",L"",WS_TABSTOP,0,0,1,1,p,0,0,0);')
    assert len(probe) == 1 and probe[0]['tabstop_declared']
    assert not probe[0]['name_role_focus_verified']
    assert not calls('// CreateWindowW();\n/* shell_make_button(); */')
    rows, names = [], []
    paths = [ROOT/'examples/reader.c', *sorted((ROOT/'examples/windows').glob('shell_*.inc'))]
    for path in paths:
        source = path.read_text(encoding='utf-8')
        for row in calls(source):
            row['path'] = path.relative_to(ROOT).as_posix()
            rows.append(row)
        for number, line in enumerate(source.splitlines(), 1):
            if 'host_a11y_describe(' in line:
                names.append({'path': path.relative_to(ROOT).as_posix(), 'line': number, 'registration': line.strip()})
    assert rows and names
    result = {'kind': 'source-inventory', 'creation_sites': rows, 'name_registration_sites': names,
              'platforms': {p: {'keyboard': 'missing current complete runtime inventory',
                                'screen_reader': 'missing speech transcript/recording'}
                            for p in ['windows', 'linux', 'macos', 'iphone', 'ipad', 'android']}}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(f'PASS inventory: {len(rows)} creation sites, {len(names)} name registration sites; unnamed/dynamic sites retained')
    print('PASS negative controls: unnamed EDIT retained, comments ignored; runtime UIA/keyboard/speech remain missing')


if __name__ == '__main__':
    main()
