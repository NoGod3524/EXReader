"""Actions-only scope for the user-authorized additive SDK candidate."""
import os
from pathlib import Path
import subprocess

BASE = 'cdfe48231853d6e70fba2c41b42bdd187155901a'
FROZEN = '9854061be331fe603a1822d9b2b36ee357154927'
CANDIDATE = 'edddc463c06ed5731195cdb8f06b2df6dff7699e'
assert os.environ.get('GITHUB_ACTIONS') == 'true'
assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip() == os.environ['GITHUB_SHA']
subprocess.run(['git', 'merge-base', '--is-ancestor', BASE, 'HEAD'], check=True)
subprocess.run(['git', 'merge-base', '--is-ancestor', FROZEN, 'HEAD'], check=True)
# Release tooling and numeric budgets came from the accepted default-branch
# foundation, whose SDK is still byte-for-byte the original frozen version.
protected = ['src', 'include', 'cmake', 'CMakeLists.txt', 'tests/fixtures', 'bindings']
subprocess.run(['git', 'diff', '--exit-code', FROZEN, BASE, '--', *protected], check=True)
subprocess.run(['git', 'diff', '--exit-code', CANDIDATE, 'HEAD', '--', *protected], check=True)
subprocess.run(['git', 'diff', '--exit-code', BASE, 'HEAD', '--', 'tests/reading_real/budgets.json',
                'tests/reading_real/contract.json', 'tools/reading_corpus/real-v1.json',
                '.github/workflows/native.yml', '.github/workflows/reliability.yml'], check=True)
paths = subprocess.check_output(['git', 'diff', '--name-only', BASE, 'HEAD'], text=True).splitlines()
direct = {'src/raster.c', 'include/exr/render.h', 'include/exr/base.h', 'CMakeLists.txt', 'cmake/versions.cmake',
          '.github/workflows/sdk-page-background.yml', '.github/workflows/sdk-page-background-mobile.yml',
          '.github/workflows/r2-reading-corpus.yml', '.github/workflows/reading-real.yml',
          'tools/reading_corpus/collect.py', 'tests/reading_corpus/check_collect.py',
          'docs/SDK-PAGE-BACKGROUND.md'}
for path in paths:
    if path in direct or path.startswith(('tests/sdk_page_background/', 'tests/sdk_page_background_mobile/')):
        continue
    assert path.startswith(('examples/', 'tests/')) and path.endswith('/CMakeLists.txt'), path
    original = subprocess.check_output(['git', 'show', BASE + ':' + path], text=True)
    assert original.replace('find_package(EXReader 3.40.0 EXACT', 'find_package(EXReader 3.41.0 EXACT') == Path(path).read_text(), path
for path, old, new in [('CMakeLists.txt', 'project(EXReader VERSION 3.40.0', 'project(EXReader VERSION 3.41.0'),
                       ('cmake/versions.cmake', 'set(EXR_CORE_VERSION 3.39.0)', 'set(EXR_CORE_VERSION 3.40.0)')]:
    original = subprocess.check_output(['git', 'show', BASE + ':' + path], text=True)
    assert original.replace(old, new) == Path(path).read_text(), path
original = subprocess.check_output(['git', 'show', BASE + ':include/exr/base.h'], text=True)
assert original.replace('EXR_VERSION "3.40.0"', 'EXR_VERSION "3.41.0"').replace(
    'EXR_CORE_VERSION "3.39.0"', 'EXR_CORE_VERSION "3.40.0"') == Path('include/exr/base.h').read_text()
print('Authorized SDK API candidate only; old tests, ABI, budgets and frozen source retained')
