# SPDX-License-Identifier: MIT
"""Actions-only public-C-ABI immutable writes, owner and callback checks."""
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import ssl
import subprocess
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cloud_native import trust_fixture_certificates


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--consumer', type=Path, required=True)
    parser.add_argument('--native-binary', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    out = args.output.resolve(); out.mkdir(parents=True)
    key, cert = out / 'fixture.key', out / 'fixture.crt'
    subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1', '-keyout', str(key),
                    '-out', str(cert), '-subj', '/CN=localhost', '-addext', 'subjectAltName=DNS:localhost'], check=True, capture_output=True)
    trust_fixture_certificates((cert,), 'reader-apple-writes-')
    payload = bytes(range(256)) * 8192
    objects, requests, checks = {}, [], []
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'
        def log_message(self, *unused): pass
        def send(self, status, body=b'', location=None):
            self.send_response(status); self.send_header('Content-Length', str(len(body)))
            if location: self.send_header('Location', location)
            self.end_headers()
            try: self.wfile.write(body)
            except (OSError, ssl.SSLError): pass
        def do_PROPFIND(self):
            self.rfile.read(int(self.headers.get('Content-Length', 0)))
            with lock: requests.append(('PROPFIND', self.path))
            self.send(207, b'<d:multistatus xmlns:d="DAV:"/>')
        def do_MKCOL(self):
            with lock: requests.append(('MKCOL', self.path)); exists = self.path in objects; objects[self.path] = b''
            self.send(405 if exists else 201)
        def do_PUT(self):
            with lock: requests.append(('PUT', self.path))
            assert self.headers.get('If-None-Match') == '*'
            left = int(self.headers['Content-Length']); data = bytearray()
            try:
                while left:
                    chunk = self.rfile.read(min(left, 65536))
                    if not chunk: return
                    data.extend(chunk); left -= len(chunk)
            except (OSError, ssl.SSLError): return
            if self.path.endswith('redirect.bin'):
                self.send(307, location='/dav/foreign-write.bin'); return
            with lock:
                exists = self.path in objects
                if not exists: objects[self.path] = bytes(data)
            if self.path.endswith('deadline.bin'): time.sleep(.5)
            self.send(412 if exists else 201)
        def do_GET(self):
            with lock: requests.append(('GET', self.path)); data = objects.get(self.path)
            if self.path.endswith('headers.bin'):
                self.send_response(200); self.send_header('X-Budget', 'x' * 40000)
                self.send_header('Content-Length', '0'); self.end_headers(); return
            self.send(404 if data is None else 200, b'' if data is None else data)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler); server.daemon_threads = True
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); tls.load_cert_chain(cert, key)
    server.socket = tls.wrap_socket(server.socket, server_side=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    root = f'https://localhost:{server.server_port}/dav/'

    def run(name, action, resource='', expected=0, timeout=10000, cancel=(1 << 64) - 1):
        folder = out / name; folder.mkdir(); (folder / 'input.bin').write_bytes(payload)
        completed = subprocess.run([str(args.consumer.resolve()), action, root, '', resource, str(folder), 'input.bin' if action == 'put' else 'output.bin',
                                    str(len(payload)), '0', '0', str(timeout), str(cancel)], capture_output=True, text=True, encoding='utf-8', timeout=145)
        assert completed.returncode == 0, (name, completed.stderr)
        value = json.loads(completed.stdout)
        (folder / 'result.json').write_text(json.dumps(value), encoding='utf-8')
        assert value['status'] == expected, (name, expected, value)
        return value, folder

    def record(name): checks.append(name); print('PASS ' + name, flush=True)
    try:
        run('collection-create', 'mkcol', 'immutable/'); record('native_mkcol_creates_collection')
        run('collection-retry', 'mkcol', 'immutable/'); record('native_mkcol_405_is_idempotent')
        run('publish', 'put', 'immutable/book.bin')
        assert objects['/dav/immutable/book.bin'] == payload; record('bounded_streamed_put_exact_bytes_and_if_none_match')
        run('publish-retry', 'put', 'immutable/book.bin', expected=11)
        assert objects['/dav/immutable/book.bin'] == payload; record('immutable_412_preserves_original')
        _, folder = run('roundtrip', 'get', 'immutable/book.bin')
        assert (folder / 'output.bin').read_bytes() == payload; record('put_get_publication_roundtrip_hash')
        value, _ = run('cancel-upload', 'put', 'cancelled.bin', expected=7, cancel=65536)
        assert value['progress'] >= 65536 and '/dav/cancelled.bin' not in objects
        record('upload_cancellation_stops_without_committing_partial_body')
        run('deadline-upload', 'put', 'deadline.bin', expected=3, timeout=100)
        record('whole_upload_deadline_includes_response_wait')
        run('write-redirect', 'put', 'redirect.bin', expected=10)
        assert ('PUT', '/dav/foreign-write.bin') not in requests
        record('immutable_write_redirect_is_never_followed')
        value, _ = run('owner', 'native-owner')
        assert value['owner_ok'] is True; record('wrong_owner_operation_and_free_leave_owner_usable')
        value, folder = run('reentry', 'native-reentry', 'immutable/book.bin')
        assert value['reentry_ok'] is True and value['callback_owner'] is True and value['settled'] is True
        assert (folder / 'output.bin').read_bytes() == payload
        record('callback_reentry_free_refused_and_callbacks_remain_on_owner')
        run('header-budget', 'get', 'headers.bin', expected=8)
        record('native_response_headers_retain_32kib_bound')
        assert len(checks) == 11
        report = {'accepted': True, 'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
                  'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'platform': sys.platform,
                  'execution_platform': 'ios-simulator' if os.environ.get('EXR_DAV_IOS_UDID') else 'macos',
                  'count': len(checks), 'checks': checks, 'consumer_sha256': hashlib.sha256(args.native_binary.read_bytes()).hexdigest(),
                  'original_bytes': len(payload), 'original_sha256': hashlib.sha256(payload).hexdigest(), 'complete_product': False}
        (out / 'result.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(report), flush=True)
    finally:
        server.shutdown(); server.server_close(); key.unlink(missing_ok=True)


if __name__ == '__main__': main()
