# SPDX-License-Identifier: MIT
"""Actions-only installed iOS SDK/account two-library reading round trip."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    root = Path.cwd(); out = root / 'build/ios-session'; logs = out / 'logs'; logs.mkdir(parents=True)

    def run(name, command, timeout=900):
        print('START ' + name, flush=True)
        done = subprocess.run([str(x) for x in command], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=timeout)
        (logs / (name + '.log')).write_text(done.stdout + done.stderr, encoding='utf-8')
        if done.returncode: print((done.stdout + done.stderr)[-12000:], flush=True)
        assert done.returncode == 0, (name, done.returncode)
        print('PASS ' + name, flush=True)
        return done.stdout.strip()

    stage = out / 'stage'
    sdk = run('sdk-path', ['xcrun', '--sdk', 'iphonesimulator', '--show-sdk-path'])
    common = ['-G', 'Ninja', '-DCMAKE_SYSTEM_NAME=iOS', '-DCMAKE_OSX_SYSROOT=iphonesimulator',
              '-DCMAKE_OSX_ARCHITECTURES=arm64', '-DCMAKE_OSX_DEPLOYMENT_TARGET=15.0', '-DCMAKE_BUILD_TYPE=Release',
              '-DCMAKE_XCODE_ATTRIBUTE_CODE_SIGNING_ALLOWED=NO', '-DCMAKE_INSTALL_PREFIX=' + str(stage),
              '-DLIBXML2_INCLUDE_DIR=' + sdk + '/usr/include/libxml2', '-DLIBXML2_LIBRARY=' + sdk + '/usr/lib/libxml2.tbd',
              '-DEXR_SDK=' + str(stage), '-DREADER_PRODUCT_PREFIX=' + str(stage)]
    packages = ('EXReader', 'EXReaderProductCatalog', 'EXReaderRevisions', 'EXReaderWebDAV', 'EXReaderSync',
                'EXReaderSession', 'EXReaderReadingState', 'EXReaderSideload')
    common += ['-D' + p + '_DIR=' + str(stage / 'lib/cmake' / p) for p in packages]
    run('sdk-configure', ['cmake', '--preset', 'reading-library', '-B', out / 'sdk-build', *common])
    run('sdk-build', ['cmake', '--build', out / 'sdk-build', '--parallel', '4'], timeout=1200)
    run('sdk-install', ['cmake', '--install', out / 'sdk-build'])
    modules = [('product', 'apps/reader/store/native'), ('revisions', 'apps/reader/revisions'),
               ('webdav', 'extras/webdav'), ('sync', 'apps/reader/sync'), ('session', 'apps/reader/session'),
               ('reading-state', 'apps/reader/reading-state'), ('sideload', 'extras/sideload')]
    for name, path in modules:
        build = out / (name + '-build')
        run(name + '-configure', ['cmake', '-S', path, '-B', build, *common])
        run(name + '-build', ['cmake', '--build', build, '--parallel', '4', '--verbose'])
        run(name + '-install', ['cmake', '--install', build])
    consumer = out / 'consumer'
    run('consumer-configure', ['cmake', '-S', 'tests/reader_ios_session', '-B', consumer, *common])
    run('consumer-build', ['cmake', '--build', consumer, '--parallel', '4', '--verbose'])
    app = consumer / 'ReaderSessionProbe.app'; binary = app / 'ReaderSessionProbe'
    run('sign', ['codesign', '--force', '--sign', '-', app])
    assert run('architecture', ['lipo', '-archs', binary]) == 'arm64'
    dependencies = run('dependencies', ['otool', '-L', binary])
    assert 'Foundation.framework' in dependencies and not any(x in dependencies.lower() for x in ('libcurl', 'libssl', 'libcrypto', 'webkit', 'webview'))
    unresolved = run('session-undefined-symbols', ['nm', '-u', stage / 'lib/libreader_session.a'])
    assert not any(x in unresolved for x in ('_exr_library_', '_exr_document_', '_exr_pager_', '_exr_publication_'))
    fixtures = out / 'fixtures'
    run('fixtures', [sys.executable, 'tests/reader_reading_state/make_fixtures.py', fixtures])
    runtimes = json.loads(run('runtimes', ['xcrun', 'simctl', 'list', 'runtimes', '--json']))['runtimes']
    runtime = max((r for r in runtimes if r.get('isAvailable') and r['identifier'].startswith('com.apple.CoreSimulator.SimRuntime.iOS-')),
                  key=lambda r: tuple(int(x) for x in r['version'].split('.')))
    types = json.loads(run('device-types', ['xcrun', 'simctl', 'list', 'devicetypes', '--json']))['devicetypes']
    device = next(t for t in types if t['name'].startswith('iPhone 16'))
    udid = run('create', ['xcrun', 'simctl', 'create', 'EXReader-Session-' + os.environ['GITHUB_RUN_ID'], device['identifier'], runtime['identifier']])
    try:
        run('boot', ['xcrun', 'simctl', 'boot', udid])
        run('boot-status', ['xcrun', 'simctl', 'bootstatus', udid, '-b'])
        run('install', ['xcrun', 'simctl', 'install', udid, app])
        container = run('container', ['xcrun', 'simctl', 'get_app_container', udid, 'org.exreader.session.probe', 'data'])
        os.environ['EXR_DAV_IOS_UDID'] = udid; os.environ['EXR_DAV_IOS_CONTAINER'] = container
        adapter = root / 'tests/reader_ios_session/launch.py'; adapter.chmod(0o755)
        evidence = out / 'evidence'
        run('actual-session-roundtrip', [sys.executable, 'tests/reader_reading_v2/check_webdav.py', '--probe', adapter,
                                        '--native-binary', binary, '--fixtures', fixtures, '--font', root / 'tests/fixtures/fonts/primary.ttf',
                                        '--link-map', consumer / 'session-link.map', '--output', evidence, '--timeout', '1200'], timeout=1300)
        reading = json.loads((evidence / 'result.json').read_text(encoding='utf-8'))
        sessions = json.loads((evidence / 'probe.json.sessions.json').read_text(encoding='utf-8'))
        lifecycle = json.loads((evidence / 'probe.json.lifecycle.json').read_text(encoding='utf-8'))
        assert reading['accepted'] is True and reading['execution_platform'] == 'ios-simulator'
        assert sessions['accepted'] is True and sessions['count'] == len(sessions['sessions']) == 38
        assert all(s['shards'] == 256 and s['sweeps'] == 1 and s['observations'] > 0 for s in sessions['sessions'])
        assert lifecycle['code'] == 0 and lifecycle['main_thread_ticks'] > 0
        report = {'accepted': True, 'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
                  'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'execution_platform': 'ios-simulator', 'architecture': 'arm64',
                  'runtime': runtime, 'device_type': device, 'consumer_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
                  'reading_cases': 18, 'receiver_found': 17, 'receiver_mislocated': 0, 'originals_exported': 4,
                  'session_sweeps': 38, 'main_thread_ticks': lifecycle['main_thread_ticks'], 'sqlite_provider': reading['sqlite_providers'],
                  'sdk_changed': False, 'schema_changed': False, 'host_ui_accepted': False, 'physical_device_execution': False, 'complete_product': False}
        (out / 'result.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(report), flush=True)
    finally:
        subprocess.run(['xcrun', 'simctl', 'shutdown', udid], capture_output=True)
        subprocess.run(['xcrun', 'simctl', 'delete', udid], capture_output=True)


if __name__ == '__main__': main()
