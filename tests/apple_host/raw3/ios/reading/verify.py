"""Strict original-ZIP identity and actual two-simulator mobile evidence."""
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / 'tools'))
from check_parallel_integration import fetch, download_artifact_zip
from validate import validate_observations


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    source, run, attempt = (os.environ[name] for name in ('GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT'))
    jobs = fetch(f'actions/runs/{run}/attempts/{attempt}/jobs?per_page=100')['jobs']
    producers = {row['name']: row for row in jobs if row['name'].startswith(('Actual raw iOS UI ', 'Installed SDK and exact raw products '))}
    names = {'Actual raw iOS UI iphone', 'Actual raw iOS UI ipad',
             'Installed SDK and exact raw products macos', 'Installed SDK and exact raw products iphonesimulator'}
    assert set(producers) == names and all(row['head_sha'] == source and row['conclusion'] == 'success' for row in producers.values())
    artifacts = fetch('actions/runs/' + run + '/artifacts?per_page=100')['artifacts']
    out = ROOT / 'build/raw3-ios-summary'; out.mkdir(parents=True, exist_ok=True)
    accepted = []
    for platform in ('iphone', 'ipad'):
        selected = [row for row in artifacts if row['name'] == f'apple-raw3-ios-{platform}-{run}-{attempt}']
        assert len(selected) == 1
        artifact = selected[0]
        assert not artifact['expired'] and artifact['workflow_run']['head_sha'] == source and artifact['workflow_run']['id'] == int(run)
        assert datetime.fromisoformat(artifact['expires_at'].replace('Z', '+00:00')) > datetime.now(timezone.utc)
        raw = download_artifact_zip(artifact['id'])
        assert len(raw) == artifact['size_in_bytes'] and 'sha256:' + hashlib.sha256(raw).hexdigest() == artifact['digest']
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            assert len(archive.namelist()) == len(set(archive.namelist()))
            for name in archive.namelist():
                path = PurePosixPath(name)
                assert not path.is_absolute() and '..' not in path.parts and '\\' not in name and ':' not in name
                assert not name.endswith(('.key', '.p12'))
            result = json.loads(archive.read('result.json'))
            assert result['accepted'] and (result['source_sha'], result['run_id'], result['attempt'], result['platform']) == (source, run, attempt, platform)
            for flag in ('physical_device_execution', 'complete_product', 'android_interop_accepted', 'full_mobile_sync_accepted', 'performance_accepted'):
                assert result[flag] is False
            for name, entry in result['files'].items():
                data = archive.read(name)
                assert len(data) == entry['bytes'] and hashlib.sha256(data).hexdigest() == entry['sha256']
            control = json.loads(archive.read('original-control/reading-ui.json'))
            assert control['accepted'] and len(control['cases']) == 7 and all(row['result'] == 'Passed' for row in control['cases'])
            assert (control['source_sha'], control['run_id'], control['attempt'], control['platform']) == (source, run, attempt, platform)
            expected = {'original-OFF-seven-cases', 'raw-ui', 'raw-kill-before', 'raw-kill-after',
                        'raw-native-HTTPS', 'legacy-v1-failure', 'raw-retries-original-v1'}
            assert len(result['phases']) == len(expected) and {phase['name'] for phase in result['phases']} == expected
            for phase in result['phases']:
                assert all(row['result'] == 'Passed' for row in phase['cases'])
                assert len(phase['cases']) == (7 if phase['mode'] == 'control' else 1)
                assert phase['provider']['selector_bytes_candidate'] == (phase['mode'] == 'raw')
                assert not phase['provider']['static_sdk_linked'] and not phase['provider']['reading_resolver_linked']
                binary = archive.read('program-' + phase['mode'] + '/EXReaderHost.app/EXReaderHost')
                assert hashlib.sha256(binary).hexdigest() == phase['app_sha256'] == phase['provider']['binary_sha256']
            for target, proof in result['sdk_proofs'].items():
                assert proof['raw']['target'] == target and proof['raw']['source_sha'] == source
            https = json.loads(archive.read('native-https.json'))
            assert https['tls_trust_checked'] and https['simulator_trust_only'] and https['anonymous_account']
            assert https['inbound_shards'] == 256 and all(row['authenticated'] for row in https['requests'])
            peer = result['peer']
            assert peer['source_sha'] == '15dab6b2270dc296ed6239db67ced2e22d255e65' and peer['run_id'] == 40196978163
            assert peer['attempt'] == 1 and peer['artifact_id'] == 12600789926 and len(peer['null_revision_ids']) == 1
            extracted = out / platform
            archive.extractall(extracted)
        check = validate_observations(extracted, peer)
        assert check == result['observations']
        for path in extracted.glob('profile-*/**/raw3-review/*.json'):
            observation = json.loads(path.read_bytes())
            assert observation['source_sha'] == source
        accepted.append({'platform': platform, 'job_id': producers['Actual raw iOS UI ' + platform]['id'],
                         'artifact': {key: artifact[key] for key in ('id', 'name', 'size_in_bytes', 'digest', 'expires_at')},
                         'observations': check, 'peer': peer})
    summary = {'accepted': True, 'source_sha': source, 'run_id': run, 'attempt': attempt, 'platforms': accepted,
               'scope': 'actual iPhone/iPad simulator raw record UI and retained NULL native HTTPS inbound only',
               'default_raw_enabled': False, 'sdk_anchor_max_default': 2, 'schema': 1, 'wire_envelope': 1,
               'physical_device_execution': False, 'complete_product': False, 'android_interop_accepted': False,
               'full_mobile_sync_accepted': False, 'performance_accepted': False}
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary), flush=True)


if __name__ == '__main__':
    main()
