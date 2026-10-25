"""Independent actual-tree mutation controls; never edits HEAD, checkout or event SHA."""
import json
import os
from pathlib import Path
import tempfile

import guard

CASES = {
    'sdk_blob': ('include/exr/base.h', '100644', b'changed SDK header\n', 'component.mismatch:approved_sdk_341:'),
    'raw_module': ('apps/reader/revisions/include/reader_revisions.h', '100644', b'changed raw revision\n', 'component.mismatch:raw_seven:'),
    'metadata': ('apps/reader/desktop-metadata/src/metadata.cpp', '100644', b'changed metadata\n', 'component.mismatch:metadata_and_schema:'),
    'windows': ('examples/reader.c', '100644', b'changed Windows owner\n', 'component.mismatch:windows:'),
    'android': ('examples/android/app/src/main/java/org/exreader/host/MainActivity.java', '100644', b'changed Android owner\n', 'component.mismatch:android:'),
    'apple': ('examples/apple/HostModel.swift', '100644', b'changed Apple owner\n', 'component.mismatch:apple:'),
    'webdav': ('extras/webdav/src/webdav.cpp', '100644', b'changed signal boundary\n', 'component.mismatch:webdav:'),
    'gtk': ('examples/linux/reader.c', '100644', b'changed GTK owner\n', 'component.mismatch:gtk:'),
    'old_workflow': ('.github/workflows/native.yml', '100644', b'name: replaced\n', 'immutable.original:'),
    'old_guard': ('tests/reader_android_raw3/guard.py', '100644', b'pass\n', 'immutable.original:'),
    'deleted_sdk': ('include/exr/base.h', None, None, 'immutable.original:'),
    'old_executable_mode': ('examples/reader.c', '100755', None, 'immutable.original:'),
    'owned_symlink': ('tests/reader_raw3_common/evil.py', '120000', b'../../src/library.c', 'scope.mode:'),
    'owned_executable': ('tests/reader_raw3_common/evil.py', '100755', b'pass\n', 'scope.mode:'),
    'owned_gitlink': ('tests/reader_raw3_common/embedded', '160000', None, 'scope.mode:'),
    'prefix_collision': ('tests/reader_raw3_common_extra/evil.py', '100644', b'pass\n', 'scope.unowned:'),
    'future_runtime_unapproved': ('tests/reader_raw3_common_runtime/guard.py', '100644', b'pass\n', 'scope.unowned:'),
    'future_leaf_workflow_unapproved': ('.github/workflows/reader-raw3-common-windows.yml', '100644', b'name: new\n', 'scope.unowned:'),
}
EXTRA = ('event_sha_spoof', 'frozen_340_manifest', 'manifest_reference', 'path_traversal')
EXPECTED = set(CASES) | set(EXTRA)


def mutation(source, path, mode, body):
    with tempfile.TemporaryDirectory(prefix='common-negative-') as temporary:
        env = dict(os.environ, GIT_INDEX_FILE=str(Path(temporary) / 'index'))
        guard.git('read-tree', source, env=env)
        if mode is None:
            guard.git('update-index', '--force-remove', '--', path, env=env)
        else:
            if mode == '160000':
                oid = source
            elif body is None:
                oid = guard.snapshot(source)[path][2]
            else:
                oid = guard.git('hash-object', '-w', '--stdin', data=body).decode().strip()
            guard.git('update-index', '--add', '--cacheinfo', mode + ',' + oid + ',' + path, env=env)
        return guard.git('write-tree', env=env).decode().strip()


def main():
    guard.require_actions()
    source = guard.git('rev-parse', 'HEAD').decode().strip()
    original_index = guard.git('write-tree')
    if source != os.environ['GITHUB_SHA']:
        raise RuntimeError('actual negative-test checkout differs from event SHA')
    positive = guard.inspect_tree(source)
    if positive['errors']:
        raise RuntimeError('positive composition rejected: ' + repr(positive['errors']))
    controls = []
    for name, (path, mode, body, prefix) in CASES.items():
        tree = mutation(source, path, mode, body)
        observed = guard.inspect_tree(tree)['errors']
        if not any(item.startswith(prefix) for item in observed):
            raise RuntimeError(name + ' did not reject the actual mutated Git tree: ' + repr(observed))
        controls.append({'name': name, 'rejected': True, 'tree': tree,
                         'reason_codes': sorted({item.split(':', 1)[0] for item in observed})})
    if not guard.event_identity(source, '0' * 40):
        raise RuntimeError('mismatching event identity was accepted')
    controls.append({'name': 'event_sha_spoof', 'rejected': True})
    record = json.loads(guard.git('show', source + ':docs/validation/reading-sdk-freeze-9854061.json'))
    record['protected_trees']['include'] = '0' * 40
    tree = mutation(source, 'docs/validation/reading-sdk-freeze-9854061.json', '100644', json.dumps(record).encode())
    if 'historical.frozen_340' not in guard.inspect_tree(tree)['errors']:
        raise RuntimeError('changed historical freeze manifest was accepted')
    controls.append({'name': 'frozen_340_manifest', 'rejected': True, 'tree': tree})
    manifest = json.loads(guard.git('show', source + ':' + guard.MANIFEST))
    manifest['components']['approved_sdk_341']['source'] = guard.FROZEN
    tree = mutation(source, guard.MANIFEST, '100644', json.dumps(manifest).encode())
    if 'manifest.component:approved_sdk_341' not in guard.inspect_tree(tree)['errors']:
        raise RuntimeError('historical 3.40 substituted for current approved 3.41 was accepted')
    controls.append({'name': 'manifest_reference', 'rejected': True, 'tree': tree})
    for path in ('../tests/reader_raw3_common/evil.py', 'tests/reader_raw3_common/../evil.py',
                 '/tests/reader_raw3_common/evil.py', 'tests\\reader_raw3_common\\evil.py'):
        if guard.owned(path):
            raise RuntimeError('ownership path escape was accepted: ' + path)
    controls.append({'name': 'path_traversal', 'rejected': True})
    if guard.git('write-tree') != original_index or guard.git('rev-parse', 'HEAD').decode().strip() != source:
        raise RuntimeError('negative controls changed the checkout or real index')
    report = {'source_sha': source, 'run_id': os.environ['GITHUB_RUN_ID'],
              'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'positive_composition_passed': True,
              'controls': controls, 'negative_controls_passed': True,
              'checkout_and_index_unchanged': True, 'event_environment_unchanged': True,
              'accepted': False, 'complete_product': False}
    guard.OUT.mkdir(parents=True, exist_ok=True)
    (guard.OUT / 'negative.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps(report, sort_keys=True), flush=True)


if __name__ == '__main__':
    main()
