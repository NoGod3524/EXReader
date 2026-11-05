#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""S10 ownership guards: this package may only add its own four paths.

The base implementation commit is fixed by the work package.  Every owner tree
(apps, examples, src, include, cmake, bindings, tests/fixtures, existing tests
and workflows) must be byte identical to that commit, so the transfer evidence
can only describe the entries this repository already ships.
"""
import argparse
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = '0889f7d1e9a537c6c1b05456547e016b26e1cd85'
ALLOWED_PREFIXES = ('tests/reader_final_s10/', 'docs/reader-final-s10/')
ALLOWED_FILES = ('.github/workflows/reader-final-s10.yml', 'HANDOFF-RESULT.md')
PROTECTED = ('apps', 'examples', 'src', 'include', 'cmake', 'CMakeLists.txt', 'bindings',
             'tests/fixtures', 'extras', 'tools', 'docs/validation',
             '.github/workflows', ':!.github/workflows/reader-final-s10.yml')


def git(*args, check=True):
    return subprocess.run(['git', '-C', str(ROOT), *args], check=check,
                          capture_output=True, text=True)


def allowed(path):
    return path in ALLOWED_FILES or path.startswith(ALLOWED_PREFIXES)


def classify(paths):
    return {'allowed': [p for p in paths if allowed(p)],
            'rejected': [p for p in paths if not allowed(p)]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.absolute()
    output.mkdir(parents=True, exist_ok=True)
    head = git('rev-parse', 'HEAD').stdout.strip()
    checks = []

    def record(check_id, ok, detail):
        checks.append({'id': check_id, 'passed': bool(ok), 'detail': detail})

    expected = os.environ.get('GITHUB_SHA', '')
    record('source.head-matches-actions-sha', expected == '' or head == expected,
           'HEAD=' + head + ' GITHUB_SHA=' + expected)

    record('source.base-is-ancestor', git('merge-base', '--is-ancestor', BASE, 'HEAD',
                                          check=False).returncode == 0, 'base ' + BASE)

    diff = git('diff', '--name-only', BASE, 'HEAD').stdout.split()
    result = classify(diff)
    record('source.only-package-paths', not result['rejected'],
           'changed=' + ','.join(diff) + ' rejected=' + ','.join(result['rejected']))

    protected = git('diff', '--exit-code', BASE, 'HEAD', '--', *PROTECTED, check=False)
    record('source.protected-trees-unchanged', protected.returncode == 0,
           protected.stdout.strip() or 'no protected change')

    with_package = classify(['tests/reader_final_s10/check_entries.py',
                              'docs/reader-final-s10/validation.json',
                              'HANDOFF-RESULT.md',
                              '.github/workflows/reader-final-s10.yml'])
    record('negative.package-paths-accepted', not with_package['rejected'], json.dumps(with_package))
    foreign = classify(['apps/reader/desktop/x.c', 'examples/apple/HostModel.swift',
                        'tests/reader_desktop_drop/check_drop.c',
                        '.github/workflows/native.yml'])
    record('negative.foreign-paths-rejected', len(foreign['rejected']) == 4, json.dumps(foreign))

    new_workflow = git('show', 'HEAD:.github/workflows/reader-final-s10.yml', check=False)
    branch_trigger = 'codex/reader-fw-s10' in new_workflow.stdout
    record('source.workflow-triggers-own-branch-only', branch_trigger,
           'workflow triggers its own branch' if branch_trigger else 'workflow missing or foreign branch')

    problems = [row['id'] + ': ' + row['detail'] for row in checks if not row['passed']]
    report = {
        'schema': 1,
        'package': 'S10',
        'kind': 'ownership-guards',
        'source_sha': head,
        'base_sha': BASE,
        'changed_paths': diff,
        'checks': checks,
        'problems': problems,
        'accepted': not problems,
    }
    (output / 'guards.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'checks': len(checks), 'problems': problems}, indent=2))
    if problems:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
