"""Actions-only: download one original artifact ZIP of this run/attempt and authenticate it."""
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import zipfile

assert os.environ.get('GITHUB_ACTIONS') == 'true'
IDENTITY = {key: os.environ[name] for key, name in (('source_sha', 'GITHUB_SHA'), ('run_id', 'GITHUB_RUN_ID'), ('attempt', 'GITHUB_RUN_ATTEMPT'))}
REPO = 'repos/' + os.environ['GITHUB_REPOSITORY'] + '/'


def api(path):
    return json.loads(subprocess.check_output(['gh', 'api', REPO + path]))


def artifacts():
    """Every artifact of the current run (all pages); attempt is encoded in the name."""
    rows, page = [], 1
    while True:
        batch = api('actions/runs/' + IDENTITY['run_id'] + '/artifacts?per_page=100&page=' + str(page))['artifacts']
        rows += batch
        if len(batch) < 100:
            return rows
        page += 1


def metadata(name):
    full = name + '-' + IDENTITY['run_id'] + '-' + IDENTITY['attempt']
    found = [row for row in artifacts() if row['name'] == full]
    assert len(found) == 1, (full, [row['name'] for row in artifacts()])
    row = found[0]
    assert not row['expired'] and row['workflow_run']['head_sha'] == IDENTITY['source_sha'] and row['workflow_run']['id'] == int(IDENTITY['run_id'])
    assert datetime.fromisoformat(row['expires_at'].replace('Z', '+00:00')) > datetime.now(timezone.utc)
    return row


def download(name, destination=None, limit=1024 ** 3):
    """Return (identity, ZipFile bytes). Extraction into *destination* rejects unsafe paths."""
    row = metadata(name)
    raw = subprocess.check_output(['gh', 'api', REPO + 'actions/artifacts/' + str(row['id']) + '/zip'], timeout=1500)
    assert len(raw) == row['size_in_bytes'] and 'sha256:' + hashlib.sha256(raw).hexdigest() == row['digest']
    identity = {key: row[key] for key in ('id', 'name', 'size_in_bytes', 'digest', 'expires_at')}
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = archive.namelist()
        assert len(names) == len(set(names)) and sum(info.file_size for info in archive.infolist()) < limit
        for info in archive.infolist():
            path = PurePosixPath(info.filename)
            assert not path.is_absolute() and '..' not in path.parts and '\\' not in info.filename and ':' not in info.filename
            assert (info.external_attr >> 16) & 0o170000 != 0o120000 and not info.filename.endswith('.key')
        if destination is not None:
            destination = Path(destination)
            destination.mkdir(parents=True, exist_ok=True)
            archive.extractall(destination)
    return identity, raw


if __name__ == '__main__':
    import sys
    identity, _ = download(sys.argv[1], sys.argv[2])
    print(json.dumps(identity), flush=True)
