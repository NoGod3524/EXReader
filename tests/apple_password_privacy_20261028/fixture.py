# SPDX-License-Identifier: MIT
"""Synthetic-only loopback TLS server; never a replacement product session."""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import os
import ssl
import subprocess
import threading
from xml.sax.saxutils import escape


@contextmanager
def fixture(folder, authorizations, checkpoint, prefix, lifecycle=None):
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    assert prefix.startswith('/privacy-') and prefix.endswith('/')
    folder.mkdir(parents=True, exist_ok=False)
    cert, key = folder / 'server.crt', folder / 'server.key'
    certificate_command = ['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
                    '-keyout', str(key), '-out', str(cert), '-subj', '/CN=localhost',
                    '-addext', 'subjectAltName=DNS:localhost,IP:127.0.0.1']
    fingerprint_command = ['openssl', 'x509', '-in', str(cert), '-noout', '-fingerprint', '-sha1']
    trust_command = ['sudo', 'security', 'add-trusted-cert', '-d', '-r', 'trustRoot',
                    '-k', '/Library/Keychains/System.keychain', str(cert)]
    if lifecycle is None:
        subprocess.run(certificate_command, check=True, capture_output=True)
        fingerprint = subprocess.check_output(fingerprint_command, text=True).strip().split('=', 1)[1].replace(':', '')
        subprocess.run(trust_command, check=True, capture_output=True)
    else:
        lifecycle.command(certificate_command)
        fingerprint = lifecycle.command(fingerprint_command).stdout.decode().strip().split('=', 1)[1].replace(':', '')
        lifecycle.certificate_delete = ['sudo', 'security', 'delete-certificate', '-Z', fingerprint,
                                       '/Library/Keychains/System.keychain']
        lifecycle.cleanup['certificate'] = 'pending'
        lifecycle.command(trust_command)
    entries, directories, requests, failures = {}, {prefix}, [], []
    lock = threading.RLock()
    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'
        def log_message(self, *unused): pass
        def send(self, code, body=b''):
            self.send_response(code); self.send_header('Content-Length', str(len(body)))
            self.send_header('Connection', 'close'); self.end_headers(); self.close_connection = True
            try: self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError, ssl.SSLError): pass
        def authenticated(self):
            credential = next((name for name, value in authorizations.items() if self.headers.get('Authorization') == value), None)
            with lock: requests.append({'method': self.command, 'path': self.path, 'credential': credential})
            if credential is None: self.send(401)
            return credential is not None
        def do_GET(self):
            if self.path.startswith(prefix + '__privacy__/'):
                try:
                    checkpoint(self.path.removeprefix(prefix + '__privacy__/'), list(requests))
                    self.send(204)
                except Exception as error:
                    failures.append(type(error).__name__); self.send(500)
                return
            if not self.authenticated(): return
            with lock: body = entries.get(self.path)
            self.send(404 if body is None else 200, body or b'')
        def do_MKCOL(self):
            if not self.authenticated(): return
            with lock:
                exists = self.path in directories; directories.add(self.path)
            self.send(405 if exists else 201)
        def do_PUT(self):
            size = int(self.headers.get('Content-Length', '0'))
            if size < 0 or size > 32 * 1024 * 1024: self.send(413); return
            body = self.rfile.read(size)
            if not self.authenticated(): return
            if self.headers.get('If-None-Match') != '*': self.send(400); return
            with lock:
                exists = self.path in entries
                if not exists: entries[self.path] = body
            self.send(412 if exists else 201)
        def do_PROPFIND(self):
            size = int(self.headers.get('Content-Length', '0'))
            if size < 0 or size > 1024 * 1024: self.send(413); return
            self.rfile.read(size)
            if not self.authenticated(): return
            if self.headers.get('Depth') != '1': self.send(400); return
            with lock:
                if self.path not in directories: self.send(404); return
                children = [(path, True, 0) for path in directories if path.startswith(self.path) and
                            (path == self.path or '/' not in path[len(self.path):].rstrip('/'))]
                children += [(path, False, len(body)) for path, body in entries.items()
                             if path.startswith(self.path) and '/' not in path[len(self.path):]]
            rows = ['<d:response><d:href>' + escape(path) + '</d:href><d:propstat><d:prop><d:resourcetype>' +
                    ('<d:collection/>' if collection else '') + '</d:resourcetype><d:getcontentlength>' + str(size) +
                    '</d:getcontentlength></d:prop><d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>'
                    for path, collection, size in children]
            self.send(207, ('<d:multistatus xmlns:d="DAV:">' + ''.join(rows) + '</d:multistatus>').encode())
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); context.load_cert_chain(cert, key)
    if lifecycle is None:
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler); server.daemon_threads = True
        server.socket = context.wrap_socket(server.socket, server_side=True)
    else:
        from continuation_lifecycle import LifecycleHTTPServer
        server = LifecycleHTTPServer(('127.0.0.1', 0), Handler, lifecycle, context, failures)
    serving = threading.Thread(target=server.serve_forever, daemon=True)
    serving.start()
    root = 'https://127.0.0.1:' + str(server.server_port) + prefix
    try:
        yield root, entries, requests, failures, cert
    finally:
        if lifecycle is None:
            server.shutdown(); server.server_close()
            key.unlink(missing_ok=True)
            subprocess.run(['sudo', 'security', 'delete-certificate', '-Z', fingerprint,
                            '/Library/Keychains/System.keychain'], check=True, capture_output=True)
        else:
            try:
                lifecycle.stop(server, serving)
            finally:
                key.unlink(missing_ok=True)
                lifecycle.cleanup_command('certificate', lifecycle.certificate_delete)
