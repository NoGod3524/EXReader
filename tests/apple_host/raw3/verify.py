"""Authenticate actual producer, original artifact bytes and complete host phases."""
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))
from check_parallel_integration import fetch, download_artifact_zip
sys.path.insert(0, str(ROOT / 'tests/apple_host/record_compatibility'))
from verify import validate as original_validate


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    source, run, attempt = (os.environ[key] for key in ('GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT'))
    jobs = fetch('actions/runs/' + run + '/attempts/' + attempt + '/jobs?per_page=100')['jobs']
    producer = [job for job in jobs if job['name'] == 'Actual macOS raw host and original controls']
    assert len(producer) == 1 and producer[0]['conclusion'] == 'success' and producer[0]['head_sha'] == source
    artifacts = fetch('actions/runs/' + run + '/artifacts?per_page=100')['artifacts']
    assert len(artifacts) == 1
    artifact = artifacts[0]
    assert artifact['name'] == 'apple-raw3-native-' + run + '-' + attempt and not artifact['expired']
    assert artifact['workflow_run']['head_sha'] == source and artifact['workflow_run']['id'] == int(run)
    assert datetime.fromisoformat(artifact['expires_at'].replace('Z', '+00:00')) > datetime.now(timezone.utc)
    raw = download_artifact_zip(artifact['id'])
    assert len(raw) == artifact['size_in_bytes'] and 'sha256:' + hashlib.sha256(raw).hexdigest() == artifact['digest']
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        assert len(archive.namelist()) == len(set(archive.namelist()))
        for name in archive.namelist():
            path = PurePosixPath(name)
            assert not path.is_absolute() and '..' not in path.parts and '\\' not in name and ':' not in name and not name.endswith('.key')
        result = json.loads(archive.read('result.json'))
        assert (result['source_sha'], result['run_id'], result['attempt']) == (source, run, attempt)
        assert result['accepted'] and result['real_reading_records'] == 11 and result['originals'] == 4
        assert result['actual_android_interop_accepted'] is False and result['physical_device_execution'] is False and result['complete_product'] is False
        for name, entry in result['files'].items():
            data = archive.read(name)
            assert len(data) == entry['bytes'] and hashlib.sha256(data).hexdigest() == entry['sha256']
        original = json.loads(archive.read('original-compatibility/result.json'))
        original_validate(original, lambda name: archive.read('original-compatibility/' + name), source, run, attempt)
        expected = {'legacy-replay-refusal', 'send', 'receive', 'independent-owner-reopen', 'operations',
                    'kill-before', 'replay-before', 'kill-after', 'replay-after', 'session-push', 'session-receive', 'session-reopen'}
        assert len(result['phases']) == len(expected) and {row['name'] for row in result['phases']} == expected
        for phase in result['phases']:
            if phase['name'].startswith('kill-'):
                assert phase['exit'] == -9
                continue
            report = json.loads(archive.read(phase['report']))
            assert report['accepted'] and report['pid'] == phase['pid'] and report['source_sha'] == source
            assert str(report['run_id']) == run and str(report['attempt']) == attempt
            if phase['name'].startswith('session-'):
                assert report['actual_native_session']['actual_host_account_session']
                assert report['actual_native_session']['completed_shards'] == 256 and report['actual_native_session']['completed_sweeps'] == 1
        provider = result['provider']
        assert provider['selector_bytes_candidate'] and not provider['static_sdk_linked']
        assert hashlib.sha256(archive.read('actual-raw-host')).hexdigest() == provider['binary_sha256'] == result['program_sha256']['raw']
        manifest = json.loads(archive.read('sender-bundle/manifest.json'))
        assert manifest['sender']['source_sha'] == source and manifest['sender']['run_id'] == run and manifest['sender']['attempt'] == attempt
        assert manifest['sender']['program_sha256'] == result['program_sha256']['raw']
        assert len(manifest['reading_records']) == 11 and len(manifest['originals']) == 4
        ids = {row['id'] for row in manifest['revisions']}
        for row in manifest['revisions']:
            data = archive.read('sender-bundle/' + row['file'])
            assert len(data) == row['bytes'] and hashlib.sha256(data).hexdigest() == row['sha256'] and set(row['parents']) <= ids
            assert json.loads(data)['version'] == 1
        http = json.loads(archive.read('native-https.json'))
        assert http['actual_host_session'] and http['tls_trust_checked'] and http['requests'] and all(row['authenticated'] for row in http['requests'])
    result = {'accepted': True, 'source_sha': source, 'run_id': run, 'attempt': attempt,
              'scope': 'actual macOS raw sender and independent owner/native HTTPS Session only',
              'artifact': {key: artifact[key] for key in ('id', 'name', 'size_in_bytes', 'digest', 'expires_at')},
              'actual_android_interop_accepted': False, 'physical_device_execution': False, 'complete_product': False}
    out = ROOT / 'build/apple-raw3-summary'; out.mkdir(parents=True, exist_ok=True)
    (out / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
