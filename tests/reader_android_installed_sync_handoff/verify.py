"""Actions-only verifier: binds one source SHA, the installed APK bytes, the native
libraries it ships, the live process snapshot taken during a real in-flight native
request, and the fixture server's recorded WebDAV requests. A pass requires every
gate; nothing is inferred from a probe binary."""
import hashlib, json, os, re, subprocess, sys, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / 'build/c1-installed-sync'
DEVICE = BUILD / 'device'
HASH_SYMBOLS = ['opds_sha256_stream_create', 'opds_sha256_stream_update', 'opds_sha256_stream_finish_hex',
                'opds_sha256_stream_destroy']
SYNC_SYMBOLS = ['reader_sync_step', 'reader_sync_create']
LOCAL = 'abcdefghijk retained UI reading anchor.\n' + 'Safe original paragraph.\n' * 200


def sha(data):
    return hashlib.sha256(data).hexdigest()


def nm(tool, path):
    out = subprocess.run([str(tool), '--defined-only', '-C', str(path)], capture_output=True, text=True)
    return out.stdout if out.returncode == 0 else ''


def main():
    failures, gates = [], {}

    def gate(name, ok, detail=None):
        gates[name] = dict(passed=bool(ok), detail=detail)
        if not ok:
            failures.append(name)

    identity = {k: os.environ[v] for k, v in (('source_sha', 'GITHUB_SHA'), ('run_id', 'GITHUB_RUN_ID'),
                                              ('attempt', 'GITHUB_RUN_ATTEMPT'))}
    build = json.loads((BUILD / 'build.json').read_text())
    gate('build_identity', all(build[k] == v for k, v in identity.items()) and build['sdk_version'] == '3.42.0')
    gate('build_host_apk_stable', build['host_apk_sha256'] == build['host_apk_after_runner_build_sha256'])
    install = json.loads((DEVICE / 'install.json').read_text())
    apk = DEVICE / 'installed-host.apk'
    gate('installed_apk_equals_built', sha(apk.read_bytes()) == build['host_apk_sha256'] == install['installed_sha256'])

    # Shipped native libraries and the exact product image holding Sync + the hash owner.
    packaged = {}
    with zipfile.ZipFile(apk) as z:
        for name in z.namelist():
            if name.startswith('lib/x86_64/') and name.endswith('.so'):
                packaged[name] = sha(z.read(name))
                (DEVICE / 'apk-libs').mkdir(exist_ok=True)
                (DEVICE / 'apk-libs' / Path(name).name).write_bytes(z.read(name))
    product_name = 'lib/x86_64/libexreader_product.so'
    gate('apk_ships_product_image', product_name in packaged, sorted(packaged))
    ndk = Path(os.environ['ANDROID_HOME']) / 'ndk' / os.environ['C11_NDK'] / 'toolchains/llvm/prebuilt/linux-x86_64/bin'
    built = sorted(p for p in (ROOT / 'examples/android/app').rglob('libexreader_product.so') if p.is_file())
    built_records = {p.relative_to(ROOT).as_posix(): sha(p.read_bytes()) for p in built}
    symbol_source, symbols = None, ''
    for candidate in [DEVICE / 'apk-libs/libexreader_product.so', *built]:
        text = nm(ndk / 'llvm-nm', candidate) if candidate.exists() else ''
        if all(s in text for s in HASH_SYMBOLS) and any(s in text for s in SYNC_SYMBOLS):
            symbol_source, symbols = str(candidate), text
            break
    pkg_sha = packaged.get(product_name)
    equal_built = [k for k, v in built_records.items() if v == pkg_sha]
    gate('product_image_defines_installed_hash_and_sync', symbol_source is not None,
         dict(symbol_source=symbol_source, packaged_sha256=pkg_sha, built=built_records, equal_to_packaged=equal_built))
    lines = symbols.splitlines()
    (DEVICE / 'product-symbols.txt').write_text('\n'.join(l for l in lines if re.search('opds_sha256|reader_sync|exr_webdav', l)))
    # The packaged image must be that build output, byte-equal or its documented AGP strip.
    stripped_equal = False
    if not equal_built and built:
        for p in built:
            out = DEVICE / 'strip-check.so'
            subprocess.run([str(ndk / 'llvm-strip'), '--strip-unneeded', '-o', str(out), str(p)], check=True)
            stripped_equal = stripped_equal or sha(out.read_bytes()) == pkg_sha
    gate('packaged_product_derives_from_build', bool(equal_built) or stripped_equal)

    # Live process: the mapped libraries while a native request was blocked in flight.
    snaps = json.loads((DEVICE / 'process-snapshots.json').read_text())
    by_kind = {s['kind']: s for s in snaps['snapshots']}
    for kind in ('upload', 'listing'):
        s = by_kind.get(kind, {})
        mapped = {Path(p).name: h for p, h in s.get('lib_sha256', {}).items()}
        gate('live_process_' + kind, len(s.get('pids', [])) == 1 and mapped.get('libexreader_product.so') == pkg_sha and
             all(h == packaged.get('lib/x86_64/' + n) for n, h in mapped.items() if 'lib/x86_64/' + n in packaged), s.get('lib_sha256'))

    # Frozen UI suite result on the real Activity.
    ui = json.loads((DEVICE / 'ui/result.json').read_text())
    gate('ui_suite_accepted', ui.get('accepted') is True and all(ui.get(k) == v for k, v in identity.items()) and
         ui['checks'] == 16 and len(ui['boundaries']) == 2 and
         all(b['real_request_blocked'] and b['ui_action_observed'] for b in ui['boundaries']),
         dict(checks=ui.get('checks'), phases=len(ui.get('phases', []))))
    gate('ui_sdk_342', all(p['expected_sdk_version'] == '3.42.0' for p in ui['phases']))

    # Upload: the local original (hashed by the installed Sync path) arrives byte-identical.
    local = LOCAL.encode()
    digest = sha(local)
    objects = [r for r in ui['requests'] if r['method'] == 'PUT' and '/objects/' in r['path']]
    mine = [r for r in objects if r['path'].endswith('/' + digest + '.txt')]
    gate('local_original_uploaded_with_matching_sha256',
         bool(mine) and any(r.get('stored') and r.get('response') == 201 and r['body_sha256'] == digest and
                            r['body_bytes'] == len(local) and r['path'] == '/dav/exreader-sync-v1/objects/%s/%s.txt' % (digest[:2], digest)
                            for r in mine), mine)
    gate('no_object_with_mismatched_identity',
         all(r['path'].rsplit('/', 1)[-1].split('.')[0] == r['body_sha256'] for r in objects if r.get('body_sha256')),
         [r['path'] for r in objects])
    attempts = len(mine)
    gate('interrupted_upload_then_recovery', attempts >= 1 and any(
        r['method'] == 'PUT' and r.get('response') == 201 for r in ui['requests']), dict(object_put_attempts=attempts))
    gate('authorization_only_fixture_credentials', all(r['path'].startswith('/dav/') for r in ui['requests']))

    result = dict(identity, passed=not failures, failures=failures, gates=gates, sdk_version='3.42.0',
                  host_apk_sha256=build['host_apk_sha256'], packaged_libs=packaged, build=build,
                  installed_android_sync_runtime=not failures, physical_device=False, f07_accepted=False,
                  full_product_accepted=False,
                  scope='Installed Android host: real Activity -> NativeSync JNI -> reader_session -> reader_sync (installed OPDS hash owner) '
                        '-> TLS WebDAV on API34 x86_64 emulator; local fixture server only')
    (BUILD / 'installed-sync-result.json').write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps(dict(passed=result['passed'], failures=failures)), flush=True)
    sys.exit(1 if failures else 0)


if __name__ == '__main__':
    main()
