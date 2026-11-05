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
                if artifact['name'].startswith('team24-apple-sdk-'):
                    target = next((t for t in ('macos', 'iphonesimulator') if artifact['name'] == f'team24-apple-sdk-{t}-{run}-{attempt}'), None)
                    assert target is not None
                    identity = json.loads(archive.read('wave3-packages.json'))
                    assert (identity['source_sha'], identity['run_id'], identity['attempt'], identity['target']) == (source, run, attempt, target)
                    assert identity['sdk_build_source'] == source
                    assert identity['sdk_content_candidate'] == '5b7a34ee4f1ce38cf3bcd7cf0220575f4ecf7da9'
                    assert identity['sdk_content_paths'] == ['src', 'include', 'cmake', 'CMakeLists.txt', 'bindings']
                    assert identity['modules'] == ['annotation-export', 'annotation-import', 'font-library', 'original-export', 'jump-history', 'sync-status-view']
                    guard = json.loads(archive.read('team24-apple-guard.json'))
                    assert (guard['source_sha'], guard['run_id'], guard['attempt'], guard['accepted']) == ('937f61057b06c5c9de3b562046e52c91b5be62b9', run, attempt, True)
                    assert any(n.startswith('sdk/') and not n.endswith('/') for n in archive.namelist())
                    assert any(n.startswith('raw-products/') and not n.endswith('/') for n in archive.namelist())
                    entry['package_identity'] = identity
                if artifact['name'].startswith('team24-apple-native-'):
                    result = json.loads(archive.read('result.json'))
                    assert (result['source_sha'], result['run_id'], result['attempt']) == (source, run, attempt)
                    expected_phases = {'wave3': 5, 'base': 13, 'control': 13, 'search': 4, 'theme': 4}
                    phases = result['phases']
                    if result['accepted']:
                        assert len(phases) == len(expected_phases)
                        assert {phase['mode']: phase['expected_cases'] for phase in phases} == expected_phases
                        for phase in phases:
                            assert phase['accepted'] and len(phase['cases']) == expected_phases[phase['mode']]
                            assert all(case['result'] == 'Passed' for case in phase['cases'])
                            manifest = archive.read(phase['mode'] + '-resource-manifest.json')
                            assert hashlib.sha256(manifest).hexdigest() == phase['resource_manifest_sha256']
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
