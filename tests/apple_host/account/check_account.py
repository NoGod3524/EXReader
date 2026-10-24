# SPDX-License-Identifier: MIT
"""Actions-only actual production Swift account controller and native TLS."""
import argparse
import base64
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import re
import sqlite3
import ssl
import subprocess
import sys
import threading
import time
import xml.sax.saxutils

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'webdav'))
from cloud_native import trust_fixture_certificates

CHECKS = [
    'stable_lowercase_profile_uuid', 'actual_keychain_roundtrip_after_profile_reopen',
    'metadata_contains_no_authorization', 'insecure_root_rejected_without_profile_write',
    'session_only_authorization_not_restored_from_disk', 'account_directories_are_isolated',
    'bounded_product_sync_page', 'exact_public_sdk_original_export',
    'existing_immutable_original_is_verified_and_reused', 'cancelled_preparation_preserves_the_valid_original',
    'verified_bootstrap_is_idempotent_history_and_outbox', 'bootstrap_preserves_product_title_author',
    'all_windows_share_one_account_controller', 'account_change_cancels_unstarted_preparation', 'native_account_sweep_completes',
    'actual_256_shard_account_scan', 'main_runloop_active_during_native_https',
    'closed_before_native_controller_release', 'verified_remote_ack_retains_history',
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--consumer', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    folder = args.output.absolute(); folder.mkdir(parents=True)
    password = secrets.token_urlsafe(32)
    authorization = 'Basic ' + base64.b64encode(('reader:' + password).encode()).decode()
    cert, key = folder / 'server.crt', folder / 'server.key'
    subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
                    '-keyout', str(key), '-out', str(cert), '-subj', '/CN=localhost',
                    '-addext', 'subjectAltName=DNS:localhost,IP:127.0.0.1'], check=True, capture_output=True)
    trust_fixture_certificates((cert,), 'apple-account-')
    entries, directories, requests = {}, {'/dav/'}, []
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def log_message(self, *unused):
            pass

        def send(self, code, body=b''):
            self.send_response(code); self.send_header('Content-Length', str(len(body)))
            self.send_header('Connection', 'close'); self.end_headers(); self.close_connection = True
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError, ssl.SSLError):
                pass

        def authenticated(self):
            valid = self.headers.get('Authorization') == authorization
            with lock:
                requests.append({'method': self.command, 'path': self.path, 'authenticated': valid})
            if not valid:
                self.send(401)
            return valid

        def do_MKCOL(self):
            if not self.authenticated(): return
            with lock:
                exists = self.path in directories; directories.add(self.path)
            self.send(405 if exists else 201)

        def do_PUT(self):
            body = self.rfile.read(int(self.headers.get('Content-Length', '0')))
            if not self.authenticated(): return
            if self.headers.get('If-None-Match') != '*': self.send(400); return
            with lock:
                exists = self.path in entries
                if not exists: entries[self.path] = body
            self.send(412 if exists else 201)

        def do_GET(self):
            if not self.authenticated(): return
            with lock: body = entries.get(self.path)
            self.send(404 if body is None else 200, body or b'')

        def do_PROPFIND(self):
            self.rfile.read(int(self.headers.get('Content-Length', '0')))
            if not self.authenticated(): return
            if self.headers.get('Depth') != '1': self.send(400); return
            # One real blocking native transfer lets the production main-loop
            # timer prove it remains active while the account worker is in TLS.
            if self.path == '/dav/exreader-sync-v1/revisions/00/': time.sleep(0.25)
            with lock:
                if self.path not in directories: self.send(404); return
                children = [(path, True, 0) for path in directories if path.startswith(self.path) and
                            (path == self.path or '/' not in path[len(self.path):].rstrip('/'))]
                children += [(path, False, len(body)) for path, body in entries.items()
                             if path.startswith(self.path) and '/' not in path[len(self.path):]]
            rows = []
            for path, collection, size in children:
                rows.append('<d:response><d:href>' + xml.sax.saxutils.escape(path) + '</d:href><d:propstat><d:prop>'
                            '<d:resourcetype>' + ('<d:collection/>' if collection else '') + '</d:resourcetype>'
                            '<d:getcontentlength>' + str(size) + '</d:getcontentlength></d:prop>'
                            '<d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>')
            self.send(207, ('<d:multistatus xmlns:d="DAV:">' + ''.join(rows) + '</d:multistatus>').encode())

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler); server.daemon_threads = True
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); context.load_cert_chain(cert, key)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    root = 'https://127.0.0.1:' + str(server.server_port) + '/dav/'
    try:
        done = subprocess.run([str(args.consumer.absolute()), root, str(folder / 'account'),
                               'apps/reader/store/001_catalog.sql'], capture_output=True, text=True, timeout=180,
                              env=dict(os.environ, READER_ACCOUNT_TEST_PASSWORD=password))
        (folder / 'consumer.log').write_text(done.stdout + done.stderr)
        (folder / 'requests.json').write_text(json.dumps(requests, indent=2) + '\n')
        assert done.returncode == 0, (done.returncode, (done.stdout + done.stderr)[-2000:])
        report = json.loads((folder / 'account/account.json').read_text())
        assert report['accepted'] is True and report['checks'] == CHECKS
        assert report['source_sha'] == os.environ['GITHUB_SHA']
        assert str(report['run_id']) == os.environ['GITHUB_RUN_ID'] and str(report['attempt']) == os.environ['GITHUB_RUN_ATTEMPT']
        assert report['sweeps'] == 1 and report['shards'] == 256 and report['main_thread_ticks'] >= 10
        assert requests and all(row['authenticated'] for row in requests)
        shards = {row['path'] for row in requests if row['method'] == 'PROPFIND' and
                  re.fullmatch(r'/dav/exreader-sync-v1/revisions/[0-9a-f]{2}/', row['path'])}
        assert shards == {'/dav/exreader-sync-v1/revisions/%02x/' % shard for shard in range(256)}, sorted(shards)
        revisions = [body for path, body in entries.items() if '/revisions/' in path and path.endswith('.json')]
        assert len(revisions) == 1
        revision = json.loads(revisions[0]); assert revision['entity_kind'] == 'book'
        assert revision['entity_key'] == report['book_key'] and revision['payload']['title'] == 'Remote title preserved'
        assert revision['payload']['author'] == 'Account author'
        assert revision['payload']['favorite'] is True
        original = b'Actual Apple account original. Exact retained bytes.\n'
        assert len([body for body in entries.values() if body == original]) == 1
        databases = list((folder / 'account/accounts').glob('*/reader-catalog.db'))
        assert len(databases) == 1
        with sqlite3.connect('file:' + str(databases[0]) + '?mode=ro', uri=True) as db:
            assert db.execute('select count(*) from reader_revisions').fetchone() == (1,)
            assert db.execute('select count(*) from reader_outbox').fetchone() == (0,)
        report.update({'consumer_sha256': hashlib.sha256(args.consumer.read_bytes()).hexdigest(),
                       'authenticated_requests': len(requests), 'actual_shards': len(shards),
                       'remote_revisions': len(revisions), 'verified_remote_originals': 1,
                       'host_account_ui_accepted': False})
        (folder / 'requests.json').write_text(json.dumps(requests, indent=2) + '\n')
        for path in folder.rglob('*'):
            if path.is_file():
                data = path.read_bytes()
                assert password.encode() not in data and authorization.encode() not in data, 'secret in retained output'
        report['secret_scan_passed'] = True
        (folder / 'account-native.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report))
    finally:
        server.shutdown(); server.server_close()


if __name__ == '__main__':
    main()
