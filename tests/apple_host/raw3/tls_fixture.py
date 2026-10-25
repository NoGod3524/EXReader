"""Actions-only HTTPS DAV fixture; no authorization or private key is retained."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import base64
import os
from pathlib import Path
import ssl
import subprocess
import sys
import threading
import uuid

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tests/webdav'))
from cloud_native import trust_fixture_certificates


class Fixture:
    def __init__(self, private):
        assert os.environ.get('GITHUB_ACTIONS') == 'true'
        private.mkdir(parents=True, exist_ok=False)
        key, cert = private / 'server.key', private / 'server.crt'
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
                        '-keyout', key, '-out', cert, '-subj', '/CN=localhost',
                        '-addext', 'subjectAltName=DNS:localhost,IP:127.0.0.1'], check=True, capture_output=True)
        trust_fixture_certificates((cert,), 'apple-raw3-')
        self.auth = 'Basic ' + base64.b64encode(('raw:' + uuid.uuid4().hex).encode()).decode()
        self.entries, self.directories, self.requests = {}, {'/dav/'}, []
        self.lock = threading.Lock()
        owner = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'
            def log_message(self, *unused): pass
            def reply(self, status, body=b''):
                self.send_response(status); self.send_header('Content-Length', str(len(body)))
                self.send_header('Connection', 'close'); self.end_headers(); self.close_connection = True
                try: self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError, ssl.SSLError): pass
            def authorized(self):
                accepted = self.headers.get('Authorization') == owner.auth
                with owner.lock: owner.requests.append({'method': self.command, 'path': self.path, 'authenticated': accepted})
                if not accepted: self.reply(401)
                return accepted
            def do_MKCOL(self):
                if not self.authorized(): return
                with owner.lock:
                    existed = self.path in owner.directories
                    parent = self.path.rstrip('/').rsplit('/', 1)[0] + '/'
                    if parent not in owner.directories and not existed: code = 409
                    else: owner.directories.add(self.path); code = 405 if existed else 201
                self.reply(code)
            def do_PUT(self):
                body = self.rfile.read(int(self.headers['Content-Length']))
                if not self.authorized(): return
                if self.headers.get('If-None-Match') != '*': self.reply(400); return
                with owner.lock:
                    existed = self.path in owner.entries
                    if not existed: owner.entries[self.path] = body
                self.reply(412 if existed else 201)
            def do_GET(self):
                if not self.authorized(): return
                with owner.lock: body = owner.entries.get(self.path)
                self.reply(404 if body is None else 200, body or b'')
            def do_PROPFIND(self):
                self.rfile.read(int(self.headers.get('Content-Length', 0)))
                if not self.authorized(): return
                if self.headers.get('Depth') != '1': self.reply(400); return
                with owner.lock:
                    if self.path not in owner.directories: rows = None
                    else:
                        children = [(p, True, 0) for p in owner.directories if p.startswith(self.path) and
                                    (p == self.path or '/' not in p[len(self.path):].rstrip('/'))]
                        children += [(p, False, len(b)) for p, b in owner.entries.items() if p.startswith(self.path) and '/' not in p[len(self.path):]]
                        rows = ['<d:response><d:href>' + p + '</d:href><d:propstat><d:prop><d:resourcetype>' +
                                ('<d:collection/>' if directory else '') + '</d:resourcetype><d:getcontentlength>' + str(size) +
                                '</d:getcontentlength></d:prop><d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>'
                                for p, directory, size in children]
                if rows is None: self.reply(404)
                else: self.reply(207, ('<d:multistatus xmlns:d="DAV:">' + ''.join(rows) + '</d:multistatus>').encode())

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = True
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); context.load_cert_chain(cert, key)
        self.server.socket = context.wrap_socket(self.server.socket, server_side=True)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.url = 'https://127.0.0.1:' + str(self.server.server_port) + '/dav/'

    def close(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=5)
