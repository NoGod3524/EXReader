# SPDX-License-Identifier: MIT
"""New D15 ownership guard; all prior guards remain byte-for-byte unchanged."""
import os
import subprocess
SEED = 'd263ce5228838ac90c0a0dc13a5193d4a7739681'
SDK = 'edddc463c06ed5731195cdb8f06b2df6dff7699e'
def git(*args): return subprocess.check_output(['git', *args], text=True).strip()
def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    assert git('rev-parse', 'HEAD') == os.environ['GITHUB_SHA']
    subprocess.run(['git', 'merge-base', '--is-ancestor', SEED, 'HEAD'], check=True)
    allowed = ('examples/apple/', 'apps/reader/apple-feature-integration/', 'tests/reader_wave3_d15/', 'docs/reader-wave3-d15/')
    exact = {'tools/build_apple_wave3.py', '.github/workflows/reader-wave3-d15.yml', 'HANDOFF-RESULT-D15.md'}
    for path in git('diff', '--name-only', SEED, 'HEAD').splitlines():
        assert path.startswith(allowed) or path in exact, 'Unowned change: ' + path
    subprocess.run(['git', 'diff', '--exit-code', SDK, 'HEAD', '--', 'src', 'include', 'bindings', 'cmake', 'CMakeLists.txt'], check=True)
    print('D15 guard passed; fixed seed is not an accepted production BASE')
if __name__ == '__main__': main()
