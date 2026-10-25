#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Fixed source, frozen SDK and exclusive-write guard for S14."""
import json
import os
import re
import subprocess
import sys

START = 'e67d87cbeabb2457e0852f681ef0b27b2c0da4d8'
SDK_340 = '9854061be331fe603a1822d9b2b36ee357154927'
SDK_341 = 'edddc463c06ed5731195cdb8f06b2df6dff7699e'
MODULE_REF = '1563f4abb85ccd28c3a0aae3e9913f4330536215'
MODULE = 'apps/reader/font-library'
REUSED = ('include/reader_font_library.h', 'src/library.cpp', 'src/sha256.hpp')
# Only these two files of the reused library may differ: the explicit SDK
# selection in the build and the matching installed package dependency.
MODULE_CHANGED = ('CMakeLists.txt', 'EXReaderFontLibraryConfig.cmake.in')
FONT_SURFACE = ('include/exr/text.h', 'include/exr/font.h', 'include/exr/core.h',
                'src/font_bitmap.c', 'src/font_color.c', 'src/font_colr_v1.c', 'src/font_outline.c',
                'src/font_path.c', 'src/font_svg.c', 'src/fonts.c', 'src/pdf_font.c')
PROTECTED = ('src', 'include', 'cmake', 'CMakeLists.txt', 'tests/fixtures', 'bindings',
             '.github/workflows/native.yml', '.github/workflows/reliability.yml')
ALLOWED = re.compile(r'^(apps/reader/font-library/|tests/reader_next_s14/|'
                     r'\.github/workflows/reader-next-s14\.yml$|docs/reader-next-s14/|'
                     r'HANDOFF-RESULT-S14\.md$)')


def git(*args):
    return subprocess.check_output(['git', *args], text=True).strip()


def ensure(commit):
    """The reused library commit lives on another branch; fetch it by exact SHA."""
    if subprocess.run(['git', 'cat-file', '-e', commit + '^{commit}'],
                      capture_output=True).returncode == 0:
        return True
    subprocess.run(['git', 'fetch', '--no-tags', 'origin', commit], capture_output=True)
    return subprocess.run(['git', 'cat-file', '-e', commit + '^{commit}'],
                          capture_output=True).returncode == 0


def diff_empty(*args):
    return subprocess.run(['git', 'diff', '--exit-code', *args], capture_output=True, text=True).returncode == 0


def main():
    problems = []
    for commit in (START, SDK_340, SDK_341, MODULE_REF):
        if not ensure(commit):
            problems.append('required commit is unavailable: ' + commit)
    if problems:
        for problem in problems:
            print('GUARD FAILED: ' + problem)
        return 1
    head = git('rev-parse', 'HEAD')
    if os.environ.get('GITHUB_SHA') and os.environ['GITHUB_SHA'] != head:
        problems.append('checkout does not match GITHUB_SHA')
    if subprocess.run(['git', 'merge-base', '--is-ancestor', START, 'HEAD']).returncode != 0:
        problems.append('fixed start is not an ancestor of HEAD')
    if not diff_empty(SDK_341, 'HEAD', '--', *PROTECTED):
        problems.append('approved SDK 3.41 tree or protected tests changed')
    if not diff_empty(SDK_340, 'HEAD', '--', *FONT_SURFACE):
        problems.append('public font surface diverged from frozen SDK 3.40')
    changed = [line for line in git('diff', '--name-only', START, 'HEAD').splitlines() if line]
    unowned = [path for path in changed if not ALLOWED.match(path)]
    if unowned:
        problems.append('unowned paths changed: %s' % unowned)
    module_changed = sorted(line for line in git('diff', '--name-only', MODULE_REF, 'HEAD', '--', MODULE).splitlines()
                            if line)
    expected_changed = sorted(MODULE + '/' + name for name in MODULE_CHANGED)
    if module_changed != expected_changed:
        problems.append('reused module changed beyond the SDK selection: %s' % module_changed)
    for path in REUSED:
        if git('hash-object', MODULE + '/' + path) != git('rev-parse', MODULE_REF + ':' + MODULE + '/' + path):
            problems.append('reused module bytes differ: ' + path)
    workflow = '.github/workflows/reader-next-s14.yml'
    text = subprocess.check_output(['git', 'show', 'HEAD:' + workflow], text=True)
    if 'branches: [codex/reader-next-s14]' not in text or 'on:\n  push:' not in text:
        problems.append('workflow trigger is not restricted to the package branch')
    if not diff_empty(START, 'HEAD', '--', 'docs/handoffs', '.github/workflows/parallel-integration.yml'):
        problems.append('handoff or integration workflows changed')
    if problems:
        for problem in problems:
            print('GUARD FAILED: ' + problem)
        return 1
    print(json.dumps({'guard': 'ok', 'head': head, 'start': START, 'sdk': SDK_341, 'frozen': SDK_340,
                      'module_ref': MODULE_REF, 'changed': changed}, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
