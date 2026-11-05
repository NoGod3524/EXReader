"""Only the C08 exclusive paths may differ from the fixed start; includes a negative self-test."""
import argparse
import json
import pathlib
import subprocess
import sys

OWNED = ('tests/reader_next_c08/', 'docs/reader-next-c08/')
OWNED_FILES = ('.github/workflows/reader-next-c08.yml', 'HANDOFF-RESULT-C08.md')


def owned(path):
    return path in OWNED_FILES or any(path.startswith(prefix) for prefix in OWNED)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--fixed', required=True)
    parser.add_argument('--output', type=pathlib.Path, default=pathlib.Path('build/c08-guards'))
    args = parser.parse_args()
    changed = subprocess.check_output(['git', 'diff', '--name-only', args.fixed, 'HEAD'], text=True).split()
    outside = [path for path in changed if not owned(path)]
    negatives = {path: not owned(path) for path in (
        'examples/android/app/build.gradle', 'include/exr/library.h', 'tests/reader_final_s04/emulator.py',
        '.github/workflows/reader-final-s04.yml', 'HANDOFF-RESULT.md', 'docs/reader-next-c07/x.md',
        'tests/reader_next_c08_other/x.py', 'src/library.c')}
    # reader_next_c08_other shares only a name prefix without the slash: it must be refused.
    result = {'fixed': args.fixed, 'changed': changed, 'outside': outside, 'negatives_refused': negatives}
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'guard.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))
    if outside or not all(negatives.values()):
        sys.exit(1)


if __name__ == '__main__':
    main()
