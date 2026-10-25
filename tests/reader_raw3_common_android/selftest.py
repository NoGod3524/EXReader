"""Actions-only refusal controls without changing the real checkout or event SHA."""
import json
import os
from pathlib import Path
import tempfile

import guard
from projection import original_projection

TREE_CASES = {
    'sdk': ('include/exr/base.h', '100644', b'changed SDK\n', 'immutable:'),
    'raw_module': ('apps/reader/revisions/include/reader_revisions.h', '100644', b'changed raw\n', 'immutable:'),
    'owner': ('examples/android/app/src/main/java/org/exreader/host/MainActivity.java', '100644', b'changed host\n', 'immutable:'),
    'old_strict': ('tests/reader_android_raw3/strict.py', '100644', b'pass\n', 'immutable:'),
    'old_guard': ('tests/reader_android_raw3/guard.py', '100644', b'pass\n', 'immutable:'),
    'old_business': ('tests/reader_android_search/run_ui.py', '100644', b'pass\n', 'immutable:'),
    'unknown_path': ('tests/reader_raw3_common_android_extra/evil.py', '100644', b'pass\n', 'unowned:'),
    'owned_symlink': ('tests/reader_raw3_common_android/evil.py', '120000', b'../../src/core.c', 'mode:'),
    'owned_executable': ('tests/reader_raw3_common_android/evil.py', '100755', b'pass\n', 'mode:'),
}
WORKFLOW_CASES = {
    'raw_flag': ('-PexrSelectorBytes=true', '-PexrSelectorBytes=false'),
    'api34': ('api-level: 34', 'api-level: 33'),
    'timeout': ('timeout-minutes: 120', 'timeout-minutes: 121'),
    'business_removed': ('python tests/reader_android_search/run_ui.py', 'echo removed-search'),
    'peer_removed': ('python tests/reader_android_raw3/fetch_apple.py', 'echo fake-peer'),
    'artifact_relaxed': ('if-no-files-found: error', 'if-no-files-found: warn'),
    'strict_removed': ('python tests/reader_raw3_common_android/strict.py', 'echo no-strict'),
    'guard_removed': ('python tests/reader_raw3_common_android/guard.py', 'echo no-guard'),
}
EXPECTED = set(TREE_CASES) | set(WORKFLOW_CASES) | {'event_sha_mismatch', 'path_escape'}


def mutation(source, path, mode, body):
    with tempfile.TemporaryDirectory(prefix='android-common-negative-') as folder:
        env = dict(os.environ, GIT_INDEX_FILE=str(Path(folder) / 'index'))
        guard.git('read-tree', source, env=env)
        oid = guard.git('hash-object', '-w', '--stdin', data=body).decode().strip()
        guard.git('update-index', '--add', '--cacheinfo', mode + ',' + oid + ',' + path, env=env)
        return guard.git('write-tree', env=env).decode().strip()


def main():
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise RuntimeError('Actions only')
    source = guard.git('rev-parse', 'HEAD').decode().strip()
    if source != os.environ['GITHUB_SHA']:
        raise RuntimeError('actual event checkout differs')
    original_index = guard.git('write-tree')
    original = guard.git('show', guard.ORIGINAL + ':' + guard.ORIGINAL_WORKFLOW)
    current = guard.git('show', source + ':' + guard.WORKFLOW).decode('utf-8')
    if original_projection(current).encode('utf-8') != original:
        raise RuntimeError('positive workflow projection differs')
    controls = []
    for name, (path, mode, body, prefix) in TREE_CASES.items():
        tree = mutation(source, path, mode, body)
        errors = guard.inspect_tree(tree)['errors']
        if not any(error.startswith(prefix) for error in errors):
            raise RuntimeError('actual tree mutation accepted: ' + name)
        controls.append({'name': name, 'rejected': True, 'tree': tree})
    for name, (before, after) in WORKFLOW_CASES.items():
        if before not in current:
            raise RuntimeError('negative control marker missing: ' + name)
        altered = current.replace(before, after, 1)
        try:
            projected = original_projection(altered).encode('utf-8')
        except RuntimeError:
            projected = None
        if projected == original:
            raise RuntimeError('altered workflow accepted: ' + name)
        controls.append({'name': name, 'rejected': True})
    try:
        guard.require_event_identity(source, '0' * 40)
    except RuntimeError:
        pass
    else:
        raise RuntimeError('wrong event SHA accepted')
    controls.append({'name': 'event_sha_mismatch', 'rejected': True})
    for path in ('../tests/reader_raw3_common_android/a.py', 'tests/reader_raw3_common_android/../a.py',
                 '/tests/reader_raw3_common_android/a.py', 'tests\\reader_raw3_common_android\\a.py'):
        if guard.owned(path):
            raise RuntimeError('ownership path escape accepted')
    controls.append({'name': 'path_escape', 'rejected': True})
    if guard.git('write-tree') != original_index or guard.git('rev-parse', 'HEAD').decode().strip() != source:
        raise RuntimeError('negative controls changed real checkout/index')
    report = {'source_sha': source, 'run_id': os.environ['GITHUB_RUN_ID'],
              'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'producer_job_key': os.environ['GITHUB_JOB'],
              'guard_kind': 'common', 'negative_controls_passed': True, 'controls': controls,
              'checkout_and_index_unchanged': True, 'event_environment_unchanged': True,
              'accepted': False, 'complete_product': False}
    folder = guard.ROOT / 'build/reader-raw3-common-android' / report['producer_job_key']
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'negative.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps(report, sort_keys=True), flush=True)


if __name__ == '__main__':
    main()
