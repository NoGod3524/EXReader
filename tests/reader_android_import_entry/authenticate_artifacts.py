"""Actions-only exact-attempt producer/ZIP authentication before summary consumes any reports."""
import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import stat
import subprocess
import zipfile

assert os.environ.get('GITHUB_ACTIONS') == 'true'
p = argparse.ArgumentParser()
p.add_argument('--output', type=Path, required=True)
p.add_argument('--evidence', type=Path, required=True)
a = p.parse_args()
source, run, attempt = (os.environ[name] for name in ('GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT'))
repo = 'repos/' + os.environ['GITHUB_REPOSITORY'] + '/'

def api(path):
    return json.loads(subprocess.check_output(['gh', 'api', repo + path]))

identity = api('actions/runs/' + run)
assert identity['head_sha'] == source and identity['run_attempt'] == int(attempt)
jobs = api('actions/runs/' + run + '/attempts/' + attempt + '/jobs?per_page=100')['jobs']
artifacts = api('actions/runs/' + run + '/artifacts?per_page=100')['artifacts']
verified = []
for role in ('guards', 'android'):
    producers = [job for job in jobs if job['name'] == role]
    assert len(producers) == 1 and producers[0]['head_sha'] == source and producers[0]['status'] == 'completed' and producers[0]['conclusion'] == 'success'
    name = 'reader-android-import-entry-' + role + '-' + run + '-' + attempt
    matches = [row for row in artifacts if row['name'] == name]
    assert len(matches) == 1
    metadata = matches[0]
    assert metadata['workflow_run']['id'] == int(run) and metadata['workflow_run']['head_sha'] == source
    assert not metadata['expired'] and 0 < metadata['size_in_bytes'] <= 512 * 1024**2
    assert datetime.fromisoformat(metadata['expires_at'].replace('Z', '+00:00')) > datetime.now(timezone.utc)
    raw = subprocess.check_output(['gh', 'api', repo + 'actions/artifacts/' + str(metadata['id']) + '/zip'])
    assert len(raw) == metadata['size_in_bytes'] and 'sha256:' + hashlib.sha256(raw).hexdigest() == metadata['digest']
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        infos = archive.infolist()
        assert len(infos) <= 30000 and len(infos) == len({row.filename for row in infos}) and sum(row.file_size for row in infos) <= 1024**3
        for row in infos:
            path = PurePosixPath(row.filename)
            assert not path.is_absolute() and '..' not in path.parts and '\\' not in row.filename and ':' not in row.filename and not stat.S_ISLNK(row.external_attr >> 16)
        archive.extractall(a.output / role)
    verified.append({**{key: metadata[key] for key in ('id', 'name', 'size_in_bytes', 'digest', 'expires_at')}, 'producer_job': producers[0]['id']})
report = {'source_sha': source, 'run_id': run, 'attempt': attempt, 'authenticated': True, 'artifacts': verified}
a.evidence.parent.mkdir(parents=True, exist_ok=True)
a.evidence.write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report), flush=True)
