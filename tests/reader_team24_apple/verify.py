# SPDX-License-Identifier: MIT
"""Authenticate original ZIP bytes inside Actions, including failed producers."""
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import sys
import zipfile
from datetime import datetime, timezone
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from check_parallel_integration import fetch, download_artifact_zip

def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    source, run, attempt = (os.environ[k] for k in ('GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT'))
    out = ROOT / 'build/team24-apple-summary'; out.mkdir(parents=True, exist_ok=True)
    summary = {'source_sha': source, 'run_id': run, 'attempt': attempt, 'accepted': False, 'artifacts': [], 'failures': []}
    try:
        jobs = fetch(f'actions/runs/{run}/attempts/{attempt}/jobs?per_page=100')['jobs']
        expected = {'Team24 Apple installed macos', 'Team24 Apple installed iphonesimulator', 'Team24 Apple native macos', 'Team24 Apple native iphone', 'Team24 Apple native ipad'}
        producers = [x for x in jobs if x['name'] in expected]
        summary['jobs'] = [{k: row[k] for k in ('id', 'name', 'head_sha', 'status', 'conclusion')} for row in producers]
        if len(producers) != len(expected): summary['failures'].append('producer job set incomplete')
        for row in producers:
            if row['head_sha'] != source or row['conclusion'] != 'success': summary['failures'].append(row['name'] + ': ' + str(row['conclusion']))
        artifacts = fetch(f'actions/runs/{run}/artifacts?per_page=100')['artifacts']
        for artifact in artifacts:
            if not artifact['name'].startswith(('team24-apple-sdk-', 'team24-apple-native-')) or not artifact['name'].endswith(f'-{run}-{attempt}'): continue
            entry = {k: artifact[k] for k in ('id', 'name', 'size_in_bytes', 'digest', 'expires_at')}
            summary['artifacts'].append(entry)
            assert not artifact['expired'] and artifact['workflow_run']['head_sha'] == source
            assert datetime.fromisoformat(artifact['expires_at'].replace('Z', '+00:00')) > datetime.now(timezone.utc)
            raw = download_artifact_zip(artifact['id']); entry['original_zip_bytes'] = len(raw); entry['original_zip_sha256'] = hashlib.sha256(raw).hexdigest()
            assert len(raw) == artifact['size_in_bytes'] and 'sha256:' + entry['original_zip_sha256'] == artifact['digest']
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                assert len(archive.namelist()) == len(set(archive.namelist()))
                assert all(not PurePosixPath(n).is_absolute() and '..' not in PurePosixPath(n).parts and '\\' not in n for n in archive.namelist())
                if artifact['name'].startswith('team24-apple-native-'):
                    result = json.loads(archive.read('result.json'))
                    assert (result['source_sha'], result['run_id'], result['attempt']) == (source, run, attempt)
                    for name, item in result['files'].items():
                        data = archive.read(name); assert len(data) == item['bytes'] and hashlib.sha256(data).hexdigest() == item['sha256']
                    entry['scoped_accepted'] = result['accepted']; entry['phases'] = result['phases']; entry['gaps'] = result['gaps']
                    if not result['accepted']: summary['failures'].append(artifact['name'] + ': scoped UI not accepted')
        if len(summary['artifacts']) != 5: summary['failures'].append('artifact set incomplete')
        summary['accepted'] = not summary['failures']
    except Exception as error: summary['failures'].append(str(error))
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary), flush=True)
    assert summary['accepted'], 'Team24 Apple retained failure or acceptance gap'
if __name__ == '__main__': main()
