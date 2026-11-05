"""S04 path-ownership guard with its own negative selftest.

Only the four paths reserved by the S04 task page may differ from the fixed
implementation start. Everything else (apps/, examples/, src/, include/,
extras/, bindings/, existing tests, existing workflows, docs, budgets) must be
byte-identical to 0889f7d1e9a537c6c1b05456547e016b26e1cd85.
"""
import argparse
import json
import os
import pathlib
import posixpath
import subprocess
import sys

FIXED_START = '0889f7d1e9a537c6c1b05456547e016b26e1cd85'
ALLOWED_FILES = ('.github/workflows/reader-final-s04.yml', 'HANDOFF-RESULT.md')
ALLOWED_PREFIXES = ('tests/reader_final_s04/', 'docs/reader-final-s04/')


def violations(paths):
    bad = []
    for path in paths:
        normalized = posixpath.normpath(path)
        if normalized.startswith('..') or normalized.startswith('/') or normalized != path:
            bad.append(path)
            continue
        if path in ALLOWED_FILES:
            continue
        if any(path.startswith(prefix) for prefix in ALLOWED_PREFIXES):
            continue
        bad.append(path)
    return bad


def selftest():
    accepted = ['tests/reader_final_s04/emulator.py',
                'docs/reader-final-s04/validation.json',
                '.github/workflows/reader-final-s04.yml',
                'HANDOFF-RESULT.md']
    if violations(accepted):
        raise SystemExit('guard selftest rejected an allowed S04 path: ' + repr(violations(accepted)))
    rejected = ['apps/reader/store/native/CMakeLists.txt',
                'examples/android/app/build.gradle',
                'tests/reader_android_reading/run_ui.py',
                '.github/workflows/native.yml',
                'src/core.c', 'include/exreader.h', 'extras/webdav/CMakeLists.txt',
                'tests/reader_final_s04_extra/thing.py',
                'docs/READER-WINDOWS-RAW3.md',
                'HANDOFF-RESULT.md.bak',
                'tests/reader_final_s04/../reader_android_reading/run_ui.py']
    for path in rejected:
        if not violations([path]):
            raise SystemExit('guard selftest accepted a forbidden path: ' + path)
    return {'allowed_accepted': len(accepted), 'forbidden_rejected': len(rejected)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--fixed', default=FIXED_START)
    parser.add_argument('--output', type=pathlib.Path, default=pathlib.Path('build/s04-guards'))
    args = parser.parse_args()
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise SystemExit('guard only runs in GitHub Actions')
    args.output.mkdir(parents=True, exist_ok=True)
    negative = selftest()
    subprocess.run(['git', 'merge-base', '--is-ancestor', args.fixed, 'HEAD'], check=True)
    changed = subprocess.run(['git', 'diff', '--name-status', args.fixed, 'HEAD'],
                             check=True, stdout=subprocess.PIPE).stdout.decode().splitlines()
    rows = []
    for line in changed:
        parts = line.split('\t')
        status, paths = parts[0], parts[1:]
        for path in paths:
            rows.append({'status': status, 'path': path})
    bad = violations([row['path'] for row in rows])
    head = subprocess.run(['git', 'rev-parse', 'HEAD'], check=True,
                          stdout=subprocess.PIPE).stdout.decode().strip()
    result = {'fixed_start': args.fixed, 'head': head, 'changed': rows,
              'violations': bad, 'negative_selftest': negative,
              'passed': not bad}
    (args.output / 'guard.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps({k: result[k] for k in ('fixed_start', 'head', 'violations', 'negative_selftest', 'passed')}))
    if bad:
        raise SystemExit('S04 changed paths outside its own reservation: ' + repr(bad))


if __name__ == '__main__':
    main()
