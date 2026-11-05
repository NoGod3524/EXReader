"""Only Actions can execute this source/path gate."""
import os
import subprocess
from contract import START, MERGED, OLD, DEPENDENCY

assert os.environ.get('GITHUB_ACTIONS') == 'true'
def git(*args):
    return subprocess.check_output(['git', *args], text=True).strip()
assert git('rev-parse', 'HEAD') == os.environ['GITHUB_SHA']
for base in (START, MERGED):
    subprocess.run(['git', 'merge-base', '--is-ancestor', base, 'HEAD'], check=True)
assert git('show', '-s', '--format=%P', MERGED).split() == [START, DEPENDENCY]
assert git('rev-parse', MERGED+'^{tree}') == '4d535b85026c3ed08e9fbdae81a0de191f0c8fc4'
subprocess.run(['git', 'diff', '--exit-code', OLD, 'HEAD', '--', 'src', 'include', 'cmake',
    'CMakeLists.txt', 'tests/fixtures', 'bindings', '.github/workflows/native.yml',
    '.github/workflows/reliability.yml'], check=True)
subprocess.run(['git', 'diff', '--exit-code', MERGED, 'HEAD', '--', 'apps', 'extras',
    'tests/reader_reading_commands', 'tests/reader_reading_state'], check=True)
for path in git('diff', '--name-only', MERGED, 'HEAD').splitlines():
    assert path.startswith('tests/reader_sdk_record_migration/') or path in {
        '.github/workflows/reader-sdk-record-migration.yml',
        'docs/READER-SDK-RECORD-MIGRATION.md', 'docs/validation/reader-sdk-record-migration.json'}, path
print('D01 fixed start, exact ordinary merge, frozen SDK/schema/modules and exclusive paths verified')
