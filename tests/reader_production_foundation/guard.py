"""Actions-only provenance for the reviewed optional-package composition."""
import hashlib
from functools import lru_cache
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
ORIGIN = '1a6d98ed613c61ffea4267f01f83e2c49b1c02f6'
REVIEWED = 'b8fcb233155957ea25ff1d39be7554b21142378f'
MANIFEST = 'docs/reader-production-foundation/snapshot-manifest.json'
WORKFLOW = '.github/workflows/reader-production-foundation.yml'
OWN = {WORKFLOW, 'tests/reader_production_foundation/guard.py'}
OUT = ROOT / 'build/reader-production-foundation'


def git(*args, **kwargs):
    return subprocess.check_output(['git', *args], cwd=ROOT, **kwargs)


@lru_cache(maxsize=32)
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
    actual, reviewed = tree(source), tree(REVIEWED)
    errors = []
    for path in sorted(set(actual) | set(reviewed)):
        if path in OWN:
            if actual.get(path, ())[:2] != ('100644', 'blob'):
                errors.append('owned.mode:' + path)
        elif actual.get(path) != reviewed.get(path):
            errors.append('unreviewed:' + path)
    if set(actual) - set(reviewed) != OWN:
        errors.append('owned.exact_set')
    plan = json.loads(git('show', REVIEWED + ':' + MANIFEST))
    baseline = tree(ORIGIN)
    if plan['production_origin'] != ORIGIN or plan['current_base'] != ORIGIN:
        errors.append('origin.identity')
    for path, blob in plan['protected_base_trees'].items():
        if subset(actual, path) != subset(baseline, path) or git('rev-parse', ORIGIN + ':' + path).decode().strip() != blob:
            errors.append('protected:' + path)
    for path in ('src', 'include', 'cmake', 'CMakeLists.txt', 'CMakePresets.json', 'bindings',
                 'tests/fixtures', '.github/workflows/native.yml', '.github/workflows/reliability.yml'):
        if subset(actual, path) != subset(tree(plan['sdk_source']), path):
            errors.append('sdk:' + path)
    for package in plan['packages']:
        fixed = tree(package['snapshot_source'])
        for path in package['paths']:
            if not subset(actual, path) or subset(actual, path) != subset(fixed, path):
                errors.append('package:' + package['id'] + ':' + path)
        for path, blob in package['module_trees'].items():
            if git('rev-parse', source + ':' + path).decode().strip() != blob:
                errors.append('module.tree:' + package['id'])
    return errors


def write(name, value):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def preflight():
    source = git('rev-parse', 'HEAD').decode().strip()
    assert source == os.environ['GITHUB_SHA'], 'actual event source differs'
    subprocess.run(['git', 'merge-base', '--is-ancestor', ORIGIN, source], cwd=ROOT, check=True)
    errors = inspect(source)
    assert not errors, errors
    negative = []
    for name, path, mode in (
            ('sdk', 'include/exr/base.h', '100644'),
            ('raw', 'apps/reader/revisions/include/reader_revisions.h', '100644'),
            ('host', 'examples/reader.c', '100644'),
            ('default', 'CMakeLists.txt', '100644'),
            ('package', 'apps/reader/jump-history/include/reader_jump_history.h', '100644'),
            ('old_judge', 'tests/reader_next_s16/check_artifacts.py', '100644'),
            ('unknown', 'tests/reader_production_foundation/unapproved.py', '100644'),
            ('symlink', 'tests/reader_production_foundation/guard.py', '120000')):
        with tempfile.TemporaryDirectory() as temporary:
            env = dict(os.environ, GIT_INDEX_FILE=str(Path(temporary) / 'index'))
            git('read-tree', source, env=env)
            blob = git('hash-object', '-w', '--stdin', input=b'changed\n').decode().strip()
            git('update-index', '--add', '--cacheinfo', mode + ',' + blob + ',' + path, env=env)
            changed = git('write-tree', env=env).decode().strip()
            refused = inspect(changed)
            assert refused, 'accepted actual mutation: ' + name
            negative.append({'name': name, 'rejected': True, 'errors': refused})
    result = dict(source_sha=source, run_id=os.environ['GITHUB_RUN_ID'], attempt=os.environ['GITHUB_RUN_ATTEMPT'],
                  guard_kind='production-foundation', composition_accepted=True, runtime_accepted=False,
                  legacy_guards_executed=False, complete_product=False, errors=errors,
                  production_origin=ORIGIN, reviewed_payload=REVIEWED, negative_controls=negative)
    write('source.json', result)
    print(json.dumps(result), flush=True)


def strict():
    sys.path.insert(0, str(ROOT / 'tools'))
    from check_parallel_integration import fetch, pages, download_artifact_zip
    source, run, attempt = (os.environ[key] for key in ('GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT'))
    metadata = fetch('actions/runs/' + run + '/attempts/' + attempt)
    assert metadata['head_sha'] == source and str(metadata['run_attempt']) == attempt
    assert metadata['path'].split('@')[0] == WORKFLOW
    jobs = pages('actions/runs/' + run + '/attempts/' + attempt + '/jobs', 'jobs')
    producer, = [job for job in jobs if job['name'] == 'composition preflight']
    assert producer['head_sha'] == source and str(producer['run_attempt']) == attempt
    assert producer['status'] == 'completed' and producer['conclusion'] == 'success'
    artifacts = pages('actions/runs/' + run + '/artifacts', 'artifacts')
    item, = [row for row in artifacts if row['name'] == 'production-foundation-source-' + run + '-' + attempt]
    from datetime import datetime, timezone
    assert item['expired'] is False and item['workflow_run']['head_sha'] == source and str(item['workflow_run']['id']) == run
    assert datetime.fromisoformat(item['expires_at'].replace('Z', '+00:00')) > datetime.now(timezone.utc)
    raw = download_artifact_zip(item['id'])
    assert len(raw) == item['size_in_bytes'] and 'sha256:' + hashlib.sha256(raw).hexdigest() == item['digest']
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        assert archive.namelist() == ['source.json'], 'exact source receipt required'
        result = json.loads(archive.read('source.json'))
    assert result['source_sha'] == source and result['run_id'] == run and result['attempt'] == attempt
    assert result['guard_kind'] == 'production-foundation' and result['composition_accepted'] is True
    assert result['runtime_accepted'] is False and result['legacy_guards_executed'] is False
    assert result['complete_product'] is False
    assert result['reviewed_payload'] == REVIEWED and result['production_origin'] == ORIGIN and result['errors'] == []
    assert {row['name'] for row in result['negative_controls']} == {'sdk','raw','host','default','package','old_judge','unknown','symlink'}
    assert len(result['negative_controls']) == 8 and all(row['rejected'] is True for row in result['negative_controls'])
    write('strict.json', dict(result, artifact={key: item[key] for key in ('id','name','size_in_bytes','digest','expires_at')}))
    print(json.dumps({'composition_accepted': True, 'runtime_accepted': False, 'source_sha': source}), flush=True)


if __name__ == '__main__':
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only'
    {'preflight': preflight, 'strict': strict}[sys.argv[1]]()
