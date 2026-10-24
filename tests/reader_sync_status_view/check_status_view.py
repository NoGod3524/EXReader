# SPDX-License-Identifier: MIT
"""Actions-only installed read-only sync status view over real native TLS.

Drives an actual reader_session plus a host-owned revisions handle through the
installed package and checks the frozen named list. Runs only in GitHub Actions:
the fixture trusts a temporary CA, binds IPv4 loopback and never touches a real
account or cloud.
"""
import argparse
import base64
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import queue
import re
import socket
import sqlite3
import ssl
import subprocess
import sys
import threading
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'reader_sync'))
from check_sync import raw, revision  # noqa: E402
from cloud_native import trust_fixture_certificates  # noqa: E402

AUTH = 'Basic ' + base64.b64encode(b'status-view:fixture-secret').decode()
SHARD_DIRECTORY = re.compile(r'^/dav/exreader-sync-v1/revisions/[0-9a-f]{2}/$')


def closed_port():
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind(('127.0.0.1', 0))
    port = probe.getsockname()[1]
    probe.close()
    return port


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--consumer', type=Path, required=True)
    parser.add_argument('--c-consumer', type=Path, required=True)
    parser.add_argument('--revision-consumer', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    options = parser.parse_args()
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    folder = options.output.resolve()
    folder.mkdir(parents=True)
    consumer = options.consumer.resolve()
    c_consumer = options.c_consumer.resolve()
    protocol = options.revision_consumer.resolve()
    checks, requests = [], []
    lock = threading.Lock()
    entries = {}
    directories = {'/dav/', '/dav/exreader-sync-v1/', '/dav/exreader-sync-v1/revisions/'}
    flags = {'pause': False, 'http': 0}
    blocked, release = threading.Event(), threading.Event()
    processes = []

    certificates = folder / 'certificates'
    certificates.mkdir()
    key, certificate = certificates / 'server.key', certificates / 'server.crt'
    subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
                    '-keyout', str(key), '-out', str(certificate), '-subj', '/CN=localhost',
                    '-addext', 'subjectAltName=DNS:localhost,IP:127.0.0.1'], check=True, capture_output=True)
    trust_fixture_certificates((certificate,), 'reader-status-view-')

    def retain(value):
        body = raw(value)
        leaf = value['id'] + '-' + hashlib.sha256(body).hexdigest() + '.json'
        path = '/dav/exreader-sync-v1/revisions/' + value['id'][:2] + '/' + leaf
        with lock:
            entries[path] = body
            directories.add(path[:path.rfind('/') + 1])
        return path

    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def log_message(self, *unused):
            pass

        def send(self, code, data=b''):
            self.send_response(code)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Connection', 'close')
            self.end_headers()
            self.close_connection = True
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError, ssl.SSLError):
                pass

        def authorized(self):
            if self.command == 'PROPFIND':
                self.rfile.read(int(self.headers.get('Content-Length', 0)))
            with lock:
                requests.append({'method': self.command, 'path': self.path,
                                 'authenticated': self.headers.get('Authorization') == AUTH})
            if self.headers.get('Authorization') != AUTH:
                self.send(401)
                return False
            if flags['http']:
                self.send(flags['http'])
                return False
            return True

        def do_MKCOL(self):
            if not self.authorized():
                return
            with lock:
                exists = self.path in directories
                directories.add(self.path)
            self.send(405 if exists else 201)

        def do_PUT(self):
            body = self.rfile.read(int(self.headers['Content-Length']))
            if not self.authorized():
                return
            assert self.headers.get('If-None-Match') == '*'
            with lock:
                exists = self.path in entries
                if not exists:
                    entries[self.path] = body
            self.send(412 if exists else 201)

        def do_GET(self):
            if not self.authorized():
                return
            with lock:
                body = entries.get(self.path)
            self.send(404 if body is None else 200, body or b'')

        def do_PROPFIND(self):
            if not self.authorized():
                return
            assert self.headers.get('Depth') == '1'
            if flags['pause']:
                flags['pause'] = False
                blocked.set()
                release.wait(30)
            with lock:
                exists = self.path in directories
                children = [(x, True, 0) for x in directories if x.startswith(self.path) and
                            (x == self.path or '/' not in x[len(self.path):].rstrip('/'))]
                children += [(x, False, len(b)) for x, b in entries.items()
                             if x.startswith(self.path) and '/' not in x[len(self.path):]]
            if not exists:
                self.send(404)
                return
            rows = []
            for path, collection, size in children:
                rows.append('<d:response><d:href>' + path + '</d:href><d:propstat><d:prop><d:resourcetype>' +
                            ('<d:collection/>' if collection else '') + '</d:resourcetype><d:getcontentlength>' +
                            str(size) + '</d:getcontentlength></d:prop><d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>')
            self.send(207, ('<d:multistatus xmlns:d="DAV:">' + ''.join(rows) + '</d:multistatus>').encode())

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.daemon_threads = True
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certificate, key)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    root = 'https://127.0.0.1:' + str(server.server_port) + '/dav/'
    env = dict(os.environ, READER_TEST_AUTH=AUTH)

    class Device:
        def __init__(self, name, url=root):
            path = folder / name
            path.mkdir()
            self.db = path / '产品.sqlite'
            self.originals, self.cache = path / 'originals', path / 'cache'
            self.originals.mkdir()
            self.cache.mkdir()
            self.account = str(uuid.uuid4())
            self.process = subprocess.Popen([str(consumer), url, str(self.db), str(self.cache),
                                             str(self.originals), self.account, '3000'],
                                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                            stderr=subprocess.PIPE, encoding='utf-8', env=env)
            processes.append(self.process)
            self.lines = queue.Queue()
            self.trace = (path / 'consumer.jsonl').open('w', encoding='utf-8')

            def reader():
                for line in self.process.stdout:
                    self.trace.write(line)
                    self.trace.flush()
                    self.lines.put(line)
            threading.Thread(target=reader, daemon=True).start()
            self.created = json.loads(self.lines.get(timeout=20))['create']

        def command(self, value, timeout=120):
            self.process.stdin.write(value + '\n')
            self.process.stdin.flush()
            return json.loads(self.lines.get(timeout=timeout))

        def wait(self, state, seconds=240):
            deadline = time.monotonic() + seconds
            view = None
            while time.monotonic() < deadline:
                view = self.command('observe')
                if view['state'] == state:
                    return view
                if view['state'] in (5, 6, 7) and state not in (5, 6, 7):
                    raise AssertionError(('unexpected terminal state', view))
                time.sleep(.02)
            raise AssertionError(('state timeout', state, view))

        def wait_shards(self, minimum, seconds=240):
            deadline = time.monotonic() + seconds
            view = None
            while time.monotonic() < deadline:
                view = self.command('observe')
                if view['completed_shards'] >= minimum:
                    return view
                assert view['state'] in (1, 2), view
                time.sleep(.02)
            raise AssertionError(('shard timeout', minimum, view))

        def counts(self):
            with sqlite3.connect(self.db, timeout=15) as db:
                return db.execute('SELECT (SELECT count(*) FROM reader_revisions),'
                                  '(SELECT count(*) FROM reader_outbox)').fetchone()

        def close(self):
            assert self.command('close-session')['status'] == 0
            self.wait(7, 60)
            assert self.command('destroy-session')['status'] == 0
            assert self.command('exit')['cmd'] == 'exit'
            assert self.process.wait(timeout=30) == 0
            self.trace.close()

    def record(name):
        assert name not in checks, name
        checks.append(name)
        print('PASS ' + name, flush=True)

    def seed(db, value):
        path = folder / (value['id'] + '.json')
        path.write_bytes(raw(value))
        result = subprocess.run([str(protocol), 'local', str(db), str(path)],
                                capture_output=True, encoding='utf-8', timeout=30)
        assert result.returncode == 0 and json.loads(result.stdout)['status'] == 0, result.stdout
        return value['id']

    def capture(device, limit=100, conflicts=0):
        view = device.command('capture %d %d' % (limit, conflicts))
        assert view['status'] == 0 and view['out_set'] == 1, view
        return view

    def capture_norev(device, limit=100):
        view = device.command('capture-norev %d' % limit)
        assert view['status'] == 0 and view['out_set'] == 1, view
        return view

    try:
        contract = subprocess.run([str(c_consumer)], capture_output=True, text=True, timeout=60)
        assert contract.returncode == 0, contract.stdout + contract.stderr
        record('installed_c_and_cpp_consumers_bind_the_public_package')

        first = Device('设备A')
        assert first.created == 0
        assert not requests
        for number in range(40):
            retain(revision(number + 1, shard=number, key='%032x' % (number + 1)))

        idle = capture_norev(first, 10)
        summary = idle['summary']
        assert summary['phase'] == 0 and summary['attempt'] == 0 and summary['operations'] == 0, summary
        assert summary['outbox_included'] == 0 and summary['pending'] == 0
        assert summary['library_complete'] == 0 and summary['sweep_complete'] == 0
        assert summary['resumable'] == 0 and summary['phase_text'] == 'idle'
        assert summary['reason'] == 0 and summary['reason_text'] == 'none'
        assert not requests
        record('idle_session_only_capture_is_read_only_and_requests_nothing')

        zeros = first.command('rows 0 1')
        assert zeros['status'] == 0 and zeros['copied'] == 0, zeros
        assert first.command('rows 1 1')['status'] == 1
        assert first.command('rows-null')['status'] == 1
        assert first.command('summary')['status'] == 0
        assert first.command('open')['status'] == 0
        record('empty_snapshot_paging_and_argument_paths')

        flags['pause'] = True
        started = time.monotonic()
        assert first.command('start')['status'] == 0
        assert time.monotonic() - started < 5
        assert blocked.wait(20)
        syncing = capture(first, 10)['summary']
        assert syncing['phase'] == 1 and syncing['phase_text'] == 'syncing', syncing
        assert syncing['reason'] == 0 and syncing['session_status'] == 0
        assert syncing['operations'] == 0 and syncing['resumable'] == 0 and syncing['sweep_complete'] == 0
        assert first.command('cancel')['status'] == 0
        release.set()
        first.wait(3, 60)
        record('running_capture_reports_syncing_phase_before_any_step_completes')

        first.command('start')
        first.wait_shards(3)
        assert first.command('cancel')['status'] == 0
        first.wait(3, 120)
        partial = first.counts()
        assert 0 < partial[0] < 40, partial
        cancelled = capture(first, 100)['summary']
        assert cancelled['phase'] == 3 and cancelled['phase_text'] == 'cancelled', cancelled
        assert cancelled['resumable'] == 1 and cancelled['sweep_complete'] == 0
        assert cancelled['cursor'] and cancelled['completed_shards'] < 256, cancelled
        assert cancelled['library_complete'] == 0
        record('cancelled_snapshot_keeps_cursor_and_partial_history_resumable')

        before = len(requests)
        first.command('start')
        finished = first.wait(4, 300)
        assert finished['sweeps'] == 1 and finished['completed_shards'] == 256, finished
        listed = {item['path'] for item in requests[before:] if item['method'] == 'PROPFIND'
                  and SHARD_DIRECTORY.match(item['path'])}
        assert len(listed) == 256, len(listed)
        assert first.counts() == (40, 0), first.counts()
        swept = capture(first, 100)['summary']
        assert swept['phase'] == 4 and swept['phase_text'] == 'sweep-complete', swept
        assert swept['sweep_complete'] == 1 and swept['library_complete'] == 0
        assert swept['completed_shards'] == 256 and swept['completed_sweeps'] >= 1
        assert swept['shard_count'] == 256 and swept['more_may_exist'] == 0
        assert swept['outbox_included'] == 1 and swept['pending'] == 0
        record('one_completed_256_shard_sweep_is_not_a_complete_library')

        local = {}
        for number in range(5):
            local[number] = seed(first.db, revision(700 + number, shard=100 + number,
                                                   key='%032x' % (900 + number),
                                                   payload={'name': '本地%d' % number}))
        conflict_key = 'c' * 32
        left = seed(first.db, revision(706, shard=110, key=conflict_key, payload={'name': 'A'}))
        right = seed(first.db, revision(707, shard=111, key=conflict_key, payload={'name': 'B'}))
        page = capture(first, 2, 0)
        assert page['summary']['pending'] == 2 and page['summary']['more_may_exist'] == 1, page['summary']
        assert page['summary']['conflicts_checked'] == 0 and page['summary']['conflict_records'] == 0
        assert [row['id'] for row in page['rows']] == [local[0], local[1]]
        head = first.command('rows 0 1')
        assert head['status'] == 0 and head['copied'] == 1 and head['rows'][0]['id'] == local[0]
        tail = first.command('rows 1 1')
        assert tail['status'] == 0 and tail['copied'] == 1 and tail['rows'][0]['id'] == local[1]
        edge = first.command('rows 2 2')
        assert edge['status'] == 0 and edge['copied'] == 0, edge
        assert first.command('rows 3 1')['status'] == 1
        record('outbox_page_counts_distinct_records_and_pages_inside_the_snapshot')

        marked = capture(first, 100, 1)
        assert marked['summary']['conflicts_checked'] == 1 and marked['summary']['pending'] == 7
        assert marked['summary']['conflict_records'] == 2, marked['summary']
        assert {row['id'] for row in marked['rows'] if row['conflict']} == {left, right}
        plain = capture(first, 100, 0)
        assert plain['summary']['conflict_records'] == 0 and plain['summary']['conflicts_checked'] == 0
        assert not any(row['conflict'] for row in plain['rows'])
        record('conflict_probe_is_opt_in_and_marks_only_listed_records')

        retried = subprocess.run([str(protocol), 'retry', str(first.db), local[4], '3'],
                                 capture_output=True, encoding='utf-8', timeout=30)
        assert retried.returncode == 0 and json.loads(retried.stdout)['status'] == 0, retried.stdout
        retry_view = capture(first, 100, 0)
        assert retry_view['summary']['retried'] == 1, retry_view['summary']
        rows = {row['id']: row for row in retry_view['rows']}
        assert rows[local[4]]['attempts'] == 1 and rows[local[4]]['code'] == 3
        assert rows[local[4]]['reason'] == 6
        assert all(rows[key]['attempts'] == 0 and rows[key]['code'] == 0 and rows[key]['reason'] == 0
                   for key in rows if key != local[4])
        record('retried_records_and_fixed_reason_come_from_module_tokens')

        for row in retry_view['rows']:
            assert set(row) == {'id', 'kind', 'op', 'bytes', 'attempts', 'code', 'reason', 'conflict'}, row
            assert row['kind'] in ('tag', 'book', 'shelf', 'series', 'progress', 'annotation'), row
            assert row['op'] in ('put', 'delete', 'restore'), row
            assert len(row['id']) == 32
        record('rows_expose_only_closed_tokens_and_ids')

        before_digest = hashlib.sha256(Path(str(first.db)).read_bytes()).hexdigest()
        for _ in range(12):
            assert capture_norev(first, 5)['summary']['phase'] == 4
            assert capture(first, 5, 1)['summary']['pending'] == 5
        after_digest = hashlib.sha256(Path(str(first.db)).read_bytes()).hexdigest()
        assert before_digest == after_digest, (before_digest, after_digest)
        assert first.counts() == (47, 7), first.counts()
        record('repeated_captures_leave_product_storage_byte_identical')

        oversized = first.command('capture 101 0')
        assert oversized['status'] == 1 and oversized['message'] == 'Row limit must be 0..100', oversized
        defaulted = first.command('capture 0 0')
        assert defaulted['status'] == 0 and defaulted['summary']['pending'] == 7
        record('row_limit_hard_bounds_and_default_are_enforced')

        wrong = first.command('capture-wrong-thread 5')
        assert wrong['status'] == 4 and wrong['err_revision'] == 11 and wrong['out_set'] == 0, wrong
        assert 'worker' in wrong['message'] and 'http' not in wrong['message']
        assert capture(first, 3, 0)['summary']['pending'] == 3
        record('revisions_owner_violation_fails_closed_without_a_snapshot')

        threaded = first.command('capture-threads 4 25', timeout=240)
        assert threaded['ok'] == 100 and threaded['failed'] == 0, threaded
        record('revisions_free_capture_is_safe_from_many_threads')

        first.command('start')
        pushed = first.wait(4, 300)
        assert pushed['sweeps'] >= 2
        assert first.counts() == (47, 0), first.counts()
        record('bounded_page_records_are_published_and_acknowledged_by_the_real_session')

        source = '状态视图私有原件夹具\n'.encode()
        digest = hashlib.sha256(source).hexdigest()
        book = revision(801, shard=200, kind='book', key='txt:' + digest,
                        payload={'format': 'txt', 'source_sha256': digest, 'source_bytes': len(source),
                                 'title': '本地原件', 'author': '', 'favorite': False})
        book_id = seed(first.db, book)
        first.command('start')
        waiting = first.wait(4, 300)
        waiting_view = capture(first, 100, 0)['summary']
        assert waiting_view['phase'] == 4 and waiting_view['original_wait'] > 0, waiting_view
        assert waiting['pending_original'] > 0, waiting
        assert waiting_view['original_wait'] == waiting['pending_original']
        pending = {row['id']: row for row in capture(first, 100, 0)['rows']}
        assert book_id in pending and pending[book_id]['kind'] == 'book'
        assert pending[book_id]['attempts'] == 0 and pending[book_id]['code'] == 0
        record('pending_original_is_surfaced_and_never_acknowledged')

        observed = first.command('observe')
        mirrored = capture(first, 100, 0)['summary']
        assert mirrored['metadata_wait'] == observed['pending_metadata'], (mirrored, observed)
        record('metadata_wait_observations_mirror_the_session_counter')

        flags['http'] = 401
        first.command('start')
        first.wait(5, 120)
        denied_view = first.command('capture 10 0')
        denied = denied_view['summary']
        assert denied['phase'] == 5 and denied['reason'] == 1 and denied['http'] == 401, denied
        assert denied['resumable'] == 1 and denied['reason_text'] == 'needs-credentials'
        assert 'http' not in denied_view['message'] and 'fixture' not in denied_view['message']
        record('credential_failure_maps_to_one_fixed_safe_reason')

        flags['http'] = 0
        offline = Device('离线设备', url='https://127.0.0.1:' + str(closed_port()) + '/dav/')
        assert offline.created == 0
        assert capture_norev(offline, 5)['summary']['phase'] == 0
        offline.command('start')
        offline.wait(5, 120)
        unreachable = capture_norev(offline, 5)['summary']
        assert unreachable['phase'] == 5 and unreachable['reason'] == 2, unreachable
        assert unreachable['reason_text'] == 'offline' and unreachable['resumable'] == 1
        offline.close()
        record('unreachable_native_transport_is_reported_as_offline')

        assert first.command('close-session')['status'] == 0
        closing = capture_norev(first, 5)['summary']
        assert closing['phase'] in (6, 7)
        first.wait(7, 120)
        closed = capture_norev(first, 5)['summary']
        assert closed['phase'] == 7 and closed['phase_text'] == 'closed', closed
        assert closed['resumable'] == 0
        record('closing_and_closed_phases_stay_observable')

        retained = capture(first, 4, 1)
        assert retained['summary']['pending'] == 1 and retained['out_set'] == 1
        assert first.command('close-revisions')['status'] == 0
        assert first.command('destroy-session')['status'] == 0
        assert first.command('destroy-session')['null_after'] == 1
        assert first.command('summary')['status'] == 0
        kept = first.command('rows 0 1')
        assert kept['status'] == 0 and kept['copied'] == 1 and kept['rows'][0]['id'] == book_id
        assert first.command('release')['status'] == 0 and first.command('release')['null_after'] == 1
        released = first.command('release-null')
        assert released['status'] == 0 and released['null_pointer'] == 1
        assert first.command('exit')['cmd'] == 'exit'
        assert first.process.wait(timeout=30) == 0
        first.trace.close()
        record('snapshot_outlives_session_and_revisions_and_releases_once')

        assert all(item['authenticated'] for item in requests)
        assert not list(folder.rglob('.reader-sync-*.tmp'))
        for path in folder.rglob('*'):
            if path.is_file() and path.suffix != '.key' and 'certificates' not in path.parts:
                data = path.read_bytes()
                assert AUTH.encode() not in data, path
                assert b'fixture-secret' not in data, path
                if not path.name.endswith('.sync-account'):
                    assert b'https://' not in data, path
        record('evidence_contains_no_credentials_server_body_or_origin_text')

        report = {
            'accepted': True, 'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
            'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'platform': sys.platform,
            'checks': checks, 'count': len(checks),
            'consumer_sha256': hashlib.sha256(consumer.read_bytes()).hexdigest(),
            'c_consumer_sha256': hashlib.sha256(c_consumer.read_bytes()).hexdigest(),
            'sdk_changed': False, 'schema_changed': False, 'wire_changed': False, 'anchor_changed': False,
            'host_ui_accepted': False, 'product_wiring_accepted': False,
            'metadata_wait_positive_covered': False,
            'fixture_endpoint': 'IPv4 loopback with verified certificate IP SAN'}
        for path in folder.rglob('*'):
            if path.is_file() and path.suffix != '.key':
                data = path.read_bytes()
                assert AUTH.encode() not in data and b'fixture-secret' not in data, path
        (folder / 'result.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(report), flush=True)
    finally:
        release.set()
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=30)
        server.shutdown()
        server.server_close()


if __name__ == '__main__':
    main()
