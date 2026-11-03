#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Exercise stale literals and all three evidence obligations without rebuilding SDKs."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import check_version_consistency as guard


def main():
    root = guard.ROOT
    path = root / guard.MANIFEST
    original = path.read_bytes()
    entries = json.loads(original)
    cases = 0
    try:
        output = io.StringIO()
        with redirect_stdout(output):
            assert not guard.check(root)
        for kind in ('stale-line', 'changed-literal', 'frozen-bytes', 'migration-reference',
                     'migration-removal', 'negative-assertion', 'duplicate'):
            rows = json.loads(original)
            entry = next(item for item in rows if item['purpose'] == {
                'frozen-bytes': 'frozen_baseline', 'migration-reference': 'migration_compat',
                'migration-removal': 'migration_compat', 'negative-assertion': 'negative_case'
            }.get(kind, 'frozen_baseline'))
            if kind == 'stale-line':
                entry['line'] = 10**9
            elif kind == 'changed-literal':
                entry['literal'] = '9.99.99'
            elif kind == 'frozen-bytes':
                entry['frozen_object']['sha256'] = '0' * 64
            elif kind == 'migration-reference':
                entry['migration_test']['invocation']['sha256'] = '0' * 64
            elif kind == 'migration-removal':
                entry['migration_test']['removal_condition'] = ''
            elif kind == 'negative-assertion':
                entry['rejection_assertion']['sha256'] = '0' * 64
            else:
                rows.append(dict(entry))
            path.write_text(json.dumps(rows), encoding='utf-8')
            output = io.StringIO()
            with redirect_stdout(output):
                assert guard.check(root), kind + ': invalid evidence accepted'
            assert f'{entry["file"]}:{entry["line"]}' in output.getvalue(), output.getvalue()
            cases += 1
            print('PASS: reject ' + kind)
    finally:
        path.write_bytes(original)
    print(f'PASS: valid manifest and {cases} refusal cases; all source bytes restored')


if __name__ == '__main__':
    main()
