#!/usr/bin/env python3
"""Authenticate and report the original full-host TXT diagnosis, in Actions."""
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import zipfile
repo = os.environ['GITHUB_REPOSITORY']
run_id, artifact_id = 40399315487, 12688856368
api = lambda path: json.loads(subprocess.check_output(['gh', 'api', f'repos/{repo}/{path}']))
run = api(f'actions/runs/{run_id}')
artifact = api(f'actions/artifacts/{artifact_id}')
assert run['head_sha'] == '7aab6e559d17e730067594ee7da5189bf00f6dd8' and run['run_attempt'] == 1
assert artifact['workflow_run']['id'] == run_id and artifact['workflow_run']['head_sha'] == run['head_sha'] and not artifact['expired']
raw = subprocess.check_output(['gh', 'api', f'repos/{repo}/actions/artifacts/{artifact_id}/zip'])
assert len(raw) == artifact['size_in_bytes'] and 'sha256:' + hashlib.sha256(raw).hexdigest() == artifact['digest']
with zipfile.ZipFile(io.BytesIO(raw)) as archive:
    names = [name for name in archive.namelist() if name.endswith('full-perf-txt/diagnosis.json')]
    assert len(names) == 1, names
    diagnosis = json.loads(archive.read(names[0]))
    data = []
    for entry in diagnosis['runs']:
        facts = entry['facts']; imp = facts['import']; catalog = facts['catalog']
        data.append({'run': entry['run'], 'verdict': entry['verdict'],
                     'native_dialog': imp.get('native_dialog'), 'completed': imp['completed'],
                     'timed_out': imp['timed_out'], 'elapsed_ms': imp['elapsed_ms'],
                     'status_after_import': imp['status_after_import'], 'catalog': catalog,
                     'probes': {k: {'count': v['count'], 'timed_out': v['timed_out']} for k, v in facts['probes'].items()},
                     'refresh': facts.get('refresh'), 'open': facts.get('open')})
    bisect = [{'declared_mib': x['declared_mib'], 'bytes': x['bytes'], 'lines': x.get('lines'),
               'completed': x.get('completed'), 'status_after_import': x.get('status_after_import'),
               'status_indicates_failure': x.get('status_indicates_failure'), 'catalog': x.get('catalog')}
              for x in diagnosis['bisect']['imports']]
    result = {'source_sha': run['head_sha'], 'producer_run': run_id, 'attempt': run['run_attempt'],
              'artifact_id': artifact_id, 'artifact_digest': artifact['digest'], 'input': diagnosis['input'],
              'verdict': diagnosis['verdict'], 'runs': data, 'bisect': bisect,
              'performance_accepted': False, 'txt_import_accepted': False}
    out = Path('build/txt-inspect'); out.mkdir(parents=True, exist_ok=True)
    (out / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False))
