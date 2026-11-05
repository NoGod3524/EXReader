#!/usr/bin/env python3
"""Authenticate original Actions evidence without elevating its scope."""
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from check_parallel_integration import fetch, download_artifact_zip

def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    source, run, attempt = (os.environ[k] for k in ('GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT'))
    out = ROOT / 'build/apple-sdk342-record-summary'; out.mkdir(parents=True, exist_ok=True)
    summary = {'source_sha': source, 'run_id': run, 'attempt': attempt, 'accepted': False, 'failure': None}
    try:
        jobs = fetch(f'actions/runs/{run}/attempts/{attempt}/jobs?per_page=100')['jobs']
        producer = [j for j in jobs if j['name'] == 'Apple old-record test-only semantic proof']
        assert len(producer) == 1 and producer[0]['head_sha'] == source and producer[0]['conclusion'] == 'success'
        name = f'apple-sdk342-record-semantics-{run}-{attempt}'
        artifacts = [a for a in fetch(f'actions/runs/{run}/artifacts?per_page=100')['artifacts'] if a['name'] == name]
        assert len(artifacts) == 1
        artifact = artifacts[0]
        assert not artifact['expired'] and artifact['workflow_run']['head_sha'] == source
        raw = download_artifact_zip(artifact['id']); digest = hashlib.sha256(raw).hexdigest()
        assert len(raw) == artifact['size_in_bytes'] and artifact['digest'] == 'sha256:' + digest
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            names = archive.namelist()
            assert len(names) == len(set(names))
            assert all(not PurePosixPath(n).is_absolute() and '..' not in PurePosixPath(n).parts and '\\' not in n for n in names)
            result = json.loads(archive.read('result.json'))
            assert (result['source_sha'], result['run_id'], result['attempt'], result['accepted']) == (source, run, attempt, True)
            assert result['test_only_policy'] and not result['production_policy_changed']
            assert not result['duplicate_import_accepted'] and not result['android_real_sender_accepted'] and not result['physical_device']
            assert result['prefixed_inputs_are_protocol_fixtures'] and len(result['phases']) == 20
            for path, expected in result['files'].items():
                data = archive.read(path)
                assert len(data) == expected['bytes'] and hashlib.sha256(data).hexdigest() == expected['sha256']
            for phase in result['phases']:
                report = json.loads(archive.read(phase['report']))
                assert report['accepted'] and report['source_sha'] == source and str(report['run_id']) == run and str(report['attempt']) == attempt
                assert len(report['checks']) == (8 if phase['name'].endswith('-produce') else 9)
        summary.update(accepted=True, artifact_id=artifact['id'], zip_sha256=digest, scope='macOS test-only policy; 8 genuine old records per version, no duplicate import or Android device sender')
    except Exception as error:
        summary['failure'] = str(error)
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary), flush=True)
    assert summary['accepted'], 'Semantic proof authentication failed'

if __name__ == '__main__': main()
