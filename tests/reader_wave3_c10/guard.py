"""C10 source-scope guard: fixed seed, exact owned paths, unchanged shared CMake. Runs only in Actions."""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
SEED = 'd263ce5228838ac90c0a0dc13a5193d4a7739681'
OWNED_FILES = {'HANDOFF-RESULT-C10.md', '.github/workflows/reader-wave3-c10.yml',
               'apps/reader/desktop/gtk_feature_integration.cmake'}
OWNED_PREFIXES = ('examples/linux/', 'tests/reader_wave3_c10/', 'docs/reader-wave3-c10/')
# Existing files that must keep their seed bytes.
FROZEN = ('apps/reader/desktop/CMakeLists.txt', 'CMakeLists.txt', 'include', 'src', 'bindings',
          'apps/reader/desktop/windows_', 'tests/reader_gtk_compact', 'tests/reader_gtk_receive',
          'tests/reader_a11y_gtk', 'tests/reader_gtk_search', 'tests/reader_gtk_navigation',
          'tests/reader_gtk_reading_records', 'apps/reader/store', 'apps/reader/revisions')


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()


def owned(path):
    return path in OWNED_FILES or path.startswith(OWNED_PREFIXES)


def main():
    head = git('rev-parse', 'HEAD')
    subprocess.check_call(['git', 'merge-base', '--is-ancestor', SEED, 'HEAD'], cwd=ROOT)
    changed = [line for line in git('diff', '--name-only', SEED, 'HEAD').splitlines() if line]
    foreign = [path for path in changed if not owned(path)]
    frozen = [path for path in changed if path.startswith(FROZEN)]
    report = dict(seed=SEED, head=head, github_sha=os.environ.get('GITHUB_SHA'), changed=changed,
                  foreign=foreign, frozen=frozen, accepted=not foreign and not frozen)
    out = ROOT / 'build/c10-guard'
    out.mkdir(parents=True, exist_ok=True)
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))
    if not report['accepted']:
        sys.exit('C10 changed paths outside its owned scope')


if __name__ == '__main__':
    main()
