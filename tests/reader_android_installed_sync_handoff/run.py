"""Actions-only device phase: the installed host's Sync/WebDAV hash, upload and recovery path."""
import hashlib, json, os, runpy, subprocess, sys, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WS = ROOT / 'build/wave3'
OUT = ROOT / 'build/installed-sync/evidence'
PACKAGE = 'org.exreader.host'
LOCAL_TEXT = 'abcdefghijk retained UI reading anchor.\n' + 'Safe original paragraph.\n' * 200
MARKERS = [b'Public SHA-256 finalization failed', b'Public SHA-256 update failed', b'Cannot create public SHA-256 state']

def sha(data): return hashlib.sha256(data).hexdigest()
def adb(*args, timeout=180): return subprocess.check_output(['adb', *map(str, args)], stderr=subprocess.STDOUT, timeout=timeout)

def identity_phase():
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    OUT.mkdir(parents=True, exist_ok=True)
    ident = {key: os.environ[value] for key, value in [('source_sha', 'GITHUB_SHA'), ('run_id', 'GITHUB_RUN_ID'), ('attempt', 'GITHUB_RUN_ATTEMPT')]}
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip() == ident['source_sha']
    build = json.loads((ROOT / 'build/installed-sync/build.json').read_text())
    assert build['source_sha'] == ident['source_sha'] and build['run_id'] == ident['run_id'] and build['attempt'] == ident['attempt']
    adb('install', '-r', '-t', WS / 'artifacts/app-debug.apk'); adb('install', '-r', '-t', WS / 'artifacts/sync-342-debug-androidTest.apk')
    path = adb('shell', 'pm', 'path', PACKAGE).decode().strip()
    assert path.startswith('package:') and '\n' not in path, path
    pulled = OUT / 'installed-base.apk'; adb('pull', path[len('package:'):], pulled)
    built_sha = sha((WS / 'artifacts/app-debug.apk').read_bytes())
    assert sha(pulled.read_bytes()) == built_sha, 'installed APK differs from the build output'
    libs = {}
    with zipfile.ZipFile(pulled) as z:
        for info in z.infolist():
            if info.filename.startswith('lib/x86_64/') and info.filename.endswith('.so'): libs[info.filename] = z.read(info)
    product = [n for n in libs if n.endswith('/libexreader_product.so')]
    assert len(product) == 1, sorted(libs)
    image = libs[product[0]]
    markers = {m.decode(): image.count(m) for m in MARKERS}
    assert all(markers.values()), markers
    stage = WS / 'stage'; hash_stage = ROOT / 'build/installed-sync/hash-stage'
    archives = {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in sorted(list(stage.glob('lib/libreader_sync*.a')) + list(hash_stage.glob('lib/*.a')))}
    assert any('libreader_sync' in k for k in archives) and any('opds_sha256_stream' in k for k in archives), archives
    blob = subprocess.check_output(['git', 'rev-parse', 'HEAD:apps/reader/sync/src/sync.cpp'], cwd=ROOT, text=True).strip()
    return ident, dict(installed_apk_path=path, installed_apk_sha256=built_sha, native_libs={n: sha(d) for n, d in libs.items()},
        product_image=product[0], product_image_sha256=sha(image), public_hash_literals_in_installed_image=markers,
        installed_archives=archives, sync_source_blob=blob, test_apk_sha256=sha((WS / 'artifacts/sync-342-debug-androidTest.apk').read_bytes()),
        provenance=json.loads((ROOT / 'build/installed-sync/candidate/provenance.json').read_text()), build=build)

def main():
    ident, program = identity_phase()
    driver_out = OUT / 'ui'
    sys.argv = ['run_ui_342.py', '--sdk-version', '3.42.0', '--fixture', str(WS / 'network-fixture'),
                '--reading-fixtures', str(WS / 'sync-reading-fixtures'), '--output', str(driver_out)]
    driver_ok = True
    try: runpy.run_path(str(Path(__file__).resolve().parent / 'run_ui_342.py'), run_name='__main__')
    except BaseException as error: driver_ok = False; driver_error = repr(error)
    result = {**ident, 'program': program, 'driver_completed': driver_ok, 'installed_android_sync_runtime': False}
    try:
        assert driver_ok, driver_error
        report = json.loads((driver_out / 'result.json').read_text())
        assert report['accepted'] is True and all(report[k] == ident[k] for k in ident)
        requests = report['requests']
        digest = sha(LOCAL_TEXT.encode()); object_path = f'/dav/exreader-sync-v1/objects/{digest[:2]}/{digest}.txt'
        puts = [r for r in requests if r['method'] == 'PUT' and r['path'] == object_path]
        assert puts and all(r.get('body_sha256') == digest and r.get('body_bytes') == len(LOCAL_TEXT.encode()) for r in puts), puts
        stored = [r for r in puts if r.get('stored')]
        assert len(stored) == 1, 'exactly one immutable object stored'
        order = [i for i, r in enumerate(requests) if r['path'] == object_path]
        assert any(requests[i]['method'] == 'GET' for i in order if i > requests.index(stored[0])), 'no post-upload verification download'
        revision_puts = [r for r in requests if r['method'] == 'PUT' and '/revisions/' in r['path'] and r.get('stored')]
        assert revision_puts, 'revision record not uploaded'
        first = report['phases'][0]
        names = [c['name'] for c in first['checks']]
        assert 'ui_cancel_blocked_native_request_then_retry' in names
        result.update(installed_android_sync_runtime=True, object_path=object_path, object_sha256=digest, object_puts=puts,
            stored_put_index=requests.index(stored[0]), revision_puts=len(revision_puts), request_count=len(requests),
            phase_pids=[p['pid'] for p in report['phases']], api=report['api'], abi=report['abi'],
            ui_checks=report['checks'], boundaries=report['boundaries'],
            scope='Installed host app process (HostSync342Test via am instrument): Sync/WebDAV local-original hash, immutable upload, '
                  'cancel of a blocked upload, retry/recovery, receive hash verification, credential/session lifecycle on API34 emulator.',
            not_claimed=['F01/F07/F08/F12', 'physical device', 'host TLS not substituted', 'no 108-list item granted'])
    finally:
        (OUT / 'installed-sync-result.json').write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps({k: result.get(k) for k in ('source_sha', 'run_id', 'attempt', 'driver_completed', 'installed_android_sync_runtime')}))
    assert result['installed_android_sync_runtime']

if __name__ == '__main__': main()
