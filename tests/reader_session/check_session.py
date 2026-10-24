# SPDX-License-Identifier: MIT
"""Actions-only installed asynchronous account session over real native HTTPS."""
import argparse
import base64
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import queue
import sqlite3
import ssl
import subprocess
import sys
import threading
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'reader_sync'))
from check_sync import raw, revision


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--consumer', type=Path, required=True)
    p.add_argument('--revision-consumer', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    folder = a.output.resolve(); folder.mkdir(parents=True)
    consumer, protocol = a.consumer.resolve(), a.revision_consumer.resolve()
    certs = folder / 'certificates'; certs.mkdir()
    key, cert = certs / 'server.key', certs / 'server.crt'
    subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
                    '-keyout', str(key), '-out', str(cert), '-subj', '/CN=localhost',
                    '-addext', 'subjectAltName=DNS:localhost,IP:127.0.0.1'], check=True, capture_output=True)
    subprocess.run(['certutil', '-addstore', '-f', 'Root', str(cert)] if os.name == 'nt' else
                   ['sudo', 'cp', str(cert), '/usr/local/share/ca-certificates/reader-session.crt'], check=True, capture_output=True)
    if os.name != 'nt':
        subprocess.run(['sudo', 'update-ca-certificates'], check=True, capture_output=True)
    secret = uuid.uuid4().hex
    auth = 'Basic ' + base64.b64encode(('session:' + secret).encode()).decode()
    entries, dirs, requests, checks = {}, {'/dav/', '/dav/exreader-sync-v1/',
                                         '/dav/exreader-sync-v1/revisions/', '/dav/exreader-sync-v1/revisions/00/'}, [], []
    lock = threading.Lock()
    blocked, release = threading.Event(), threading.Event()
    flags = {'pause': False, 'http': 0, 'late': False}

    def retain(value):
        body = raw(value)
        leaf = value['id'] + '-' + hashlib.sha256(body).hexdigest() + '.json'
        path = '/dav/exreader-sync-v1/revisions/' + value['id'][:2] + '/' + leaf
        with lock:
            entries[path] = body
            dirs.update(['/dav/exreader-sync-v1/', '/dav/exreader-sync-v1/revisions/', path[:path.rfind('/') + 1]])
        return path

    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'
        def log_message(self, *unused):
            pass
        def send(self, code, data=b''):
            self.send_response(code); self.send_header('Content-Length', str(len(data)))
            self.send_header('Connection', 'close'); self.end_headers(); self.close_connection = True
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError, ssl.SSLError):
                pass
        def authorized(self):
            if self.command == 'PROPFIND':
                self.rfile.read(int(self.headers.get('Content-Length', 0)))
            with lock:
                requests.append({'method': self.command, 'path': self.path,
                                 'authenticated': self.headers.get('Authorization') == auth})
            if self.headers.get('Authorization') != auth:
                self.send(401); return False
            if flags['http']:
                self.send(flags['http']); return False
            return True
        def do_MKCOL(self):
            if not self.authorized(): return
            with lock:
                exists = self.path in dirs; dirs.add(self.path)
            self.send(405 if exists else 201)
        def do_PUT(self):
            body = self.rfile.read(int(self.headers['Content-Length']))
            if not self.authorized(): return
            assert self.headers.get('If-None-Match') == '*'
            with lock:
                exists = self.path in entries
                if not exists: entries[self.path] = body
            self.send(412 if exists else 201)
        def do_GET(self):
            if not self.authorized(): return
            with lock: body = entries.get(self.path)
            self.send(404 if body is None else 200, body or b'')
        def do_PROPFIND(self):
            if not self.authorized(): return
            assert self.headers.get('Depth') == '1'
            if flags['pause']:
                flags['pause'] = False; blocked.set(); release.wait(15)
            if flags['late'] and self.path.endswith('/revisions/01/'):
                flags['late'] = False; retain(revision(999, shard=0, key='f' * 32))
            with lock:
                children = [(x, True, 0) for x in dirs if x.startswith(self.path) and
                            (x == self.path or '/' not in x[len(self.path):].rstrip('/'))]
                children += [(x, False, len(b)) for x, b in entries.items() if x.startswith(self.path) and '/' not in x[len(self.path):]]
                exists = self.path in dirs
            if not exists: self.send(404); return
            rows = []
            for path, collection, size in children:
                rows.append('<d:response><d:href>' + path + '</d:href><d:propstat><d:prop><d:resourcetype>' +
                            ('<d:collection/>' if collection else '') + '</d:resourcetype><d:getcontentlength>' +
                            str(size) + '</d:getcontentlength></d:prop><d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>')
            self.send(207, ('<d:multistatus xmlns:d="DAV:">' + ''.join(rows) + '</d:multistatus>').encode())

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler); server.daemon_threads = True
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); context.load_cert_chain(cert, key)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    root = 'https://localhost:' + str(server.server_port) + '/dav/'
    env = dict(os.environ, READER_TEST_AUTH=auth)
    processes = []

    class Device:
        def __init__(self, name, database=None, account=None, url=root, authorization=auth):
            path = folder / name; path.mkdir()
            self.db = database or path / '产品.sqlite'
            self.originals, self.cache = path / 'originals', path / 'cache'
            self.originals.mkdir(); self.cache.mkdir()
            self.account = account or str(uuid.uuid4())
            self.trace = path / 'native-controls.jsonl'
            self.process = subprocess.Popen([str(consumer), url, str(self.db), str(self.cache), str(self.originals), self.account, '3000'],
                                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                             encoding='utf-8', env=dict(env, READER_TEST_AUTH=authorization))
            processes.append(self.process); self.lines = queue.Queue()
            def reader():
                with self.trace.open('w', encoding='utf-8') as trace:
                    for line in self.process.stdout:
                        trace.write(line); trace.flush(); self.lines.put(line)
            threading.Thread(target=reader, daemon=True).start()
            self.created = json.loads(self.lines.get(timeout=10))['create']
        def command(self, value):
            self.process.stdin.write(value + '\n'); self.process.stdin.flush()
            return json.loads(self.lines.get(timeout=3))
        def wait(self, state, seconds=90):
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                view = self.command('observe')
                if view['state'] == state: return view
                assert view['state'] not in (5, 7), view
                time.sleep(.02)
            raise AssertionError(('state timeout', state, view))
        def close(self):
            assert self.command('close')['code'] == 0
            self.wait(7, 10)
            assert self.command('destroy')['code'] == 0
            assert self.process.wait(timeout=5) == 0
        def count(self):
            with sqlite3.connect(self.db) as db:
                return db.execute('SELECT (SELECT count(*) FROM reader_revisions),(SELECT count(*) FROM reader_outbox),(SELECT count(*) FROM reader_tags)').fetchone()

    def record(name):
        assert name not in checks; checks.append(name); print('PASS ' + name, flush=True)
    def seed(db, value):
        path = folder / (value['id'] + '.json'); path.write_bytes(raw(value))
        result = subprocess.run([str(protocol), 'local', str(db), str(path)], capture_output=True, encoding='utf-8', timeout=20)
        assert result.returncode == 0 and json.loads(result.stdout)['status'] == 0, result.stdout

    try:
        d = Device('设备A'); assert d.created == 0 and d.command('observe')['state'] == 0 and not requests
        record('c_abi_and_idle_creation_make_no_network_request')
        assert d.command('destroy')['code'] == 2
        record('premature_destroy_is_nonblocking_busy_and_preserves_handle')
        flags['pause'] = True; start = time.monotonic(); assert d.command('start')['code'] == 0
        assert time.monotonic() - start < 1
        assert blocked.wait(8)
        assert d.command('observe')['state'] == 1
        record('background_worker_and_observation_remain_responsive_during_native_https')
        assert d.command('start')['code'] == 2
        record('overlapping_sweeps_are_refused')
        assert d.command('cancel')['code'] == 0
        assert d.command('observe')['state'] == 2
        release.set(); cancelled = d.wait(3)
        assert cancelled['steps'] == 0 and cancelled['completed_shards'] == 0 and cancelled['sweeps'] == 0, cancelled
        record('cancelled_transfer_keeps_the_last_successful_cursor')
        n = len(requests)
        second = Device('同库并发', database=d.db, account=d.account)
        second.command('start'); failure = second.wait(5)
        assert failure['status'] == 4 and len(requests) == n
        second.close()
        record('same_product_account_is_exclusively_locked_across_processes')
        for n in range(105): retain(revision(n + 1, key='%032x' % (n + 1)))
        flags['late'] = True
        n = len(requests); assert d.command('start')['code'] == 0
        first = d.wait(4)
        assert first['steps'] == 257 and first['completed_shards'] == 256 and first['sweeps'] == 1 and not first['full_library_complete']
        assert len({x['path'] for x in requests[n:] if x['method'] == 'PROPFIND' and '/revisions/' in x['path']}) == 256
        record('full_256_shards_and_100_record_continuation_are_actually_processed')
        assert d.count() == (105, 0, 0)
        record('remote_history_is_retained_without_sdk_writes_or_implicit_projection')
        d.command('start'); fresh = d.wait(4)
        assert fresh['sweeps'] == 2 and fresh['completed_shards'] == 256 and d.count()[0] == 106
        record('a_new_sweep_discovers_insertions_preceding_an_old_cursor')
        seed(d.db, revision(888, shard=32, key='e' * 32))
        d.command('start'); pushed = d.wait(4)
        assert pushed['pushed'] == 1 and d.count()[1] == 0
        record('offline_outbox_is_published_verified_and_acked_on_the_worker')
        source = '会话模块私有原件夹具\n'.encode()
        digest = hashlib.sha256(source).hexdigest()
        book = revision(889, shard=32, kind='book', key='txt:' + digest,
                        payload={'format': 'txt', 'source_sha256': digest, 'source_bytes': len(source),
                                 'title': '本地原件', 'author': '', 'favorite': False})
        staged = d.originals / (digest + '.txt'); staged.write_bytes(b'wrong staged bytes')
        seed(d.db, book); d.command('start'); refused = d.wait(5)
        assert refused['status'] == 5 and d.count()[1] == 1
        record('wrong_staged_original_is_refused_without_acknowledging_the_outbox')
        staged.write_bytes(source); d.command('start'); d.wait(4)
        assert d.count()[1] == 0 and entries['/dav/exreader-sync-v1/objects/' + digest[:2] + '/' + digest + '.txt'] == source
        record('repaired_private_original_is_hash_verified_published_and_acknowledged')
        b = Device('设备B'); b.command('start'); b.wait(4)
        assert b.count() == (108, 0, 0)
        record('another_independent_product_database_receives_the_same_history')
        b.close()
        snapshot = d.count(); d.close()
        manifest = Path(str(d.db) + '.sync-account')
        assert manifest.exists() and secret not in manifest.read_text() and auth not in manifest.read_text()
        record('persistent_account_binding_contains_no_authorization')
        for name, account, url in [('换账号', str(uuid.uuid4()), root), ('换地址', d.account, root + 'other/')]:
            n = len(requests); wrong = Device(name, database=d.db, account=account, url=url)
            wrong.command('start'); result = wrong.wait(5)
            assert result['status'] == 4 and len(requests) == n
            wrong.close()
        assert d.count() == snapshot
        record('account_or_root_changes_are_refused_before_network_and_preserve_history')
        reopened = Device('同账号重开', database=d.db, account=d.account)
        reopened.command('start'); reopened.wait(4)
        assert reopened.count() == snapshot
        record('same_account_reopens_after_process_shutdown_without_rebinding')
        flags['http'] = 503; reopened.command('start'); failed = reopened.wait(5)
        assert failed['status'] == 5 and failed['http_status'] == 503 and failed['sweeps'] == 1
        record('network_failure_is_observed_without_an_automatic_retry_loop')
        count = len(requests); time.sleep(.15); assert len(requests) == count
        flags['http'] = 0; reopened.command('start'); retried = reopened.wait(4)
        assert retried['sweeps'] == 2 and retried['attempt'] == 3
        record('explicit_retry_resumes_and_preserves_durable_history')
        reopened.close()
        bad = Device('坏UUID', account='NOT-A-UUID'); assert bad.created == 1
        assert bad.process.wait(timeout=5) == 0
        record('invalid_account_identity_is_rejected_before_worker_creation')
        assert all(x['authenticated'] for x in requests)
        assert not list(folder.rglob('.reader-sync-*.tmp'))
        record('all_native_requests_keep_credentials_at_the_selected_origin_and_leave_no_transfer_temp')
        assert len(checks) == 20
        report = {'accepted': True, 'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
                  'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'platform': sys.platform, 'checks': checks, 'count': len(checks),
                  'consumer_sha256': hashlib.sha256(consumer.read_bytes()).hexdigest(), 'sdk_changed': False,
                  'schema_changed': False, 'metadata_projection_accepted': False, 'host_ui_accepted': False,
                  'six_platform_accepted': False, 'complete_product': False}
        for path in folder.rglob('*'):
            if path.is_file() and path.suffix != '.key':
                data = path.read_bytes(); assert secret.encode() not in data and auth.encode() not in data
        (folder / 'result.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(report), flush=True)
    finally:
        release.set()
        for process in processes:
            if process.poll() is None: process.kill(); process.wait(timeout=10)
        server.shutdown(); server.server_close()


if __name__ == '__main__': main()
