"""Actions-only real 3.40 Activity produces records and sends exact bytes over TLS."""
import argparse
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import traceback
import zipfile

assert os.environ.get('GITHUB_ACTIONS') == 'true'
sys.path.insert(0, 'tests/reader_session_android')
from run_roundtrip import Dav

p = argparse.ArgumentParser()
for key in ('fixture', 'fixtures', 'output'):
    p.add_argument('--' + key, type=Path, required=True)
a = p.parse_args()
a.output.mkdir(parents=True, exist_ok=True)
package = 'org.exreader.host'
identity = {key: os.environ[value] for key, value in (
    ('source_sha', 'GITHUB_SHA'), ('run_id', 'GITHUB_RUN_ID'), ('attempt', 'GITHUB_RUN_ATTEMPT'))}
user, password = 'android340-' + secrets.token_hex(12), secrets.token_hex(32)
auth = 'Basic ' + base64.b64encode((user + ':' + password).encode()).decode()
sensitive = [value.encode() for value in (user, password, auth)]
server = Dav(a.fixture, auth)
assert not server.entries, 'server must start without revisions or originals'
report = {**identity, 'accepted': False, 'scope': 'TXT progress, bookmark, selection annotation and note edit',
          'historical_host_sha': '047648865e509d5835b7d6e1389681e314d94e28',
          'sdk_sha': '9854061be331fe603a1822d9b2b36ee357154927',
          'sdk_version': '3.40.0', 'api': 34, 'abi': 'x86_64', 'physical_device': False}

def digest(data):
    return hashlib.sha256(data).hexdigest()

def adb(*args, input=None, timeout=120):
    return subprocess.check_output(['adb', *map(str, args)], input=input,
                                   stderr=subprocess.STDOUT, timeout=timeout)

def private(path):
    return adb('exec-out', 'run-as', package, 'cat', 'files/' + path)

def save(path, data):
    target = a.output / path
    target.parent.mkdir(parents=True, exist_ok=True)
    assert not any(value in data for value in sensitive), 'credential found in evidence'
    target.write_bytes(data)
    return {'file': path, 'bytes': len(data), 'sha256': digest(data)}

def push(file, destination):
    temporary = '/data/local/tmp/android340-' + digest(destination.encode())
    adb('push', file, temporary)
    adb('exec-out', 'run-as', package, 'mkdir', '-p', 'files/' + str(Path(destination).parent))
    adb('exec-out', 'run-as', package, 'cp', temporary, 'files/' + destination)

try:
    apk = Path('examples/android/app/build/outputs/apk/debug/app-debug.apk')
    apk_bytes = apk.read_bytes()
    app_identity = save('identity/app-debug.apk', apk_bytes)
    test_apk = Path('build/android340-sender/test-apks/sender.apk')
    test_identity = save('identity/sender-test.apk', test_apk.read_bytes())
    adb('install', '-r', '-t', apk)
    adb('install', '-r', '-t', test_apk)
    installed = adb('shell', 'pm', 'path', package).decode().strip().splitlines()
    assert len(installed) == 1 and installed[0].startswith('package:')
    installed_path = installed[0][len('package:'):]
    actual_apk = adb('exec-out', 'cat', installed_path)
    assert actual_apk == apk_bytes, 'installed APK differs from built APK'
    assert adb('shell', 'pm', 'clear', package).strip() == b'Success'
    adb('shell', 'am', 'start', '-W', '-n', package + '/.MainActivity')
    adb('shell', 'am', 'force-stop', package)
    manifest = json.loads((a.fixtures / 'manifest.json').read_bytes())
    sender_input = {**manifest, 'books': [row for row in manifest['books'] if row['role'] == 'txt']}
    assert len(sender_input['books']) == 1
    for row in sender_input['books']:
        data = (a.fixtures / row['file']).read_bytes()
        assert len(data) == row['bytes'] and digest(data) == row['sha256']
        push(a.fixtures / row['file'], 'reading-fixtures/' + row['file'])
    adb('shell', f"run-as {package} sh -c 'cat > files/reading-input.json'",
        input=json.dumps(sender_input, ensure_ascii=False).encode())
    port = server.server.server_port
    adb('reverse', f'tcp:{port}', f'tcp:{port}')
    payload = json.dumps({'root': f'https://127.0.0.1:{port}/dav/', 'user': user, 'password': password}).encode()
    adb('shell', f"run-as {package} sh -c 'cat > files/android340-account.json'", input=payload)
    command = ['shell', 'am', 'instrument', '-w', '-r']
    for key, value in identity.items():
        command.extend(('-e', key, value))
    command += [package + '.test/' + package + '.Android340SenderTest']
    process = subprocess.run(['adb', *command], capture_output=True, timeout=1500)
    save('instrumentation.txt', process.stdout + process.stderr)
    raw = private('android340-sender-report.json')
    ui = json.loads(raw)
    save('ui/report.json', raw)
    for observation in ui['observations']:
        save('ui/' + observation['name'] + '.png', private('reading-captures/' + observation['name'] + '.png'))
    assert process.returncode == 0 and b'ANDROID340_SENDER_PASS' in process.stdout
    assert b'INSTRUMENTATION_CODE: -1' in process.stdout and ui['passed'] is True
    assert all(ui[key] == value for key, value in identity.items())
    assert ui['sdk_version'] == '3.40.0'
    assert [row['name'] for row in ui['checks']] == [
        'public_sdk_import_originals_without_prefilled_records', 'actual_txt_ui_progress_and_bookmark',
        'actual_txt_gesture_annotation_and_ui_edit', 'actual_ui_authenticated_https_sync']
    assert all(row['pass'] is True for row in ui['checks'])
    maps = ui['loaded_sdk']['maps']
    runtime = ui['loaded_sdk']['runtime']
    assert runtime[0] == '3.40.0' and runtime[1] == runtime[2]
    assert installed_path in maps or str(Path(installed_path).parent) in maps
    assert 'libexreader.so' in runtime[1]
    with zipfile.ZipFile(io.BytesIO(actual_apk)) as archive:
        libraries = []
        for name in ('lib/x86_64/libexreader.so', 'lib/x86_64/libexreader_jni.so', 'lib/x86_64/libexreader_host.so'):
            data = archive.read(name)
            libraries.append({'apk_entry': name, 'bytes': len(data), 'sha256': digest(data)})
        loaded_path = runtime[1]
        if '!/' in loaded_path:
            container, member = loaded_path.split('!/', 1)
            assert container == installed_path and member == 'lib/x86_64/libexreader.so'
            loaded_sdk = archive.read(member)
        else:
            assert loaded_path in maps and loaded_path.startswith(str(Path(installed_path).parent) + '/')
            loaded_sdk = adb('exec-out', 'run-as', package, 'cat', loaded_path)
        assert loaded_sdk == archive.read('lib/x86_64/libexreader.so')
        loaded_sdk_identity = {'loaded_path': loaded_path, 'bytes': len(loaded_sdk), 'sha256': digest(loaded_sdk)}
    before = json.loads(private('android340-before-sync.json'))
    after = json.loads(private('android340-after-sync.json'))
    save('state/before.json', private('android340-before-sync.json'))
    save('state/after.json', private('android340-after-sync.json'))
    assert before['reader_revisions'] == after['reader_revisions'], 'sync mutated original revision wire'
    revisions = []
    parsed = {}
    with server.lock:
        entries, requests = dict(server.entries), list(server.requests)
    for row in before['reader_revisions']:
        revision_id, kind, key, operation, wire, wire_sha = row
        raw = wire.encode('utf-8')
        assert digest(raw) == wire_sha
        value = json.loads(raw)
        assert value['id'] == revision_id and value['entity_kind'] == kind and value['entity_key'] == key
        remote_path = f'/dav/exreader-sync-v1/revisions/{revision_id[:2]}/{revision_id}-{wire_sha}.json'
        assert entries[remote_path] == raw, 'remote bytes differ from actual persisted app revision'
        proof = [request for request in requests if request['method'] == 'PUT' and request['path'] == remote_path
                 and request['authorization_sha256'] == digest(auth.encode()) and request.get('body_sha256') == wire_sha
                 and request.get('response') == 201 and request.get('stored') is True]
        assert proof, 'revision lacks authenticated app PUT proof'
        entry = save('bundle/revisions/' + revision_id + '.json', raw)
        revisions.append({**entry, 'id': revision_id, 'entity_kind': kind, 'entity_key': key,
                          'parents': value['parents'], 'remote_path': remote_path})
        parsed[revision_id] = value
    assert revisions
    assert len(parsed) == len(revisions)
    for value in parsed.values():
        for parent in value['parents']:
            assert parent in parsed and parsed[parent]['entity_kind'] == value['entity_kind']
            assert parsed[parent]['entity_key'] == value['entity_key']
    visited, visiting = set(), set()
    def visit(revision_id):
        assert revision_id not in visiting, 'revision parent cycle'
        if revision_id in visited:
            return
        visiting.add(revision_id)
        for parent in parsed[revision_id]['parents']:
            visit(parent)
        visiting.remove(revision_id)
        visited.add(revision_id)
    for revision_id in parsed:
        visit(revision_id)
    books = json.loads(private('android340-books.json'))
    txt = next(row for row in manifest['books'] if row['role'] == 'txt')
    key = 'txt:' + txt['sha256']
    assert books['txt']['sha256'] == txt['sha256']
    assert any(row['id'] == books['txt']['id'] and row['source_sha256'] == txt['sha256'] for row in before['sdk'])
    originals = []
    for row in manifest['books']:
        remote_path = f"/dav/exreader-sync-v1/objects/{row['sha256'][:2]}/{row['sha256']}.{row['format']}"
        if remote_path not in entries:
            continue
        original = (a.fixtures / row['file']).read_bytes()
        assert private('reading-fixtures/' + row['file']) == original and entries[remote_path] == original
        assert any(request['method'] == 'PUT' and request['path'] == remote_path
                   and request['authorization_sha256'] == digest(auth.encode())
                   and request.get('body_sha256') == row['sha256'] and request.get('response') == 201 for request in requests)
        entry = save('bundle/originals/' + row['sha256'] + '.' + row['format'], original)
        originals.append({**entry, 'role': row['role'], 'format': row['format'], 'book_key': row['format'] + ':' + row['sha256']})
    assert any(row['book_key'] == key for row in originals)
    assert any(value['entity_kind'] == 'book' and value['entity_key'] == key for value in parsed.values())
    assert any(value['entity_kind'] == 'progress' and value['entity_key'] == key for value in parsed.values())
    annotations = [value for value in parsed.values() if value['entity_kind'] == 'annotation' and value['entity_key'].startswith(key + ':')]
    assert len(annotations) == 3, 'exactly bookmark + annotation + UI edit revisions required'
    # Exact selectors/parser are retained in original revision bytes, never regenerated.
    reading = [value for value in parsed.values() if value['entity_kind'] in ('progress', 'annotation')]
    assert all(value['payload']['location']['parser_version'] == 'exreader-sdk-3.40.0' for value in reading)
    original_captures = []
    for label in ('progress', 'bookmark', 'annotation', 'edit'):
        raw = private('android340-request-' + label + '.json')
        request = json.loads(raw)
        revision = parsed[request['revision']]
        assert request['book'] == key and request['sdk_book'] == books['txt']['id']
        assert revision['parents'] == request['expected']
        location = revision['payload']['location']
        capture = request['capture']
        if label == 'edit':
            assert capture is None and len(request['expected']) == 1
            assert location == parsed[request['expected'][0]]['payload']['location']
            assert revision['payload']['text'] == request['body']
        else:
            assert capture is not None
            mode, unit, start, end = map(int, capture['numbers'])
            assert mode == 1 and location['mode'] == 'reflow_global'
            route = capture['route']
            assert route[0] == key and route[1] == location['parser_version'] == 'exreader-sdk-3.40.0'
            assert route[2] is None and route[3] is None
            selector = location['selector']
            assert selector['start'] == start and selector['end'] == end and selector['chapter'] == route[4]
            for index, name in enumerate(('exact', 'prefix', 'suffix')):
                captured = capture['selectors'][index]
                # The unchanged historical codec maps nullable prefix/suffix to
                # empty strings. Preserve the original null tag in this request.
                original = None if captured is None else base64.b64decode(captured, validate=True)
                assert (b'' if original is None and index > 0 else original) == selector[name].encode('utf-8')
            assert (end == start) if label in ('progress', 'bookmark') else (end > start)
        original_captures.append({**save('capture/' + label + '-request.json', raw), 'label': label,
                                  'revision_id': request['revision'], 'book_key': key})
    assert {row['revision_id'] for row in original_captures} == {value['id'] for value in reading}
    assert len(revisions) == 5, 'one actual book bootstrap and four actual UI reading commits'
    wire_files = sorted(path for path in entries if '/revisions/' in path)
    assert len(wire_files) == len(revisions), 'unaccounted remote revisions'
    for request in requests:
        assert request['authorization_sha256'] == digest(auth.encode())
    save('https/requests.json', (json.dumps(requests, indent=2) + '\n').encode())
    save('https/ca.crt', (a.fixture / 'public/ca.crt').read_bytes())
    bundle = {**report, **identity, 'accepted': True, 'schema': 'android340-real-ui-sender-v1',
        'file_paths_relative_to': 'artifact_root', 'sender': {**identity,
        'historical_host_sha': report['historical_host_sha'], 'sdk_sha': report['sdk_sha'],
        'platform': 'android', 'exr_version': '3.40.0', 'parser_version': 'exreader-sdk-3.40.0',
        'installed_apk_path': installed_path, 'apk': app_identity, 'test_apk': test_identity,
        'packaged_libraries': libraries, 'actual_runtime': runtime, 'loaded_sdk': loaded_sdk_identity},
        'originals': originals, 'revisions': revisions, 'reading_records': reading,
        'original_capture_requests': original_captures,
        'authenticated_https': True, 'complete_parent_graph': True,
        'not_covered': ['EPUB', 'PDF', 'CBZ', 'physical device', 'receiver compatibility']}
    manifest_entry = save('manifest.json', (json.dumps(bundle, indent=2) + '\n').encode())
    report.update(accepted=True, manifest_sha256=manifest_entry['sha256'], originals=len(originals),
                  revisions=len(revisions), packaged_libraries=libraries, loaded_sdk=loaded_sdk_identity, apk=app_identity)
except Exception as error:
    report['failure'] = str(error)
    report['trace'] = traceback.format_exc()
finally:
    server.release.set()
    server.server.shutdown()
    server.server.server_close()
    try:
        adb('shell', 'am', 'force-stop', package)
    except Exception as cleanup_error:
        report['cleanup_failure'] = str(cleanup_error)
        report['accepted'] = False
    # Do not upload account files, TLS private keys or arbitrary private app files.
    for path in a.output.rglob('*'):
        if path.is_file() and any(value in path.read_bytes() for value in sensitive):
            path.write_text('removed generated credential\n')
            report['accepted'] = False
            report['credential_leak'] = str(path)
    save('result.json', (json.dumps(report, indent=2) + '\n').encode())
    print(json.dumps(report), flush=True)
sys.exit(0 if report['accepted'] else 1)
