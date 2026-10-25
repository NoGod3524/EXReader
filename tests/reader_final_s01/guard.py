#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""S01 boundary guard: own paths only, fixed producer and approved SDK 3.41 identity.

Actions only. Runs before any Windows build and fails closed when the producer
checkout, the SDK source, a retained acceptance file or this package's own diff
scope is not the recorded one.
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from contract import (ALLOWED_PATHS, APPROVED_SDK, FROZEN_SDK, IMPLEMENTATION_START, PRODUCER_SOURCE,
                      PRODUCER_TREE, REFERENCE_DOC, REFERENCE_PROGRAM, REFERENCE_SEAL,
                      RETAINED_SOURCES, SDK_CORE_PATHS, SDK_INCLUDE_TREE, SDK_SRC_TREE, SDK_VERSION,
                      require)

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = '.github/workflows/reader-final-s01.yml'


def git(*arguments, cwd=None):
    return subprocess.check_output(['git', *arguments], cwd=str(cwd or ROOT), text=True,
                                   encoding='utf-8', errors='replace').strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--producer', type=Path, required=True)
    args = parser.parse_args()
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'run the S01 guard in GitHub Actions only')
    source = os.environ['GITHUB_SHA']
    require(git('rev-parse', 'HEAD') == source, 'checkout and workflow source differ')
    require(git('status', '--porcelain', '--untracked-files=no') == '', 'tracked source changed')
    subprocess.run(['git', 'merge-base', '--is-ancestor', IMPLEMENTATION_START, source], check=True)
    changed = [line for line in git('diff', '--name-only', IMPLEMENTATION_START, source).splitlines() if line]
    outside = sorted(line for line in changed
                     if not any(line == path or line.startswith(path) for path in ALLOWED_PATHS))
    require(not outside, 'S01 changed files outside its own paths: ' + repr(outside))

    workflow = (ROOT / WORKFLOW).read_text(encoding='utf-8')
    require('branches: [codex/reader-fw-s01]' in workflow,
            'the S01 workflow does not trigger on its own branch')
    require('tags:' not in workflow and 'release: write' not in workflow,
            'the S01 workflow can publish tags or releases')
    for other in sorted((ROOT / '.github' / 'workflows').glob('*.yml')):
        relative = '.github/workflows/' + other.name
        if relative != WORKFLOW:
            require(relative not in changed, 'S01 changed another workflow: ' + relative)

    producer = args.producer.resolve()
    require(git('rev-parse', 'HEAD', cwd=producer) == PRODUCER_SOURCE,
            'the producer checkout is not the fixed producer source')
    require(git('rev-parse', 'HEAD^{tree}', cwd=producer) == PRODUCER_TREE,
            'the producer checkout tree differs from the fixed producer tree')
    require(git('status', '--porcelain', '--untracked-files=no', cwd=producer) == '',
            'the producer checkout has tracked changes')
    for commit, label in ((FROZEN_SDK, 'frozen 3.40 SDK'), (APPROVED_SDK, 'approved 3.41 SDK')):
        subprocess.run(['git', 'merge-base', '--is-ancestor', commit, PRODUCER_SOURCE],
                       cwd=str(producer), check=True)
        require(git('cat-file', '-t', commit, cwd=producer) == 'commit', label + ' commit is missing')
    drift = git('diff', '--name-only', APPROVED_SDK, PRODUCER_SOURCE, '--', *SDK_CORE_PATHS, cwd=producer)
    require(drift == '', 'the producer SDK source differs from the approved 3.41 SDK: ' + repr(drift))
    require(git('rev-parse', 'HEAD:src', cwd=producer) == SDK_SRC_TREE,
            'the producer SDK core source tree differs from the approved SDK')
    require(git('rev-parse', 'HEAD:include', cwd=producer) == SDK_INCLUDE_TREE,
            'the producer SDK public headers differ from the approved SDK')
    header = (producer / 'include/exr/base.h').read_text(encoding='utf-8')
    require('#define EXR_VERSION "%s"' % SDK_VERSION in header, 'the producer SDK is not version 3.41.0')

    retained = []
    for relative in RETAINED_SOURCES:
        producer_blob = git('rev-parse', 'HEAD:' + relative, cwd=producer)
        require(producer_blob == git('rev-parse', 'HEAD:' + relative),
                'retained source differs between producer and implementation: ' + relative)
        retained.append(relative)
    require(git('rev-parse', 'HEAD:' + REFERENCE_DOC) == git('rev-parse', REFERENCE_SEAL + ':' + REFERENCE_DOC),
            'the published program hash document is not the sealed one')
    require(REFERENCE_PROGRAM in (ROOT / REFERENCE_DOC).read_text(encoding='utf-8'),
            'the sealed document does not publish the reference program hash')

    print(json.dumps({'guard': 'passed', 'source': source,
                      'implementation_start': IMPLEMENTATION_START,
                      'producer_source': PRODUCER_SOURCE, 'producer_tree': PRODUCER_TREE,
                      'sdk_version': SDK_VERSION, 'approved_sdk': APPROVED_SDK,
                      'frozen_sdk': FROZEN_SDK, 'changed_paths': len(changed),
                      'retained_sources': len(retained),
                      'reference_document': REFERENCE_DOC}, flush=True))


if __name__ == '__main__':
    main()
