# SPDX-License-Identifier: MIT
"""Actions-only candidate identity: SDK and shared packages have separate owners."""
import os
import subprocess

BASE = '687def68862649479ce536d619c7b37ba2d2cc4b'
SDK = 'b911815e26a10e7c45f50f56bf7c4e46cbca010b'
VERSION_SUPPORT = 'f5f7f92a330aa30759125778626e956ac4a4374a'
DEPENDENCY_MERGE = 'd2d627e8a69d8d27ad902490b920cc5bf3173f83'


def git(*args):
    return subprocess.check_output(['git', *args], text=True).strip()


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    assert git('rev-parse', 'HEAD') == os.environ['GITHUB_SHA']
    assert os.environ['GTK_PAGE_BACKGROUND_SDK_SOURCE'] == SDK
    for ancestor in (BASE, SDK, VERSION_SUPPORT):
        subprocess.run(['git', 'merge-base', '--is-ancestor', ancestor, 'HEAD'], check=True)
    subprocess.run(['git', 'diff', '--exit-code', SDK, 'HEAD', '--', 'src', 'include', 'cmake', 'CMakeLists.txt',
                    'bindings', 'tests/fixtures', 'licenses', '.github/workflows/native.yml', '.github/workflows/reliability.yml'], check=True)
    subprocess.run(['git', 'diff', '--exit-code', VERSION_SUPPORT, 'HEAD', '--', 'apps', 'extras', 'tools'], check=True)
    for path in ('tests/reader_gtk_preferences', 'tests/reader_gtk_batch_import', 'tests/reader_gtk_drop_import',
                 'tests/reader_gtk_search', 'tests/reader_gtk_navigation', 'tests/reader_gtk_reading_records',
                 'tests/linux_host', 'tests/reader_catalog', 'tests/reader_batch_import',
                 '.github/workflows/reader-gtk-drop-import.yml'):
        subprocess.run(['git', 'diff', '--exit-code', VERSION_SUPPORT, 'HEAD', '--', path], check=True)
    own = {'examples/linux/CMakeLists.txt', 'examples/linux/reading.h', 'examples/linux/reading.c',
           'examples/linux/reader.c', 'examples/linux/preferences_ui.inc', '.github/workflows/reader-gtk-page-background.yml',
           'docs/READER-GTK-PAGE-BACKGROUND.md', 'docs/validation/reader-gtk-page-background.json'}
    for path in git('diff', '--name-only', DEPENDENCY_MERGE, 'HEAD').splitlines():
        if path in own or path.startswith('tests/reader_gtk_page_background/'):
            continue
        # Later root delivery paths must match its exact bytes, not a wildcard.
        assert git('rev-parse', 'HEAD:' + path) == git('rev-parse', VERSION_SUPPORT + ':' + path), path
    print('GTK_PAGE_BACKGROUND_GUARD fixed candidate SDK, exact shared version support and unchanged old tests passed')


if __name__ == '__main__':
    main()
