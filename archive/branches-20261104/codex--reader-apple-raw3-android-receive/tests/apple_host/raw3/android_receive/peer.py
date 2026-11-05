"""Authenticate the real Android sender packet and actual APK/shared SDK proofs."""
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import sys
import zipfile
from android_bundle import verify

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'tools'))
from check_parallel_integration import fetch, download_artifact_zip
SOURCE = '4a04a9cc74dde67f755c87e87b278d63a254a3ac'
RUN, ATTEMPT = 40207467982, 1
APK_SHA = '860927a89eb7ab2e6ffcd93d596e7206a830f15d396be0e0135bf82bedb0b5f3'
SDK_SHA = 'a345ab4c1def2e864a76b9e879da8a372e8821ad09b7991c8fe4e04626b2e8ac'
MANIFEST_SHA = '65a7c6e2be7a0d80e1a7c9eed3731383aa9bdbc71cfd09f89ce63861193b5345'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def archive(identity, name, size, digest):
    meta = fetch('actions/artifacts/' + str(identity))
    assert meta['name'] == name and meta['size_in_bytes'] == size and meta['digest'] == 'sha256:' + digest
    assert not meta['expired'] and meta['workflow_run']['head_sha'] == SOURCE and meta['workflow_run']['id'] == RUN
    assert datetime.fromisoformat(meta['expires_at'].replace('Z', '+00:00')) > datetime.now(timezone.utc)
    data = download_artifact_zip(identity)
    assert len(data) == size and sha(data) == digest
    result = zipfile.ZipFile(io.BytesIO(data))
    assert len(result.namelist()) == len(set(result.namelist()))
    for name in result.namelist():
        path = PurePosixPath(name)
        assert not path.is_absolute() and '..' not in path.parts and '\\' not in name and ':' not in name
        assert not name.endswith('.key')
    return meta, result


def load(directory):
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    record = fetch(f'actions/runs/{RUN}/attempts/{ATTEMPT}')
    assert record['head_sha'] == SOURCE and record['conclusion'] == 'success' and record['run_attempt'] == 1
    jobs = fetch(f'actions/runs/{RUN}/attempts/{ATTEMPT}/jobs?per_page=100')['jobs']
    assert {job['id'] for job in jobs if job['conclusion'] == 'success'} == {121211376063, 121211375764, 121216568574}
    assert all(job['head_sha'] == SOURCE for job in jobs)
    packet_meta, packet = archive(12604233206, 'reader-android-raw3-bundle-40207467982-1', 18682,
                                  'a38bffdb57ca35699e21b902def18a9d584a6055b7fbef41995e61b240c6168c')
    directory.mkdir(parents=True, exist_ok=False)
    bundle = directory / 'bundle'; bundle.mkdir()
    with packet:
        verified = verify(packet.read); manifest = verified['manifest']
        assert (verified['revisions'], verified['originals'], verified['reading_records']) == (19, 4, 11)
        assert verified['manifest_sha256'] == MANIFEST_SHA
        sender = manifest['sender']
        assert (sender['source_sha'], sender['run_id'], sender['attempt'], sender['platform']) == (SOURCE, str(RUN), '1', 'android')
        assert sender['raw_selector_candidate'] and sender['apk_sha256'] == APK_SHA and sender['sdk_dso_sha256'] == SDK_SHA
        assert sender['parser_version'] == 'exreader-sdk-3.41.0'
        for name in verified['files']:
            target = bundle / name; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(packet.read(name))
    native_meta, native = archive(12604412854, 'reader-android-raw3-40207467982-1', 113970957,
                                  'c3db2ad1a2e31bc53d01620f2ef90e02a976e3b4f90ac76ed2e179c7c9052805')
    def read(suffix):
        matches = [name for name in native.namelist() if name == suffix or name.endswith('/' + suffix)]
        assert len(matches) == 1, (suffix, matches)
        return native.read(matches[0])
    proofs = directory / 'proofs'; proofs.mkdir()
    with native:
        ui = json.loads(read('ui/result.json')); compiled = json.loads(read('native/result.json')); guard = json.loads(read('guard.json'))
        for value in (ui, compiled):
            assert value['accepted'] and (value['source_sha'], value['run_id'], value['attempt']) == (SOURCE, str(RUN), '1')
        assert ui['api'] == 34 and ui['abi'] == 'x86_64' and ui['incoming_apple_status'] == 'passed' and ui['authentic_apple_null_status'] == 'passed'
        assert not ui['physical_device'] and not ui['complete_product'] and not ui['bidirectional_interoperability_accepted']
        assert guard['accepted'] and guard['sdk_boundaries_unchanged'] and guard['seven_modules_unchanged'] and guard['legacy_suites_unchanged']
        assert len(compiled['archives']) == 7 and compiled['single_shared_sdk'] and compiled['one_product_sqlite']
        assert compiled['legacy_anchor_max_version'] == 2 and not compiled['default_enabled']
        apk = read('apks/host-debug.apk'); assert sha(apk) == APK_SHA
        with zipfile.ZipFile(io.BytesIO(apk)) as package:
            sdk = package.read('lib/x86_64/libexreader.so'); assert sha(sdk) == SDK_SHA
        (proofs / 'host-debug.apk').write_bytes(apk); (proofs / 'libexreader.so').write_bytes(sdk)
        for name, value in (('native.json', compiled), ('ui.json', ui), ('guard.json', guard)):
            (proofs / name).write_text(json.dumps(value, indent=2) + '\n')
    attestation = {'source_sha': SOURCE, 'run_id': RUN, 'attempt': ATTEMPT, 'manifest_sha256': MANIFEST_SHA,
                   'sender_zip': {key: packet_meta[key] for key in ('id', 'name', 'size_in_bytes', 'digest', 'expires_at')},
                   'native_zip': {key: native_meta[key] for key in ('id', 'name', 'size_in_bytes', 'digest', 'expires_at')},
                   'apk_sha256': APK_SHA, 'sdk_dso_sha256': SDK_SHA, 'revisions': 19, 'originals': 4, 'reading_records': 11,
                   'verified_actual_APK_and_SDK': True, 'complete_original_graph': True}
    (directory / 'attestation.json').write_text(json.dumps(attestation, indent=2) + '\n')
    print(json.dumps(attestation), flush=True)
    return attestation, manifest, bundle
