# SPDX-License-Identifier: MIT
"""Path-ownership guard for C03, with its own negative selftest."""
import argparse
import json
import os
import re
import subprocess
import sys

ALLOWED = re.compile(r'^(tests/reader_final_c03/|\.github/workflows/reader-final-c03\.yml$|docs/reader-final-c03/|HANDOFF-RESULT\.md$)')
TRANSPORT_CANDIDATE='8cc57c078f50c7e81bd2a75620a4acf9b23bb456'
TRANSPORT_BASE='0889f7d1e9a537c6c1b05456547e016b26e1cd85'


def unowned(paths):
    return [p for p in paths if p and not ALLOWED.match(p)]


def selftest():
    good = ['tests/reader_final_c03/check_c03.py', '.github/workflows/reader-final-c03.yml',
            'docs/reader-final-c03/validation.json', 'HANDOFF-RESULT.md']
    bad = ['apps/reader/cloud-import/src/cloud_import.c', 'extras/webdav/src/webdav.cpp', 'src/library.c',
           'tests/reader_webdav_import/check_cloud_import.py', '.github/workflows/reader-webdav-import.yml',
           'tests/reader_final_c03x/a.py', 'docs/reader-final-c030/x', 'docs/README.md']
    assert unowned(good) == [] and unowned(bad) == bad
    return {'allowed': len(good), 'refused': len(bad)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--fixed', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    proof = selftest()
    head = subprocess.run(['git', 'rev-parse', 'HEAD'], capture_output=True, text=True, check=True).stdout.strip()
    assert head == os.environ.get('GITHUB_SHA', head), 'checkout is not the pushed source'
    subprocess.run(['git', 'merge-base', '--is-ancestor', args.fixed, 'HEAD'], check=True)
    changed = subprocess.run(['git', 'diff', '--name-only', args.fixed, 'HEAD'], capture_output=True, text=True, check=True).stdout.split('\n')
    # Root-reviewed transport repair is a distinct producer, pinned byte-for-byte.
    # The original C03 allowlist and its ownership rejection selftest stay intact.
    assert args.fixed==TRANSPORT_BASE,'unexpected composition base'
    subprocess.run(['git','merge-base','--is-ancestor',TRANSPORT_CANDIDATE,'HEAD'],check=True)
    transport_paths=subprocess.check_output(['git','diff','--name-only',TRANSPORT_BASE,TRANSPORT_CANDIDATE],text=True,encoding='utf-8').splitlines()
    for path in transport_paths:
        want=subprocess.check_output(['git','rev-parse',TRANSPORT_CANDIDATE+':'+path],text=True,encoding='utf-8').strip()
        actual=subprocess.check_output(['git','rev-parse','HEAD:'+path],text=True,encoding='utf-8').strip()
        assert actual==want,'reviewed transport candidate changed: '+path
    bad = unowned([p for p in changed if p not in transport_paths])
    os.makedirs(args.output, exist_ok=True)
    record = {'ok': not bad, 'fixed': args.fixed, 'head': head, 'changed': [c for c in changed if c], 'unowned': bad, 'selftest': proof,
              'reviewed_transport_candidate':TRANSPORT_CANDIDATE,'transport_paths_exact':transport_paths}
    with open(os.path.join(args.output, 'guards.json'), 'w', encoding='utf-8') as f:
        json.dump(record, f, indent=2)
    print(json.dumps(record))
    return 0 if not bad else 1


if __name__ == '__main__':
    sys.exit(main())
