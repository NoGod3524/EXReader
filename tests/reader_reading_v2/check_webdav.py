# SPDX-License-Identifier: MIT
"""Actions-only real SDK originals/captures over the installed native TLS client."""
import argparse
import base64
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import sqlite3
import ssl
import subprocess
import sys
import threading
import uuid
sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_sdk import EXPECTED
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'reader_reading_state'))
from check_reading_state import sqlite_providers


def main():
    p = argparse.ArgumentParser()
    for name in ('probe', 'fixtures', 'font', 'link-map', 'output'): p.add_argument('--' + name, required=True, type=Path)
    a = p.parse_args(); assert os.environ.get('GITHUB_ACTIONS') == 'true'
    out = a.output.resolve(); out.mkdir(parents=True)
    certs = out / 'certificates'; certs.mkdir()
    key, cert = certs / 'server.key', certs / 'server.crt'
    subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
                    '-keyout', str(key), '-out', str(cert), '-subj', '/CN=localhost',
                    '-addext', 'subjectAltName=DNS:localhost,IP:127.0.0.1'], check=True, capture_output=True)
    subprocess.run(['certutil', '-addstore', '-f', 'Root', str(cert)] if os.name == 'nt' else
                   ['sudo', 'cp', str(cert), '/usr/local/share/ca-certificates/reader-v2-roundtrip.crt'], check=True, capture_output=True)
    if os.name != 'nt': subprocess.run(['sudo', 'update-ca-certificates'], check=True, capture_output=True)
    secret = uuid.uuid4().hex
    auth = 'Basic ' + base64.b64encode(('reading-v2:' + secret).encode()).decode()
    entries, directories, requests = {}, {'/dav/'}, []
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'
        def log_message(self, *args): pass
        def send(self, code, body=b''):
            self.send_response(code); self.send_header('Content-Length', str(len(body)))
            self.send_header('Connection', 'close'); self.end_headers(); self.close_connection = True
            with lock:
                requests.append({'method': self.command, 'path': self.path, 'status': code,
                                 'authenticated': self.headers.get('Authorization') == auth,
                                 'depth': self.headers.get('Depth'), 'if_none_match': self.headers.get('If-None-Match')})
            try: self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError, ssl.SSLError): pass
        def authorized(self):
            if self.headers.get('Authorization') == auth: return True
            self.send(401); return False
        def do_MKCOL(self):
            if not self.authorized(): return
            with lock:
                exists = self.path in directories
                parent = self.path.rstrip('/').rsplit('/', 1)[0] + '/'
                code = 405 if exists else 409 if parent not in directories else 201
                if code == 201: directories.add(self.path)
            self.send(code)
        def do_PUT(self):
            count = int(self.headers['Content-Length']); assert 0 < count <= 128 * 1024 * 1024
            body = self.rfile.read(count); assert len(body) == count
            if not self.authorized(): return
            assert self.headers.get('If-None-Match') == '*'
            with lock:
                code = 412 if self.path in entries else 409 if self.path.rsplit('/', 1)[0] + '/' not in directories else 201
                if code == 201: entries[self.path] = body
            self.send(code)
        def do_GET(self):
            if not self.authorized(): return
            with lock: body = entries.get(self.path)
            self.send(404 if body is None else 200, body or b'')
        def do_PROPFIND(self):
            self.rfile.read(int(self.headers.get('Content-Length', 0)))
            if not self.authorized(): return
            assert self.headers.get('Depth') == '1'
            with lock:
                exists = self.path in directories
                children = [(x, True, 0) for x in directories if x.startswith(self.path) and
                            (x == self.path or '/' not in x[len(self.path):].rstrip('/'))]
                children += [(x, False, len(b)) for x, b in entries.items() if x.startswith(self.path) and '/' not in x[len(self.path):]]
            if not exists: self.send(404); return
            rows = ['<d:response><d:href>' + path + '</d:href><d:propstat><d:prop><d:resourcetype>' +
                    ('<d:collection/>' if directory else '') + '</d:resourcetype><d:getcontentlength>' + str(size) +
                    '</d:getcontentlength></d:prop><d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>'
                    for path, directory, size in sorted(children)]
            self.send(207, ('<d:multistatus xmlns:d="DAV:">' + ''.join(rows) + '</d:multistatus>').encode())

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler); server.daemon_threads = True
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); context.load_cert_chain(cert, key)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    try:
        manifest = json.loads((a.fixtures / 'manifest.json').read_text(encoding='utf-8'))
        work = out / 'work'; work.mkdir()
        command = [str(a.probe.resolve()), '--fixtures', str(a.fixtures.resolve()), '--font', str(a.font.resolve()),
                   '--work', str(work), '--report', str(out / 'probe.json'),
                   '--webdav-root', 'https://127.0.0.1:' + str(server.server_port) + '/dav/']
        for role, entry in manifest.items():
            assert hashlib.sha256((a.fixtures / entry['file']).read_bytes()).hexdigest() == entry['sha256']
            command += ['--sha', role + '=' + entry['sha256']]
        done = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', timeout=180,
                              env=dict(os.environ, READER_TEST_AUTH=auth))
        (out / 'probe.log').write_text(done.stdout + '\n' + done.stderr, encoding='utf-8')
        print(done.stdout); print(done.stderr); assert done.returncode == 0, 'native SDK/WebDAV roundtrip refused'
        report = json.loads((out / 'probe.json').read_text(encoding='utf-8'))
        assert report['native_webdav'] is True and report['originals_exported'] == 4 and report['network_pushed'] == 22
        assert report['network_pulled'] >= 22 and report['failures'] == 0 and report['checks'] and all(c['pass'] is True for c in report['checks'])
        assert [c['id'] for c in report['cases']] == EXPECTED and report['receiver_found'] == 17 and report['receiver_mislocated'] == 0
        for case in report['cases']:
            assert case['state'] == ('AMBIGUOUS' if case['id'] == 'txt-ambiguous' else 'FOUND')
        objects = {path: body for path, body in entries.items() if '/objects/' in path}
        revisions = {path: body for path, body in entries.items() if '/revisions/' in path}
        assert len(objects) == 4 and len(revisions) == 22
        for role in ('txt', 'epub', 'pdf', 'cbz'):
            entry = manifest[role]; digest = entry['sha256']; fmt = entry['file'].rsplit('.', 1)[1]
            path = '/dav/exreader-sync-v1/objects/' + digest[:2] + '/' + digest + '.' + fmt
            assert hashlib.sha256(objects[path]).hexdigest() == digest and len(objects[path]) == entry['bytes']
            assert (work / 'A-originals' / (digest + '.' + fmt)).read_bytes() == objects[path]
            assert (work / 'B-cache' / (digest + '.' + fmt)).read_bytes() == objects[path]
        for path, body in revisions.items():
            value = json.loads(body); leaf = path.rsplit('/', 1)[1]
            assert re.fullmatch('[0-9a-f]{32}-[0-9a-f]{64}\\.json', leaf)
            assert leaf == value['id'] + '-' + hashlib.sha256(body).hexdigest() + '.json'
        for case in report['cases']:
            leaf = case['revision_id'] + '-' + case['wire_sha256'] + '.json'
            body = revisions['/dav/exreader-sync-v1/revisions/' + case['revision_id'][:2] + '/' + leaf]
            assert len(body) == case['wire_bytes'] and json.loads(body)['payload']['location']['anchor_version'] == 2
        with sqlite3.connect(work / 'A-product.sqlite') as db:
            assert db.execute('SELECT count(*) FROM reader_outbox').fetchone() == (0,)
        with sqlite3.connect(work / 'B-product.sqlite') as db:
            assert db.execute('SELECT count(*) FROM reader_revisions').fetchone() == (22,)
            assert db.execute('SELECT count(*) FROM reader_outbox').fetchone() == (0,)
        assert requests and all(r['authenticated'] for r in requests)
        assert all(r['if_none_match'] == '*' for r in requests if r['method'] == 'PUT')
        assert all(r['depth'] == '1' for r in requests if r['method'] == 'PROPFIND')
        assert any(r['method'] == 'PUT' and r['status'] == 412 for r in requests)
        providers = sqlite_providers(a.link_map.read_text(encoding='utf-8', errors='replace'))
        assert len(providers) == 1 and 'reader_catalog_sqlite' in providers[0], providers
        (out / 'native-requests.json').write_text(json.dumps(requests, indent=2) + '\n', encoding='utf-8')
        for path in out.rglob('*'):
            if path.is_file() and path.suffix != '.key':
                data = path.read_bytes(); assert secret.encode() not in data and auth.encode() not in data
        summary = {'accepted': True, 'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
                   'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'platform': sys.platform, 'cases': report['cases'],
                   'receiver_found': 17, 'receiver_mislocated': 0, 'originals_exported': 4, 'network_pushed': 22,
                   'network_pulled': report['network_pulled'], 'request_count': len(requests), 'sqlite_providers': providers,
                   'consumer_sha256': hashlib.sha256(a.probe.read_bytes()).hexdigest(), 'sdk_changed': False,
                   'schema_changed': False, 'host_ui_accepted': False, 'six_platform_accepted': False, 'complete_product': False,
                   'scope': 'real SDK original export, native HTTPS fixture and second-library import/resolve'}
        (out / 'result.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8'); print(json.dumps(summary), flush=True)
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)


if __name__ == '__main__': main()
