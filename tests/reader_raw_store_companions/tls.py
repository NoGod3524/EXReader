"""Actions-only native TLS transport of genuine raw3 and legacy1/2 wires."""
import argparse
import base64
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import queue
import shutil
import socket
import ssl
import subprocess
import sys
import threading
import time
import uuid
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'webdav'))
from cloud_native import trust_fixture_certificates

def main():
    a = argparse.ArgumentParser()
    for key in ['programs', 'core', 'old-revision', 'output']:
        a.add_argument('--' + key, type=Path, required=True)
    args = a.parse_args()
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    out = args.output.resolve();out.mkdir(parents=True)
    suffix = '.exe' if os.name == 'nt' else ''
    program = lambda name: args.programs.resolve() / ('raw-' + name + suffix)
    core_program = args.core.resolve() / 'candidate-consumer' / ('selector-bytes' + suffix)
    certs = out / 'certificates';certs.mkdir()
    key, cert = certs / 'server.key', certs / 'server.crt'
    subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
                    '-keyout', str(key), '-out', str(cert), '-subj', '/CN=localhost',
                    '-addext', 'subjectAltName=DNS:localhost,IP:127.0.0.1'], check=True, capture_output=True)
    trust_fixture_certificates((cert,), 'raw-store-companions-')
    secret = uuid.uuid4().hex
    auth = 'Basic ' + base64.b64encode(('raw:' + secret).encode()).decode()
    env = dict(os.environ, READER_TEST_AUTH=auth)
    entries, dirs, requests, checks = {}, set(), [], []
    lock = threading.Lock()
    blocked, release = threading.Event(), threading.Event()
    flags = {'pause': False, 'disconnect': ''}
    processes = []

    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'
        def log_message(self, *unused): pass
        def send(self, code, body=b''):
            self.send_response(code);self.send_header('Content-Length', str(len(body)))
            self.send_header('Connection', 'close');self.end_headers();self.close_connection = True
            try: self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError, ssl.SSLError): pass
        def authorized(self):
            if self.command == 'PROPFIND': self.rfile.read(int(self.headers.get('Content-Length', 0)))
            authenticated = self.headers.get('Authorization') == auth
            with lock: requests.append({'method': self.command, 'path': self.path, 'authenticated': authenticated})
            if not authenticated: self.send(401)
            return authenticated
        def do_MKCOL(self):
            if not self.authorized(): return
            with lock:
                exists = self.path in dirs
                parent = self.path.rstrip('/').rsplit('/', 1)[0] + '/'
                if parent not in dirs and self.path not in dirs: code = 409
                else: dirs.add(self.path);code = 405 if exists else 201
            self.send(code)
        def do_PUT(self):
            body = self.rfile.read(int(self.headers['Content-Length']))
            if not self.authorized(): return
            assert self.headers.get('If-None-Match') == '*'
            with lock:
                exists = self.path in entries
                if not exists: entries[self.path] = body
            if flags['disconnect'] == self.path:
                flags['disconnect'] = ''
                self.close_connection = True
                try: self.connection.shutdown(socket.SHUT_RDWR)
                except OSError: pass
                self.connection.close()
                return
            self.send(412 if exists else 201)
        def do_GET(self):
            if not self.authorized(): return
            with lock: body = entries.get(self.path)
            self.send(404 if body is None else 200, body or b'')
        def do_PROPFIND(self):
            if not self.authorized(): return
            assert self.headers.get('Depth') == '1'
            if flags['pause']:
                flags['pause'] = False;blocked.set();release.wait(20)
            with lock:
                exists = self.path in dirs
                children = [(x, True, 0) for x in dirs if x.startswith(self.path) and
                            (x == self.path or '/' not in x[len(self.path):].rstrip('/'))]
                children += [(x, False, len(b)) for x, b in entries.items() if x.startswith(self.path) and '/' not in x[len(self.path):]]
            if not exists: self.send(404);return
            rows = []
            for path, directory, size in children:
                rows.append('<d:response><d:href>' + path + '</d:href><d:propstat><d:prop><d:resourcetype>'
                    + ('<d:collection/>' if directory else '') + '</d:resourcetype><d:getcontentlength>'
                    + str(size) + '</d:getcontentlength></d:prop><d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>')
            self.send(207, ('<d:multistatus xmlns:d="DAV:">' + ''.join(rows) + '</d:multistatus>').encode())

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler);server.daemon_threads = True
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(cert, key)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    def url(namespace='dav'):
        dirs.add('/' + namespace + '/')
        return 'https://127.0.0.1:' + str(server.server_port) + '/' + namespace + '/'
    def call(argv, name, expected=None):
        p = subprocess.run(list(map(str, argv)), env=env, capture_output=True, encoding='utf-8', errors='strict', timeout=180)
        (out / (name + '.log')).write_text(p.stdout + p.stderr, encoding='utf-8')
        assert p.returncode == 0, (name, p.returncode, p.stdout, p.stderr)
        if expected is not None:
            value = json.loads(p.stdout)
            assert value['status'] == expected, (name, value)
            return value
        return p.stdout
    def record(name):
        assert name not in checks
        checks.append(name);print('PASS ' + name, flush=True)
    def device(name):
        path = out / name;path.mkdir()
        for part in ['cache', 'originals']: (path / part).mkdir()
        return path
    def sync(path, name, namespace='dav'):
        return call([program('sync'), url(namespace), path / 'catalog.sqlite', path / 'cache', path / 'originals',
                     '0', '-', '100', 'inert-current-position', str(2**64 - 1)], name, 0)
    def revision(path, action, *tail, expected=0, old=False, name=None):
        return call([args.old_revision if old else program('revision'), action, path / 'catalog.sqlite', *tail],
                    name or (path.name + '-' + action), expected)
    def reopen(path, expected, name):
        call([program('bootstrap'), 'check', path, expected], name + '-retained')
        # Every native process has exited. Copy the actual received database into
        # the unchanged sealed probe's expected filename; no synthetic receive.
        shutil.copyfile(path / 'catalog.sqlite', path / 'receiver.sqlite')
        for part in ['progress', 'bookmark', 'highlight']:
            shutil.copyfile(args.core / 'actual' / (part + '.json'), path / (part + '.json'))
        downloaded = path / 'cache' / (pdf_sha + '.pdf')
        assert downloaded.read_bytes() == original
        text = call([core_program, 'reopen', downloaded, path], name + '-sdk-reopen')
        assert 'PASS third process reopen' in text

    class Session:
        def __init__(self, path, account=None):
            self.path = path;self.account = account or str(uuid.uuid4());self.lines = queue.Queue()
            self.trace = path / ('session-' + str(len(processes)) + '.jsonl')
            self.process = subprocess.Popen([str(program('session')), url(), str(path / 'catalog.sqlite'),
                str(path / 'cache'), str(path / 'originals'), self.account, '5000'],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding='utf-8', env=env)
            processes.append(self.process)
            def reader():
                with self.trace.open('w') as trace:
                    for line in self.process.stdout:
                        trace.write(line);trace.flush();self.lines.put(line)
            threading.Thread(target=reader, daemon=True).start()
            assert json.loads(self.lines.get(timeout=10))['create'] == 0
        def command(self, name):
            self.process.stdin.write(name + '\n');self.process.stdin.flush()
            return json.loads(self.lines.get(timeout=5))
        def wait(self, state):
            deadline = time.monotonic() + 150
            while time.monotonic() < deadline:
                view = self.command('observe')
                if view['state'] == state: return view
                assert view['state'] not in (5, 7), view
                time.sleep(.025)
            raise AssertionError(('session timeout', state, view))
        def close(self):
            assert self.command('close')['code'] == 0
            self.wait(7)
            assert self.command('destroy')['code'] == 0
            assert self.process.wait(timeout=10) == 0
    try:
        a = device('sender');b = device('sync-receiver');c = device('session-receiver')
        packet = args.core / 'actual/packet'
        call([program('bootstrap'), 'seed', a, packet], 'bootstrap-seed')
        expected = a / 'expected'
        wires = {p.name: p.read_bytes() for p in expected.glob('*.json')}
        assert len(wires) == len(list(packet.glob('*.json'))) + 2
        original = (args.core / 'actual/original.pdf').read_bytes()
        pdf_sha = hashlib.sha256(original).hexdigest()
        assert pdf_sha == '5627a430fa04cbe11d38eb2682e336ef21e147d445753ed46ed11a7d5e3167cc'
        (a / 'originals' / (pdf_sha + '.pdf')).write_bytes(original)
        record('typed-book-bootstrap-exact-and-owner-capability-refusals')
        first_wire = sorted(wires)[-1]
        flags['disconnect'] = '/dav/exreader-sync-v1/revisions/00/' + first_wire[:-5] + '-' + hashlib.sha256(wires[first_wire]).hexdigest() + '.json'
        sent = sync(a, 'sender-sync')
        assert sent['pushed'] == len(wires) and not revision(a, 'outbox')['outbox'] and not flags['disconnect']
        actual_remote = {Path(p).name.split('-')[0] + '.json': body for p, body in entries.items() if '/revisions/' in p}
        assert actual_remote == wires
        for filename, wire in wires.items():
            resource = '/dav/exreader-sync-v1/revisions/00/' + filename[:-5] + '-' + hashlib.sha256(wire).hexdigest() + '.json'
            put = next(i for i,r in enumerate(requests) if r['method'] == 'PUT' and r['path'] == resource)
            assert any(r['method'] == 'GET' and r['path'] == resource for r in requests[put+1:])
        record('native-tls-conditional-put-fresh-get-before-ack-including-lost-response')
        received = sync(b, 'receiver-sync')
        assert received['pulled'] == len(wires) and received['originals_verified'] >= 1
        reopen(b, expected, 'sync-receiver')
        record('network-received-raw3-retained-exact-and-public-sdk-found-recapture')
        call([program('guard'), url(), out / 'guard'], 'capability-guard')
        record('old-step-wrong-owner-and-raw-step-on-old-store-refused')
        # A legacy reader must reject genuine new wire without writing anything.
        old_device = device('legacy-refuse')
        v3 = next(p for p in packet.glob('*.json') if b'"anchor_version":3' in p.read_bytes())
        revision(old_device, 'receive', v3, hashlib.sha256(v3.read_bytes()).hexdigest(), expected=4, old=True)
        assert not revision(old_device, 'outbox', old=True)['outbox']
        record('default-old-reader-rejects-raw3-without-outbox')
        s = Session(c)
        flags['pause'] = True;blocked.clear();release.clear()
        assert s.command('start')['code'] == 0 and blocked.wait(10)
        assert s.command('cancel')['code'] == 0
        release.set()
        cancelled = s.wait(3)
        assert cancelled['completed_shards'] == 0
        assert s.command('start')['code'] == 0
        completed = s.wait(4)
        assert completed['completed_shards'] == 256 and completed['sweeps'] == 1
        account = s.account;s.close()
        reopen(c, expected, 'session-receiver')
        record('session-worker-cancel-resume-256-shards-close-and-public-sdk-reopen')
        s = Session(c, account)
        s.command('start');assert s.wait(4)['completed_shards'] == 256;s.close()
        reopen(c, expected, 'session-second-process')
        record('session-owner-worker-second-process-same-account-reopens-exact-history')
        txt = b'A real public SDK text capture has enough context for stable matching.'
        txt_sha = hashlib.sha256(txt).hexdigest()
        legacy_results = []
        for version in (1, 2):
            namespace = 'legacy' + str(version)
            left, right = device(namespace + '-sender'), device(namespace + '-receiver')
            wire = args.core / 'candidate-legacy' / ('v' + str(version) + '-wire.json')
            body = wire.read_bytes();w = json.loads(body)
            assert w['payload']['location']['anchor_version'] == version
            book = {'version': 1, 'id': '00000000000000000000000000009999', 'entity_kind': 'book',
                'entity_key': 'txt:' + txt_sha, 'operation': 'put', 'location_kind': 'none', 'parents': [],
                'payload': {'format': 'txt', 'source_sha256': txt_sha, 'source_bytes': len(txt),
                            'title': 'compatibility', 'author': '', 'favorite': False}}
            file = out / (namespace + '-book.json');file.write_text(json.dumps(book, separators=(',', ':')))
            revision(left, 'local', file);revision(left, 'local', wire)
            (left / 'originals' / (txt_sha + '.txt')).write_bytes(txt)
            assert sync(left, namespace + '-push', namespace)['pushed'] == 2
            assert sync(right, namespace + '-pull', namespace)['pulled'] == 2
            exported = out / (namespace + '-received.json')
            revision(right, 'get', w['id'], exported)
            assert exported.read_bytes() == body and (right / 'cache' / (txt_sha + '.txt')).read_bytes() == txt
            old_store = device(namespace + '-old')
            revision(old_store, 'receive', exported, hashlib.sha256(body).hexdigest(), old=True)
            legacy_results.append({'version': version, 'sha256': hashlib.sha256(body).hexdigest(), 'exact_bytes': True})
        record('raw-clients-transport-legacy1-and2-unchanged-and-old-reader-still-accepts')
        assert requests and all(r['authenticated'] for r in requests)
        assert not list(out.rglob('.reader-sync-*.tmp'))
        record('verified-origin-auth-and-no-transfer-temporaries')
        for file in out.rglob('*'):
            if file.is_file() and file.suffix != '.key':
                body = file.read_bytes()
                assert secret.encode() not in body and auth.encode() not in body, file
        result = {'accepted': True, 'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
            'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'checks': checks, 'count': len(checks),
            'exact_wires': {k: hashlib.sha256(v).hexdigest() for k,v in wires.items()}, 'pdf_sha256': pdf_sha,
            'legacy': legacy_results, 'requests': requests, 'adopted': False, 'actual_hosts': False}
        (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps({k:v for k,v in result.items() if k != 'requests'}), flush=True)
    finally:
        release.set()
        for p in processes:
            if p.poll() is None: p.kill();p.wait(timeout=15)
        server.shutdown();server.server_close()

if __name__ == '__main__': main()

