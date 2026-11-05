#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""S02 source guard: fixed base, allowed paths and pinned producer sources.

This verifier never edits another owner's tree. It proves that everything this
branch changed since the fixed implementation start lives in the four paths the
S02 task page allows, and that the producer, J24 tool and AT-SPI client sources
it consumes are the pinned ones.
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

BASE = '0889f7d1e9a537c6c1b05456547e016b26e1cd85'
PRODUCER_SOURCE = '57203a52aee439be5194ee0a4b13563a975e8daf'
PRODUCER_SEAL = '9fc407a5cce5a0bfe644a60bd8dc29f84dea6d0e'
J24_SOURCE = '2f5677f13efc34b200af697f1b6f7bff2b656e3b'
J24_CONTRACT_BLOB = '289b435fe7c71cbdfefdf1c01c0eee2b3e2141a3'
J24_TREE_BLOB = '2f28a436a82c72fd84dd026ac1026e4b72695397'
ATSPI_SOURCE = '67e2f8c4941205c5581e82fd5a1469d18f696019'
ATSPI_BLOB = '50d51ac904502e0d6574876a9afb1883afcbde07'
ALLOWED = ('tests/reader_final_s02/',
           '.github/workflows/reader-final-s02.yml',
           'docs/reader-final-s02/',
           'HANDOFF-RESULT.md')


def git(*arguments, cwd=None, check=True):
    rendered = [str(item) for item in arguments]
    result = subprocess.run(['git', *rendered], cwd=None if cwd is None else str(cwd),
                            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if check and result.returncode:
        raise SystemExit('guard: git %s failed: %s' % (' '.join(rendered), result.stderr.strip()))
    return result


def present(repository, revision, label):
    result = git('cat-file', '-e', revision + '^{commit}', cwd=repository, check=False)
    if result.returncode:
        raise SystemExit('guard: %s commit %s is not available in %s' % (label, revision, repository))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', type=Path, default=Path.cwd())
    parser.add_argument('--j24-tools', type=Path,
                        help='pinned J24 tool directory extracted at its tested commit')
    parser.add_argument('--atspi', type=Path,
                        help='pinned AT-SPI client directory extracted at its tested commit')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    repository = args.repository.resolve()
    problems, checks = [], []

    def check(identifier, ok, detail):
        checks.append({'id': identifier, 'status': 'pass' if ok else 'fail', 'detail': detail})
        print(json.dumps({'check': identifier, 'status': 'pass' if ok else 'fail',
                          'detail': detail}, ensure_ascii=False), flush=True)
        if not ok:
            problems.append(identifier + ': ' + detail)

    head = git('rev-parse', 'HEAD', cwd=repository).stdout.strip()
    expected = os.environ.get('GITHUB_SHA', '')
    check('checkout_matches_workflow_source', not expected or head == expected,
          'HEAD %s workflow %s' % (head, expected or '(local)'))

    ancestor = git('merge-base', '--is-ancestor', BASE, 'HEAD', cwd=repository, check=False)
    check('fixed_implementation_start', ancestor.returncode == 0,
          'base %s is an ancestor of %s' % (BASE, head))

    changed = [line for line in git('diff', '--name-only', BASE, 'HEAD', cwd=repository)
               .stdout.splitlines() if line.strip()]
    outside = [path for path in changed if not path.startswith(ALLOWED)]
    check('only_s02_paths_changed', not outside,
          '%d changed paths, outside whitelist: %s' % (len(changed), outside or 'none'))

    for revision, label in ((PRODUCER_SOURCE, 'GTK compact producer'),
                            (PRODUCER_SEAL, 'GTK compact evidence seal'),
                            (ATSPI_SOURCE, 'AT-SPI client')):
        try:
            present(repository, revision, label)
            ok, detail = True, label + ' ' + revision + ' is present'
        except SystemExit as error:
            ok, detail = False, str(error)
        check('pinned_source_' + label.replace(' ', '_').lower(), ok, detail)

    blob = git('rev-parse', ATSPI_SOURCE + ':tests/reader_a11y_gtk/atspi_client.py',
               cwd=repository).stdout.strip()
    check('pinned_atspi_client_blob', blob == ATSPI_BLOB,
          'git blob %s expected %s' % (blob, ATSPI_BLOB))

    if args.j24_tools is not None:
        tree_blob = git('rev-parse', J24_SOURCE + ':tools/reader_distribution_unix',
                        cwd=repository).stdout.strip()
        contract = args.j24_tools.resolve() / 'contract.py'
        extracted = git('hash-object', '--no-filters', contract, cwd=repository, check=False)
        check('pinned_j24_tool_tree', tree_blob == J24_TREE_BLOB,
              'commit %s tool tree %s expected %s' % (J24_SOURCE, tree_blob, J24_TREE_BLOB))
        check('pinned_j24_contract_blob',
              extracted.returncode == 0 and extracted.stdout.strip() == J24_CONTRACT_BLOB,
              'extracted contract.py blob %r expected %s' % (
                  extracted.stdout.strip() if extracted.returncode == 0 else extracted.stderr.strip(),
                  J24_CONTRACT_BLOB))
    if args.atspi is not None:
        client = args.atspi.resolve() / 'atspi_client.py'
        extracted = git('hash-object', '--no-filters', client, cwd=repository, check=False)
        check('pinned_atspi_client_extracted_blob',
              extracted.returncode == 0 and extracted.stdout.strip() == ATSPI_BLOB,
              'extracted atspi_client.py blob %r expected %s' % (
                  extracted.stdout.strip() if extracted.returncode == 0 else extracted.stderr.strip(),
                  ATSPI_BLOB))

    report = {'schema': 1, 'kind': 's02-source-guard', 'head': head,
              'base': BASE, 'changed_paths': changed, 'checks': checks,
              'problems': problems, 'ok': not problems}
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    if problems:
        print('guard: ' + '; '.join(problems), file=sys.stderr)
        return 1
    print(json.dumps({'guard': 'pass', 'changed_paths': len(changed), 'head': head}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
