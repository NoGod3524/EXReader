# SPDX-License-Identifier: MIT
"""Download exact Actions ZIPs and check their digest, source and original files."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import time
import xml.etree.ElementTree as ET
import zipfile

API = 'repos/NoGod3524/EXReader/'


def check_model_tests(data, android_host=False):
    suite = ET.fromstring(data)
    expected = {'dfinal-c-annotation-exchange-model', 'dfinal-c-installed-sdk-version-guard'}
    if android_host:
        expected |= {'dfinal-c-product-catalog-upgrade', 'dfinal-c-android-abi-inspection'}
    cases = suite.findall('.//testcase')
    assert int(suite.attrib['tests']) == len(cases) == len(expected)
    assert {case.attrib['name'] for case in cases} == expected
    assert all(int(suite.attrib.get(key, 0)) == 0 for key in ('failures', 'errors', 'disabled', 'skipped'))
    assert all(case.attrib.get('status') == 'run' and
               not any(case.find(tag) is not None for tag in ('failure', 'error', 'skipped')) for case in cases)
    return sorted(expected)


def check_android_host(archive, name, source, run):
    report = json.loads(archive.read(name))
    assert report['source'] == source and report['run'] == str(run)
    assert report['target'] == 'android-arm64-v8a' and report['tier'] == 'debug-apk-build-only'
    assert report['host_deployed'] is False and report['physical_device_verified'] is False
    prefix = name.removesuffix('build.json')
    actual = {path.removeprefix(prefix + 'artifacts/') for path in archive.namelist()
              if path.startswith(prefix + 'artifacts/') and not path.endswith('/')}
    assert actual == set(report['files'])
    for path, digest in report['files'].items():
        assert hashlib.sha256(archive.read(prefix + 'artifacts/' + path)).hexdigest() == digest, path
    assert report['apk']['path'] == 'artifacts/app-debug.apk'
    apk = archive.read(prefix + report['apk']['path'])
    assert len(apk) == report['apk']['bytes'] and hashlib.sha256(apk).hexdigest() == report['apk']['sha256']
    required = {'lib/arm64-v8a/' + library for library in
                ('libexreader_product.so', 'libexreader.so', 'libexreader_jni.so', 'libexreader_host.so')}
    assert set(report['native']) == required
    with zipfile.ZipFile(io.BytesIO(apk)) as package:
        assert len(package.namelist()) == len(set(package.namelist()))
        assert {p for p in package.namelist() if p.startswith('lib/') and not p.endswith('/')} == required
        for path, entry in report['native'].items():
            data = package.read(path)
            assert data[:6] == b'\x7fELF\x02\x01' and int.from_bytes(data[18:20], 'little') == entry['machine'] == 183
            assert hashlib.sha256(data).hexdigest() == entry['sha256'], path
            assert re.fullmatch('[0-9a-f]+', entry['build_id']) and min(entry['load_alignments']) >= 16384
        for document in ('LICENSE', 'THIRD_PARTY_NOTICES.md', 'READER-INSTALL-UPGRADE-IMPORT-SYNC.md'):
            assert package.read('assets/' + document) == archive.read(prefix + 'artifacts/' + document)
        assert any(path.startswith('assets/licenses/') for path in package.namelist())
    signature = archive.read(prefix + 'artifacts/signature.txt').decode('utf-8')
    assert re.search(r'^Verifies\s*$', signature, re.M)
    certificate = re.search(r'^Signer #1 certificate SHA-256 digest: ([0-9a-fA-F]{64})\s*$', signature, re.M)
    assert certificate and re.search(r'^Verified using v[23].*: true\s*$', signature, re.M)
    badging = archive.read(prefix + 'artifacts/badging.txt').decode('utf-8')
    assert "native-code: 'arm64-v8a'" in badging and "sdkVersion:'26'" in badging
    return report, {'apk_sha256': report['apk']['sha256'], 'native_libraries_checked': len(required),
                    'apksigner_report_verified': True, 'signer_certificate_sha256': certificate[1],
                    'host_deployed': False, 'physical_device_verified': False}


def api(path):
    for attempt in range(3):
        try:
            return subprocess.check_output(['gh', 'api', API + path], timeout=120)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            if attempt == 2:
                raise
            time.sleep(attempt + 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True, type=int)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--android-host', action='store_true', help='Require the four-job SDK/model/arm64 APK follow-up')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    run = json.loads(api(f'actions/runs/{args.run}'))
    jobs = json.loads(api(f'actions/runs/{args.run}/jobs'))
    artifacts = json.loads(api(f'actions/runs/{args.run}/artifacts'))
    for name, data in [('run', run), ('jobs', jobs), ('artifacts', artifacts)]:
        (args.output / (name + '.json')).write_text(json.dumps(data, indent=2), encoding='utf-8')
    assert run['status'] == 'completed' and run['conclusion'] == 'success', run['conclusion']
    expected_count = 4 if args.android_host else 3
    assert len(jobs['jobs']) == expected_count and all(j['conclusion'] == 'success' for j in jobs['jobs'])
    assert len(artifacts['artifacts']) == expected_count
    expected_names = {'dfinal-c-' + target + '-' + run['head_sha'] for target in
                      ('models', 'android-arm64-v8a', 'iphoneos-arm64')}
    if args.android_host:
        expected_names.add('dfinal-c-android-arm64-host-' + run['head_sha'])
    assert {a['name'] for a in artifacts['artifacts']} == expected_names
    rows = []
    for artifact in artifacts['artifacts']:
        assert not artifact['expired'] and artifact['workflow_run']['head_sha'] == run['head_sha']
        assert artifact['workflow_run']['id'] == args.run
        blob = api(f"actions/artifacts/{artifact['id']}/zip")
        digest = hashlib.sha256(blob).hexdigest()
        assert artifact['digest'] == 'sha256:' + digest and len(blob) == artifact['size_in_bytes']
        (args.output / (str(artifact['id']) + '.zip')).write_bytes(blob)
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            assert len(archive.namelist()) == len(set(archive.namelist()))
            details = {}
            manifests = [n for n in archive.namelist() if n.endswith('mobile-evidence/manifest.json')]
            hosts = [n for n in archive.namelist() if n == 'build.json' or n.endswith('/build.json')]
            if manifests:
                assert len(manifests) == 1
                manifest = json.loads(archive.read(manifests[0]))
                assert manifest['source'] == run['head_sha'] and manifest['run'] == str(args.run)
                assert manifest['target'] in ('android-arm64-v8a', 'iphoneos-arm64')
                assert artifact['name'] == 'dfinal-c-' + manifest['target'] + '-' + run['head_sha']
                assert manifest['tier'] == 'sdk-build-only' and manifest['physical_device_verified'] is False
                assert manifest['host_deployed'] is False
                prefix = manifests[0].removesuffix('mobile-evidence/manifest.json') + 'mobile-stage/'
                for name, expected in manifest['files'].items():
                    assert hashlib.sha256(archive.read(prefix + name)).hexdigest() == expected, name
                count = len(manifest['files'])
                (args.output / (manifest['target'] + '-manifest.json')).write_text(json.dumps(manifest, indent=2), encoding='utf-8')
                if args.android_host:
                    licenses = json.loads(archive.read(manifests[0].removesuffix('manifest.json') + 'licenses.json'))
                    assert licenses['source_sha'] == run['head_sha'] and licenses['ci']['GITHUB_RUN_ID'] == str(args.run)
                    assert licenses['materials_check_passed'] is True and not licenses['failures']
                    assert licenses['release_ready'] == (not licenses['failures'] and not licenses['mandatory_missing'])
                    details['licenses'] = {key: licenses[key] for key in ('materials_check_passed', 'pending', 'release_ready')}
                    (args.output / (manifest['target'] + '-licenses.json')).write_text(json.dumps(licenses, indent=2), encoding='utf-8')
            elif hosts:
                assert args.android_host and len(hosts) == 1
                assert artifact['name'] == 'dfinal-c-android-arm64-host-' + run['head_sha']
                host, details = check_android_host(archive, hosts[0], run['head_sha'], args.run)
                count = len(host['files']) + len(host['native'])
                (args.output / 'android-arm64-host-build.json').write_text(json.dumps(host, indent=2), encoding='utf-8')
            else:
                assert artifact['name'] == 'dfinal-c-models-' + run['head_sha']
                names = [n for n in archive.namelist() if n.endswith('/results/result.json')]
                assert len(names) == 1
                result = json.loads(archive.read(names[0]))
                assert result['passed'] and not result['failed'] and result['source'] == run['head_sha']
                assert result['actions'] is True and result['host_ui_verified'] is False and result['physical_device_verified'] is False
                assert result['count'] == len(result['checks'])
                xml = [n for n in archive.namelist() if n == 'model-tests.xml' or n.endswith('/model-tests.xml')]
                assert len(xml) == 1
                details['model_tests_passed'] = check_model_tests(archive.read(xml[0]), args.android_host)
                (args.output / 'model-tests.xml').write_bytes(archive.read(xml[0]))
                count = result['count']
                (args.output / 'model-result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
            rows.append({'id': artifact['id'], 'name': artifact['name'], 'bytes': len(blob),
                         'zip_sha256': digest, 'checked_files_or_model_assertions': count, **details})
    result = {'run': args.run, 'source': run['head_sha'], 'jobs_passed': expected_count, 'artifacts': rows, 'passed': True}
    (args.output / 'verified.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
