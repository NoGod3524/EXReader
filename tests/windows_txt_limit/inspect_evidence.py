"""Inspect an authenticated retained performance artifact without rerunning it."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import zipfile
import io

repo = os.environ['GITHUB_REPOSITORY']
run_id = '40399315487'
artifact_id = 12688856368
expected_digest = '7d4b5189a6fabdda7f03a1a8fadb8aed0bff806dc11a4555a3f7d20f5838b008'

def api(path):
    return json.loads(subprocess.check_output(['gh', 'api', f'repos/{repo}/{path}']))

run = api('actions/runs/' + run_id)
artifact = api('actions/artifacts/' + str(artifact_id))
assert run['head_sha'] == '7aab6e559d17e730067594ee7da5189bf00f6dd8'
assert artifact['workflow_run']['id'] == int(run_id)
assert artifact['workflow_run']['head_sha'] == run['head_sha']
raw = subprocess.check_output(['gh', 'api', f'repos/{repo}/actions/artifacts/{artifact_id}/zip'])
assert len(raw) == artifact['size_in_bytes']
assert hashlib.sha256(raw).hexdigest() == expected_digest
assert artifact['digest'] == 'sha256:' + expected_digest
with zipfile.ZipFile(io.BytesIO(raw)) as archive:
    def read(suffix):
        names = [name for name in archive.namelist() if name.endswith(suffix)]
        assert len(names) == 1, (suffix, names)
        return json.loads(archive.read(names[0]))
    summary = read('full-perf-windows/summary.json')
    identity = read('full-perf-windows/full-package-identity.json')
    assert summary['source_sha'] == run['head_sha']
    assert str(summary['run_id']) == run_id
    assert str(summary['attempt']) == str(run['run_attempt'])
    result = {'run_id': run_id, 'attempt': run['run_attempt'], 'source_sha': run['head_sha'],
              'artifact_id': artifact_id, 'artifact_sha256': expected_digest,
              'package_identity': identity, 'txt_path': summary['txt_path']}
    out = Path('build/windows-txt-evidence.json')
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    def find_peaks(value, path='txt_path'):
        if isinstance(value, dict):
            for key, item in value.items():
                if 'peak' in key.lower() or 'memory' in key.lower():
                    print(json.dumps({'path': path + '.' + key, 'value': item}, ensure_ascii=False))
                else:
                    find_peaks(item, path + '.' + key)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                find_peaks(item, path + '[' + str(index) + ']')
    print('PACKAGE ' + json.dumps(identity, ensure_ascii=False))
    find_peaks(summary['txt_path'])
