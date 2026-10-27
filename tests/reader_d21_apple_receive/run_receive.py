# SPDX-License-Identifier: MIT
"""Actions-only same-source native receive owners and three-target UI over HTTPS."""
import argparse, base64, hashlib, json, os, secrets, subprocess, sys, time, plistlib, ssl, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests/apple_host/account'))
from check_account import with_fixture
sys.path.insert(0, str(ROOT / 'tools'))
from apple_swift import flags
from check_apple_product import inspect
sys.path.insert(0, str(ROOT / 'tests/apple_host'))
from collect_evidence import load_results
assert os.environ.get('GITHUB_ACTIONS') == 'true' and sys.platform == 'darwin'
p = argparse.ArgumentParser(); p.add_argument('--platform', required=True); platform = p.parse_args().platform
out = ROOT / 'build/d21-receive' / platform; out.mkdir(parents=True)
result = {'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'], 'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'platform': platform, 'physical_device': False, 'accepted': False, 'commands': []}
def run(argv, role, env=None):
    print('D21 PHASE ' + role, flush=True)
    with (out / (role + '.log')).open('wb') as log:
        value = subprocess.run(list(map(str, argv)), stdout=log, stderr=subprocess.STDOUT, env=env, timeout=4800)
    result['commands'].append({'role': role, 'exit': value.returncode})
    if value.returncode:
        print((out / (role + '.log')).read_text(errors='replace')[-18000:], flush=True)
        raise RuntimeError(role + ' failed')
sdks = {}
for target in ('macos', 'iphonesimulator'):
    roots = list((ROOT / 'sdk-input').glob('team24-apple-sdk-' + target + '-*')); assert len(roots) == 1
    identity = json.loads((roots[0] / 'wave3-packages.json').read_text())
    assert all(identity[k] == result[k] for k in ('source_sha', 'run_id', 'attempt'))
    sdks[target] = roots[0]
password = secrets.token_hex(16)
auth = 'Basic ' + base64.b64encode(('reader:' + password).encode()).decode()
env = dict(os.environ, READER_ACCOUNT_TEST_PASSWORD=password)
try:
    # The producer artifact is also downloaded to its original installation
    # layout for the public flags helper's strict prefix check. No manifest edits.
    mac = ROOT / 'build/raw3-ios-sdk/macos'
    identity = json.loads((mac / 'wave3-packages.json').read_text())
    assert all(identity[k] == result[k] for k in ('source_sha', 'run_id', 'attempt'))
    sdk = mac / 'sdk'; products = mac / 'raw-products' 
    consumer = out / 'receive-review'
    run(['xcrun', 'swiftc', '-swift-version', '5', '-parse-as-library', '-O', '-I', sdk / 'include', '-L', sdk / 'lib', '-lexreader', '-Xlinker', '-rpath', '-Xlinker', sdk / 'lib', 'examples/apple/HostSDK.swift', 'examples/apple/HostCatalog.swift', 'examples/apple/HostAccount.swift', 'tests/reader_d21_apple_receive/ReceiveReview.swift', '-o', consumer, *flags(str(sdk), str(products), True)], 'native-owner-build')
    source = out / 'remote.txt'; source.write_text('D21 remote original readable content.\n' * 300)
    resources = out / 'resources'; run([sys.executable, 'tests/apple_host/prepare_fixtures.py', '--resources', resources], 'fixtures')
    destination = 'platform=macOS'; scheme = 'EXReaderHost-macOS'; target = 'macos'; signing = 'YES'
    if platform != 'macos':
        target = 'iphonesimulator'; scheme = 'EXReaderHost-iOS'; signing = 'NO'
        devices = json.loads(subprocess.check_output(['xcrun', 'simctl', 'list', 'devices', 'available', '--json']))
        prefix = 'iPhone' if platform == 'iphone' else 'iPad'
        runtime, name, udid = max((r, d['name'], d['udid']) for r, rows in devices['devices'].items() for d in rows if d.get('isAvailable') and d['name'].startswith(prefix))
        subprocess.run(['xcrun', 'simctl', 'shutdown', udid], capture_output=True)
        run(['xcrun', 'simctl', 'erase', udid], 'erase'); run(['xcrun', 'simctl', 'boot', udid], 'boot'); run(['xcrun', 'simctl', 'bootstatus', udid, '-b'], 'boot-ready')
        destination = 'platform=iOS Simulator,id=' + udid
        result['device'] = {'name': name, 'runtime': runtime, 'udid': udid}
    def consume(root, entries, requests, cert):
        migration = ROOT / 'apps/reader/store/001_catalog.sql'
        run([consumer, 'seed', root, out / 'seed', migration, source], 'seed-upload', env)
        run([consumer, 'receive', root, out / 'receiver', migration, source], 'native-receive', env)
        objects = [key for key in entries if '/objects/' in key]
        assert len(objects) == 1
        key = objects[0]; original = entries[key]
        try:
            entries[key] = b'X' * len(original)
            run([consumer, 'fault', root, out / 'receiver', migration, source], 'hash-fault-preserves-local', env)
            class InterruptedBytes(bytes):
                def __len__(self): return len(original)
            entries[key] = InterruptedBytes(original[:len(original)//2])
            run([consumer, 'fault', root, out / 'receiver', migration, source], 'interrupted-response-preserves-local', env)
            class DelayedBytes(bytes):
                def __len__(self): time.sleep(0.5); return super().__len__()
            entries[key] = DelayedBytes(original)
            run([consumer, 'cancel', root, out / 'receiver', migration, source], 'cancel-in-flight-download', env)
        finally:
            entries[key] = original
        run([consumer, 'retry', root, out / 'receiver', migration, source], 'restored-original-retry', env)
        if platform != 'macos': run(['xcrun', 'simctl', 'keychain', udid, 'add-root-cert', cert], 'simulator-trust')
        # CI-only controller drives faults in the real app sandbox and HTTPS
        # fixture. Product UI and transport remain unmodified.
        controls = []
        control_token = secrets.token_hex(16)
        original_entries = dict(entries)
        class Control(BaseHTTPRequestHandler):
            def log_message(self, *unused): pass
            def do_POST(self):
                action = self.path.strip('/')
                if self.headers.get('Authorization') != control_token:
                    self.send_error(403); return
                try:
                    if action == 'offline':
                        entries.clear()
                    elif action == 'restore':
                        entries.clear(); entries.update(original_entries)
                    else:
                        if platform == 'macos':
                            app_root = Path.home() / 'Library/Application Support/EXReader'
                        else:
                            container = Path(subprocess.check_output(['xcrun', 'simctl', 'get_app_container', udid, 'org.exreader.host', 'data'], text=True).strip())
                            app_root = container / 'Library/Application Support/EXReader'
                        profiles = json.loads((app_root / 'accounts.json').read_text())
                        matches = [p for p in profiles if p['root'] == root]
                        assert len(matches) == 1
                        cache = app_root / 'accounts' / matches[0]['id'] / 'sync' / (hashlib.sha256(original).hexdigest() + '.txt')
                        assert cache.parent.is_dir()
                        if cache.exists(): cache.unlink()
                        entries.clear(); entries.update(original_entries)
                        if action == 'corrupt':
                            cache.write_bytes(b'damaged local cache retained as evidence')
                            entries[key] = b'X' * len(original)
                        elif action == 'interrupt': entries[key] = InterruptedBytes(original[:len(original)//2])
                        elif action == 'delay':
                            class UIDelayedBytes(bytes):
                                def __len__(self): time.sleep(3); return super().__len__()
                            entries[key] = UIDelayedBytes(original)
                        elif action != 'missing': raise RuntimeError('unknown fixture control')
                    controls.append({'action': action, 'ok': True})
                    self.send_response(200); self.send_header('Content-Length', '2'); self.end_headers(); self.wfile.write(b'OK')
                except Exception as error:
                    controls.append({'action': action, 'ok': False, 'error': str(error)})
                    self.send_error(500)
        controller = ThreadingHTTPServer(('127.0.0.1', 0), Control); controller.daemon_threads = True
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); context.load_cert_chain(cert, cert.with_suffix('.key'))
        controller.socket = context.wrap_socket(controller.socket, server_side=True)
        threading.Thread(target=controller.serve_forever, daemon=True).start()
        control_root = 'https://127.0.0.1:' + str(controller.server_port) + '/'
        tests = out / 'ui'; tests.mkdir()
        template = (ROOT / 'tests/reader_d21_apple_receive/ReceiveUITests.swift').read_text()
        (tests / 'ReceiveUITests.swift').write_text(template.replace('__D21_ROOT__', root).replace('__D21_PASSWORD__', password).replace('__D21_CONTROL__', control_root).replace('__D21_TOKEN__', control_token))
        project = out / 'project'
        run(['ruby', 'tests/reader_team24_apple/make_project.rb', project, resources, tests, 'wave3'], 'project')
        chosen = sdks[target]
        try:
            run(['xcodebuild', 'test', '-project', project / 'EXReaderHost.xcodeproj', '-scheme', scheme, '-destination', destination, '-derivedDataPath', out / 'derived', '-resultBundlePath', out / 'receive.xcresult', '-parallel-testing-enabled', 'NO', 'EXR_SDK_DIR=' + str(chosen / 'sdk'), 'EXR_PRODUCTS_DIR=' + str(chosen / 'raw-products'), 'CODE_SIGNING_ALLOWED=' + signing], 'native-ui')
        finally:
            controller.shutdown(); controller.server_close()
            (out / 'ui-fault-controls.json').write_text(json.dumps(controls, indent=2))
            (out / 'https-requests.json').write_text(json.dumps(requests, indent=2))
        assert [x['action'] for x in controls if x['ok']] == ['corrupt', 'interrupt', 'delay', 'missing', 'offline', 'restore']
        suffix = 'Debug' if platform == 'macos' else 'Debug-iphonesimulator'
        app = out / 'derived/Build/Products' / suffix / 'EXReaderHost.app'
        info = plistlib.loads((app / ('Contents/Info.plist' if platform == 'macos' else 'Info.plist')).read_bytes())
        assert info['EXRSourceSHA'] == result['source_sha'] and info['CFBundleIdentifier'] == 'org.exreader.host'
        binary = app / ('Contents/MacOS/EXReaderHost' if platform == 'macos' else 'EXReaderHost')
        mapping = out / 'derived/Build/Products' / suffix / 'EXReaderHost.link.map'
        result['program'] = {'sha256': hashlib.sha256(binary.read_bytes()).hexdigest(), 'bytes': binary.stat().st_size,
                             'bundle_source_sha': info['EXRSourceSHA'], 'bundle_id': info['CFBundleIdentifier']}
        result['installed_sdk_checker'] = inspect(binary, mapping, selector_bytes_candidate=True)
        result['cases'] = load_results(out / 'receive.xcresult')
        assert len(result['cases']) == 1 and all(case['result'] == 'Passed' for case in result['cases'])
        run(['ditto', '-c', '-k', '--sequesterRsrc', '--keepParent', app, out / 'receive-program.zip'], 'package-native-program')
        run([consumer, 'seed', root, out / 'second-author', migration, source], 'independent-concurrent-author', env)
        run([consumer, 'conflict', root, out / 'receiver', migration, source], 'concurrent-history-keeps-local', env)
        (out / 'https-requests.json').write_text(json.dumps(requests, indent=2))
        assert any(x['method'] == 'GET' and '/objects/' in x['path'] and x['authenticated'] for x in requests)
        result['service_mode'] = 'continuous HTTPS service across seed, owner receive, and UI'
    with_fixture(out / 'tls', auth, consume, shard_delay=0)
    result['accepted'] = True
finally:
    (out / 'result.json').write_text(json.dumps(result, indent=2))
