"""Explicit changed-owner policy. This is not any historical unchanged-owner guard."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
BASE = '96270a2b478b673eb45b7e2467e2e2acb6b64a88'
OWNERS = {
    'examples/reader.c', 'examples/linux/reading_records_ui.inc',
    'apps/reader/desktop/windows_navigation.inc',
    'apps/reader/desktop/windows_preferences_ui.inc',
    'apps/reader/desktop/windows_records.inc',
    'apps/reader/desktop/windows_records_owner.cpp',
    'apps/reader/desktop/windows_records_owner.h',
    'apps/reader/desktop/windows_search.inc',
}
PREFIXES = ('tests/reader_native_owner_repairs/', 'docs/reader-native-owner-repairs/')
WORKFLOW = '.github/workflows/reader-native-owner-repairs.yml'


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def allowed(path):
    return path in OWNERS or path == WORKFLOW or path.startswith(PREFIXES)


def validate(rows):
    for state, path in rows:
        if not allowed(path) or state not in ('A', 'M'):
            raise RuntimeError('outside explicit owner repair policy: ' + state + ' ' + path)


def inspect_source():
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise RuntimeError('Actions only')
    source = os.environ['GITHUB_SHA']
    if git('rev-parse', 'HEAD').decode().strip() != source:
        raise RuntimeError('actual checkout differs from Actions source')
    subprocess.run(['git', 'merge-base', '--is-ancestor', BASE, source], cwd=ROOT, check=True)
    rows = [tuple(line.split('\t', 1)) for line in git('diff', '--name-status', BASE, source).decode().splitlines()]
    validate(rows)
    owners = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in sorted(OWNERS)}
    result = dict(guard_kind='native-owner-repairs', source_sha=source,
                  run_id=os.environ['GITHUB_RUN_ID'], attempt=os.environ['GITHUB_RUN_ATTEMPT'],
                  base_sha=BASE, legacy_guard_executed=False, accepted=False,
                  runtime_accepted=False, source_preflight_passed=True,
                  owner_sha256=owners, changed_paths=rows,
                  frozen_scope='All base paths other than eight enumerated native owner files remain byte-identical, including SDK, seven raw packages, schemas, budgets and original tests')
    return result


def main():
    report = inspect_source()
    refused = []
    for state, path in [('M', 'CMakeLists.txt'), ('M', 'include/exr/base.h'),
                        ('M', 'apps/reader/revisions/src/revisions.cpp'),
                        ('M', 'apps/reader/store/001_catalog.sql'),
                        ('M', 'tests/reader_windows_raw3/host_build.py'),
                        ('M', 'tests/windows_host/worker_review/hooks.h'),
                        ('D', 'examples/reader.c'), ('R100', 'examples/reader.c')]:
        try:
            validate([(state, path)])
        except RuntimeError:
            refused.append(dict(state=state, path=path, rejected=True))
        else:
            raise RuntimeError('source-policy negative accepted')
    report['negative_controls'] = refused
    folder = ROOT / 'build/native-owner-preflight'
    folder.mkdir(parents=True, exist_ok=True)
    (folder / (os.environ['GITHUB_JOB'] + '.json')).write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
