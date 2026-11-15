# SPDX-License-Identifier: MIT
"""Download exact Actions ZIPs and check their digest, source and original files."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import time
import zipfile
import xml.etree.ElementTree as ET
from build_android_host import elf_check

API = 'repos/NoGod3524/EXReader/'


def unique_member(archive, suffix):
    names = [name for name in archive.namelist() if name.endswith(suffix)]
    assert len(names) == 1, (suffix, names)
    return archive.read(names[0])


def check_ctest(report, expected=None):
    suite = ET.fromstring(report)
    assert suite.tag == 'testsuite', suite.tag
    cases = suite.findall('testcase')
    names = [case.attrib['name'] for case in cases]
    assert names and len(set(names)) == len(names), names
    assert int(suite.attrib['tests']) == len(cases)
    assert all(int(suite.attrib.get(key, 0)) == 0 for key in ('failures', 'errors', 'disabled', 'skipped'))
    assert all(case.attrib.get('status') == 'run' and not any(
        case.find(tag) is not None for tag in ('failure', 'error', 'skipped')) for case in cases)
    if expected is not None:
        assert len(expected) == len(set(expected)) and set(names) == set(expected), (names, expected)
        assert not {'sdk-release', 'sdk-doc-coverage'} & set(names)
    return {'passed': len(names), 'failed': 0, 'skipped': 0, 'names': names}


def check_roles(roles):
    assert len(roles) == 3 and set(roles) == {'models', 'android-arm64-v8a', 'iphoneos-arm64'}, roles


def check_android_host(archive, source, run):
    manifest = json.loads(unique_member(archive, '/host-manifest.json'))
    assert manifest['source'] == source and manifest['run'] == str(run)
    assert manifest['tier'] == 'host-apk-build-only' and manifest['target'] == 'android-arm64-v8a'
    assert not manifest['host_deployed'] and not manifest['physical_device_verified']
    assert manifest['variant'] == 'debug' and manifest['abis'] == ['arm64-v8a']
    blob = unique_member(archive, '/' + manifest['apk'])
    assert len(blob) == manifest['apk_size'] and hashlib.sha256(blob).hexdigest() == manifest['apk_sha256']
    with zipfile.ZipFile(io.BytesIO(blob)) as apk, tempfile.TemporaryDirectory(prefix='apk-evidence-') as folder:
        names = {name for name in apk.namelist() if name.startswith('lib/') and name.endswith('.so')}
        expected = {'lib/arm64-v8a/' + name for name in (
            'libexreader_product.so', 'libexreader.so', 'libexreader_jni.so', 'libexreader_host.so')}
        assert names == expected == set(manifest['native'])
        for name in sorted(names):
            path = Path(folder) / Path(name).name
            path.write_bytes(apk.read(name))
            actual = elf_check(path, 'arm64-v8a')
            assert all(manifest['native'][name][key] == value for key, value in actual.items()), name
    return manifest


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
    parser.add_argument('--require-current-evidence', action='store_true',
                        help='Require a full CTest inventory and Android host APK evidence')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    run = json.loads(api(f'actions/runs/{args.run}'))
    jobs = json.loads(api(f'actions/runs/{args.run}/jobs'))
    artifacts = json.loads(api(f'actions/runs/{args.run}/artifacts'))
    for name, data in [('run', run), ('jobs', jobs), ('artifacts', artifacts)]:
        (args.output / (name + '.json')).write_text(json.dumps(data, indent=2), encoding='utf-8')
    assert run['status'] == 'completed' and run['conclusion'] == 'success', run['conclusion']
    assert len(jobs['jobs']) == 3 and all(j['conclusion'] == 'success' for j in jobs['jobs'])
    assert len(artifacts['artifacts']) == 3
    rows, roles = [], []
    for artifact in artifacts['artifacts']:
        assert not artifact['expired'] and artifact['workflow_run']['head_sha'] == run['head_sha']
        blob = api(f"actions/artifacts/{artifact['id']}/zip")
        digest = hashlib.sha256(blob).hexdigest()
        assert artifact['digest'] == 'sha256:' + digest and len(blob) == artifact['size_in_bytes']
        (args.output / (str(artifact['id']) + '.zip')).write_bytes(blob)
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            manifests = [n for n in archive.namelist() if n.endswith('mobile-evidence/manifest.json')]
            if manifests:
                assert len(manifests) == 1
                manifest = json.loads(archive.read(manifests[0]))
                assert manifest['source'] == run['head_sha'] and manifest['run'] == str(args.run)
                assert manifest['tier'] == 'sdk-build-only' and not manifest['physical_device_verified']
                assert not manifest['host_deployed'] and manifest['files']
                assert any(name.endswith('.a') for name in manifest['files'])
                roles.append(manifest['target'])
                prefix = manifests[0].removesuffix('mobile-evidence/manifest.json') + 'mobile-stage/'
                for name, expected in manifest['files'].items():
                    assert hashlib.sha256(archive.read(prefix + name)).hexdigest() == expected, name
                count = len(manifest['files'])
                (args.output / (manifest['target'] + '-manifest.json')).write_text(json.dumps(manifest, indent=2), encoding='utf-8')
                if args.require_current_evidence and manifest['target'] == 'android-arm64-v8a':
                    host = check_android_host(archive, run['head_sha'], args.run)
                    (args.output / 'android-host-manifest.json').write_text(json.dumps(host, indent=2), encoding='utf-8')
            else:
                roles.append('models')
                names = [n for n in archive.namelist() if n.endswith('/results/result.json')]
                assert len(names) == 1
                result = json.loads(archive.read(names[0]))
                assert result['passed'] and not result['failed'] and result['source'] == run['head_sha']
                assert result['actions'] and not result['host_ui_verified'] and not result['physical_device_verified']
                assert result['count'] == len(result['checks']) > 0
                expected = None
                if args.require_current_evidence:
                    inventory = json.loads(unique_member(archive, '/ctest-inventory.json'))
                    expected = [test['name'] for test in inventory['tests']]
                ctest = check_ctest(unique_member(archive, '/ctest-full.xml'), expected)
                model_names = ['dfinal-c-annotation-exchange-model', 'dfinal-c-installed-sdk-version-guard',
                               'dfinal-c-product-catalog-upgrade'] if args.require_current_evidence else None
                models = check_ctest(unique_member(archive, '/model-tests.xml'), model_names)
                assert {'dfinal-c-annotation-exchange-model', 'dfinal-c-installed-sdk-version-guard'} <= set(models['names'])
                assert unique_member(archive, '/source.txt').decode().strip() == run['head_sha']
                summary = {'source': run['head_sha'], 'full_ctest': ctest, 'model_ctest': models}
                (args.output / 'ctest-evidence.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
                count = result['count']
                (args.output / 'model-result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
            rows.append({'id': artifact['id'], 'name': artifact['name'], 'bytes': len(blob),
                         'zip_sha256': digest, 'checked_files_or_model_assertions': count})
    check_roles(roles)
    result = {'run': args.run, 'source': run['head_sha'], 'jobs_passed': 3, 'artifacts': rows, 'passed': True}
    (args.output / 'verified.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
