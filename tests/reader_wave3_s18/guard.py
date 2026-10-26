"""Actions-only provenance for the wave3 S18 joint default/raw install replay.

This guard replaces the single-package guards of the reviewed waves: it declares
the exact seed this branch starts from and the exact paths this package owns, then
proves every other path in the pushed tree is byte-identical to the seed. The
untouched original judges are executed as independent validators; none of their
own branch/ownership guards is executed or claimed.
"""
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
SEED = 'd263ce5228838ac90c0a0dc13a5193d4a7739681'
SDK_SOURCE = '9d3a3f8bfa06c099ebba0d9e1ba613d276c3af09'
FROZEN_SDK = '9854061be331fe603a1822d9b2b36ee357154927'
LEGACY_START = 'e67d87cbeabb2457e0852f681ef0b27b2c0da4d8'
WORKFLOW = '.github/workflows/reader-team24-core.yml'
OWN_FILES = {WORKFLOW, 'HANDOFF-RESULT-S18.md', 'tests/reader_wave3_s18/README.md',
             'tests/reader_wave3_s18/guard.py', 'tests/reader_wave3_s18/runtime.py',
             'tests/reader_wave3_s18/strict.py', 'tests/reader_wave3_s18/consumer/CMakeLists.txt',
             'tests/reader_wave3_s18/consumer/main.cpp'}
OWN_FILES.add('tools/reader_host_feature_link.cmake')
OWN_DIRS = ('tests/reader_wave3_s18/', 'docs/reader-wave3-s18/',
            'tests/reader_wave3_s19/', 'docs/reader-wave3-s19/',
            'docs/reader-team24-core/', 'apps/reader/host-feature-link/')
# These are exact input blobs, not editable ownership exceptions. A mutation of
# the native host or either adopted parser must still fail the source guard.
FIXED_BLOBS = {'examples/reader.c': '35bd6d909014e722ef00317e8404c17590f318a2'}
SDK_ADOPTED = ('src/rtf.c', 'src/cbz.c')
PACKAGES = ('annotation-export', 'annotation-import', 'font-library', 'original-export',
            'jump-history', 'sync-status-view', 'revisions', 'reading-state', 'commands',
            'sync', 'session')
SDK_PATHS = ('src', 'include', 'cmake', 'CMakeLists.txt', 'CMakePresets.json', 'bindings',
             'tests/fixtures', 'extras/sideload', 'extras/webdav')
OLD_JUDGES = ('tests/reader_next_c06', 'tests/reader_next_s14', 'tests/reader_next_s15',
              'tests/reader_next_s16', 'tests/reader_next_s17', 'tests/reader_next_s14/run.py',
              'tests/reader_jump_history', 'tests/reader_sync_status_view', 'tests/reader_revisions',
              'tests/reader_sync')
OUT = ROOT / 'build/reader-wave3-s18'


def git(*args, **kwargs):
    return subprocess.check_output(['git', *args], cwd=ROOT, **kwargs)


def owned(path):
    return path in OWN_FILES or any(path.startswith(directory) for directory in OWN_DIRS)


def tree(ref):
    result = {}
    for record in git('ls-tree', '-rz', '--full-tree', ref).split(b'\0'):
        if record:
            mode, name = record.split(b'\t', 1)
            result[name.decode()] = tuple(mode.decode().split())
    return result


def subset(files, path):
    return {key: value for key, value in files.items() if key == path or key.startswith(path + '/')}


def inspect(source):
    actual, base = tree(source), tree(SEED)
    candidate = tree(SDK_SOURCE)
    errors = []
    for path in sorted(set(actual) | set(base)):
        if path in SDK_ADOPTED:
            if actual.get(path) != candidate.get(path):
                errors.append('sdk.candidate:' + path)
        elif path in FIXED_BLOBS:
            if actual.get(path) != ('100644', 'blob', FIXED_BLOBS[path]):
                errors.append('host.hook:' + path)
        elif owned(path):
            if actual.get(path, ())[:2] != ('100644', 'blob'):
                errors.append('owned.mode:' + path)
        elif actual.get(path) != base.get(path):
            errors.append('unowned:' + path)
    return errors


def write(name, value):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def mutate(source, path, mode='100644', data=b'changed\n'):
    """Add one blob to a private index and return the resulting tree id."""
    with tempfile.TemporaryDirectory() as temporary:
        env = dict(os.environ, GIT_INDEX_FILE=str(Path(temporary) / 'index'))
        git('read-tree', source, env=env)
        blob = git('hash-object', '-w', '--stdin', input=data).decode().strip()
        git('update-index', '--add', '--cacheinfo', mode + ',' + blob + ',' + path, env=env)
        return git('write-tree', env=env).decode().strip()


def preflight():
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only'
    source = git('rev-parse', 'HEAD').decode().strip()
    assert source == os.environ['GITHUB_SHA'], 'the pushed event source differs from HEAD'
    subprocess.run(['git', 'merge-base', '--is-ancestor', SEED, source], cwd=ROOT, check=True)
    errors = inspect(source)
    assert not errors, errors
    actual = tree(source)
    seeds = {package: git('rev-parse', SEED + ':apps/reader/' + package).decode().strip() for package in PACKAGES}
    for package, object_id in seeds.items():
        assert git('rev-parse', source + ':apps/reader/' + package).decode().strip() == object_id, package
    sdk = {path: git('rev-parse', source + ':' + path).decode().strip() for path in SDK_PATHS}
    for path in SDK_PATHS:
        expected = SDK_SOURCE if path in ('src', 'include', 'cmake', 'CMakeLists.txt',
                                         'CMakePresets.json', 'bindings', 'tests/fixtures') else SEED
        assert git('rev-parse', expected + ':' + path).decode().strip() == sdk[path], path
    judges = {path: git('rev-parse', source + ':' + path).decode().strip() for path in OLD_JUDGES}
    for path in OLD_JUDGES:
        assert git('rev-parse', SEED + ':' + path).decode().strip() == judges[path], path
    negative = []
    for name, path, mode in (
            ('sdk', 'include/exr/base.h', '100644'),
            ('package', 'apps/reader/jump-history/include/reader_jump_history.h', '100644'),
            ('raw', 'apps/reader/revisions/include/reader_revisions.h', '100644'),
            ('host', 'examples/reader.c', '100644'),
            ('default_cmake', 'CMakeLists.txt', '100644'),
            ('old_judge', 'tests/reader_next_s16/check_artifacts.py', '100644'),
            ('unknown', 'tests/reader_wave3_s18_extra/unapproved.py', '100644'),
            ('symlink', 'tests/reader_wave3_s18/guard.py', '120000')):
        refused = inspect(mutate(source, path, mode))
        assert refused, 'accepted an actual mutation: ' + name
        negative.append({'name': name, 'rejected': True, 'errors': refused})
    positive = inspect(mutate(source, 'docs/reader-wave3-s18/owned-addition.md'))
    assert positive == [], positive
    result = dict(source_sha=source, seed=SEED, run_id=os.environ['GITHUB_RUN_ID'],
                  attempt=os.environ['GITHUB_RUN_ATTEMPT'], guard_kind='reader-wave3-s18-joint-install',
                  seed_accepted=True, composition_accepted=True, runtime_accepted=False,
                  legacy_guards_executed=False, complete_product=False,
                  scope='shared default/raw install and unchanged original business replay only',
                  production_candidates={'sdk': SDK_SOURCE, 'frozen_sdk': FROZEN_SDK, 'legacy_start': LEGACY_START},
                  owned_files=sorted(OWN_FILES), owned_directories=list(OWN_DIRS),
                  module_trees=seeds, sdk_trees=sdk, original_judge_trees=judges,
                  errors=errors, negative_controls=negative,
                  positive_control={'name': 'owned_addition', 'accepted': True},
                  pending_gates=['product DSO and host adoption', 'delivery, PR, tag, Release and default branch'])
    write('source.json', result)
    print(json.dumps({key: result[key] for key in ('source_sha', 'seed', 'guard_kind', 'composition_accepted',
                                                  'runtime_accepted', 'legacy_guards_executed',
                                                  'complete_product')}), flush=True)


def _source_strict():
    sys.path.insert(0, str(ROOT / 'tools'))
    from check_parallel_integration import fetch, pages, download_artifact_zip
    from datetime import datetime, timezone
    source, run, attempt = (os.environ[key] for key in ('GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT'))
    metadata = fetch('actions/runs/' + run + '/attempts/' + attempt)
    assert metadata['head_sha'] == source and str(metadata['run_attempt']) == attempt
    assert metadata['path'].split('@')[0] == WORKFLOW, metadata['path']
    jobs = pages('actions/runs/' + run + '/attempts/' + attempt + '/jobs', 'jobs')
    producer, = [job for job in jobs if job['name'] == 'joint install preflight']
    assert producer['head_sha'] == source and str(producer['run_attempt']) == attempt
    assert producer['status'] == 'completed' and producer['conclusion'] == 'success'
    artifacts = pages('actions/runs/' + run + '/artifacts', 'artifacts')
    item, = [row for row in artifacts if row['name'] == 'reader-wave3-s18-source-' + run + '-' + attempt]
    assert item['expired'] is False and item['workflow_run']['head_sha'] == source
    assert str(item['workflow_run']['id']) == run
    assert datetime.fromisoformat(item['expires_at'].replace('Z', '+00:00')) > datetime.now(timezone.utc)
    raw = download_artifact_zip(item['id'])
    assert len(raw) == item['size_in_bytes'] and 'sha256:' + hashlib.sha256(raw).hexdigest() == item['digest']
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        assert archive.namelist() == ['source.json'], 'exact source receipt required'
        result = json.loads(archive.read('source.json'))
    assert (result['source_sha'], result['run_id'], result['attempt']) == (source, run, attempt)
    assert result['guard_kind'] == 'reader-wave3-s18-joint-install' and result['seed'] == SEED
    assert result['seed_accepted'] is True and result['composition_accepted'] is True
    assert result['runtime_accepted'] is False and result['legacy_guards_executed'] is False
    assert result['complete_product'] is False and result['errors'] == []
    assert {row['name'] for row in result['negative_controls']} == {
        'sdk', 'package', 'raw', 'host', 'default_cmake', 'old_judge', 'unknown', 'symlink'}
    assert len(result['negative_controls']) == 8 and all(row['rejected'] is True for row in result['negative_controls'])
    assert result['positive_control'] == {'name': 'owned_addition', 'accepted': True}
    assert set(result['module_trees']) == set(PACKAGES) and set(result['original_judge_trees']) == set(OLD_JUDGES)
    write('strict.json', dict(result, artifact={key: item[key] for key in
                                              ('id', 'name', 'size_in_bytes', 'digest', 'expires_at')}))
    print(json.dumps({'composition_accepted': True, 'runtime_accepted': False, 'source_sha': source}), flush=True)


if __name__ == '__main__':
    {'preflight': preflight, 'strict': _source_strict}[sys.argv[1]]()
