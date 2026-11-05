"""Exact successful producer pin and same-run Actions evidence authentication."""
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import zipfile

SOURCE = '5ac5e1fa4cf6dcbfe81ea14b9f64b6288470164a'
RUN = 40217963443
ATTEMPT = 1
WORKFLOW = '.github/workflows/reader-apple-raw3-ios-ready.yml'
JOBS = {
    'Installed SDK and exact raw products iphonesimulator': 121243123378,
    'Installed SDK and exact raw products macos': 121243123534,
    'Actual raw iOS UI ipad': 121243863572,
    'Actual raw iOS UI iphone': 121243863628,
    'summary': 121249802254,
}
ARTIFACTS = {
    'iphone': dict(id=12608976777, name='apple-raw3-ios-iphone-40217963443-1',
                   size_in_bytes=152515213, digest='sha256:06cf2e467ce225e927b32f36dccf7febe93fc15bc60fc0d5450cfc56b068f49f'),
    'ipad': dict(id=12608483488, name='apple-raw3-ios-ipad-40217963443-1',
                 size_in_bytes=186145203, digest='sha256:2a37546c8d0bbcb8f171e6f2292bb3d2a94fa24e2ea07d4dcdd12ffe07fd7ead'),
}


def require(value, message):
    if not value:
        raise ValueError(message)


def implementation(sha, branch=None):
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only')
    require(sha == os.environ['GITHUB_SHA'], 'implementation source differs from Actions')
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    require(head == sha, 'implementation checkout differs')
    return dict(sha=sha, branch=branch or os.environ['GITHUB_REF_NAME'],
                run_id=os.environ['GITHUB_RUN_ID'], attempt=os.environ['GITHUB_RUN_ATTEMPT'])


def same_implementation(value, expected):
    require(all(str(value.get(key)) == str(expected[key]) for key in ('sha', 'run_id', 'attempt')),
            'foreign implementation source/run/attempt')


def api(path):
    proc = subprocess.run(['gh', 'api', path], capture_output=True, text=True)
    require(proc.returncode == 0, 'GitHub metadata request failed: ' + path)
    return json.loads(proc.stdout)


def metadata(meta, source, run):
    require(meta.get('size_in_bytes', 0) > 0 and not meta.get('expired'), 'missing/expired artifact')
    require(meta.get('workflow_run', {}).get('id') == int(run) and
            meta.get('workflow_run', {}).get('head_sha') == source, 'artifact source/run differs')
    require(datetime.fromisoformat(meta['expires_at'].replace('Z', '+00:00')) > datetime.now(timezone.utc),
            'artifact expiry is not in the future')


def archive_bytes(repository, meta, source, run):
    metadata(meta, source, run)
    proc = subprocess.run(['gh', 'api', 'repos/%s/actions/artifacts/%s/zip' % (repository, meta['id'])],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    require(proc.returncode == 0, 'artifact download failed')
    raw = proc.stdout
    validate_download(meta, raw)
    inspect_zip(raw)
    return raw


def validate_download(meta, raw):
    require(len(raw) == meta['size_in_bytes'] and
            'sha256:' + hashlib.sha256(raw).hexdigest() == meta['digest'], 'artifact ZIP bytes/digest differ')


def inspect_zip(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = archive.namelist()
        require(0 < len(names) <= 100000 and len(names) == len(set(names)), 'duplicate/oversized ZIP member set')
        total = 0
        for item in archive.infolist():
            path = PurePosixPath(item.filename)
            require(not path.is_absolute() and '..' not in path.parts and '\\' not in item.filename and
                    ':' not in item.filename, 'unsafe ZIP path')
            mode = item.external_attr >> 16
            require((mode & 0o170000) in (0, 0o100000, 0o040000),
                    'ZIP links/special files require an authoritative safe transport, refused before extraction')
            total += item.file_size
            require(item.file_size <= 512 * 1024**2 and total <= 2 * 1024**3, 'ZIP extracted bytes exceed bound')


def producer_jobs(repository):
    prefix = 'repos/%s/actions/runs/%s/attempts/%s' % (repository, RUN, ATTEMPT)
    run = api(prefix)
    require((run['id'], run['head_sha'], run['run_attempt'], run['path'], run['status'], run['conclusion']) ==
            (RUN, SOURCE, ATTEMPT, WORKFLOW, 'completed', 'success'), 'designated producer attempt did not pass')
    listing = api(prefix + '/jobs?per_page=100')
    jobs = listing['jobs']
    require(listing['total_count'] == len(jobs) == len(JOBS), 'producer job set incomplete/duplicated')
    require({row['name']: row['id'] for row in jobs} == JOBS, 'producer exact job identity differs')
    require(all(row['status'] == 'completed' and row['conclusion'] == 'success' and
                row['head_sha'] == SOURCE and row['run_attempt'] == ATTEMPT for row in jobs),
            'producer job source/attempt/status differs')
    return run, jobs


def unique(rows, message):
    require(len(rows) == 1, message)
    return rows[0]
