"""Actual-source composition preflight. Never invokes or spoofs an old guard."""
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess

ROOT = Path(__file__).resolve().parents[2]
BASE = 'e67d87cbeabb2457e0852f681ef0b27b2c0da4d8'
FROZEN = '9854061be331fe603a1822d9b2b36ee357154927'
MANIFEST = 'tests/reader_raw3_common/composition.json'
WORKFLOW = '.github/workflows/reader-raw3-common.yml'
DOCS = {'docs/READER-RAW3-COMMON-PREFLIGHT.md',
        'docs/validation/reader-raw3-common-preflight.json'}
REFS = {
    'approved_sdk_341': 'edddc463c06ed5731195cdb8f06b2df6dff7699e',
    'raw_seven': '56793e7ca4f8ecdc5f2d9c3394fce4e201aca275',
    'metadata_and_schema': '0889f7d1e9a537c6c1b05456547e016b26e1cd85',
    'windows': '13abefbbe82b70d0e8eb3ae197d671e27edfec6c',
    'android': 'caa84411ae79c866c28cf982243b6cb80b4bbe49',
    'apple': '3ee3b7de96cb2ec950c3ec78a36726fc7c3eb9a4',
    'webdav': '98fa8e0f87dc47197677a0cc860e648dbae5b59b',
    'gtk': '8cc9f4eb49ad31f743f2bef762d4b2ec0c72f6b4',
}
FROZEN_PATHS = {'src', 'include', 'cmake', 'CMakeLists.txt', 'bindings',
                'tests/fixtures', '.github/workflows/native.yml', '.github/workflows/reliability.yml'}
OUT = ROOT / 'build/reader-raw3-common'


def git(*args, data=None, env=None):
    return subprocess.check_output(['git', *args], cwd=ROOT, input=data, env=env)


def require_actions():
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise RuntimeError('composition tooling executes only in Actions')


def owned(path):
    return ('\\' not in path and str(PurePosixPath(path)) == path
            and not PurePosixPath(path).is_absolute() and '..' not in PurePosixPath(path).parts
            and (path.startswith('tests/reader_raw3_common/') or path == WORKFLOW or path in DOCS))


@lru_cache(maxsize=64)
def snapshot(source):
    result = {}
    for entry in git('ls-tree', '-rz', '--full-tree', source).split(b'\0'):
        if not entry:
            continue
        header, path = entry.split(b'\t', 1)
        mode, kind, oid = header.decode('ascii').split()
        result[path.decode('utf-8')] = (mode, kind, oid)
    return result


def selected(tree, path):
    return {name: value for name, value in tree.items()
            if name == path or name.startswith(path + '/')}


def event_identity(source, event_sha):
    return [] if source == event_sha else ['identity.event_sha']


def inspect_tree(source):
    """Pure Git-object checks, also exercised against independent mutation trees."""
    current, baseline = snapshot(source), snapshot(BASE)
    errors, changed = [], []
    for path in sorted(set(current) | set(baseline)):
        before, after = baseline.get(path), current.get(path)
        if before == after:
            continue
        changed.append(path)
        if before is not None:
            errors.append('immutable.original:' + path)
        elif not owned(path):
            errors.append('scope.unowned:' + path)
        elif after[:2] != ('100644', 'blob'):
            errors.append('scope.mode:' + path)

    manifest = json.loads(git('show', source + ':' + MANIFEST))
    if (manifest.get('schema') != 1 or manifest.get('composition_base') != BASE
            or manifest.get('frozen_340_source') != FROZEN
            or manifest.get('frozen_340_record') != 'docs/validation/reading-sdk-freeze-9854061.json'
            or set(manifest.get('components', {})) != set(REFS)):
        errors.append('manifest.identity')
    components = {}
    for name, ref in REFS.items():
        definition = manifest.get('components', {}).get(name, {})
        paths = definition.get('paths', [])
        if (definition.get('source') != ref or not isinstance(paths, list) or not paths
                or len(set(paths)) != len(paths)):
            errors.append('manifest.component:' + name)
        rows = []
        expected = snapshot(ref)
        for path in paths:
            if not isinstance(path, str) or not path or '\\' in path or '..' in PurePosixPath(path).parts:
                errors.append('manifest.path:' + name)
                continue
            before, after = selected(expected, path), selected(current, path)
            equal = bool(before) and before == after
            if not equal:
                errors.append('component.mismatch:' + name + ':' + path)
            rows.append({'path': path, 'files': len(before), 'equal': equal,
                         'expected_object': git('rev-parse', ref + ':' + path).decode().strip(),
                         'actual_object': git('rev-parse', source + ':' + path).decode().strip()
                         if after else None})
        components[name] = {'source': ref, 'paths': rows}

    record = json.loads(git('show', source + ':' + manifest['frozen_340_record']))
    protected = record.get('protected_trees', {})
    frozen_ok = (record.get('source_sha') == FROZEN and record.get('sdk_freeze_accepted') is True
                 and record.get('versions', {}).get('sdk') == '3.40.0'
                 and record.get('versions', {}).get('abi') == 1
                 and record.get('versions', {}).get('schema') == 7
                 and set(protected) == FROZEN_PATHS)
    for path in FROZEN_PATHS:
        if protected.get(path) != git('rev-parse', FROZEN + ':' + path).decode().strip():
            frozen_ok = False
    if not frozen_ok:
        errors.append('historical.frozen_340')
    return {'errors': errors, 'changed_paths': changed, 'components': components,
            'frozen_340': {'source': FROZEN, 'record': manifest['frozen_340_record'],
                           'protected_trees': protected, 'verified': frozen_ok,
                           'historical_only': True},
            'manifest_sha256': hashlib.sha256(git('show', source + ':' + MANIFEST)).hexdigest()}


def inspect_source():
    require_actions()
    source = git('rev-parse', 'HEAD').decode().strip()
    errors = event_identity(source, os.environ['GITHUB_SHA'])
    if subprocess.run(['git', 'merge-base', '--is-ancestor', BASE, source], cwd=ROOT).returncode:
        errors.append('identity.base_ancestor')
    if git('diff', '--name-only', 'HEAD', '--').strip():
        errors.append('identity.dirty_tracked')
    if git('ls-files', '--others', '--exclude-standard', '-z').strip(b'\0'):
        errors.append('identity.untracked_source')
    result = inspect_tree(source)
    result['errors'] = errors + result['errors']
    return dict(result, source_sha=source, run_id=os.environ['GITHUB_RUN_ID'],
                attempt=os.environ['GITHUB_RUN_ATTEMPT'], composition_base=BASE,
                source_preflight_passed=not result['errors'], accepted=False, complete_product=False,
                old_guards_unchanged=not any(item.startswith('immutable.original:') for item in result['errors']),
                runtime_accepted=False,
                scope='source composition preflight only; no build, runtime, platform, SDK or product acceptance')


def main():
    report = inspect_source()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'guard.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps(report, sort_keys=True), flush=True)
    if not report['source_preflight_passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
