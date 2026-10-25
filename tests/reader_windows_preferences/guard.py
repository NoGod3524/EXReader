"""Actions-only F3 ownership gate: fixed source, frozen trees, additive SDK.

The branch is a separate candidate. It starts from the recorded ordinary merge,
checks that the SDK tree is exactly the authorized 3.41.0 candidate, that the
installed F3 package and every other production module are unchanged, and that
only the declared paths differ from the post-merge base.
"""
import os
import subprocess

BASE = '6ba247d06b040fdf7d02c522820b1d19fcdc0e85'
FROZEN = '9854061be331fe603a1822d9b2b36ee357154927'
CANDIDATE = 'edddc463c06ed5731195cdb8f06b2df6dff7699e'
VERSION_SUPPORT = 'f680aeaddfb1ecc67ead353554f5b91a5703f72f'
PREFERENCES = '1f51b4066cd705a670b3139061336c298e479081'
ALLOWED = ('examples/reader.c',
           'apps/reader/windows-account/CMakeLists.txt',
           'apps/reader/desktop/windows_preferences',
           'tests/reader_windows_preferences/',
           '.github/workflows/reader-windows-preferences-ui.yml',
           'docs/READER-WINDOWS-PREFERENCES.md',
           'docs/validation/reader-windows-preferences.json')
IMMUTABLE = ('bindings', 'tests/fixtures', 'apps/reader/store', 'apps/reader/preferences',
             'tests/reader_preferences', 'tests/windows_host', 'tests/reader_windows_account',
             'tests/reader_windows_search', 'tests/reader_windows_navigation',
             'tests/reader_windows_records', 'tests/reader_windows_import_organize',
             'examples/apple', 'examples/android', 'examples/linux',
             '.github/workflows/reader-windows-import-organize.yml',
             '.github/workflows/reader-windows-search-ui.yml',
             '.github/workflows/reader-windows-navigation-ui.yml',
             '.github/workflows/reader-windows-reading-records.yml')


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    source = os.environ['GITHUB_SHA']
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip() == source
    for ancestor in (BASE, FROZEN, CANDIDATE, VERSION_SUPPORT, PREFERENCES):
        subprocess.run(['git', 'merge-base', '--is-ancestor', ancestor, source], check=True)
    # The SDK tree is byte-for-byte the authorized candidate, including its
    # version strings and the new page-background entry point.
    subprocess.run(['git', 'diff', '--exit-code', CANDIDATE, source, '--',
                    'src', 'include', 'cmake', 'CMakeLists.txt', 'bindings',
                    'tests/fixtures', 'tests/sdk_page_background'], check=True)
    # The installed F3 package, its public header and its own tests are unchanged.
    subprocess.run(['git', 'diff', '--exit-code', PREFERENCES, source, '--',
                    'apps/reader/preferences', 'tests/reader_preferences'], check=True)
    # Nothing outside the declared allowlist moved from the recorded merge base.
    for path in subprocess.check_output(['git', 'diff', '--name-only', BASE, source],
                                        text=True).splitlines():
        assert any(path == allowed or path.startswith(allowed) for allowed in ALLOWED), path
    subprocess.run(['git', 'diff', '--exit-code', BASE, source, '--', *IMMUTABLE], check=True)
    host = open('apps/reader/windows-account/CMakeLists.txt', encoding='utf-8').read()
    assert 'option(EXR_READER_WINDOWS_PREFERENCES "Enable native F3 reading settings and page theme" OFF)' in host
    assert 'find_package(EXReaderPreferences 0.1.0 EXACT CONFIG REQUIRED)' in host
    assert 'target_compile_definitions(${target} PRIVATE EXR_READER_WINDOWS_PREFERENCES=1)' in host
    desktop = open('apps/reader/desktop/CMakeLists.txt', encoding='utf-8').read()
    assert 'EXR_READER_WINDOWS_PREFERENCES' not in desktop
    workflow = open('.github/workflows/reader-windows-preferences-ui.yml', encoding='utf-8').read()
    for required in ('-DEXR_SDK_VERSION=3.41.0',
                     '-DEXR_READER_WINDOWS_PREFERENCES=ON',
                     '9854061be331fe603a1822d9b2b36ee357154927',
                     'tests/reader_windows_preferences/check_ui.py',
                     'reader-windows-search-initial-'):
        assert required in workflow, required
    print('F3 exact source, additive 3.41.0 candidate, frozen package trees and ownership '
          'authenticated:', source, 'post-merge base', BASE, flush=True)


if __name__ == '__main__':
    main()
