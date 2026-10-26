# SPDX-License-Identifier: MIT
"""Exact source admission only; this does not grant product acceptance."""
import argparse
import json
from pathlib import Path
import re
import subprocess

MANIFEST = 'docs/reader-team24-composition/inputs.json'
ROOT_PATHS = frozenset((
    MANIFEST,
    'docs/reader-team24-composition/PLAN.md',
    'tools/reader_composition/guard.py',
    'tests/reader_composition/test_guard.py',
    '.github/workflows/reader-team24-composition.yml',
))
BASE = 'd263ce5228838ac90c0a0dc13a5193d4a7739681'


def git(*args):
    return subprocess.check_output(['git', *args])


def tree(source):
    result = {}
    for record in git('ls-tree', '-rz', source).split(b'\0'):
        if record:
            metadata, path = record.split(b'\t', 1)
            result[path.decode('utf-8')] = metadata.decode('ascii')
    return result


def differences(base, actual, pinned):
    errors = []
    owners = {}
    for name, expected in pinned:
        for path, identity in expected.items():
            if path in owners or path in ROOT_PATHS:
                errors.append('overlapping ownership: ' + path)
            owners[path] = name
            if identity is None or actual.get(path) != identity:
                errors.append('input identity mismatch: ' + path)
    for path in base.keys() | actual.keys():
        if base.get(path) != actual.get(path) and path not in owners and path not in ROOT_PATHS:
            errors.append('unregistered change: ' + path)
    return errors


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', required=True)
    parser.add_argument('--report', required=True)
    args = parser.parse_args()
    if not re.fullmatch('[0-9a-f]{40}', args.source):
        raise ValueError('source must be a full commit SHA')
    if git('rev-parse', 'HEAD').decode().strip() != args.source:
        raise ValueError('checkout differs from requested source')
    manifest = json.loads(git('show', args.source + ':' + MANIFEST))
    if manifest['schema'] != 1 or manifest['base'] != BASE:
        raise ValueError('composition base/schema changed')
    subprocess.run(['git', 'merge-base', '--is-ancestor', BASE, args.source], check=True)
    actual = tree(args.source)
    pinned = []
    names = set()
    for item in manifest['inputs']:
        name, source, paths = item['name'], item['source'], item['paths']
        if name in names or not name or not re.fullmatch('[0-9a-f]{40}', source):
            raise ValueError('duplicate name or invalid input source')
        names.add(name)
        if not paths or len(paths) != len(set(paths)):
            raise ValueError('empty or repeated input paths')
        subprocess.run(['git', 'merge-base', '--is-ancestor', source, args.source], check=True)
        expected = tree(source)
        pinned.append((name, {path: expected.get(path) for path in paths}))
    errors = differences(tree(BASE), actual, pinned)
    report = {
        'scope': 'composition-source-admission', 'product_accepted': False,
        'source': args.source, 'base': BASE, 'inputs': manifest['inputs'],
        'ok': not errors, 'errors': errors,
    }
    output = Path(args.report)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    if errors:
        raise SystemExit('\n'.join(errors))


if __name__ == '__main__':
    main()
