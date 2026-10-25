"""Authenticate a common source and exact full Apple workflow projections in Actions."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
BASE = '1a6d98ed613c61ffea4267f01f83e2c49b1c02f6'
SDK = 'edddc463c06ed5731195cdb8f06b2df6dff7699e'
FAMILY = '56793e7ca4f8ecdc5f2d9c3394fce4e201aca275'
CORE = '0737d03c1316295a210aa527833c05054d29c1d4'
BRANCH = 'codex/reader-raw3-common-integration'
KIND = 'common-source-exact-apple-workflow-projection-v1'
HERE = 'tests/reader_raw3_common_apple/'
SPECS = {
    'records': ('reader-apple-records-ready.yml', 'reader-raw3-common-apple-records.yml',
                'Apple original records with bounded native simulator readiness',
                'Common raw3 source full Apple original records and bounded readiness',
                'codex/reader-apple-records-ready',
                'tests/reader_apple_records_ready/guard.py',
                'tests/reader_apple_records_ready/verify.py'),
    'macos': ('reader-apple-raw3.yml', 'reader-raw3-common-apple-macos.yml',
              'Independent actual Apple raw3 host candidate',
              'Common raw3 source complete actual macOS raw host and original controls',
              'codex/reader-apple-raw3',
              'tests/apple_host/raw3/guard.py', 'tests/apple_host/raw3/verify.py'),
    'ios': ('reader-apple-raw3-ios-ready.yml', 'reader-raw3-common-apple-ios.yml',
            'Actual iPhone iPad raw3 with bounded native readiness',
            'Common raw3 source complete iPhone iPad raw3 and bounded readiness',
            'codex/reader-apple-raw3-ios-ready',
            'tests/reader_apple_records_ready/raw3_guard.py',
            'tests/reader_apple_records_ready/raw3_verify.py'),
}
NEW_FILES = {'.github/workflows/' + spec[1] for spec in SPECS.values()} | {
    HERE + name for name in ('guard.py', 'verify.py', 'test_guard.py', 'README.md')}
SELF_TEST = '''      - name: Check exact common-source Apple projection and rejection cases in Actions
        run: |
          python3 -m py_compile tests/reader_raw3_common_apple/*.py
          python3 tests/reader_raw3_common_apple/test_guard.py
'''
IOS_SIDECAR = '            build/raw3-ios-sdk/${{ matrix.target }}/common-source-guard.json\n'
IOS_SUMMARY = '            build/raw3-ios-summary/common-source.json\n'
IOS_VERIFY_ENV = '''      - name: Bind original full raw strict to actual bounded native readiness
        env:
          GH_TOKEN: ${{ github.token }}
        run: '''
IOS_VERIFY_ORIGINAL = '''      - name: Bind original full raw strict to actual bounded native readiness
        run: '''


def require(value, message):
    if not value:
        raise ValueError(message)


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def tree(ref):
    values = {}
    for row in git('ls-tree', '-rz', ref).split(b'\0'):
        if row:
            metadata, path = row.split(b'\t', 1)
            values[path.decode('utf-8')] = metadata.decode('ascii')
    return values


def validate_tree(baseline, current, extensions=None):
    for path, value in baseline.items():
        require(current.get(path) == value, 'Existing common-source blob/mode changed: ' + path)
    added = set(current) - set(baseline)
    expected = NEW_FILES if extensions is None else NEW_FILES | set(extensions)
    require(added == expected, 'Common Apple projection file set differs: ' + repr(sorted(added)))
    require(all(current[path].split()[0] == '100644' for path in added), 'Nonregular/executable projection file')


def replace_exact(text, new, old, count=1):
    require(text.count(new) == count, 'Missing/repeated projection fragment: ' + new)
    return text.replace(new, old)


def project_workflow(mode, text):
    """Undo only explicit identity, guard and additive provenance changes."""
    original, workflow, old_name, name, old_branch, guard, verify = SPECS[mode]
    text = replace_exact(text, 'name: ' + name, 'name: ' + old_name)
    # Records also binds SDK3.41/ON and the legacy guard fallback to the actual branch.
    text = replace_exact(text, BRANCH, old_branch, 5 if mode == 'records' else 1)
    command = 'python3 ' + HERE + 'guard.py --mode ' + mode
    if mode in ('records', 'ios'):
        command += " --target '${{ matrix.target }}'"
    text = replace_exact(text, command, 'python3 ' + guard)
    text = replace_exact(text, 'python3 ' + HERE + 'verify.py --mode ' + mode, 'python3 ' + verify)
    text = replace_exact(text, SELF_TEST, '')
    if mode == 'ios':
        text = replace_exact(text, IOS_SIDECAR, '')
        text = replace_exact(text, IOS_SUMMARY, '')
        text = replace_exact(text, IOS_VERIFY_ENV, IOS_VERIFY_ORIGINAL)
    return text


def workflow_identity(mode):
    original, workflow, *_ = SPECS[mode]
    return {
        'workflow': '.github/workflows/' + workflow,
        'original_workflow': '.github/workflows/' + original,
        'workflow_sha256': hashlib.sha256((ROOT / '.github/workflows' / workflow).read_bytes()).hexdigest(),
        'original_workflow_sha256': hashlib.sha256((ROOT / '.github/workflows' / original).read_bytes()).hexdigest(),
    }


def validate_record(record, mode, target, source, run, attempt):
    """Reject historical guard records and provenance for a different source/job target."""
    expected = dict(guard_kind=KIND, mode=mode, target=target, source_sha=source,
                    run_id=run, attempt=attempt, composition_source=BASE, sdk_source=SDK,
                    exact_raw_family_source=FAMILY, sdk_version='3.41.0', sdk_abi=1,
                    branch=BRANCH, original_guard_executed=False,
                    all_existing_blobs_and_modes_unchanged=True,
                    original_full_workflow_projection_exact=True,
                    accepted=False, complete_product=False, physical_device_execution=False,
                    guard_sha256=hashlib.sha256((ROOT / HERE / 'guard.py').read_bytes()).hexdigest(),
                    **workflow_identity(mode))
    require(record == expected, 'New common-source guard identity differs or old guard impersonated')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', required=True, choices=SPECS)
    parser.add_argument('--target', choices=('macos', 'iphonesimulator'), default='macos')
    args = parser.parse_args()
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only')
    require(os.environ.get('GITHUB_REF_NAME') == BRANCH, 'Actual common-source branch required')
    source = git('rev-parse', 'HEAD').decode().strip()
    require(source == os.environ['GITHUB_SHA'], 'Actions checkout/source differs')
    for ancestor in (BASE, CORE, FAMILY):
        subprocess.run(['git', 'merge-base', '--is-ancestor', ancestor, 'HEAD'], cwd=ROOT, check=True)
    # Read the reviewed extension set without invoking configure() or changing
    # sys.modules: the original Apple guard remains the active imported module.
    spec = importlib.util.spec_from_file_location('apple_common_source_extensions',
        ROOT / 'tests/reader_raw3_common_runtime/combined.py')
    composition = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(composition)
    validate_tree(tree(BASE), tree('HEAD'), composition.EXTENSIONS)
    subprocess.run(['git', 'diff', '--exit-code', 'HEAD', '--', '.'], cwd=ROOT, check=True)
    # All three workflows and every original driver/judge are pinned together.
    for mode, spec in SPECS.items():
        original = git('show', BASE + ':.github/workflows/' + spec[0]).decode('utf-8')
        current = (ROOT / '.github/workflows' / spec[1]).read_text(encoding='utf-8')
        require(project_workflow(mode, current) == original, 'Full original workflow differs: ' + mode)
    protected = ('src', 'include', 'cmake', 'CMakeLists.txt', 'bindings', 'tests/fixtures',
                 'licenses', 'tools/layers.json', '.github/workflows/native.yml', '.github/workflows/reliability.yml')
    subprocess.run(['git', 'diff', '--exit-code', SDK, 'HEAD', '--', *protected], cwd=ROOT, check=True)
    for package in ('revisions', 'reading-state', 'reading-commands', 'annotation-view', 'commands', 'sync', 'session'):
        path = 'apps/reader/' + package
        require(git('rev-parse', 'HEAD:' + path) == git('rev-parse', FAMILY + ':' + path), 'Raw module family differs: ' + path)
    if args.mode == 'macos':
        # Preserve the original macOS guard's passed-family prerequisite as well
        # as the source pins; this is not an original guard-success record.
        sys.path.insert(0, str(ROOT / 'tools'))
        from check_parallel_integration import fetch
        proof = fetch('actions/runs/40192929457/attempts/1')
        require(proof['head_sha'] == FAMILY and proof['status'] == 'completed' and proof['conclusion'] == 'success',
                'Original raw family run is not successful at its frozen source')
        jobs = fetch('actions/runs/40192929457/attempts/1/jobs?per_page=100')['jobs']
        require(len(jobs) == 3 and all(job['conclusion'] == 'success' and job['head_sha'] == FAMILY for job in jobs),
                'Original raw family jobs differ')
    record = dict(guard_kind=KIND, mode=args.mode, target=args.target, source_sha=source,
                  run_id=os.environ['GITHUB_RUN_ID'], attempt=os.environ['GITHUB_RUN_ATTEMPT'],
                  composition_source=BASE, sdk_source=SDK, exact_raw_family_source=FAMILY,
                  sdk_version='3.41.0', sdk_abi=1, branch=BRANCH, original_guard_executed=False,
                  all_existing_blobs_and_modes_unchanged=True, original_full_workflow_projection_exact=True,
                  accepted=False, complete_product=False, physical_device_execution=False,
                  guard_sha256=hashlib.sha256((ROOT / HERE / 'guard.py').read_bytes()).hexdigest(),
                  **workflow_identity(args.mode))
    validate_record(record, args.mode, args.target, source, os.environ['GITHUB_RUN_ID'], os.environ['GITHUB_RUN_ATTEMPT'])
    outputs = {'records': 'build/apple-records-ready/guard.json', 'macos': 'build/apple-raw3/guard.json',
               'ios': 'build/raw3-ios-sdk/' + args.target + '/common-source-guard.json'}
    out = ROOT / outputs[args.mode]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(record), flush=True)


if __name__ == '__main__':
    main()
