"""Authenticate the fixed G1 base and the root-owned Windows UI edits in Actions."""
import os
import subprocess

BASE = '3bcc6511'
SDK = '9854061be331fe603a1822d9b2b36ee357154927'
ALLOWED = ('examples/reader.c', 'apps/reader/windows-account/CMakeLists.txt',
           'apps/reader/desktop/windows_search.inc', 'apps/reader/desktop/windows_search_types.h',
           'tests/reader_windows_search/', '.github/workflows/reader-windows-search-ui.yml',
           'docs/READER-WINDOWS-SEARCH.md', 'docs/validation/reader-windows-search.json')


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    sha = os.environ['GITHUB_SHA']
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip() == sha
    subprocess.run(['git', 'merge-base', '--is-ancestor', BASE, sha], check=True)
    subprocess.run(['git', 'diff', '--exit-code', SDK, sha, '--', 'src', 'include', 'cmake',
                    'CMakeLists.txt', 'tests/fixtures', 'bindings', '.github/workflows/native.yml',
                    '.github/workflows/reliability.yml'], check=True)
    subprocess.run(['git', 'diff', '--exit-code', BASE, sha, '--',
                    'apps/reader/store/001_catalog.sql', 'apps/reader/search', 'apps/reader/reading-state'], check=True)
    paths = subprocess.check_output(['git', 'diff', '--name-only', BASE, sha], text=True).splitlines()
    for path in paths:
        assert any(path.startswith(p) if p.endswith('/') else path == p for p in ALLOWED), path
    print('Authenticated Windows search UI source:', sha)


if __name__ == '__main__':
    main()
