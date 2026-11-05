#!/usr/bin/env python3
"""Authenticate original 3.42 theme native evidence in Actions."""
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from check_parallel_integration import fetch, download_artifact_zip

def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    source, run, attempt = (os.environ[k] for k in ('GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT'))
    out = ROOT / 'build/apple-sdk342-theme-summary'; out.mkdir(parents=True, exist_ok=True)
    result = {'source_sha': source, 'run_id': run, 'attempt': attempt, 'accepted': False, 'failure': None}
    try:
        name = f'apple-sdk342-theme-native-{run}-{attempt}'
        items = [a for a in fetch(f'actions/runs/{run}/artifacts?per_page=100')['artifacts'] if a['name'] == name]
        assert len(items) == 1
        item = items[0]
        assert not item['expired'] and item['workflow_run']['head_sha'] == source
        raw = download_artifact_zip(item['id']); digest = hashlib.sha256(raw).hexdigest()
        assert len(raw) == item['size_in_bytes'] and item['digest'] == 'sha256:' + digest
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            assert len(z.namelist()) == len(set(z.namelist()))
            value = json.loads(z.read('native/native.json'))
            proof = json.loads(z.read('provenance.json'))
            for entry in (value, proof):
                assert (entry['source_sha'], entry['run_id'], entry['attempt']) == (source, run, attempt)
            assert value['accepted'] and value['sdk_version'] == '3.42.0' and value['sdk_source'] == source
            assert proof['sdk_content_candidate'] == '8357eafa28423a7ab93ba08b823af80f01ad1505'
            assert value['original_on_off_exact'] and len(value['reports']['off']['checks']) == 10 and len(value['reports']['on']['checks']) == 37
            assert not proof['page_theme_ui_accepted'] and not proof['physical_device']
            assert hashlib.sha256(z.read('original-run-native.py')).hexdigest() == proof['original_sha256']
            assert hashlib.sha256(z.read('derived-run-native.py')).hexdigest() == proof['derived_sha256']
        result.update(accepted=True, artifact_id=item['id'], zip_sha256=digest)
    except Exception as error:
        result['failure'] = str(error)
    (out / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result), flush=True)
    assert result['accepted'], 'Native theme authentication failed'

if __name__ == '__main__': main()
