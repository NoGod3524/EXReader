"""Actions-only independent audit of C3's retained Android delivery archive."""
import base64
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import stat
import sys
import zipfile

assert os.environ.get('GITHUB_ACTIONS') == 'true'
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from check_parallel_integration import fetch, download_artifact_zip

SOURCE = '9bced259710edff4bb98c730121ca09295500d73'
RUN, JOB, ARTIFACT, SIZE = 40950703390, 123717743311, 12931817204, 19778654
DIGEST = 'f6f164d07ad081785d8a10cb95e52f8a4a8784e5ad3630fee3e506113906b368'
APK = 'df7defce60b99ca6eb3ad50450671518a69c256256a6f6e3eb6642fa6f849dbd'
OUT = Path('build/claude-c3-independent')
OUT.mkdir(parents=True, exist_ok=True)
result = dict(accepted=False, source=SOURCE, run=RUN, job=JOB, artifact=ARTIFACT,
              catalog_changed=False, f12_accepted=False, complete_product=False)

def sha(data):
    return hashlib.sha256(data).hexdigest()

def members(data):
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        infos = z.infolist()
        names = [i.filename for i in infos]
        assert len(names) == len(set(n.casefold() for n in names)), 'duplicate member'
        for i in infos:
            n = i.filename
            mode = (i.external_attr >> 16) & 0o170000
            assert n and '\\' not in n and ':' not in n and '\x00' not in n
            assert not PurePosixPath(n).is_absolute() and '..' not in n.split('/')
            assert mode in (0, stat.S_IFREG, stat.S_IFDIR) and not i.flag_bits & 1
        return {i.filename: z.read(i) for i in infos if not i.is_dir()}

try:
    run = fetch(f'actions/runs/{RUN}/attempts/1')
    job = fetch(f'actions/jobs/{JOB}')
    assert (run['head_sha'], run['run_attempt'], run['status'], run['conclusion']) == (SOURCE, 1, 'completed', 'success')
    assert (job['run_id'], job['head_sha'], job['status'], job['conclusion']) == (RUN, SOURCE, 'completed', 'success')
    pin = fetch(f'actions/artifacts/{ARTIFACT}')
    assert pin['name'] == f'c3-android-sdk342-licenses-{RUN}-1' and not pin['expired']
    assert (pin['workflow_run']['id'], pin['workflow_run']['head_sha']) == (RUN, SOURCE)
    assert pin['size_in_bytes'] == SIZE and pin['digest'] == 'sha256:' + DIGEST
    raw = download_artifact_zip(ARTIFACT)
    assert len(raw) == SIZE and sha(raw) == DIGEST
    outer = members(raw)
    def one(suffix):
        found = [n for n in outer if n.endswith(suffix)]
        assert len(found) == 1, (suffix, found)
        return outer[found[0]]
    manifest = json.loads(one('f06/android/manifest.json'))
    original = json.loads(one('f06/android/result.json'))
    entry = json.loads(one('f06/android/entry.json'))
    report = json.loads(one('c3-android/license-verify.json'))
    admission = json.loads(one('c3-android/admission.json'))
    for value in (manifest, original, report, admission):
        assert value['source_sha'] == SOURCE
    for value in (original, report):
        assert (str(value['run_id']), str(value['attempt'])) == (str(RUN), '1')
    assert manifest['sdk_version'] == '3.42.0' and manifest['target'] == original['target'] == 'android'
    assert (str(manifest['provenance']['run_id']), str(manifest['provenance']['attempt'])) == (str(RUN), '1')
    assert original['passed'] is True and report['passed'] is True and report['failures'] == []
    archive = manifest['archive']
    assert archive == report['archive'] == original['archive']
    archive_bytes = one('f06/android/' + archive['name'])
    assert len(archive_bytes) == archive['bytes'] and sha(archive_bytes) == archive['sha256']
    assert archive['sha256'] == 'b4baebfabbd9d05c243aade3765143335f00d5d856a8a29332fb0d8149e963f2'
    package = members(archive_bytes)
    assert set(package) == set(manifest['files']) | set(manifest['metadata_files'])
    assert set(manifest['metadata_files']) == {'manifest.json', 'SHA256SUMS'}
    assert json.loads(package['manifest.json']) == {k: v for k, v in manifest.items() if k != 'archive'}
    for name, record in manifest['files'].items():
        assert len(package[name]) == record['bytes'] and sha(package[name]) == record['sha256'], name
    sums = ''.join(r['sha256'] + '  ' + n + '\n' for n, r in sorted(manifest['files'].items()))
    assert package['SHA256SUMS'].decode() == sums
    sdk = {n: sha(data) for n, data in package.items() if n.startswith('licenses/')}
    product = {n: sha(data) for n, data in package.items() if n.startswith('product-licenses/')}
    assert len(sdk) == report['sdk_licence_files'] == report['archive_licence_files'] == report['registry_expected'] == 15
    assert set(product) == {'product-licenses/exreader-product/sqlite-public-domain.txt', 'product-licenses/exreader-webdav/LICENSE.txt'}
    assert set(n.removeprefix('product-licenses/') for n in product) == set(report['product_licence_files'])
    assert report['registry_missing'] == report['installed_but_not_in_registry_expected'] == []
    assert report['vendor_missing'] == report['vendor_unregistered'] == []
    assert report['product_sqlite_matches_repository'] is True and report['byte_identical_to_sdk_tree'] is True
    item = fetch('contents/licenses/sqlite-public-domain.txt?ref=' + SOURCE)
    assert item['encoding'] == 'base64'
    sqlite = base64.b64decode(item['content'])
    assert package['product-licenses/exreader-product/sqlite-public-domain.txt'] == sqlite
    assert package['licenses/sqlite/sqlite-public-domain.txt'] == sqlite
    assert sha(package['artifacts/app-debug.apk']) == APK == original['program_sha256'] == entry['installed_apk_sha256']
    assert entry['launch_passed'] is True
    members(package['artifacts/app-debug.apk'])
    result.update(accepted=True, archive_sha256=sha(archive_bytes), apk_sha256=APK,
                  sdk_licences=sdk, product_licences=product,
                  retained_files_verified=len(manifest['files']),
                  installed_tree_byte_comparison='original passing job; install trees not retained separately',
                  scope='Android archive closed membership, licence bytes, source identity and original emulator receipt only',
                  physical_device=False, common_source_acceptance=False)
except Exception as error:
    result['error'] = repr(error)
finally:
    (OUT / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result), flush=True)
assert result['accepted'], result.get('error')
