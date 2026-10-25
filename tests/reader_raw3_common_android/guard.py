"""Honest common-kind guard; the original Android-only guard remains untouched."""
from functools import lru_cache
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import subprocess

from projection import ORIGINAL, ORIGINAL_WORKFLOW, WORKFLOW, original_projection

ROOT = Path(__file__).resolve().parents[2]
BASE = '1a6d98ed613c61ffea4267f01f83e2c49b1c02f6'
SDK = 'edddc463c06ed5731195cdb8f06b2df6dff7699e'
RAW = '56793e7ca4f8ecdc5f2d9c3394fce4e201aca275'
ANDROID_FAMILY = '0793b26256e1397ba0f60d27de7d090fad61af81'
WEBDAV = '98fa8e0f87dc47197677a0cc860e648dbae5b59b'
MODULES = ('revisions', 'reading-state', 'reading-commands', 'annotation-view', 'commands', 'sync', 'session')
SDK_PATHS = ('src', 'include', 'cmake', 'CMakeLists.txt', 'bindings', 'tests/fixtures', 'licenses',
             '.github/workflows/native.yml', '.github/workflows/reliability.yml')
SUITES = ('reader_android_raw3', 'reader_android_record_interop', 'reader_android_page_theme',
          'reader_android_host_import', 'reader_android_fixed_pan', 'reader_android_cbz_reading',
          'reader_android_reading', 'reader_android_preferences', 'reader_android_navigation',
          'reader_android_search', 'reader_host_session_android', 'reader_session_android',
          'webdav_android', 'apple_host/record_compatibility', 'apple_host/reading')
DOCS = {'docs/READER-RAW3-COMMON-ANDROID.md', 'docs/validation/reader-raw3-common-android.json'}


def git(*args, data=None, env=None):
    return subprocess.check_output(['git', *args], cwd=ROOT, input=data, env=env)


@lru_cache(maxsize=64)
def snapshot(source):
    result = {}
    for raw in git('ls-tree', '-rz', '--full-tree', source).split(b'\0'):
        if raw:
            entry, path = raw.split(b'\t', 1)
            result[path.decode('utf-8')] = tuple(entry.decode('ascii').split())
    return result


def root_extensions():
    path = ROOT / 'tests/reader_raw3_common_runtime/combined.py'
    spec = importlib.util.spec_from_file_location('common_android_root_extension_policy', path)
    policy = importlib.util.module_from_spec(spec)
    # Only load the declarations. Do not call configure() or register its guard
    # under another module name; the root's reviewed EXTENSIONS is the policy.
    spec.loader.exec_module(policy)
    if policy.BASE != BASE or not isinstance(policy.EXTENSIONS, (set, frozenset)):
        raise RuntimeError('root extension policy identity differs')
    if not all(isinstance(item, str) for item in policy.EXTENSIONS):
        raise RuntimeError('root extension policy contains a non-path')
    return frozenset(policy.EXTENSIONS)


def owned(path, extensions=None):
    if extensions is None:
        extensions = root_extensions()
    return ('\\' not in path and str(PurePosixPath(path)) == path
            and not PurePosixPath(path).is_absolute() and '..' not in PurePosixPath(path).parts
            and (path.startswith('tests/reader_raw3_common_android/') or path == WORKFLOW
                 or path in DOCS or path in extensions))


def part(tree, path):
    return {name: row for name, row in tree.items() if name == path or name.startswith(path + '/')}


def require_event_identity(source, event_sha):
    if source != event_sha:
        raise RuntimeError('actual checkout differs from event SHA')


def inspect_tree(source):
    before, after = snapshot(BASE), snapshot(source)
    extensions = root_extensions()
    errors, changed = [], []
    additions = set(after) - set(before)
    if additions != extensions:
        errors.append('extensions.exact_set')
    for path in sorted(set(before) | set(after)):
        if before.get(path) == after.get(path):
            continue
        changed.append(path)
        if path in before:
            errors.append('immutable:' + path)
        elif not owned(path, extensions):
            errors.append('unowned:' + path)
        elif after[path][:2] != ('100644', 'blob'):
            errors.append('mode:' + path)
    groups = (
        ('approved_sdk', SDK, SDK_PATHS),
        ('seven_modules', RAW, tuple('apps/reader/' + name for name in MODULES)),
        ('android_family', ANDROID_FAMILY, tuple('apps/reader/' + name for name in MODULES)),
        ('android_owner', ORIGINAL, ('examples/android',)),
        ('legacy_suites', ORIGINAL, tuple('tests/' + name for name in SUITES)),
        ('metadata_schema', BASE, ('apps/reader/desktop-metadata', 'apps/reader/store')),
        ('approved_webdav', WEBDAV, ('extras/webdav',)),
    )
    trees = {}
    for label, ref, paths in groups:
        trees[label] = {'source': ref, 'paths': {}}
        for path in paths:
            original = part(snapshot(ref), path)
            equal = bool(original) and original == part(after, path)
            trees[label]['paths'][path] = equal
            if not equal:
                errors.append('component:' + label + ':' + path)
    original_workflow = git('show', ORIGINAL + ':' + ORIGINAL_WORKFLOW)
    if git('show', source + ':' + ORIGINAL_WORKFLOW) != original_workflow:
        errors.append('original_workflow')
    current_workflow = git('show', source + ':' + WORKFLOW)
    try:
        exact = original_projection(current_workflow.decode('utf-8')).encode('utf-8') == original_workflow
    except RuntimeError:
        exact = False
    if not exact:
        errors.append('workflow_projection')
    return {'errors': errors, 'changed': changed, 'components': trees,
            'root_extensions': sorted(extensions), 'extensions_exact_set': additions == extensions,
            'workflow_projection_exact': exact,
            'original_workflow_sha256': hashlib.sha256(original_workflow).hexdigest(),
            'common_workflow_sha256': hashlib.sha256(current_workflow).hexdigest()}


def inspect_source():
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise RuntimeError('Actions only')
    source = git('rev-parse', 'HEAD').decode().strip()
    require_event_identity(source, os.environ['GITHUB_SHA'])
    subprocess.run(['git', 'merge-base', '--is-ancestor', BASE, source], cwd=ROOT, check=True)
    if git('diff', '--name-only', 'HEAD', '--').strip() or git('ls-files', '--others', '--exclude-standard', '-z').strip(b'\0'):
        raise RuntimeError('source checkout is dirty')
    result = inspect_tree(source)
    if result['errors']:
        raise RuntimeError('common Android source refused: ' + repr(result['errors']))
    return dict(result, accepted=True, guard_kind='common', legacy_guard_executed=False,
                source_guard_only=True, source_sha=source, run_id=os.environ['GITHUB_RUN_ID'],
                attempt=os.environ['GITHUB_RUN_ATTEMPT'], common_base=BASE, sdk=SDK, family=RAW,
                seven_modules_unchanged=True, legacy_suites_unchanged=True, sdk_boundaries_unchanged=True,
                complete_product=False, runtime_accepted=False,
                scope='common-source composition and exact workflow projection only; old Android guard was not executed')


def main():
    report = dict(inspect_source(), producer_job_key=os.environ['GITHUB_JOB'])
    if report['producer_job_key'] not in ('android', 'protocol'):
        raise RuntimeError('unexpected producer stage')
    raw = json.dumps(report, indent=2, sort_keys=True) + '\n'
    folder = ROOT / 'build/reader-raw3-common-android' / report['producer_job_key']
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'guard.json').write_text(raw, encoding='utf-8')
    # The unchanged original strict reads this location. The report explicitly
    # identifies the common guard; the added strict authenticates its provenance.
    compatibility = ROOT / 'build/android-raw3/guard.json'
    compatibility.parent.mkdir(parents=True, exist_ok=True)
    compatibility.write_text(raw, encoding='utf-8')
    print(raw, flush=True)


if __name__ == '__main__':
    main()
