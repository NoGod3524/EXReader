"""Exact independent Apple caller scope, SDK, schema and passed raw family."""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
BASE = '896420028fa3923f3713afb673f56b913f93373f'
CORE = '0737d03c1316295a210aa527833c05054d29c1d4'
FAMILY = '56793e7ca4f8ecdc5f2d9c3394fce4e201aca275'
MERGED = 'b2001e719732d7f9e91c330d618b647f836bd31e'
SDK = 'edddc463c06ed5731195cdb8f06b2df6dff7699e'
PACKAGES = ('revisions', 'reading-state', 'reading-commands', 'annotation-view', 'commands', 'sync', 'session')
OWNED = {'examples/apple/HostCatalog.swift', 'examples/apple/HostReadingRecords.swift',
         'examples/apple/HostModel.swift', 'examples/apple/HostAccount.swift',
         'tools/apple_swift.py', 'tools/build_apple_product.py', 'tools/build_apple_host.py',
         'tools/check_apple_product.py', '.github/workflows/reader-apple-raw3.yml',
         'docs/READER-APPLE-RAW3.md', 'docs/validation/reader-apple-raw3.json'}


def git(*args):
    return subprocess.check_output(['git', '-C', ROOT, *args], text=True).strip()


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    assert git('rev-parse', 'HEAD') == os.environ['GITHUB_SHA']
    assert os.environ['GITHUB_REF_NAME'] == 'codex/reader-apple-raw3'
    for ancestor in (BASE, CORE, FAMILY, MERGED):
        subprocess.run(['git', '-C', ROOT, 'merge-base', '--is-ancestor', ancestor, 'HEAD'], check=True)
    sdk_paths = ('src', 'include', 'cmake', 'CMakeLists.txt', 'bindings', 'tests/fixtures',
                 'licenses', 'tools/layers.json', '.github/workflows/native.yml', '.github/workflows/reliability.yml')
    subprocess.run(['git', '-C', ROOT, 'diff', '--exit-code', SDK, 'HEAD', '--', *sdk_paths], check=True)
    subprocess.run(['git', '-C', ROOT, 'diff', '--exit-code', BASE, 'HEAD', '--', 'apps/reader/store/001_catalog.sql'], check=True)
    for package in PACKAGES:
        path = 'apps/reader/' + package
        assert git('rev-parse', 'HEAD:' + path) == git('rev-parse', FAMILY + ':' + path), path
    for path in git('diff', '--name-only', BASE, 'HEAD').splitlines():
        if path in OWNED or path.startswith('tests/apple_host/raw3/'):
            continue
        if any(path.startswith('apps/reader/' + package + '/') for package in PACKAGES):
            continue
        # Inherited fixture/workflow/docs provenance is immutable; no other host
        # or module implementation is adopted by this Apple-only caller package.
        if path.startswith(('examples/', 'apps/', 'extras/', 'src/', 'include/', 'bindings/', 'tools/')):
            raise AssertionError('Unowned production change: ' + path)
        assert git('rev-parse', 'HEAD:' + path) == git('rev-parse', MERGED + ':' + path), path
    for folder in ('reading', 'record_compatibility', 'navigation', 'search', 'shelf'):
        path = 'tests/apple_host/' + folder
        assert git('rev-parse', 'HEAD:' + path) == git('rev-parse', BASE + ':' + path), path
    sys.path.insert(0, str(ROOT / 'tools'))
    from check_parallel_integration import fetch
    proof = fetch('actions/runs/40192929457/attempts/1')
    assert proof['head_sha'] == FAMILY and proof['conclusion'] == 'success' and proof['status'] == 'completed'
    jobs = fetch('actions/runs/40192929457/attempts/1/jobs?per_page=100')['jobs']
    assert len(jobs) == 3 and all(job['conclusion'] == 'success' and job['head_sha'] == FAMILY for job in jobs)
    result = {'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
              'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'base': BASE, 'core': CORE, 'family': FAMILY,
              'sdk_source': SDK, 'schema_changed': False, 'family_run': 40192929457,
              'input_authenticated': True, 'actual_host_accepted': False}
    out = ROOT / 'build/apple-raw3/guard.json'; out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
