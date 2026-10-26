# SPDX-License-Identifier: MIT
"""C10 source guard: exact own paths only, on top of the reviewed seed.

This package owns the GTK host sources, its one named CMake include, its own
tests/workflow/docs and the result handoff. Everything else must still be the
seed's bytes: the frozen SDK tree, the five reviewed modules, the other module
owners, the original test drivers and every other workflow.
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

SEED = 'd263ce5228838ac90c0a0dc13a5193d4a7739681'
ALLOWED = (
    'examples/linux/',
    'apps/reader/desktop/gtk_feature_integration.cmake',
    'tests/reader_wave3_c10/',
    '.github/workflows/reader-wave3-c10.yml',
    'docs/reader-wave3-c10/',
    'HANDOFF-RESULT-C10.md',
)
PROTECTED_TREES = (
    'include', 'src', 'bindings', 'cmake', 'apps/reader/store',
    'apps/reader/desktop/CMakeLists.txt', 'CMakeLists.txt', 'README.md',
    'apps/reader/annotation-import', 'apps/reader/font-library',
    'apps/reader/original-export', 'apps/reader/jump-history',
    'apps/reader/sync-status-view', 'apps/reader/revisions', 'apps/reader/sync',
    'apps/reader/session', 'apps/reader/reading-state', 'apps/reader/search',
    'apps/reader/navigation', 'apps/reader/reading-commands',
    'apps/reader/annotation-view', 'apps/reader/annotation-export',
    'apps/reader/batch-import', 'apps/reader/preferences',
    'tests/reader_gtk_compact', 'tests/reader_gtk_receive',
    'tests/reader_gtk_search', 'tests/reader_gtk_navigation',
    'tests/reader_gtk_reading_records', 'tests/reader_gtk_batch_import',
    'tests/reader_gtk_drop_import', 'tests/reader_gtk_record_compatibility',
    'tests/reader_a11y_gtk', 'tests/linux_host', 'tools',
    '.github/workflows/reader-gtk-compact.yml',
    '.github/workflows/reader-raw3-common-gtk.yml',
    '.github/workflows/reader-gtk-341-final.yml',
    '.github/workflows/reader-gtk-reading-records.yml',
    '.github/workflows/reader-gtk-search.yml',
    '.github/workflows/reader-gtk-navigation.yml',
    '.github/workflows/reader-gtk-batch-import.yml',
    '.github/workflows/reader-gtk-drop-import.yml',
)
REFUSED_SAMPLES = (
    'src/render.c', 'include/exr/base.h', 'bindings/reader.c',
    'apps/reader/annotation-import/src/annotation_import.cpp',
    'apps/reader/font-library/include/reader_font_library.h',
    'tests/reader_gtk_receive/check_atspi_fixes.py',
    'tests/reader_gtk_compact/check_ui.py',
    '.github/workflows/reader-gtk-compact.yml',
    'apps/reader/desktop/CMakeLists.txt', 'CMakeLists.txt',
    'docs/reader-wave3-c11/PLAN.md', 'examples/windows/reader.c',
)
ACCEPTED_SAMPLES = (
    'examples/linux/reader.c', 'examples/linux/wave3_ui.inc',
    'apps/reader/desktop/gtk_feature_integration.cmake',
    'tests/reader_wave3_c10/check_ui.py',
    '.github/workflows/reader-wave3-c10.yml',
    'docs/reader-wave3-c10/VALIDATION.md', 'HANDOFF-RESULT-C10.md',
)


def git(*args, check=True):
    result = subprocess.run(['git', *args], text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)
    if check and result.returncode:
        raise SystemExit('git %s failed: %s' % (' '.join(args), result.stderr.strip()))
    return result.stdout


def allowed(path):
    return any(path == prefix or path.startswith(prefix) for prefix in ALLOWED)


def self_test():
    wrong = [path for path in REFUSED_SAMPLES if allowed(path)]
    missed = [path for path in ACCEPTED_SAMPLES if not allowed(path)]
    assert not wrong, wrong
    assert not missed, missed
    return {'refused': len(REFUSED_SAMPLES), 'accepted': len(ACCEPTED_SAMPLES)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('build/reader-wave3-c10/source.json'))
    args = parser.parse_args()
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    head = git('rev-parse', 'HEAD').strip()
    assert head == os.environ['GITHUB_SHA'], (head, os.environ['GITHUB_SHA'])
    subprocess.run(['git', 'merge-base', '--is-ancestor', SEED, head], check=True)
    changed = [line for line in git('diff', '--name-only', SEED, head).splitlines() if line]
    outside = [path for path in changed if not allowed(path)]
    assert not outside, outside
    protected = {}
    for tree in PROTECTED_TREES:
        before = git('rev-parse', '%s:%s' % (SEED, tree), check=False).strip()
        after = git('rev-parse', '%s:%s' % (head, tree), check=False).strip()
        assert before, 'protected path missing from the seed: ' + tree
        assert after == before, 'protected path changed: ' + tree
        protected[tree] = before
    record = {'seed': SEED, 'head': head, 'run_id': os.environ['GITHUB_RUN_ID'],
              'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'changed': changed,
              'allowed': list(ALLOWED), 'protected': protected,
              'protected_count': len(protected), 'self_test': self_test()}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'guard': 'pass', 'head': head, 'seed': SEED, 'changed': len(changed),
                      'protected': len(protected), 'self_test': record['self_test']}), flush=True)


if __name__ == '__main__':
    main()
