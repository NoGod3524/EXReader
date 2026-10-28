"""Authenticate immutable original upload bytes and independently replay identities."""
import json
from pathlib import Path
import sys
import zipfile

import af07_contract as C
sys.path.insert(0, str(C.ROOT / 'tools'))
from check_parallel_integration import fetch, pages, download_artifact_zip


def obtain():
    run = fetch(f'actions/runs/{C.PACKAGE_RUN}/attempts/{C.PACKAGE_ATTEMPT}')
    C.require(run['id'] == C.PACKAGE_RUN and run['head_sha'] == C.PACKAGE_SHA and
              run['run_attempt'] == C.PACKAGE_ATTEMPT and run['path'] == C.PACKAGE_WORKFLOW and
              run['head_branch'] == C.PACKAGE_BRANCH and run['status'] == 'completed' and run['conclusion'] == 'success', 'original capture run identity/conclusion')
    jobs = pages(f'actions/runs/{C.PACKAGE_RUN}/attempts/{C.PACKAGE_ATTEMPT}/jobs', 'jobs')
    selected = [j for j in jobs if j['name'] == 'android']
    C.require(len(selected) == 1 and selected[0]['status'] == 'completed' and selected[0]['conclusion'] == 'success'
              and selected[0]['head_sha'] == C.PACKAGE_SHA, 'original producer job')
    artifacts = pages(f'actions/runs/{C.PACKAGE_RUN}/artifacts', 'artifacts')
    C.save(C.OUT / 'upstream.json', dict(run=run, jobs=jobs, artifacts=artifacts))
    folders = {}
    for key, (id_, name, size, digest) in C.PINS.items():
        found = [a for a in artifacts if a['id'] == id_]
        C.require(len(found) == 1, 'original artifact absent/duplicate')
        item = found[0]
        C.require(item['name'] == name and item['size_in_bytes'] == size and item['digest'] == 'sha256:' + digest
                  and item['expired'] is False and item['workflow_run']['id'] == C.PACKAGE_RUN
                  and item['workflow_run']['head_sha'] == C.PACKAGE_SHA, 'original artifact metadata drift')
        path = C.OUT / (key + '-original-upload.zip')
        with path.open('w+b') as stream: download_artifact_zip(id_, output=stream)
        C.require(path.stat().st_size == size and C.digest(path) == digest, 'original upload bytes differ')
        folders[key] = C.extract(path, C.OUT / (key + '-upload'))
    return folders


def package_identity(value):
    C.require(value['source_sha'] == C.PACKAGE_SHA and str(value['run_id']) == str(C.PACKAGE_RUN)
              and str(value['attempt']) == str(C.PACKAGE_ATTEMPT), 'mixed package source/run/attempt')


def replay(folders):
    capture_root = folders['capture'] / 'android-f07-capture'
    capture = json.loads((capture_root / 'capture.json').read_text())
    inventory = json.loads((capture_root / 'inventory.json').read_text())
    source = json.loads((capture_root / 'source.json').read_text())
    for value in (capture, inventory, source): package_identity(value)
    C.require(capture['capture_complete'] is True and capture['failures'] == [] and capture['full_f07_accepted'] is False, 'original capture incomplete/inflated')
    raw = capture_root / 'raw'
    actual = {p.relative_to(raw).as_posix() for p in raw.rglob('*') if p.is_file()}
    C.require(actual == set(inventory['files']), 'raw capture file set differs')
    for name, item in inventory['files'].items():
        C.safe_name(name); path = raw / name
        C.require(path.stat().st_size == item['bytes'] and C.digest(path) == item['sha256'], 'retained file hash: ' + name)
    f06 = folders['f06']
    C.require({p.relative_to(f06).as_posix() for p in f06.rglob('*') if p.is_file()} ==
              {p.relative_to(raw / 'build/f06/android').as_posix() for p in (raw / 'build/f06/android').rglob('*') if p.is_file()}, 'separate F06 upload file set differs')
    for path in f06.rglob('*'):
        if path.is_file():
            retained = raw / 'build/f06/android' / path.relative_to(f06)
            C.require(retained.is_file() and C.digest(retained) == C.digest(path), 'independent F06 upload differs from capture')
    def read(name): return json.loads((f06 / name).read_text())
    result, manifest, config, entry = (read(name) for name in ('result.json', 'manifest.json', 'configuration.json', 'entry.json'))
    for value in (result, config, entry): package_identity(value)
    C.require(result['passed'] is True and result['target'] == 'android' and result['program_sha256'] == C.APK_SHA, 'original F06 result')
    C.require(manifest['source_sha'] == C.PACKAGE_SHA and manifest['sdk_version'] == '3.42.0'
              and manifest['target'] == 'android' and manifest['entry'] == 'artifacts/app-debug.apk', 'original F06 manifest')
    C.require(manifest['provenance']['run_id'] == str(C.PACKAGE_RUN) and manifest['provenance']['attempt'] == str(C.PACKAGE_ATTEMPT), 'F06 manifest provenance')
    C.require(entry['launch_passed'] is True and entry['installed_apk_sha256'] == C.APK_SHA
              and entry['api'] == '34' and entry['abi'] == 'x86_64', 'actual original installed/launch evidence')
    for key, filename in (('entry_report_sha256', 'entry.json'), ('configuration_sha256', 'configuration.json')):
        C.require(result[key] == C.digest(f06 / filename), 'F06 report digest')
    archive = manifest['archive']; C.safe_name(archive['name'])
    C.require('/' not in archive['name'] and archive == result['archive'], 'F06 archive record')
    path = f06 / archive['name']
    C.require(path.stat().st_size == archive['bytes'] and C.digest(path) == archive['sha256'], 'F06 nested archive hash')
    payload = C.extract(path, C.OUT / 'actual-f06-payload')
    C.require({p.relative_to(payload).as_posix() for p in payload.rglob('*') if p.is_file()}
              == set(manifest['files']) | set(manifest['metadata_files']), 'F06 nested file set')
    inner = json.loads((payload / 'manifest.json').read_text())
    C.require(inner == {k: v for k, v in manifest.items() if k != 'archive'}, 'F06 inner/outer manifest')
    expected_sums = ''.join(row['sha256'] + '  ' + name + '\n' for name, row in sorted(manifest['files'].items())).encode()
    C.require((payload / 'SHA256SUMS').read_bytes() == expected_sums and C.sha(expected_sums) == archive['checksums_sha256'], 'F06 checksum list')
    for name, row in manifest['files'].items():
        C.safe_name(name); path = payload / name
        C.require(path.stat().st_size == row['bytes'] and C.digest(path) == row['sha256'], 'F06 actual payload bytes')
    producer = json.loads((payload / 'build.json').read_text())
    C.require(producer == config['producer'] and producer['source_sha'] == C.PACKAGE_SHA
              and producer['sdk_version'] == '3.42.0' and manifest['producer']['source_sha'] == C.PACKAGE_SHA
              and manifest['producer']['sdk_version'] == '3.42.0'
              and C.digest(payload / 'build.json') == manifest['producer']['build_json_sha256'], 'original producer binding')
    apk = payload / 'artifacts/app-debug.apk'
    for name in ('build/f06/unpacked-android/artifacts/app-debug.apk', 'build/f06/installed-android.apk',
                 'build/wave3/artifacts/app-debug.apk', 'examples/android/app/build/outputs/apk/debug/app-debug.apk'):
        C.require(C.digest(raw / name) == C.digest(apk) == C.APK_SHA, 'actual APK chain differs')
    apk_folder = C.extract(apk, C.OUT / 'actual-apk')
    native = sorted((apk_folder / 'lib/x86_64').glob('*.so'))
    C.require({p.relative_to(apk_folder).as_posix() for p in (apk_folder / 'lib').rglob('*') if p.is_file()}
              == {'lib/x86_64/' + p.name for p in native}, 'unexpected APK native architecture/file')
    C.require(native, 'APK has no native images')
    # Recompute actual raw link output and installed-image comparisons; do not
    # accept captured match lists or transformation booleans as proof.
    linked = [item for graph in capture['build_graphs'] for item in graph['linked_outputs']]
    bindings = {}
    for path in native:
        signature = C.allocated(path)
        candidates = [row for row in linked if Path(row['path']).name.split('.so')[0] == path.name[:-3]]
        matching = [row for row in candidates if C.allocated(raw / row['path']) == signature]
        if not matching:
            C.save(C.OUT / ('unresolved-binding-' + path.name + '.json'), dict(apk=signature,
                   candidates={row['path']: C.allocated(raw / row['path']) for row in candidates}))
        C.require(matching, 'APK has no exact all-allocated-section/raw-link match (install transform unresolved): ' + path.name)
        for row in matching:
            C.require(C.digest(raw / row['path']) == row['sha256'], 'raw linked image digest')
            for name in row['inputs'] + row['maps']:
                C.require(name in inventory['files'], 'link input/map absent')
        if path.name in ('libexreader_host.so', 'libexreader_product.so'):
            map_name = 'sdk-host-link.map' if path.name == 'libexreader_host.so' else 'product-link.map'
            C.require(all(any(Path(name).name == map_name for name in row['maps']) for row in matching), 'map not bound to actual host link')
        else:
            installed = [p for p in (raw / C.SDK / 'lib').glob(path.name + '*') if p.is_file()]
            C.require(any(C.allocated(p) == signature for p in installed), 'actual installed SDK does not match APK')
        bindings[path.name] = dict(apk_path=str(path), apk_sha256=C.digest(path), allocated=signature,
                                   linked=matching)
    C.save(C.OUT / 'replay.json', dict(C.identity(), uploads=C.PINS, apk_sha256=C.APK_SHA,
             inventory_files=len(actual), bindings=bindings, independent_replay=True))
    return raw, capture, inventory, native, bindings
