#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Guard the S20 fixed seed, the immutable candidate and the exclusive write set."""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).absolute().parents[2]
SEED = 'd263ce5228838ac90c0a0dc13a5193d4a7739681'
SHA = re.compile(r'\A[0-9a-f]{40}\Z')
ALLOWED = (
    'tools/reader_wave3_package/',
    'tests/reader_wave3_s20/',
    '.github/workflows/reader-wave3-s20.yml',
    'docs/reader-wave3-s20/',
    'HANDOFF-RESULT-S20.md',
)


def git(*arguments):
    return subprocess.check_output(['git', '-C', str(ROOT), *arguments], text=True).strip()


def allowed(path):
    return any(path == item or path.startswith(item) for item in ALLOWED)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed', default=SEED)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    problems = []
    rows = {}
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        problems.append('the guard runs in GitHub Actions only')
    candidate = os.environ.get('S20_CANDIDATE') or os.environ.get('GITHUB_SHA', '')
    head = ''
    try:
        head = git('rev-parse', 'HEAD')
    except subprocess.CalledProcessError as error:
        problems.append('cannot read HEAD: ' + str(error))
    if not SHA.match(candidate or ''):
        problems.append('candidate input must be the full lowercase 40-hex commit id')
    if head and candidate and head != candidate:
        problems.append('checked-out HEAD differs from the requested candidate')
    if head and not SHA.match(args.seed):
        problems.append('seed must be the full lowercase 40-hex commit id')
    try:
        git('cat-file', '-e', args.seed + '^{commit}')
    except subprocess.CalledProcessError:
        problems.append('the fixed seed commit is not present in this checkout')
    try:
        result = subprocess.run(['git', '-C', str(ROOT), 'merge-base', '--is-ancestor', args.seed, 'HEAD'])
        if result.returncode != 0:
            problems.append('the fixed seed is not an ancestor of the candidate')
    except OSError as error:
        problems.append('cannot compare the seed ancestry: ' + str(error))
    changed = []
    if head:
        try:
            changed = [line for line in git('diff', '--name-only', args.seed, head).splitlines() if line]
        except subprocess.CalledProcessError as error:
            problems.append('cannot list changed paths: ' + str(error))
    outside = [path for path in changed if not allowed(path)]
    if outside:
        problems.append('paths outside the exclusive write set: ' + ', '.join(outside[:10]))
    frozen = []
    try:
        frozen = [line for line in git('diff', '--name-only', args.seed, head, '--',
                                       'src', 'include', 'cmake', 'CMakeLists.txt', 'CMakePresets.json',
                                       'bindings', 'apps', 'extras', 'examples', 'tests/fixtures',
                                       'README.md').splitlines() if line]
    except subprocess.CalledProcessError as error:
        problems.append('cannot inspect the frozen tree: ' + str(error))
    if frozen:
        problems.append('frozen SDK, platform or task files changed: ' + ', '.join(frozen[:10]))
    rows = {'seed': args.seed, 'candidate': candidate, 'head': head,
            'changed': changed, 'outside': outside, 'frozen': frozen}
    report = {'schema': 1, 'accepted': not problems, 'problems': problems, **rows,
              'allowed': list(ALLOWED), 'runner': os.environ.get('RUNNER_OS', ''),
              'run_id': os.environ.get('GITHUB_RUN_ID', ''), 'attempt': os.environ.get('GITHUB_RUN_ATTEMPT', '')}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps({'accepted': report['accepted'], 'problems': problems, 'changed': len(changed),
                      'seed': args.seed, 'candidate': candidate}, ensure_ascii=True))
    return 0 if report['accepted'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
