"""Actual original OFF controls and raw iPhone/iPad UI against installed SDKs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
HERE = ROOT / 'tests/apple_host/raw3/ios/reading'
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / 'tests/apple_host'))
from collect_evidence import load_results
sys.path.insert(0, str(ROOT / 'tests/apple_host/reading'))
from reading_contract import CASES
sys.path.insert(0, str(ROOT / 'tools'))
from check_apple_product import inspect
sys.path.insert(0, str(ROOT / 'tests/apple_host/raw3'))
from tls_fixture import Fixture
from peer import load as load_peer
from validate import observations as load_observations, validate_observations


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true' and sys.platform == 'darwin'
    parser = argparse.ArgumentParser()
    parser.add_argument('--platform', choices=('iphone', 'ipad'), required=True)
    parser.add_argument('--sdk-input', type=Path, required=True)
    args = parser.parse_args()
    args.sdk_input = args.sdk_input.resolve()
    out = ROOT / 'build/raw3-ios' / args.platform
    evidence = out / 'evidence'; evidence.mkdir(parents=True, exist_ok=False)
    resources = out / 'resources'
    commands = []

    def run(argv, name, env=None, timeout=1800):
        print('ACTUAL_MOBILE_PHASE_BEGIN ' + name, flush=True)
        log = evidence / (name + '.log')
        with log.open('wb') as stream:
            value = subprocess.run(list(map(str, argv)), cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT, timeout=timeout)
        commands.append({'name': name, 'argv': list(map(str, argv)), 'exit': value.returncode})
        if value.returncode:
            print('\n'.join(log.read_text(errors='replace').splitlines()[-100:]), flush=True)
            raise RuntimeError('Actual mobile command failed: ' + name)

    sdk_roots = {}
    sdk_proofs = {}
    for target in ('macos', 'iphonesimulator'):
        folders = list(args.sdk_input.glob('raw3-ios-sdk-' + target + '-*'))
        assert len(folders) == 1
        folder = folders[0]
        sdk_roots[target] = folder / 'sdk'
        identity = json.loads((folder / 'raw-identity.json').read_text())
        assert (identity['source_sha'], identity['run_id'], identity['attempt'], identity['target']) == (
            os.environ['GITHUB_SHA'], os.environ['GITHUB_RUN_ID'], os.environ['GITHUB_RUN_ATTEMPT'], target)
        raw = folder / 'raw-products'
        for name, entry in identity['raw_files'].items():
            path = raw / name
            assert path.stat().st_size == entry['bytes'] and digest(path) == entry['sha256']
        sys.path.insert(0, str(ROOT / 'tests/apple_host'))
        from evidence_contract import validate_sdk
        sdk_identity = json.loads((folder / 'sdk-identity.json').read_text())
        validate_sdk(sdk_roots[target], sdk_identity, os.environ['GITHUB_SHA'], os.environ['GITHUB_RUN_ID'], os.environ['GITHUB_RUN_ATTEMPT'], target)
        product = json.loads((raw / 'share/exreader-apple/product.json').read_text())
        assert product['selector_bytes_candidate'] and product['source_sha'] == os.environ['GITHUB_SHA']
        assert product['exact_candidate_family'] == {'EXReaderRevisions': '0.4.0', 'EXReaderReadingState': '0.2.0',
            'EXReaderReadingCommands': '0.2.0', 'EXReaderAnnotationView': '0.2.0',
            'EXReaderCommands': '0.2.0', 'EXReaderSync': '0.2.0', 'EXReaderSession': '0.2.0'}
        sdk_proofs[target] = {'sdk': sdk_identity, 'raw': identity, 'product': product}
    mobile_sdk = sdk_roots['iphonesimulator']
    raw_prefix = mobile_sdk.parent / 'raw-products'
    run([sys.executable, 'tests/apple_host/prepare_fixtures.py', '--resources', resources], 'original-fixtures')
    run([sys.executable, 'tests/apple_host/navigation/prepare_navigation_fixture.py', '--resources', resources], 'navigation-fixtures')
    make_cfi = out / 'make-cfi'
    mac = sdk_roots['macos']
    run(['cc', '-I', mac / 'include', 'tests/apple_host/navigation/make_cfi.c', '-L', mac / 'lib', '-lexreader',
         '-Wl,-rpath,' + str(mac / 'lib'), '-o', make_cfi], 'compile-original-CFI-helper')
    cfi = subprocess.check_output([make_cfi, resources / 'Sample.epub'], cwd=ROOT)
    (out / 'authored-cfi.txt').write_bytes(cfi)
    run([sys.executable, 'tests/apple_host/navigation/prepare_navigation_fixture.py', '--resources', resources,
         '--cfi', out / 'authored-cfi.txt'], 'authored-navigation-fixtures')
    run([sys.executable, 'tests/apple_host/reading/prepare_reading_fixture.py', '--resources', resources], 'original-reading-fixtures')
    shutil.copyfile(ROOT / 'tests/fixtures/pdf-public-text.pdf', resources / 'RawSelectorNUL.pdf')
    assert (resources / 'RawSelectorNUL.pdf').stat().st_size == 8845
    assert digest(resources / 'RawSelectorNUL.pdf') == '5627a430fa04cbe11d38eb2682e336ef21e147d445753ed46ed11a7d5e3167cc'
    peer, wires, originals = load_peer(evidence / 'fixed-peer', resources)
    fixture_hashes = {path.name: digest(path) for path in resources.iterdir() if path.is_file() and path.name != 'manifest.json'}
    (resources / 'manifest.json').write_text(json.dumps(fixture_hashes, indent=2) + '\n')
    shutil.copytree(resources, evidence / 'inputs')
    devices = json.loads(subprocess.check_output(['xcrun', 'simctl', 'list', 'devices', 'available', '--json']))
    prefix = 'iPhone' if args.platform == 'iphone' else 'iPad'
    choices = [(runtime, device['name'], device['udid']) for runtime, values in devices['devices'].items()
               for device in values if device.get('isAvailable') and device['name'].startswith(prefix)]
    runtime, device, udid = max(choices)
    subprocess.run(['xcrun', 'simctl', 'shutdown', udid], capture_output=True)
    run(['xcrun', 'simctl', 'erase', udid], 'erase-isolated-simulator')
    run(['xcrun', 'simctl', 'boot', udid], 'boot-isolated-simulator')
    run(['xcrun', 'simctl', 'bootstatus', udid, '-b'], 'simulator-ready')
    sys.path.insert(0, str(ROOT / 'tests/apple_host/page_theme'))
    from simulator_ready import prepare_service
    prepare_service(udid, evidence)
    destination = 'platform=iOS Simulator,id=' + udid
    (out / 'destination.txt').write_text('\n'.join((destination, udid, device, runtime)) + '\n')
    env = dict(os.environ, EXR_APPLE_SDK_VERSION='3.41.0', EXR_APPLE_PAGE_THEME='ON', EXR_APPLE_RAW3='OFF')
    projects = {}
    for mode in ('control', 'legacy', 'raw'):
        project = out / ('project-' + mode)
        if mode == 'control':
            run(['ruby', 'tests/apple_host/make_xcodeproj.rb', project, resources, ROOT / 'tests/apple_host/reading/ui'], mode + '-project', env=env)
        else:
            run(['ruby', HERE / 'make_project.rb', project, resources, HERE / 'ui', mode], mode + '-project', env=env)
        projects[mode] = project

    def ui(mode, name, case=None, reset=False, extra_env=None):
        if reset: subprocess.run(['xcrun', 'simctl', 'uninstall', udid, 'org.exreader.host'], capture_output=True)
        result = evidence / (name + '.xcresult')
        argv = ['xcodebuild', 'test', '-project', projects[mode] / 'EXReaderHost.xcodeproj', '-scheme', 'EXReaderHost-iOS',
                '-destination', destination, '-derivedDataPath', out / ('derived-' + mode), '-resultBundlePath', result,
                '-parallel-testing-enabled', 'NO', '-test-timeouts-enabled', 'YES', '-default-test-execution-time-allowance', '180' if mode == 'control' else '600',
                '-maximum-test-execution-time-allowance', '300' if mode == 'control' else '600',
                'EXR_SDK_DIR=' + str(mobile_sdk), 'EXR_PRODUCTS_DIR=' + str(raw_prefix), 'CODE_SIGNING_ALLOWED=NO']
        if case: argv += ['-only-testing:EXReaderHostUITests-iOS/RawSelectorUITests/' + case]
        try:
            run(argv, name, env=dict(env, **(extra_env or {})), timeout=2200)
        except BaseException:
            # Failed UI runs still retain their actual container/program. They
            # never produce an accepted report or substitute for a passing case.
            try:
                container = Path(subprocess.check_output(['xcrun', 'simctl', 'get_app_container', udid, 'org.exreader.host', 'data'], text=True).strip())
                source = container / 'Library/Application Support/EXReader'
                if source.exists(): shutil.copytree(source, evidence / ('profile-' + name))
                app = out / ('derived-' + mode) / 'Build/Products/Debug-iphonesimulator/EXReaderHost.app'
                if app.exists(): shutil.copytree(app, evidence / ('failed-program-' + name) / 'EXReaderHost.app')
            except Exception as failure:
                (evidence / (name + '-snapshot-error.txt')).write_text(str(failure) + '\n')
            raise
        cases = load_results(result)
        if mode == 'control':
            assert len(cases) == 7 and all(row['result'] == 'Passed' for row in cases)
            assert all(any(expected in row['name'] for row in cases) for expected in CASES)
            run([sys.executable, 'tests/apple_host/reading/collect_reading_evidence.py', '--platform', args.platform,
                 '--xcresult', result, '--output', evidence / 'original-control',
                 '--app', out / ('derived-' + mode) / 'Build/Products/Debug-iphonesimulator/EXReaderHost.app',
                 '--sdk-root', mobile_sdk, '--sdk-identity', mobile_sdk.parent / 'sdk-identity.json',
                 '--destination', out / 'destination.txt', '--fixtures', resources / 'manifest.json'], 'original-control-contract')
        else:
            assert len(cases) == 1 and case in cases[0]['name'] and cases[0]['result'] == 'Passed'
        app = out / ('derived-' + mode) / 'Build/Products/Debug-iphonesimulator/EXReaderHost.app'
        info = plistlib.loads((app / 'Info.plist').read_bytes())
        assert info['EXRSourceSHA'] == os.environ['GITHUB_SHA'] and info['EXRSDKVersion'] == '3.41.0'
        if mode != 'control': assert info['EXRRawSelectorEnabled'] == (mode == 'raw')
        provider = inspect(app / 'EXReaderHost', app.parent / 'EXReaderHost.link.map', mode == 'raw')
        assert not provider['static_sdk_linked'] and provider['selector_bytes_candidate'] == (mode == 'raw')
        saved_app = evidence / ('program-' + mode)
        if not saved_app.exists():
            shutil.copytree(app, saved_app / 'EXReaderHost.app')
            for suffix in ('', '.symbols.txt', '.dependencies.txt'):
                shutil.copyfile(str(app.parent / 'EXReaderHost.link.map') + suffix, saved_app / ('link.map' + suffix))
        container = Path(subprocess.check_output(['xcrun', 'simctl', 'get_app_container', udid, 'org.exreader.host', 'data'], text=True).strip())
        source = container / 'Library/Application Support/EXReader'
        snapshot = evidence / ('profile-' + name)
        shutil.copytree(source, snapshot)
        run(['xcrun', 'xcresulttool', 'export', 'attachments', '--path', result, '--output-path', evidence / ('attachments-' + name)], name + '-attachments')
        return {'name': name, 'mode': mode, 'case': case, 'cases': cases, 'profile': snapshot.name,
                'xcresult': result.name, 'provider': provider, 'app_sha256': digest(app / 'EXReaderHost')}

    phases = [ui('control', 'original-OFF-seven-cases', reset=True)]
    for name, case in [('raw-ui', 'testRawPDFPointsRangeEditRestoreJumpAndReopen'),
                       ('raw-kill-before', 'testRawTerminationBeforeCommit'), ('raw-kill-after', 'testRawTerminationAfterCommit')]:
        phases.append(ui('raw', name, case, reset=True))
    os.environ['EXR_DAV_IOS_UDID'] = udid
    fixture = Fixture(ROOT / ('build/raw3-ios-private-' + args.platform))
    fixture.auth = None  # Real existing anonymous-account support; no typed secret in XCTest logs.
    try:
        for value in range(256): fixture.directories.add('/dav/exreader-sync-v1/revisions/%02x/' % value)
        fixture.directories.update({'/dav/exreader-sync-v1/', '/dav/exreader-sync-v1/revisions/', '/dav/exreader-sync-v1/objects/'})
        for revision, sha, wire in wires:
            fixture.entries['/dav/exreader-sync-v1/revisions/' + revision[:2] + '/' + revision + '-' + sha + '.json'] = wire
        for key, (row, data) in originals.items():
            fixture.directories.add('/dav/exreader-sync-v1/objects/' + row['sha256'][:2] + '/')
            fixture.entries['/dav/exreader-sync-v1/objects/' + row['sha256'][:2] + '/' + row['sha256'] + '.' + row['format']] = data
        phases.append(ui('raw', 'raw-native-HTTPS', 'testNativeHTTPSRetainedNullAndSourceVersions', reset=True,
                         extra_env={'TEST_RUNNER_EXR_RAW3_IOS_ROOT': fixture.url}))
        assert fixture.requests and all(row['authenticated'] for row in fixture.requests)
        shards = {row['path'].split('/')[-2] for row in fixture.requests if row['method'] == 'PROPFIND' and '/revisions/' in row['path']}
        assert shards == {'%02x' % value for value in range(256)}
        for revision, sha, wire in wires:
            assert fixture.entries['/dav/exreader-sync-v1/revisions/' + revision[:2] + '/' + revision + '-' + sha + '.json'] == wire
        (evidence / 'native-https.json').write_text(json.dumps({'requests': fixture.requests, 'tls_trust_checked': True,
            'simulator_trust_only': True, 'anonymous_account': True, 'inbound_shards': len(shards), 'peer': peer}, indent=2) + '\n')
    finally:
        fixture.close()
    phases.append(ui('legacy', 'legacy-v1-failure', 'testLegacyOFFLeavesActualFailedV1Request', reset=True))
    phases.append(ui('raw', 'raw-retries-original-v1', 'testRawBuildRetainsLegacyV1Failure'))
    observations = validate_observations(evidence, peer)
    for phase in ('raw-ui', 'raw-kill-before', 'raw-kill-after', 'raw-native-HTTPS', 'legacy-v1-failure', 'raw-retries-original-v1'):
        for value in load_observations(evidence, phase):
            assert value['source_sha'] == os.environ['GITHUB_SHA']
            image = value['sdk_images'][0]
            assert sdk_proofs['iphonesimulator']['sdk']['files_sha256']['lib/' + image['name']] == image['sha256']
    result = {'accepted': True, 'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
              'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'platform': args.platform,
              'destination': {'device': device, 'runtime': runtime, 'udid': udid}, 'sdk_proofs': sdk_proofs,
              'phases': phases, 'observations': observations, 'peer': peer, 'commands': commands,
              'physical_device_execution': False, 'complete_product': False, 'android_interop_accepted': False,
              'full_mobile_sync_accepted': False, 'performance_accepted': False}
    result['files'] = {path.relative_to(evidence).as_posix(): {'bytes': path.stat().st_size, 'sha256': digest(path)}
                       for path in evidence.rglob('*') if path.is_file()}
    (evidence / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({key: value for key, value in result.items() if key not in ('commands', 'files', 'sdk_proofs', 'phases')}), flush=True)


if __name__ == '__main__':
    main()
