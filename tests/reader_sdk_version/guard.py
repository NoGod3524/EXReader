"""Actions-only scope for explicit SDK dependency selection; production stays frozen."""
import os
from pathlib import Path
import subprocess

BASE = '8e979ef0c14dd111ccad5d77aa241d8e58226cb3'
SDK = '9854061be331fe603a1822d9b2b36ee357154927'
assert os.environ.get('GITHUB_ACTIONS') == 'true'
assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip() == os.environ['GITHUB_SHA']
subprocess.run(['git', 'merge-base', '--is-ancestor', BASE, 'HEAD'], check=True)
subprocess.run(['git', 'diff', '--exit-code', SDK, 'HEAD', '--', 'src', 'include', 'cmake', 'CMakeLists.txt',
                'tests/fixtures', 'bindings', '.github/workflows/native.yml', '.github/workflows/reliability.yml'], check=True)
allowed = {'apps/reader/desktop/CMakeLists.txt', 'tools/build_linux_host.py',
           'tests/reader_batch_import/consumer/CMakeLists.txt', 'tests/reader_navigation/consumer/CMakeLists.txt',
           'tests/reader_gtk_receive/CMakeLists.txt', 'tests/linux_host/check_fixed_ui.py',
           '.github/workflows/reader-sdk-version-support.yml', 'docs/READER-SDK-VERSION-SUPPORT.md'}
for package in ('reading-state', 'search', 'navigation', 'batch-import'):
    directory = Path('apps/reader')/package
    allowed.add((directory/'CMakeLists.txt').as_posix())
    allowed.update(path.as_posix() for path in directory.glob('EXReader*Config.cmake.in'))
for path in subprocess.check_output(['git', 'diff', '--name-only', BASE, 'HEAD'], text=True).splitlines():
    assert path in allowed or path.startswith('tests/reader_sdk_version/'), path
print('Only explicit SDK version selection, installed Config and isolated validation changed')
