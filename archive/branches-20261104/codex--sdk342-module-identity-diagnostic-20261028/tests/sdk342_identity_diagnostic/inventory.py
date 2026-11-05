"""Actions-only inventory of retained source-bound artifacts; no build or test."""
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

RUN = '40678657371'
ATTEMPT = '1'
SOURCE = '8f8acf3234cba747165f001c0c96efe1b911e6ad'
ARTIFACTS = {
    'windows': (12812276328, '0206e54988ca50e3feae37d7f83457ab959d052ef350fb55eb9269007c2c9cd2'),
    'linux': (12811449234, 'be3a91161939b3b61bce041feaa06679d03120af9f53abea02bab141d5665641'),
    'macos': (12811976629, 'f480b2a8489f8b21aa00c795b38fbd4a85261200a654cb2daf6c880bb538b599'),
    'android': (12812325830, 'e120fb8a3d73aafb19578aed9d114788177ae104a00f1f754b2cb413c174760e'),
    'iphone': (12813015622, 'c56a913aca689f4290a4d66787666e3b22617c39308c3acfc45bd1b3794f3c3b'),
    'ipad': (12812242328, '34cb0a2b9b56f5b6cd4f3347f08505aac3abe128aba59e982cf208e93829acf9'),
    'gtk_producer': (12811723170, '7fd83bd5af2c8c8a57b60566a2c94e99441c021bb2f02f453759b33c6cc292be'),
    'macos_raw': (12812815122, '11a2403aff450fdf8c7e9b2fe892d6da89ed4d031162c6e9dea3bfd304499c97'),
    'mobile_raw': (12812182450, '1a0e59ee76f3003d01a7094c28dd591aed9da23c65475e3f404f89c850df4889'),
    'windows_build': (12811543563, '7da5b053b02d25ff89bcf5b7bc7723c62ca8e88afd8cc3e1ecb6cc1faed7b918'),
    'android_build': (12811403529, 'a42bea811407479f26460c219b34a35a84b1bac81f2be880106d0147eef07835'),
}

def sha(data): return hashlib.sha256(data).hexdigest()
def safe_zip(raw):
    z = zipfile.ZipFile(io.BytesIO(raw))
    names = z.namelist()
    assert len(names) == len(set(names))
    assert all(not PurePosixPath(n).is_absolute() and '..' not in PurePosixPath(n).parts and '\\' not in n for n in names)
    return z

def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    out = ROOT / 'build/sdk342-identity-diagnostic'
    out.mkdir(parents=True, exist_ok=True)
    report = {'original_source_sha': SOURCE, 'original_run_id': RUN, 'original_attempt': ATTEMPT,
              'diagnostic_source_sha': os.environ['GITHUB_SHA'], 'diagnostic_run_id': os.environ['GITHUB_RUN_ID'],
              'diagnostic_attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'accepted': False, 'artifacts': {},
              'f06': {}, 'inventories': {}, 'limitations': [], 'failures': []}
    try:
        run = fetch(f'actions/runs/{RUN}')
        assert run['head_sha'] == SOURCE and run['run_attempt'] == int(ATTEMPT) and run['conclusion'] == 'success'
        for name, (artifact_id, expected) in ARTIFACTS.items():
            item = fetch(f'actions/artifacts/{artifact_id}')
            assert item['id'] == artifact_id and item['workflow_run']['id'] == int(RUN)
            assert item['workflow_run']['head_sha'] == SOURCE and item['digest'] == 'sha256:' + expected and not item['expired']
            raw = download_artifact_zip(artifact_id)
            assert len(raw) == item['size_in_bytes'] and sha(raw) == expected
            report['artifacts'][name] = {'id':artifact_id, 'sha256':expected,
                'url':f'https://github.com/{os.environ["GITHUB_REPOSITORY"]}/actions/runs/{RUN}/artifacts/{artifact_id}'}
            with safe_zip(raw) as z:
                names = z.namelist()
                if name in ('windows', 'linux', 'macos', 'android', 'iphone', 'ipad'):
                    manifest = json.loads(z.read('manifest.json'))
                    assert manifest['target'] == name and manifest['source_sha'] == SOURCE and manifest['sdk_version'] == '3.42.0'
                    assert manifest['producer']['source_sha'] == SOURCE and manifest['producer']['sdk_version'] == '3.42.0'
                    assert str(manifest['provenance']['run_id']) == RUN and str(manifest['provenance']['attempt']) == ATTEMPT
                    config = json.loads(z.read('configuration.json'))
                    assert config['source_sha'] == SOURCE and str(config['run_id']) == RUN and str(config['attempt']) == ATTEMPT
                    package = z.read(manifest['archive']['name'])
                    assert sha(package) == manifest['archive']['sha256']
                    report['f06'][name] = {'archive_sha256':sha(package), 'configuration_sha256':sha(z.read('configuration.json')),
                                           'producer':config['producer']}
                    if name == 'android':
                        with safe_zip(package) as delivery:
                            apk = delivery.read('artifacts/app-debug.apk')
                        with safe_zip(apk) as packed:
                            libs = {p:sha(packed.read(p)) for p in packed.namelist() if p.startswith('lib/x86_64/') and p.endswith('.so')}
                        assert libs and any(p.endswith('/libexreader_jni.so') for p in libs)
                        report['inventories']['android_packaged_apk_shared_libraries'] = libs
                elif name == 'gtk_producer':
                    record = json.loads(z.read('gtk-sdk342/build.json'))
                    assert record['source_sha'] == SOURCE and str(record['run_id']) == RUN and str(record['attempt']) == ATTEMPT
                    assert record['passed'] is True and record['sdk_version'] == '3.42.0'
                    values = record['installed_sha256']
                    assert values and all(len(v) == 64 for v in values.values())
                    report['inventories']['linux_recorded_installed_files'] = values
                elif name in ('macos_raw', 'mobile_raw'):
                    prefix = 'macos-build/' if name == 'macos_raw' else 'iphonesimulator-build/'
                    libs = {p:sha(z.read(p)) for p in names if p.startswith((prefix+'sdk/lib/', prefix+'product/lib/'))
                            and not p.endswith('/') and (p.endswith(('.a','.dylib','.so')) or '.dylib.' in p)}
                    assert libs, 'missing retained Apple stage libraries: '+name
                    report['inventories'][name+'_retained_stage_library_bytes'] = libs
                elif name in ('windows_build','android_build'):
                    stages = [p for p in names if ('sdk-stage/' in p or 'raw-stage/' in p or '/stage/lib/' in p)
                              and p.lower().endswith(('.a','.lib','.dll','.so'))]
                    report['inventories'][name+'_retained_stage_binary_paths'] = stages
            del raw
        report['limitations'] = [
            'GTK hashes are recorded installed-file hashes in the same-run producer build.json; this diagnostic did not independently rehash the installed files.',
            'Apple stage entries are hashes of retained artifact bytes; ZIP preservation may not retain original filesystem symlink metadata.',
            'Android APK libraries are packaged bytes, not separate evidence of all loaded libraries or every installed static product module.',
            'Windows and Android installed stage binary hashes remain unknown if the retained stage-binary path lists are empty.',
            'Simulator, signature, release and behavioral limits of the original run remain unchanged.'
        ]
        report['accepted'] = True
    except Exception as error:
        report['failures'].append(repr(error))
    (out/'inventory.json').write_text(json.dumps(report, indent=2, sort_keys=True)+'\n')
    print(json.dumps(report, indent=2, sort_keys=True), flush=True)
    assert report['accepted'], 'identity inventory failed; inspect retained report'

if __name__ == '__main__': main()
