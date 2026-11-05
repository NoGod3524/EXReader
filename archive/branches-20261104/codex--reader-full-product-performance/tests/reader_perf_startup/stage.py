#!/usr/bin/env python3
"""Extract authenticated existing full Windows package and 2202-book seed in Actions."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import zipfile

repo = os.environ['GITHUB_REPOSITORY']
run = 40397287811
artifact_id = 12687463168
source = '77a54227a78b0160e98609032e7ceef87fb29d00'
api = lambda suffix: json.loads(subprocess.check_output(['gh', 'api', f'repos/{repo}/{suffix}']))
run_info = api(f'actions/runs/{run}')
item = api(f'actions/artifacts/{artifact_id}')
assert run_info['head_sha'] == source and run_info['run_attempt'] == 1 and run_info['conclusion'] == 'success'
assert item['workflow_run']['id'] == run and item['workflow_run']['head_sha'] == source and not item['expired']
raw = subprocess.check_output(['gh', 'api', f'repos/{repo}/actions/artifacts/{artifact_id}/zip'])
assert len(raw) == item['size_in_bytes'] and 'sha256:' + hashlib.sha256(raw).hexdigest() == item['digest']
out = Path('build/startup-stage'); out.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(__import__('io').BytesIO(raw)) as archive:
    def member(suffix):
        names = [name for name in archive.namelist() if name.endswith(suffix)]
        assert len(names) == 1, (suffix, names)
        return archive.read(names[0])
    identity = json.loads(member('full-perf-windows/full-package-identity.json'))
    seed = member('full-perf-txt-work/template/library.sqlite')
    payload = member('EXReader-wave3-windows.zip')
    assert identity['source_sha'] == source and str(identity['run_id']) == str(run)
    assert hashlib.sha256(payload).hexdigest() == identity['zip_sha256']
    (out / 'seed.sqlite').write_bytes(seed)
    with zipfile.ZipFile(__import__('io').BytesIO(payload)) as product:
        for info in product.infolist():
            p = Path(info.filename)
            assert not p.is_absolute() and '..' not in p.parts and ':' not in info.filename and '\\' not in info.filename
        product.extractall(out / 'package')
    exe = out / 'package/EXReader/EXReader.exe'
    assert hashlib.sha256(exe.read_bytes()).hexdigest() == identity['program_sha256']
    record = {'producer_source': source, 'producer_run': run, 'producer_attempt': 1,
              'artifact_id': artifact_id, 'artifact_sha256': item['digest'],
              'program_sha256': identity['program_sha256'], 'package_sha256': identity['zip_sha256'],
              'seed_sha256': hashlib.sha256(seed).hexdigest(), 'seed_bytes': len(seed)}
    (out / 'source.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record))
