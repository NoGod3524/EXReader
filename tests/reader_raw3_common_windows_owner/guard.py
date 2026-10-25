"""Common owner source provenance. No old guard is run or impersonated."""
from functools import lru_cache
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import subprocess

from projection import ORIGINAL, OLD_WORKFLOW, OLD_AUTH, WORKFLOW, project_workflow

ROOT = Path(__file__).resolve().parents[2]
BASE = 'bd8c3638019280bea6496b778339abf04629bd27'
COMPOSITION_BASE = '1a6d98ed613c61ffea4267f01f83e2c49b1c02f6'
SDK = 'edddc463c06ed5731195cdb8f06b2df6dff7699e'
RAW = '56793e7ca4f8ecdc5f2d9c3394fce4e201aca275'
WEBDAV = '98fa8e0f87dc47197677a0cc860e648dbae5b59b'
MODULES = ('revisions', 'reading-state', 'reading-commands', 'annotation-view', 'commands', 'sync', 'session')
OWN_FILES = {WORKFLOW, *('tests/reader_raw3_common_windows_owner/' + name for name in
                       ('projection.py', 'guard.py', 'selftest.py', 'strict.py', 'README.md'))}


def git(*args, data=None, env=None):
    return subprocess.check_output(['git', *args], cwd=ROOT, input=data, env=env)


@lru_cache(maxsize=64)
def snapshot(source):
    result = {}
    for entry in git('ls-tree', '-rz', '--full-tree', source).split(b'\0'):
        if entry:
            row, path = entry.split(b'\t', 1)
            result[path.decode('utf-8')] = tuple(row.decode('ascii').split())
    return result


def extensions():
    spec = importlib.util.spec_from_file_location('windows_owner_root_policy',
        ROOT / 'tests/reader_raw3_common_runtime/combined.py')
    policy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(policy)  # declarations only; never configure or change sys.modules
    if policy.BASE != COMPOSITION_BASE or not isinstance(policy.EXTENSIONS, (set, frozenset)):
        raise RuntimeError('root extension identity differs')
    return frozenset(policy.EXTENSIONS)


def valid_path(path):
    return (isinstance(path, str) and '\\' not in path and str(PurePosixPath(path)) == path
            and not PurePosixPath(path).is_absolute() and '..' not in PurePosixPath(path).parts)


def part(tree, path):
    return {name: row for name, row in tree.items() if name == path or name.startswith(path + '/')}


def event_identity(source, event_sha):
    if source != event_sha:
        raise RuntimeError('checkout is not the actual event source')


def inspect_tree(source):
    baseline, current, approved = snapshot(BASE), snapshot(source), extensions()
    errors, changes = [], []
    if not OWN_FILES <= approved:
        errors.append('root.owner_paths_not_approved')
    if set(current) - set(snapshot(COMPOSITION_BASE)) != approved:
        errors.append('root.extensions_exact_set')
    for path in sorted(set(baseline) | set(current)):
        before, after = baseline.get(path), current.get(path)
        if before == after:
            continue
        changes.append(path)
        if path not in approved or not valid_path(path):
            errors.append('unapproved:' + path)
        elif after is None or after[:2] != ('100644', 'blob'):
            errors.append('mode_or_deletion:' + path)
    groups = (
        ('sdk', SDK, ('src', 'include', 'cmake', 'CMakeLists.txt', 'bindings', 'tests/fixtures',
                      'licenses', '.github/workflows/native.yml', '.github/workflows/reliability.yml')),
        ('raw_seven', RAW, tuple('apps/reader/' + name for name in MODULES)),
        ('windows_owner', ORIGINAL, ('examples/reader.c', 'apps/reader/windows-account',
            'apps/reader/desktop/windows_records.inc', 'apps/reader/desktop/windows_records_owner.cpp',
            'apps/reader/desktop/windows_raw3_apis.h', 'apps/reader/desktop/windows_compact_ui.inc',
            'apps/reader/desktop/reading_capture_bytes.h', 'apps/reader/desktop-metadata', 'apps/reader/bulk-organization')),
        ('original_suites_and_drivers', ORIGINAL, ('tests/reader_windows_raw3', 'tests/reader_windows_compact',
            'tests/reader_windows_records', 'tests/reader_bulk_organization', 'tests/reader_windows_preferences')),
        ('webdav', WEBDAV, ('extras/webdav',)),
    )
    pins = {}
    for label, ref, paths in groups:
        pins[label] = {'source': ref, 'paths': {}}
        for path in paths:
            expected = part(snapshot(ref), path)
            equal = bool(expected) and expected == part(current, path)
            pins[label]['paths'][path] = equal
            if not equal:
                errors.append('component:' + label + ':' + path)
    original = git('show', ORIGINAL + ':' + OLD_WORKFLOW)
    for path in (OLD_WORKFLOW, OLD_AUTH):
        if git('show', source + ':' + path) != git('show', ORIGINAL + ':' + path):
            errors.append('old_entry_changed:' + path)
    current_workflow = git('show', source + ':' + WORKFLOW)
    try:
        projected = project_workflow(current_workflow.decode('utf-8')).encode('utf-8')
    except RuntimeError:
        projected = None
    if projected != original:
        errors.append('workflow_projection')
    return {'errors': errors, 'changed_paths': changes, 'components': pins,
            'root_extensions': sorted(approved), 'workflow_projection_exact': projected == original,
            'original_host_workflow_sha256': hashlib.sha256(original).hexdigest(),
            'common_workflow_sha256': hashlib.sha256(current_workflow).hexdigest(),
            'original_auth_sha256': hashlib.sha256(git('show', ORIGINAL + ':' + OLD_AUTH)).hexdigest()}


def inspect_source():
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise RuntimeError('Actions only')
    source = git('rev-parse', 'HEAD').decode().strip()
    event_identity(source, os.environ['GITHUB_SHA'])
    subprocess.run(['git', 'merge-base', '--is-ancestor', BASE, source], cwd=ROOT, check=True)
    if git('diff', '--name-only', 'HEAD', '--').strip() or git('ls-files', '--others', '--exclude-standard', '-z').strip(b'\0'):
        raise RuntimeError('dirty source checkout')
    report = inspect_tree(source)
    if report['errors']:
        raise RuntimeError('common Windows owner source refused: ' + repr(report['errors']))
    return dict(report, source_sha=source, run_id=os.environ['GITHUB_RUN_ID'], attempt=os.environ['GITHUB_RUN_ATTEMPT'],
                guard_kind='common-windows-owner', source_preflight_passed=True, legacy_guard_executed=False,
                original_auth_reference_source=ORIGINAL, original_auth_reference_run=40222024767,
                old_auth_run_reused=False, accepted=False, complete_product=False, runtime_accepted=False)


def main():
    report = inspect_source()
    out = ROOT / 'build/windows-raw3-preflight'
    out.mkdir(parents=True, exist_ok=True)
    (out / 'common-source.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps(report, sort_keys=True), flush=True)


if __name__ == '__main__':
    main()
