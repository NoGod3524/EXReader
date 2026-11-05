#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Source guard for the C02 package (Actions only).

Proves the consumer checkout descends from the fixed implementation start and
that nothing outside this package's path whitelist changed since then, so the
owner/SDK/judge/budget trees are byte-identical to the start. With --producer
it also proves the second checkout is exactly the pinned producer commit.
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

START = '0889f7d1e9a537c6c1b05456547e016b26e1cd85'
ALLOWED_PREFIXES = ('tests/reader_final_c02/', 'docs/reader-final-c02/')
ALLOWED_FILES = ('.github/workflows/reader-final-c02.yml', 'HANDOFF-RESULT.md')


def git(*args, cwd=None):
    return subprocess.check_output(['git', *args], text=True, cwd=cwd).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--producer', type=Path)
    parser.add_argument('--producer-sha')
    arguments = parser.parse_args()
    head = git('rev-parse', 'HEAD')
    if os.environ.get('GITHUB_SHA') and head != os.environ['GITHUB_SHA']:
        raise SystemExit('checked-out HEAD %s is not GITHUB_SHA' % head)
    subprocess.check_call(['git', 'merge-base', '--is-ancestor', START, head])
    changed = [line for line in git('diff', '--name-only', START, head).splitlines() if line]
    outside = [path for path in changed
               if not (path in ALLOWED_FILES or path.startswith(ALLOWED_PREFIXES))]
    guards = {'consumer_head': head, 'fixed_start': START, 'changed_files': changed, 'outside_whitelist': outside,
              'owner_trees_equal_to_start': not outside}
    if arguments.producer:
        producer_head = git('rev-parse', 'HEAD', cwd=str(arguments.producer))
        guards['producer_head'] = producer_head
        guards['producer_pinned'] = arguments.producer_sha
        if producer_head != arguments.producer_sha:
            raise SystemExit('producer checkout %s is not the pinned %s' % (producer_head, arguments.producer_sha))
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(guards, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps(guards, sort_keys=True))
    if outside:
        raise SystemExit('changed files outside the C02 whitelist: ' + ', '.join(outside))


if __name__ == '__main__':
    sys.exit(main())
