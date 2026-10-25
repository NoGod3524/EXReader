# SPDX-License-Identifier: MIT
"""Actions-only rejection regressions; synthetic rows grant no UI acceptance."""
import copy
import json
import os
from pathlib import Path

from collect_ui import validate_observations


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only'
    owner = 'testTextThemesPreserveNonzeroPosition'
    original = 'original|ffffffff|' + '0' * 64 + '|42|第 2 页'
    rows = [{'role': role, 'bitmap': bitmap} for role, bitmap in [
        ('text-original', original), ('text-dark', 'dark|101010ff|' + '1' * 64 + '|42|第 2 页'),
        ('text-light', 'light|ffffffff|' + '2' * 64 + '|42|第 2 页'), ('text-original-roundtrip', original)]]
    validate_observations('macos', owner, rows)
    mutants = {'missing': rows[:-1], 'duplicate': rows + rows[:1], 'reordered': list(reversed(rows))}
    for name, find, replace in [('wrong_canvas', '101010ff', 'ffffffff'), ('different_offset', '|42|', '|43|'),
                                ('malformed_hash', '1' * 64, 'not-a-hash'), ('invalid_choice', 'dark|', 'foreign|'),
                                ('changed_location', '第 2 页', '第 3 页'), ('unchanged_dark_pixels', '1' * 64, '0' * 64)]:
        value = copy.deepcopy(rows); value[1]['bitmap'] = value[1]['bitmap'].replace(find, replace)
        assert value != rows, name
        mutants[name] = value
    value = copy.deepcopy(rows); value[-1]['bitmap'] = value[-1]['bitmap'].replace('0' * 64, '3' * 64)
    mutants['different_original_roundtrip'] = value
    rejected = []
    for name, value in mutants.items():
        try:
            validate_observations('macos', owner, value)
        except ValueError:
            rejected.append(name)
        else:
            raise AssertionError('accepted mutated native theme observations: ' + name)
    report = {'accepted': False, 'protocol_checks_passed': True, 'source_sha': os.environ['GITHUB_SHA'],
              'run_id': os.environ['GITHUB_RUN_ID'], 'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'rejected': rejected}
    output = Path('build/apple-theme-native/protocol.json'); output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print('PAGE_THEME_PROTOCOL_NEGATIVES', len(rejected))


if __name__ == '__main__':
    main()
