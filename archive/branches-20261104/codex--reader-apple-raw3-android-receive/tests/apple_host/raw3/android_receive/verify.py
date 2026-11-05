"""Close the authenticated Android sender, unchanged Mac judges, and actual receiver evidence."""
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import sys
import zipfile
from android_bundle import verify as verify_bundle
from peer import SOURCE as ANDROID, APK_SHA, SDK_SHA, MANIFEST_SHA

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'tools'))
from check_parallel_integration import fetch, download_artifact_zip


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    source, run, attempt = (os.environ[name] for name in ('GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT'))
    jobs = fetch(f'actions/runs/{run}/attempts/{attempt}/jobs?per_page=100')['jobs']
    wanted = {'Actual macOS raw host and original controls', 'Original unchanged macOS strict summary',
              'Actual authenticated Android to macOS receive'}
    producers = [row for row in jobs if row['name'] in wanted]
    assert len(producers) == 3 and {row['name'] for row in producers} == wanted
    assert all(row['conclusion'] == 'success' and row['head_sha'] == source for row in producers)
    artifacts = fetch(f'actions/runs/{run}/artifacts?per_page=100')['artifacts']
    selected = [row for row in artifacts if row['name'] == f'apple-raw3-android-receive-{run}-{attempt}']; assert len(selected) == 1
    meta = selected[0]
    assert not meta['expired'] and meta['workflow_run']['head_sha'] == source and meta['workflow_run']['id'] == int(run)
    assert datetime.fromisoformat(meta['expires_at'].replace('Z', '+00:00')) > datetime.now(timezone.utc)
    raw = download_artifact_zip(meta['id'])
    assert len(raw) == meta['size_in_bytes'] and 'sha256:' + hashlib.sha256(raw).hexdigest() == meta['digest']
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        assert len(archive.namelist()) == len(set(archive.namelist()))
        for name in archive.namelist():
            path = PurePosixPath(name); assert not path.is_absolute() and '..' not in path.parts and '\\' not in name and ':' not in name and not name.endswith('.key')
        result = json.loads(archive.read('result.json'))
        assert result['accepted'] and (result['source_sha'], result['run_id'], result['attempt']) == (source, run, attempt)
        assert result['android_to_macos_receive_accepted'] and result['original_mac_controls_passed_in_same_run'] and result['original_mac_judge_unchanged']
        for flag in ('same_source_bidirectional_accepted', 'physical_device_execution', 'ios_ui_accepted', 'complete_product'):
            assert result[flag] is False
        for name, entry in result['files'].items():
            data = archive.read(name)
            assert len(data) == entry['bytes'] and hashlib.sha256(data).hexdigest() == entry['sha256']
        old = json.loads(archive.read('original-native/result.json'))
        assert old['accepted'] and (old['source_sha'], old['run_id'], old['attempt']) == (source, run, attempt)
        assert old['original_compatibility_phases'] == 18 and old['original_owner_cases_per_sdk'] == 19 and old['java_policy_cases'] == 20
        assert len(old['phases']) == 12 and old['actual_android_interop_accepted'] is False
        for declared in (result['original_native_artifact'], result['original_strict_artifact']):
            original = next(row for row in artifacts if row['id'] == declared['id'])
            assert all(original[key] == declared[key] for key in ('name', 'size_in_bytes', 'digest', 'expires_at')) and not original['expired']
            assert original['workflow_run']['head_sha'] == source and original['workflow_run']['id'] == int(run)
        old_summary = json.loads(archive.read('original-native/strict-summary.json'))
        assert old_summary['accepted'] and old_summary['artifact']['id'] == result['original_native_artifact']['id']
        assert old_summary['actual_android_interop_accepted'] is False
        packet = verify_bundle(lambda name: archive.read('android-peer/bundle/' + name))
        assert packet['manifest_sha256'] == MANIFEST_SHA and (packet['revisions'], packet['originals'], packet['reading_records']) == (19, 4, 11)
        manifest = packet['manifest']; sender = manifest['sender']; peer = result['peer']
        assert (sender['source_sha'], sender['run_id'], sender['attempt']) == (ANDROID, '40207467982', '1')
        assert peer['source_sha'] == ANDROID and peer['manifest_sha256'] == MANIFEST_SHA and peer['verified_actual_APK_and_SDK']
        assert sender['apk_sha256'] == peer['apk_sha256'] == APK_SHA and sender['sdk_dso_sha256'] == peer['sdk_dso_sha256'] == SDK_SHA
        apk = archive.read('android-peer/proofs/host-debug.apk'); assert hashlib.sha256(apk).hexdigest() == APK_SHA
        with zipfile.ZipFile(io.BytesIO(apk)) as package:
            assert hashlib.sha256(package.read('lib/x86_64/libexreader.so')).hexdigest() == SDK_SHA
        assert hashlib.sha256(archive.read('android-peer/proofs/libexreader.so')).hexdigest() == SDK_SHA
        peer_run = fetch('actions/runs/40207467982/attempts/1')
        assert peer_run['head_sha'] == ANDROID and peer_run['conclusion'] == 'success'
        for declared in (peer['sender_zip'], peer['native_zip']):
            original = fetch('actions/artifacts/' + str(declared['id']))
            assert not original['expired'] and original['workflow_run']['head_sha'] == ANDROID and original['workflow_run']['id'] == 40207467982
            assert all(original[key] == declared[key] for key in ('name', 'size_in_bytes', 'digest', 'expires_at'))
        assert hashlib.sha256(archive.read('original-native/actual-raw-host')).hexdigest() == result['program_sha256'] == result['provider']['binary_sha256']
        assert hashlib.sha256(archive.read('original-native/sender-bundle/proofs/sdk.dylib')).hexdigest() == result['sdk_dso_sha256']
        assert result['provider']['selector_bytes_candidate'] and not result['provider']['static_sdk_linked'] and not result['provider']['reading_resolver_linked']
        expected = {'actual-owner-receive', 'actual-owner-reopen', 'actual-native-HTTPS-receive', 'actual-native-HTTPS-reopen'}
        assert len(result['phases']) == 4 and {row['name'] for row in result['phases']} == expected
        assert len({row['pid'] for row in result['phases']}) == 4
        wires = {row['id']: row['sha256'] for row in manifest['revisions']}
        selected_ids = {row['revision_id'] for row in manifest['reading_records']}
        for phase in result['phases']:
            report = json.loads(archive.read(phase['report']))
            assert report['accepted'] and report['pid'] == phase['pid'] and report['mode'] == phase['mode']
            assert (report['source_sha'], report['run_id'], report['attempt']) == (source, run, attempt)
            assert report['program_sha256'] == result['program_sha256'] and report['sdk_dso_sha256'] == result['sdk_dso_sha256']
            assert len(report['records']) == 11 and all(row['found'] for row in report['records'])
            assert {row['revision_id'] for row in report['records']} == selected_ids
            assert all(row['wire_sha256'] == wires[row['revision_id']] for row in report['records'])
            if phase['mode'].startswith('session-'):
                assert report['actual_native_session']['actual_host_account_session']
                assert report['actual_native_session']['completed_shards'] == 256 and report['actual_native_session']['completed_sweeps'] == 1
        https = json.loads(archive.read('native-https.json'))
        assert https['actual_host_account_session'] and https['tls_trust_checked'] and https['authenticated']
        assert https['inbound_shards'] == 256 and https['original_remote_bytes_unchanged'] and all(row['authenticated'] for row in https['requests'])
    summary = {'accepted': True, 'source_sha': source, 'run_id': run, 'attempt': attempt,
               'android_to_macos_receive_accepted': True, 'same_source_bidirectional_accepted': False,
               'physical_device_execution': False, 'ios_ui_accepted': False, 'complete_product': False,
               'original_mac_controls': 'same-run complete unchanged native and strict judges passed',
               'peer': peer, 'artifact': {key: meta[key] for key in ('id', 'name', 'size_in_bytes', 'digest', 'expires_at')},
               'program_sha256': result['program_sha256'], 'sdk_dso_sha256': result['sdk_dso_sha256'],
               'revisions': 19, 'originals': 4, 'reading_records': 11, 'actual_receiver_processes': 4}
    out = ROOT / 'build/apple-android-raw3-summary'; out.mkdir(parents=True, exist_ok=True)
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary), flush=True)


if __name__ == '__main__':
    main()
