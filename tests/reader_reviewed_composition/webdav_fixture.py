# SPDX-License-Identifier: MIT
"""Actions-only TLS WebDAV fixture for the module composition gate.

Every object, revision and request of this fixture is created inside the same
job; the self-signed certificate exists only in the temporary runner trust
store. The protocol surface is the one the installed native client uses:
MKCOL, PUT with If-None-Match: *, GET and Depth:1 PROPFIND with Basic auth.
"""
import base64
import os
import ssl
import subprocess
import sys
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def trust_certificate(certificate, prefix='reader-composition-'):
    """Install one fixture-only root certificate in this runner's trust store."""
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'fixture trust is cloud only'
    certificate = Path(certificate)
    if os.name == 'nt':
        command = ['certutil', '-addstore', '-f', 'Root', str(certificate)]
    elif sys.platform == 'darwin':
        command = ['sudo', 'security', 'add-trusted-cert', '-d', '-r', 'trustRoot',
                   '-k', '/Library/Keychains/System.keychain', str(certificate)]
    else:
        command = ['sudo', 'cp', str(certificate), '/usr/local/share/ca-certificates/' + prefix + certificate.name]
    subprocess.run(command, check=True, capture_output=True)
    if os.name != 'nt' and sys.platform != 'darwin':
        subprocess.run(['sudo', 'update-ca-certificates'], check=True, capture_output=True)


def issue_certificate(folder, host='localhost'):
    """One short-lived self-signed certificate with a DNS and an IP SAN."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    key, certificate = folder / 'server.key', folder / 'server.crt'
    result = subprocess.run(
        ['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1', '-sha256',
         '-keyout', str(key), '-out', str(certificate), '-subj', '/CN=' + host,
         '-addext', 'subjectAltName=DNS:' + host + ',IP:127.0.0.1'],
        capture_output=True, check=True)
    (folder / 'openssl.log').write_bytes(result.stdout + result.stderr)
    return key, certificate


class WebDAVFixture:
    """One TLS server, several independent roots, one request journal."""

    def __init__(self, folder, roots=('/dav/',), account='composition', secret=None):
        self.folder = Path(folder)
        self.roots = tuple(roots)
        self.account = account
        self.secret = secret or uuid.uuid4().hex
        self.authorization = 'Basic ' + base64.b64encode(
            (account + ':' + self.secret).encode()).decode()
        self.entries = {}
        self.directories = set(self.roots)
        self.requests = []
        self.lock = threading.Lock()
        self.server = None
        self.thread = None

    # -- lifecycle ---------------------------------------------------------
    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exception):
        self.stop()
        return False

    def start(self):
        key, certificate = issue_certificate(self.folder)
        self.certificate = certificate
        trust_certificate(certificate)
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'

            def log_message(self, *args):
                pass

            def respond(self, code, body=b''):
                self.send_response(code)
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Connection', 'close')
                self.end_headers()
                self.close_connection = True
                with fixture.lock:
                    fixture.requests.append({
                        'method': self.command, 'path': self.path, 'status': code,
                        'authenticated': self.headers.get('Authorization') == fixture.authorization,
                        'depth': self.headers.get('Depth'),
                        'if_none_match': self.headers.get('If-None-Match'),
                        'root': fixture.root_of(self.path)})
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError, ssl.SSLError):
                    pass

            def authorized(self):
                if self.headers.get('Authorization') == fixture.authorization:
                    return True
                self.respond(401)
                return False

            def do_MKCOL(self):
                if not self.authorized():
                    return
                with fixture.lock:
                    exists = self.path in fixture.directories
                    parent = self.path.rstrip('/').rsplit('/', 1)[0] + '/'
                    code = 405 if exists else 409 if parent not in fixture.directories else 201
                    if code == 201:
                        fixture.directories.add(self.path)
                self.respond(code)

            def do_PUT(self):
                count = int(self.headers.get('Content-Length', 0))
                if not 0 < count <= 128 * 1024 * 1024:
                    self.respond(400)
                    return
                body = self.rfile.read(count)
                if not self.authorized():
                    return
                if self.headers.get('If-None-Match') != '*':
                    self.respond(428)
                    return
                with fixture.lock:
                    parent = self.path.rsplit('/', 1)[0] + '/'
                    code = 412 if self.path in fixture.entries else 409 if parent not in fixture.directories else 201
                    if code == 201:
                        fixture.entries[self.path] = body
                self.respond(code)

            def do_GET(self):
                if not self.authorized():
                    return
                with fixture.lock:
                    body = fixture.entries.get(self.path)
                self.respond(404 if body is None else 200, body or b'')

            def do_PROPFIND(self):
                self.rfile.read(int(self.headers.get('Content-Length', 0)))
                if not self.authorized():
                    return
                if self.headers.get('Depth') != '1':
                    self.respond(400)
                    return
                with fixture.lock:
                    exists = self.path in fixture.directories
                    children = [(path, True, 0) for path in fixture.directories
                                if path.startswith(self.path)
                                and (path == self.path or '/' not in path[len(self.path):].rstrip('/'))]
                    children += [(path, False, len(body)) for path, body in fixture.entries.items()
                                 if path.startswith(self.path) and '/' not in path[len(self.path):]]
                if not exists:
                    self.respond(404)
                    return
                rows = ['<d:response><d:href>' + path + '</d:href><d:propstat><d:prop><d:resourcetype>' +
                        ('<d:collection/>' if directory else '') + '</d:resourcetype>' +
                        '<d:getcontentlength>' + str(size) + '</d:getcontentlength></d:prop>' +
                        '<d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>'
                        for path, directory, size in sorted(children)]
                self.respond(207, ('<d:multistatus xmlns:d="DAV:">' + ''.join(rows) +
                                   '</d:multistatus>').encode())

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = True
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certificate, key)
        self.server.socket = context.wrap_socket(self.server.socket, server_side=True)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self

    def stop(self):
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
            self.server = None
        if self.thread is not None:
            self.thread.join(timeout=10)
            self.thread = None

    # -- helpers -----------------------------------------------------------
    @property
    def port(self):
        return self.server.server_port

    def root_of(self, path):
        for root in sorted(self.roots, key=len, reverse=True):
            if path.startswith(root):
                return root
        return ''

    def root_url(self, index=0):
        return 'https://127.0.0.1:' + str(self.port) + self.roots[index]

    def objects(self, root=None):
        return {path: body for path, body in self.entries.items()
                if '/objects/' in path and (root is None or path.startswith(root))}

    def revisions(self, root=None):
        return {path: body for path, body in self.entries.items()
                if '/revisions/' in path and (root is None or path.startswith(root))}

    def redactions(self):
        """Every request of this run, with the session secret removed."""
        return [{k: v for k, v in entry.items()} for entry in self.requests]

    def assert_secret_free(self, folder):
        folder = Path(folder)
        markers = (self.secret.encode(), self.authorization.encode())
        for path in folder.rglob('*'):
            if not path.is_file() or path.suffix in ('.key', '.crt'):
                continue
            data = path.read_bytes()
            for marker in markers:
                assert marker not in data, 'fixture secret leaked into ' + str(path)
