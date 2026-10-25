"""C09 source-scope guard: fixed seed, exact owned paths, unchanged shared CMake. Runs only in Actions."""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
SEED = 'd263ce5228838ac90c0a0dc13a5193d4a7739681'
OWNED_FILES = {'examples/reader.c', 'HANDOFF-RESULT-C09.md', '.github/workflows/reader-wave3-c09.yml'}
OWNED_PREFIXES = ('examples/windows/', 'tests/reader_wave3_c09/', 'docs/reader-wave3-c09/')
OWNED_DESKTOP = 'apps/reader/desktop/windows_'
# Existing files that must keep their seed bytes (public CMake entry and the frozen judges).
FROZEN = ('apps/reader/desktop/CMakeLists.txt', 'CMakeLists.txt', 'tests/reader_windows_raw3', 'tests/reader_windows_compact',
          'tests/reader_windows_341', 'include', 'src', 'bindings', 'apps/reader/windows-account')


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()


def owned(path):
    return path in OWNED_FILES or path.startswith(OWNED_PREFIXES) or path.startswith(OWNED_DESKTOP)


def main():
    head = git('rev-parse', 'HEAD')
    subprocess.check_call(['git', 'merge-base', '--is-ancestor', SEED, 'HEAD'], cwd=ROOT)
    changed = [line for line in git('diff', '--name-only', SEED, 'HEAD').splitlines() if line]
    foreign = [path for path in changed if not owned(path)]
    frozen = [path for path in changed if path.startswith(FROZEN)]
    report = dict(seed=SEED, head=head, github_sha=os.environ.get('GITHUB_SHA'), changed=changed, foreign=foreign, frozen=frozen,
                  accepted=not foreign and not frozen)
    out = ROOT / 'build/c09-guard'
    out.mkdir(parents=True, exist_ok=True)
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))
    if not report['accepted']:
        sys.exit('C09 changed paths outside its owned scope')


if __name__ == '__main__':
    main()
