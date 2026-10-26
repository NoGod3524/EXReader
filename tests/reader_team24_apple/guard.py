# SPDX-License-Identifier: MIT
"""Actions-only exact team owner boundary; original SDK and checks stay frozen."""
import json
import os
from pathlib import Path
import subprocess

SEED = 'd263ce5228838ac90c0a0dc13a5193d4a7739681'


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    subprocess.run(['git', 'merge-base', '--is-ancestor', SEED, 'HEAD'], check=True)
    paths = subprocess.check_output(['git', 'diff', '--name-only', SEED, 'HEAD'], text=True).splitlines()
    prefixes = ('examples/apple/', 'apps/reader/apple-feature-integration/',
                'tests/reader_team24_apple/', 'docs/handoffs/team24-apple')
    assert all(path.startswith(prefixes) or path == '.github/workflows/team24-apple.yml'
               for path in paths), paths
    subprocess.run(['git', 'diff', '--exit-code', SEED, 'HEAD', '--', 'src', 'include',
                    'bindings', 'CMakeLists.txt', 'cmake', 'tests/apple_host',
                    'tools', 'tests/fixtures', 'tests/reader_a11y_apple'], check=True)
    out = Path('build/team24-apple-guard.json')
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({'seed': SEED, 'source_sha': os.environ['GITHUB_SHA'],
                              'run_id': os.environ['GITHUB_RUN_ID'],
                              'attempt': os.environ['GITHUB_RUN_ATTEMPT'],
                              'changed_paths': paths, 'accepted': True}, indent=2) + '\n')


if __name__ == '__main__':
    main()
