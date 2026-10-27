# SPDX-License-Identifier: MIT
"""Actions-only iPhone native application relay; no injected history or database writes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import secrets
import shutil
import ssl
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tests/apple_android_relay'))
from relay import start, save
sys.path.insert(0, str(ROOT / 'tests/apple_host'))
from collect_evidence import load_results
sys.path.insert(0, str(ROOT / 'tools'))
from check_apple_product import inspect


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true' and sys.platform == 'darwin'
    p = argparse.ArgumentParser()
    p.add_argument('--phase', required=True, choices=['apple-first', 'apple-return'])
    p.add_argument('--previous', type=Path)
    p.add_argument('--original', type=Path, required=True)
    args = p.parse_args()
    out = ROOT / 'build/apple-android' / args.phase
    out.mkdir(parents=True, exist_ok=True)
    data = {'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
            'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'passed': False,
            'platform': 'iPhone Simulator', 'physical_device': False,
            'same_apple_sandbox': False, 'checks': [], 'commands': []}
    controller = dav = None
    def run(argv, role):
        print('APPLE RELAY ' + role, flush=True)
        with (out / (role + '.log')).open('wb') as log:
            value = subprocess.run(list(map(str, argv)), stdout=log, stderr=subprocess.STDOUT, timeout=4800)
        data['commands'].append({'role': role, 'exit': value.returncode})
        if value.returncode:
            print((out / (role + '.log')).read_text(errors='replace')[-20000:], flush=True)
            raise RuntimeError(role + ' failed')
    try:
        original = args.original.read_bytes()
        data.update(original_sha256=hashlib.sha256(original).hexdigest(), original_bytes=len(original),
                    book_identity='epub:' + hashlib.sha256(original).hexdigest())
        assert data['original_sha256'] == '4f81245d31380ac1d6eafb9a321e3691369bc70985736ae4bccf849a4f784036'
        assert len(original) == 189249
        roots = list((ROOT / 'sdk-input').glob('team24-apple-sdk-iphonesimulator-*'))
        assert len(roots) == 1
        sdk = roots[0]
        identity = json.loads((sdk / 'wave3-packages.json').read_text())
        assert all(identity[k] == data[k] for k in ('source_sha', 'run_id', 'attempt'))
        resources = out / 'resources'
        run([sys.executable, 'tests/apple_host/prepare_fixtures.py', '--resources', resources], 'resources')
        # This changes only the test app resource, not the historical fixture or
        # its frozen assertions. Import still passes through the actual UI/owner.
        shutil.copyfile(args.original, resources / 'Sample.epub')
        assert (resources / 'Sample.epub').read_bytes() == original
        manifest = json.loads((resources / 'manifest.json').read_text())
        manifest['Sample.epub'] = data['original_sha256']
        (resources / 'manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True))
        (out / 'original-identity.json').write_text(json.dumps({
            'source': 'F5 epub-alice', 'manifest_commit': '278d63691a4c73e7aa932d71a40a5938c5427514',
            'sha256': data['original_sha256'], 'bytes': len(original)}, indent=2))
        devices = json.loads(subprocess.check_output(['xcrun', 'simctl', 'list', 'devices', 'available', '--json']))
        runtime, name, udid = max((r, d['name'], d['udid']) for r, rows in devices['devices'].items()
                                  for d in rows if d.get('isAvailable') and d['name'].startswith('iPhone'))
        subprocess.run(['xcrun', 'simctl', 'shutdown', udid], capture_output=True)
        run(['xcrun', 'simctl', 'erase', udid], 'erase')
        run(['xcrun', 'simctl', 'boot', udid], 'boot')
        run(['xcrun', 'simctl', 'bootstatus', udid, '-b'], 'boot-ready')
        data['device'] = {'name': name, 'runtime': runtime, 'udid': udid}
        dav, user, password = start(out, previous=args.previous)
        run(['xcrun', 'simctl', 'keychain', udid, 'add-root-cert', out / 'cert.pem'], 'simulator-trust')
        checkpoints = {}
        token = secrets.token_hex(20)
        class Control(BaseHTTPRequestHandler):
            def log_message(self, *unused): pass
            def do_POST(self):
                if self.headers.get('Authorization') != token:
                    self.send_error(403); return
                name = self.path.strip('/')
                if name not in ('position', 'uploaded'):
                    self.send_error(404); return
                try:
                    container = Path(subprocess.check_output(['xcrun', 'simctl', 'get_app_container', udid,
                                                              'org.exreader.host', 'data'], text=True).strip())
                    root = container / 'Library/Application Support/EXReader'
                    profiles = json.loads((root / 'accounts.json').read_text())
                    matching = [x for x in profiles if x['root'] == dav.base + '/dav/']
                    assert len(matching) == 1
                    state = root / 'accounts' / matching[0]['id'] / 'host-state.json'
                    # Existing product state is read, never rewritten or seeded.
                    payload = json.loads(state.read_text())
                    checkpoints[name] = payload
                    (out / ('host-' + name + '.json')).write_text(json.dumps(payload, indent=2))
                    self.send_response(200); self.send_header('Content-Length', '2'); self.end_headers(); self.wfile.write(b'OK')
                except Exception as error:
                    (out / 'checkpoint-error.txt').write_text(repr(error))
                    self.send_error(500)
        controller = ThreadingHTTPServer(('127.0.0.1', 0), Control)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(out / 'cert.pem', out / 'key.pem')
        controller.socket = context.wrap_socket(controller.socket, server_side=True)
        threading.Thread(target=controller.serve_forever, daemon=True).start()
        tests = out / 'ui'; tests.mkdir(exist_ok=True)
        template = (ROOT / 'tests/apple_android_relay/apple/RelayUITests.swift').read_text()
        substitutions = {'__ROOT__': dav.base + '/dav/', '__USER__': user, '__PASSWORD__': password,
                         '__PHASE__': args.phase, '__TOKEN__': token,
                         '__CONTROL__': 'https://127.0.0.1:' + str(controller.server_port) + '/'}
        for key, value in substitutions.items(): template = template.replace(key, value)
        (tests / 'RelayUITests.swift').write_text(template)
        project = out / 'project'
        run(['ruby', 'tests/reader_team24_apple/make_project.rb', project, resources, tests, 'wave3'], 'project')
        run(['xcodebuild', 'test', '-project', project / 'EXReaderHost.xcodeproj', '-scheme', 'EXReaderHost-iOS',
             '-destination', 'platform=iOS Simulator,id=' + udid, '-derivedDataPath', out / 'derived',
             '-resultBundlePath', out / 'relay.xcresult', '-parallel-testing-enabled', 'NO',
             'EXR_SDK_DIR=' + str(sdk / 'sdk'), 'EXR_PRODUCTS_DIR=' + str(sdk / 'raw-products'),
             'CODE_SIGNING_ALLOWED=NO'], 'native-ui')
        cases = load_results(out / 'relay.xcresult')
        assert len(cases) == 1 and all(c['result'] == 'Passed' for c in cases)
        data['cases'] = cases
        books = checkpoints['position']['books']; assert len(books) == 1
        book = books[0]; location = book['epub_progress']
        data['remote_title'] = book['title']
        assert book['storage'] == 'epub' and not book['unresolved_progress']
        assert location['part'] == book['part'] and location['path'] == book['path']
        assert location['start'] == book['reading_offset']
        data['location'] = location
        data['page_text_sha256'] = book['page_text_sha256']
        data['checks'].append('real app imported/opened EPUB and exposed public SDK saved selector')
        if args.phase == 'apple-first':
            assert location['start'] > 0 or location['part'] > 0
            assert 'uploaded' in checkpoints
            assert any(r['method'] == 'PUT' and '/objects/' in r['path'] and r['authenticated'] for r in dav.requests)
            data['checks'].append('three actual native page actions and explicit save progress followed by application HTTPS sync')
        else:
            previous = json.loads(args.previous.read_text())['data']
            assert previous['original_sha256'] == data['original_sha256']
            expected = previous['location']
            assert all(location[k] == expected[k] for k in ('part', 'path', 'start', 'end'))
            assert any(r['method'] == 'GET' and '/objects/' in r['path'] and r['authenticated'] for r in dav.requests)
            data['expected_location'] = expected
            data['checks'].append('received Android progress; native reading.jump public resolver restored exact part/path/start/end')
        objects = dav.objects()
        assert len(objects) == 1 and next(iter(objects.values())) == original
        data['checks'].append('HTTPS original bytes and SHA256 match fixed F5 real EPUB')
        app = out / 'derived/Build/Products/Debug-iphonesimulator/EXReaderHost.app'
        info = plistlib.loads((app / 'Info.plist').read_bytes())
        assert info['EXRSourceSHA'] == data['source_sha'] and info['CFBundleIdentifier'] == 'org.exreader.host'
        binary = app / 'EXReaderHost'
        data['program'] = {'sha256': hashlib.sha256(binary.read_bytes()).hexdigest(), 'bytes': binary.stat().st_size,
                           'bundle_source_sha': info['EXRSourceSHA'], 'bundle_id': info['CFBundleIdentifier']}
        data['installed_sdk_checker'] = inspect(binary, app.parent / 'EXReaderHost.link.map', selector_bytes_candidate=True)
        run(['ditto', '-c', '-k', '--sequesterRsrc', '--keepParent', app, out / 'program.zip'], 'package')
        data['passed'] = True
        print(json.dumps({'phase': args.phase, 'source_sha': data['source_sha'],
                          'original_sha256': data['original_sha256'], 'original_bytes': data['original_bytes'],
                          'remote_title': data['remote_title'], 'location': data['location'],
                          'checks': data['checks'], 'passed': True}, ensure_ascii=False), flush=True)
        save(dav, out, args.phase, data); dav = None
    finally:
        if controller: controller.shutdown(); controller.server_close()
        if dav:
            (out / 'requests.json').write_text(json.dumps(dav.requests, indent=2))
            dav.server.shutdown(); dav.server.server_close()
        (out / 'result.json').write_text(json.dumps(data, indent=2))

if __name__ == '__main__': main()
