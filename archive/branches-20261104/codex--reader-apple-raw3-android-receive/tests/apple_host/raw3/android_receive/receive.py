"""Run the unchanged actual Mac owner/AccountSession with the authenticated Android packet."""
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import uuid
import zipfile
from peer import load as load_peer

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'tools'))
from check_parallel_integration import fetch, download_artifact_zip
sys.path.insert(0, str(ROOT / 'tests/apple_host/raw3'))
from tls_fixture import Fixture


def sha(data):
    return hashlib.sha256(data).hexdigest()


def original_artifact(prefix):
    source, run, attempt = (os.environ[key] for key in ('GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT'))
    rows = fetch('actions/runs/' + run + '/artifacts?per_page=100')['artifacts']
    matches = [row for row in rows if row['name'] == prefix + '-' + run + '-' + attempt]; assert len(matches) == 1
    meta = matches[0]
    assert not meta['expired'] and meta['workflow_run']['head_sha'] == source and meta['workflow_run']['id'] == int(run)
    assert datetime.fromisoformat(meta['expires_at'].replace('Z', '+00:00')) > datetime.now(timezone.utc)
    raw = download_artifact_zip(meta['id'])
    assert len(raw) == meta['size_in_bytes'] and 'sha256:' + sha(raw) == meta['digest']
    archive = zipfile.ZipFile(io.BytesIO(raw)); assert len(archive.namelist()) == len(set(archive.namelist()))
    for name in archive.namelist():
        path = PurePosixPath(name); assert not path.is_absolute() and '..' not in path.parts and '\\' not in name and ':' not in name
    return meta, archive


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true' and sys.platform == 'darwin'
    source, run, attempt = (os.environ[key] for key in ('GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT'))
    jobs = fetch(f'actions/runs/{run}/attempts/{attempt}/jobs?per_page=100')['jobs']
    for name in ('Actual macOS raw host and original controls', 'Original unchanged macOS strict summary'):
        matches = [row for row in jobs if row['name'] == name]
        assert len(matches) == 1 and matches[0]['head_sha'] == source and matches[0]['conclusion'] == 'success'
    out = ROOT / 'build/apple-android-raw3-receive'
    evidence = out / 'evidence'; evidence.mkdir(parents=True, exist_ok=False)
    meta, archive = original_artifact('apple-raw3-native')
    with archive:
        native = json.loads(archive.read('result.json'))
        assert native['accepted'] and (native['source_sha'], native['run_id'], native['attempt']) == (source, run, attempt)
        assert native['original_compatibility_phases'] == 18 and native['original_owner_cases_per_sdk'] == 19 and native['java_policy_cases'] == 20
        for name, entry in native['files'].items():
            data = archive.read(name); assert len(data) == entry['bytes'] and sha(data) == entry['sha256']
            if name.startswith(('actual-raw-host', 'inputs/')) or name in ('sender-bundle/manifest.json', 'sender-bundle/proofs/sdk.dylib'):
                target = evidence / 'original-native' / name
                target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(data)
        (evidence / 'original-native/result.json').write_bytes(archive.read('result.json'))
    original_summary_meta, archive = original_artifact('apple-raw3-summary')
    with archive:
        old_summary = json.loads(archive.read('summary.json'))
        assert old_summary['accepted'] and (old_summary['source_sha'], old_summary['run_id'], old_summary['attempt']) == (source, run, attempt)
        assert old_summary['artifact']['id'] == meta['id'] and old_summary['actual_android_interop_accepted'] is False
        (evidence / 'original-native/strict-summary.json').write_bytes(archive.read('summary.json'))
    program = evidence / 'original-native/actual-raw-host'; program.chmod(0o755)
    provider = native['provider']; assert provider['selector_bytes_candidate'] and not provider['static_sdk_linked'] and not provider['reading_resolver_linked']
    assert sha(program.read_bytes()) == provider['binary_sha256'] == native['program_sha256']['raw']
    original_manifest = json.loads((evidence / 'original-native/sender-bundle/manifest.json').read_bytes())
    dso = (evidence / 'original-native/sender-bundle/proofs/sdk.dylib').read_bytes()
    assert sha(dso) == original_manifest['sender']['sdk_dso_sha256']
    # Relocate the same authenticated installed runtime. The old program's
    # own SDK-image observer still rejects missing or multiple loaded providers.
    runtime = ROOT / 'build/apple-record-compatibility/sdk-new/lib'; runtime.mkdir(parents=True, exist_ok=True)
    names = {original_manifest['sender']['sdk_dso_basename']}
    dependencies = subprocess.check_output(['otool', '-L', program], text=True)
    for line in dependencies.splitlines()[1:]:
        name = line.strip().split(' ', 1)[0].rsplit('/', 1)[-1]
        if re.fullmatch(r'libexreader(?:\.[0-9]+)*\.dylib', name): names.add(name)
    assert names and all(re.fullmatch(r'libexreader(?:\.[0-9]+)*\.dylib', name) for name in names)
    for name in names: (runtime / name).write_bytes(dso)
    env = dict(os.environ, DYLD_LIBRARY_PATH=str(runtime))
    attestation, manifest, bundle = load_peer(evidence / 'android-peer')
    resources = evidence / 'original-native/inputs'
    phases = []

    def phase(mode, name, profile, extra=None):
        log = evidence / (name + '.log'); report = evidence / (name + '.json')
        print('ACTUAL_ANDROID_TO_MAC_PHASE ' + name, flush=True)
        with log.open('wb') as stream:
            process = subprocess.Popen([program, mode, resources, profile, bundle, report], cwd=ROOT,
                                       env=dict(env, **(extra or {})), stdout=stream, stderr=subprocess.STDOUT)
            try: code = process.wait(timeout=600)
            except subprocess.TimeoutExpired: process.kill(); process.wait(); raise
        if code:
            print('\n'.join(log.read_text(errors='replace').splitlines()[-100:]), flush=True)
            raise RuntimeError('Actual unchanged Mac receiver failed: ' + name)
        value = json.loads(report.read_bytes())
        assert value['accepted'] and value['pid'] == process.pid and value['mode'] == mode
        assert (value['source_sha'], value['run_id'], value['attempt']) == (source, run, attempt)
        assert value['program_sha256'] == native['program_sha256']['raw'] and value['sdk_dso_sha256'] == sha(dso)
        assert value['exr_version'] == '3.41.0'
        assert len(value['records']) == 11 and all(row['found'] for row in value['records'])
        expected = {row['revision_id']: next(item['sha256'] for item in manifest['revisions'] if item['id'] == row['revision_id']) for row in manifest['reading_records']}
        assert {row['revision_id']: row['wire_sha256'] for row in value['records']} == expected
        if mode.startswith('session-'):
            assert value['actual_native_session']['actual_host_account_session']
            assert value['actual_native_session']['completed_shards'] == 256 and value['actual_native_session']['completed_sweeps'] == 1
        phases.append({'name': name, 'mode': mode, 'pid': process.pid, 'report': report.name, 'found': 11})
        print(json.dumps({'phase': name, 'pid': process.pid, 'found': 11}), flush=True)

    profiles = evidence / 'profiles'; profiles.mkdir()
    phase('receive', 'actual-owner-receive', profiles / 'independent-owner')
    phase('receive', 'actual-owner-reopen', profiles / 'independent-owner')
    fixture = Fixture(ROOT / 'build/apple-android-raw3-private')
    try:
        fixture.directories.update({'/dav/exreader-sync-v1/', '/dav/exreader-sync-v1/revisions/', '/dav/exreader-sync-v1/objects/'})
        for value in range(256): fixture.directories.add('/dav/exreader-sync-v1/revisions/%02x/' % value)
        for row in manifest['originals']:
            path = '/dav/exreader-sync-v1/objects/' + row['sha256'][:2] + '/'
            fixture.directories.add(path)
            fixture.entries[path + row['sha256'] + '.' + row['format']] = (bundle / row['file']).read_bytes()
        for row in manifest['revisions']:
            fixture.entries['/dav/exreader-sync-v1/revisions/' + row['id'][:2] + '/' + row['id'] + '-' + row['sha256'] + '.json'] = (bundle / row['file']).read_bytes()
        remote_before = {key: sha(value) for key, value in fixture.entries.items()}
        network = {'EXR_RAW_DAV_ROOT': fixture.url, 'EXR_RAW_ACCOUNT': str(uuid.uuid4()), 'EXR_RAW_AUTH': fixture.auth}
        phase('session-receive', 'actual-native-HTTPS-receive', profiles / 'actual-account-receiver', network)
        phase('session-reopen', 'actual-native-HTTPS-reopen', profiles / 'actual-account-receiver', network)
        assert remote_before == {key: sha(value) for key, value in fixture.entries.items()}
        assert fixture.requests and all(row['authenticated'] for row in fixture.requests)
        shards = {row['path'].split('/')[-2] for row in fixture.requests if row['method'] == 'PROPFIND' and '/revisions/' in row['path']}
        assert shards == {'%02x' % value for value in range(256)}
        (evidence / 'native-https.json').write_text(json.dumps({'requests': fixture.requests, 'authenticated': True,
            'tls_trust_checked': True, 'actual_host_account_session': True, 'inbound_shards': len(shards),
            'original_remote_bytes_unchanged': True, 'remote_sha256': remote_before}, indent=2) + '\n')
        for path in evidence.rglob('*'):
            if path.is_file(): assert fixture.auth.encode() not in path.read_bytes()
    finally:
        fixture.close()
    assert len({value['pid'] for value in phases}) == 4
    result = {'accepted': True, 'source_sha': source, 'run_id': run, 'attempt': attempt,
              'scope': 'authenticated Android raw3 packet received by actual macOS owners and native HTTPS account session only',
              'android_to_macos_receive_accepted': True, 'same_source_bidirectional_accepted': False,
              'physical_device_execution': False, 'ios_ui_accepted': False, 'complete_product': False,
              'original_native_artifact': {key: meta[key] for key in ('id', 'name', 'size_in_bytes', 'digest', 'expires_at')},
              'original_strict_artifact': {key: original_summary_meta[key] for key in ('id', 'name', 'size_in_bytes', 'digest', 'expires_at')},
              'original_mac_judge_unchanged': True, 'original_mac_controls_passed_in_same_run': True,
              'program_sha256': native['program_sha256']['raw'], 'sdk_dso_sha256': sha(dso), 'runtime_names': sorted(names),
              'provider': provider, 'peer': attestation, 'revisions': 19, 'originals': 4, 'reading_records': 11, 'phases': phases}
    result['files'] = {path.relative_to(evidence).as_posix(): {'bytes': path.stat().st_size, 'sha256': sha(path.read_bytes())}
                       for path in evidence.rglob('*') if path.is_file()}
    (evidence / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({key: value for key, value in result.items() if key not in ('files', 'provider')}), flush=True)


if __name__ == '__main__':
    main()
