"""Actions-only admission of the immutable shared product and narrowly scoped wiring."""
import os
import subprocess
assert os.environ.get('GITHUB_ACTIONS') == 'true'
base = 'f34a4f27161061d08ecc40f5cebfb6f5018aa77f'
def git(*args):
    return subprocess.check_output(['git', *args], text=True).strip()
head = git('rev-parse', 'HEAD')
assert head == os.environ['GITHUB_SHA']
subprocess.run(['git', 'merge-base', '--is-ancestor', base, head], check=True)
allowed = {
    '.github/workflows/windows-wave3-txt-progress.yml',
    '.github/workflows/sdk-ot-cache-acceptance.yml',
    '.github/workflows/reader-d26-accessibility.yml',
    '.github/workflows/reader-android-font-reader.yml',
    'tests/android_font_reader/common_guard.py',
    'tests/apple_android_relay/guard.py',
    'tests/opentype_cache_acceptance/run.py',
    'tests/common_source_integration/guard.py',
}
changed = set(git('diff', '--name-only', base, head).splitlines())
assert changed <= allowed, sorted(changed - allowed)
subprocess.run(['git', 'diff', '--exit-code', base, head, '--',
                'src', 'include', 'cmake', 'CMakeLists.txt', 'bindings',
                'apps', 'examples', 'extras', 'tools', 'tests/fixtures'], check=True)
print('Common source admitted:', head, 'base:', base, 'changes:', sorted(changed))
