# SPDX-License-Identifier: MIT
"""Actions-only fault-boundary acceptance for the installed account session and
immutable sync modules.

Every scenario runs a real child process against real native HTTPS served by a
controlled fixture on IPv4 loopback with a verified certificate IP SAN. The
fixture gates each named stage by protocol handshake (request received, body
committed, response withheld, partial body, reset, explicit status fault), so a
real forced termination or an abrupt self-exit lands on an externally
observable boundary. No shared module gains a test hook, and this package
modifies no session, sync, revisions or WebDAV source.

The pre-existing 20-item account-session suite is preserved unchanged: its
report from the same source/run/attempt is authenticated here and carried into
this report, and the cross-platform aggregate refuses a run that is missing it.
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import queue
import socket
import sqlite3
import ssl
import subprocess
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'reader_sync'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'webdav'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_sync import raw, revision
from cloud_native import trust_fixture_certificates
from boundaries import NEW_CHECKS, ORIGINAL_SESSION_CHECKS, UNCOVERED_LIMITS


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--consumer', type=Path, required=True)
    parser.add_argument('--revision-consumer', type=Path, required=True)
    parser.add_argument('--original-report', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    arguments = parser.parse_args()
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    started = time.monotonic()
    folder = arguments.output.resolve()
    folder.mkdir(parents=True)
    consumer, protocol = arguments.consumer.resolve(), arguments.revision_consumer.resolve()

    certificates = folder / 'certificates'
    certificates.mkdir()
    server_key, server_certificate = certificates / 'server.key', certificates / 'server.crt'
    subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
                    '-keyout', str(server_key), '-out', str(server_certificate),
                    '-subj', '/CN=127.0.0.1',
                    '-addext', 'subjectAltName=DNS:localhost,IP:127.0.0.1'],
                   check=True, capture_output=True)
    trust_fixture_certificates((server_certificate,), 'reader-sync-resilience-')
    secret = uuid.uuid4().hex
    authorization = 'Basic ' + base64.b64encode(('resilience:' + secret).encode()).decode()
    environment = dict(os.environ, READER_TEST_AUTH=authorization)

    entries, directories = {}, {'/dav/'}
    requests, checks = [], []
    lock = threading.Lock()
    gates, faults, global_faults = {}, {}, []
    all_gates, processes = [], []

    def revision_path(value):
        body = raw(value)
        return ('/dav/exreader-sync-v1/revisions/' + value['id'][:2] + '/' + value['id'] + '-' +
                hashlib.sha256(body).hexdigest() + '.json')

    def object_path(sha, kind='txt'):
        return '/dav/exreader-sync-v1/objects/' + sha[:2] + '/' + sha + '.' + kind

    def provision(path):
        parent = path[:path.rfind('/') + 1]
        parts = parent.strip('/').split('/')
        with lock:
            for size in range(1, len(parts) + 1):
                directories.add('/' + '/'.join(parts[:size]) + '/')

    def publish_revision(value, body=None):
        data = raw(value) if body is None else body
        path = revision_path(value)
        provision(path)
        with lock:
            entries[path] = data
        return path

    def publish_object(sha, data, kind='txt'):
        path = object_path(sha, kind)
        provision(path)
        with lock:
            entries[path] = data
        return path

    def gate(method, path, mode, partial=0):
        value = {'mode': mode, 'partial': partial, 'event': threading.Event(),
                 'release': threading.Event()}
        with lock:
            gates[(method, path)] = value
            all_gates.append(value)
        return value

    def fault(method, path, status, headers=None):
        with lock:
            faults.setdefault((method, path), []).append((status, headers or {}))

    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def log_message(self, *unused):
            pass

        def note(self):
            value = {'method': self.command, 'path': self.path,
                     'authorized': self.headers.get('Authorization') == authorization,
                     'if_none_match': self.headers.get('If-None-Match'),
                     'depth': self.headers.get('Depth'),
                     'content_length': self.headers.get('Content-Length'),
                     'status': None, 'stage': None, 'body_sha256': None}
            with lock:
                requests.append(value)
            return value

        def emit(self, entry, code, data=b'', headers=None):
            entry['status'] = code
            try:
                self.send_response(code)
                self.send_header('Connection', 'close')
                self.send_header('Content-Length', str(len(data)))
                for name, value in (headers or {}).items():
                    self.send_header(name, value)
                self.end_headers()
                self.close_connection = True
                if data:
                    self.wfile.write(data)
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, ssl.SSLError, OSError):
                self.close_connection = True

        def take(self):
            with lock:
                return gates.pop((self.command, self.path), None)

        def fault_for(self):
            with lock:
                if global_faults:
                    return global_faults[0]
                queue_for_path = faults.get((self.command, self.path))
                if queue_for_path:
                    return queue_for_path.pop(0)
            return None

        def close_socket(self, reset=False):
            self.close_connection = True
            try:
                if reset:
                    self.connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                self.connection.close()
            except OSError:
                pass

        def do_MKCOL(self):
            entry = self.note()
            injected = self.fault_for()
            if injected:
                self.emit(entry, injected[0], b'', injected[1])
                return
            if not entry['authorized']:
                self.emit(entry, 401)
                return
            with lock:
                exists = self.path in directories
                parent = self.path.rsplit('/', 2)[0] + '/'
                if not exists and parent not in directories:
                    code = 409
                else:
                    directories.add(self.path)
                    code = 405 if exists else 201
            self.emit(entry, code)

        def do_PROPFIND(self):
            entry = self.note()
            try:
                self.rfile.read(int(self.headers.get('Content-Length', '0')))
            except (ConnectionResetError, ssl.SSLError, OSError):
                pass
            injected = self.fault_for()
            if injected:
                self.emit(entry, injected[0], b'', injected[1])
                return
            if not entry['authorized']:
                self.emit(entry, 401)
                return
            held = self.take()
            if held and held['mode'] == 'before_response':
                entry['stage'] = 'before_response'
                held['event'].set()
                held['release'].wait(60)
            with lock:
                if self.path not in directories:
                    body = None
                else:
                    rows = ['<d:response><d:href>' + self.path + '</d:href><d:propstat><d:prop><d:resourcetype>' +
                            '<d:collection/></d:resourcetype><d:getcontentlength>0</d:getcontentlength></d:prop>' +
                            '<d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>']
                    for name in sorted(directories):
                        if name != self.path and name.startswith(self.path) and \
                                '/' not in name[len(self.path):].rstrip('/'):
                            rows.append('<d:response><d:href>' + name + '</d:href><d:propstat><d:prop><d:resourcetype>' +
                                        '<d:collection/></d:resourcetype><d:getcontentlength>0</d:getcontentlength></d:prop>' +
                                        '<d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>')
                    for name in sorted(entries):
                        if name.startswith(self.path) and '/' not in name[len(self.path):]:
                            rows.append('<d:response><d:href>' + name + '</d:href><d:propstat><d:prop><d:resourcetype/>' +
                                        '<d:getcontentlength>' + str(len(entries[name])) + '</d:getcontentlength></d:prop>' +
                                        '<d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>')
                    body = ('<d:multistatus xmlns:d="DAV:">' + ''.join(rows) + '</d:multistatus>').encode()
            self.emit(entry, 404 if body is None else 207, body or b'')

        def do_PUT(self):
            entry = self.note()
            held = self.take()
            mode = held['mode'] if held else ''
            injected = self.fault_for()
            if mode == 'before_body':
                entry['stage'] = 'before_body'
                held['event'].set()
                held['release'].wait(60)
                entry['status'] = 'undelivered'
                self.close_socket()
                return
            if mode == 'reset_mid_body':
                try:
                    self.rfile.read(held['partial'])
                except (ConnectionResetError, ssl.SSLError, OSError):
                    pass
                entry['stage'] = 'reset_mid_body'
                held['event'].set()
                entry['status'] = 'reset'
                self.close_socket(reset=True)
                return
            if mode == 'stall_before_headers':
                entry['stage'] = 'stall_before_headers'
                held['event'].set()
                held['release'].wait(60)
                entry['status'] = 'undelivered'
                self.close_socket()
                return
            size = int(self.headers.get('Content-Length', '0'))
            try:
                data = self.rfile.read(size)
            except (ConnectionResetError, ssl.SSLError, OSError):
                entry['status'] = 'reset'
                self.close_socket(reset=True)
                return
            if len(data) != size:
                entry['status'] = 'truncated'
                self.close_socket()
                return
            entry['body_sha256'] = hashlib.sha256(data).hexdigest()
            if injected:
                self.emit(entry, injected[0], b'', injected[1])
                return
            if not entry['authorized']:
                self.emit(entry, 401)
                return
            with lock:
                exists = self.path in entries
                if not exists:
                    entries[self.path] = data
                    code = 201
                else:
                    code = 412
            entry['status'] = code
            if mode == 'after_commit_hold':
                entry['stage'] = 'after_commit'
                held['event'].set()
                held['release'].wait(60)
            self.emit(entry, code)

        def do_GET(self):
            entry = self.note()
            injected = self.fault_for()
            if injected:
                self.emit(entry, injected[0], b'', injected[1])
                return
            if not entry['authorized']:
                self.emit(entry, 401)
                return
            with lock:
                body = entries.get(self.path)
            if body is None:
                self.emit(entry, 404)
                return
            held = self.take()
            mode = held['mode'] if held else ''
            if mode in ('before_response', 'stall_before_headers'):
                entry['stage'] = mode
                held['event'].set()
                held['release'].wait(60)
                self.emit(entry, 200, body)
                return
            if mode == 'partial_body':
                entry['stage'] = 'partial_body'
                try:
                    self.send_response(200)
                    self.send_header('Connection', 'close')
                    self.send_header('Content-Length', str(len(body)))
                    self.end_headers()
                    self.wfile.write(body[:held['partial']])
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, ssl.SSLError, OSError):
                    pass
                entry['status'] = 'partial'
                held['event'].set()
                held['release'].wait(60)
                self.close_socket()
                return
            if mode == 'short_body_close':
                entry['stage'] = 'short_body_close'
                try:
                    self.send_response(200)
                    self.send_header('Connection', 'close')
                    self.send_header('Content-Length', str(len(body)))
                    self.end_headers()
                    self.wfile.write(body[:max(1, len(body) // 2)])
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, ssl.SSLError, OSError):
                    pass
                entry['status'] = 'short'
                held['event'].set()
                self.close_socket(reset=True)
                return
            self.emit(entry, 200, body)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.daemon_threads = True
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(server_certificate, server_key)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    root = 'https://127.0.0.1:' + str(server.server_port) + '/dav/'

    def device(name, account=None, database=None, timeout=3000):
        base = folder / name
        base.mkdir(exist_ok=True)
        value = {'base': base, 'url': root, 'account': account or str(uuid.uuid4()),
                 'db': database or base / '\u4ea7\u54c1.sqlite',
                 'cache': base / 'cache', 'originals': base / 'originals', 'timeout': timeout}
        value['cache'].mkdir(exist_ok=True)
        value['originals'].mkdir(exist_ok=True)
        return value

    class Session:
        def __init__(self, spec, timeout=None):
            self.spec = spec
            self.trace = spec['base'] / ('session-controls-' + uuid.uuid4().hex[:12] + '.jsonl')
            self.process = subprocess.Popen(
                [str(consumer), 'session', spec['url'], str(spec['db']), str(spec['cache']),
                 str(spec['originals']), spec['account'], str(timeout or spec['timeout'])],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                encoding='utf-8', env=environment)
            processes.append(self.process)
            self.lines = queue.Queue()

            def reader():
                with self.trace.open('w', encoding='utf-8') as trace:
                    for line in self.process.stdout:
                        trace.write(line)
                        trace.flush()
                        self.lines.put(line)

            threading.Thread(target=reader, daemon=True).start()
            self.created = json.loads(self.lines.get(timeout=30))['create']

        def command(self, value, timeout=30):
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
                if view['state'] in (3, 4, 5, 7):
                    raise AssertionError(('unexpected terminal session state', state, view))
                time.sleep(.02)
            raise AssertionError(('session state timeout', state, view))

        def identity(self):
            return {'pid': self.process.pid,
                    'termination': 'TerminateProcess' if os.name == 'nt' else 'SIGKILL',
                    'returncode': self.process.returncode}

        def kill(self):
            self.process.kill()
            self.process.wait(timeout=30)
            return self.identity()

        def abort(self):
            self.process.stdin.write('abort\n')
            self.process.stdin.flush()
            self.process.wait(timeout=30)
            return {'pid': self.process.pid, 'termination': 'self exit without unwinding',
                    'returncode': self.process.returncode}

        def close(self):
            assert self.command('close')['code'] == 0
            self.wait(7)
            assert self.command('destroy')['code'] == 0
            assert self.process.wait(timeout=30) == 0

    def counting(spec):
        def counts():
            if not Path(spec['db']).exists():
                return (0, 0)
            try:
                with sqlite3.connect(str(spec['db'])) as database:
                    return tuple(database.execute(
                        'SELECT (SELECT count(*) FROM reader_revisions),'
                        '(SELECT count(*) FROM reader_outbox)').fetchone())
            except sqlite3.OperationalError:
                return (0, 0)
        return counts

    def seed(spec, name, value):
        path = folder / (name + '.json')
        path.write_bytes(raw(value))
        assert path.read_bytes() == raw(value)
        result = subprocess.run([str(protocol), 'local', str(spec['db']), str(path)],
                                capture_output=True, encoding='utf-8', timeout=120)
        assert result.returncode == 0, (name, result.stderr)
        assert json.loads(result.stdout)['status'] == 0, result.stdout

    def protocol_call(spec, action, *rest, expected=0):
        result = subprocess.run([str(protocol), action, str(spec['db'])] + [str(x) for x in rest],
                                capture_output=True, encoding='utf-8', timeout=180)
        assert result.returncode == 0, (action, result.stderr)
        value = json.loads(result.stdout)
        assert value['status'] == expected, (action, value)
        return value

    def step_command(spec, shard, after='-', limit=100, timeout=15000):
        return [str(consumer), 'step', spec['url'], str(spec['db']), str(spec['cache']),
                str(spec['originals']), str(shard), after, str(limit), str(timeout)]

    def step(spec, shard=18, after='-', limit=100, timeout=15000):
        result = subprocess.run(step_command(spec, shard, after, limit, timeout), env=environment,
                                capture_output=True, encoding='utf-8', timeout=240)
        assert result.returncode == 0, (result.returncode, result.stderr)
        return json.loads(result.stdout)

    def record(name, expected, actual):
        assert name not in {check['id'] for check in checks}, name
        assert name in NEW_CHECKS, name
        assert isinstance(actual, dict) and actual, name
        checks.append({'id': name, 'expected': expected, 'actual': actual, 'pass': True})
        print('PASS ' + name, flush=True)

    def cleanup():
        for value in list(all_gates):
            value['release'].set()
        for process in processes:
            if process.poll() is None:
                process.kill()
                try:
                    process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    pass
        try:
            server.shutdown()
            server.server_close()
        except Exception:
            pass

    try:
        assert not requests
        # 1. The fixture stores the PUT body and withholds the response, so the
        #    client is provably blocked before it can acknowledge the outbox.
        device_1 = device('put-committed-before-ack')
        counts_1 = counting(device_1)
        tag_1 = revision(1, shard=18, key='a' * 32)
        seed(device_1, 'kill-put', tag_1)
        assert counts_1() == (1, 1)
        path_1 = revision_path(tag_1)
        held_1 = gate('PUT', path_1, 'after_commit_hold')
        session_1 = Session(device_1)
        assert session_1.created == 0 and session_1.command('start')['code'] == 0
        assert held_1['event'].wait(120), 'the revision PUT was never received'
        assert entries[path_1] == raw(tag_1)
        assert counts_1() == (1, 1), 'the outbox row was acknowledged before the response'
        killed_1 = session_1.kill()
        assert killed_1['returncode'] != 0, killed_1
        held_1['release'].set()
        assert counts_1() == (1, 1) and entries[path_1] == raw(tag_1)
        resume_1 = Session(device_1)
        assert resume_1.command('start')['code'] == 0
        finished_1 = resume_1.wait(4)
        assert counts_1() == (1, 0)
        outcomes_1 = [item['status'] for item in requests
                      if item['method'] == 'PUT' and item['path'] == path_1]
        assert outcomes_1 == [201, 412], outcomes_1
        assert entries[path_1] == raw(tag_1)
        heads_1 = protocol_call(device_1, 'heads', 'tag', 'a' * 32)
        assert heads_1['state']['heads'] == 1
        readback_1 = folder / ('readback-' + tag_1['id'] + '.json')
        protocol_call(device_1, 'get', tag_1['id'], readback_1)
        assert readback_1.read_bytes() == raw(tag_1)
        resume_1.close()
        assert counts_1() == (1, 0)
        record('put_committed_before_ack_response_withheld_then_kill_preserves_remote_bytes_and_outbox',
               'A kill while the 201 is withheld leaves exactly the committed remote bytes and the '
               'unacknowledged outbox row; the next sweep replays conditionally (412), verifies by GET, '
               'acknowledges once and never rewrites the immutable object.',
               {'exit': killed_1, 'outbox_after_kill': 1, 'outbox_after_resume': 0,
                'put_outcomes': outcomes_1, 'remote_sha256': digest(entries[path_1]),
                'expected_sha256': digest(raw(tag_1)), 'pushed': finished_1['pushed'],
                'public_read_heads': heads_1['state']['heads'],
                'readback_exact': True})

        # 2. The fixture never reads the body, so nothing can be committed while
        #    the staging snapshot is the only durable local copy.
        device_2 = device('kill-original-upload')
        counts_2 = counting(device_2)
        source_2 = ('resilience original bytes\n' * 36000).encode()
        sha_2 = digest(source_2)
        staged_2 = device_2['originals'] / (sha_2 + '.txt')
        staged_2.write_bytes(source_2)
        book_2 = revision(1, shard=32, kind='book', key='txt:' + sha_2,
                          payload={'format': 'txt', 'source_sha256': sha_2, 'source_bytes': len(source_2),
                                   'title': 'Resilience fixture', 'author': '', 'favorite': False})
        seed(device_2, 'kill-original-upload', book_2)
        object_2 = object_path(sha_2)
        held_2 = gate('PUT', object_2, 'before_body')
        session_2 = Session(device_2)
        assert session_2.command('start')['code'] == 0
        assert held_2['event'].wait(120), 'the original upload was never received'
        assert object_2 not in entries
        assert counts_2() == (1, 1)
        killed_2 = session_2.kill()
        assert killed_2['returncode'] != 0, killed_2
        held_2['release'].set()
        assert object_2 not in entries and counts_2() == (1, 1)
        assert digest(staged_2.read_bytes()) == sha_2
        leftovers_2 = sorted(item.name for item in device_2['cache'].iterdir())
        assert len(leftovers_2) == 1, leftovers_2
        assert leftovers_2[0].startswith('.reader-sync-') and leftovers_2[0].endswith('.tmp'), leftovers_2
        resume_2 = Session(device_2)
        assert resume_2.command('start')['code'] == 0
        resume_2.wait(4)
        assert counts_2() == (1, 0)
        assert digest(entries[object_2]) == sha_2
        uploads_2 = [item['status'] for item in requests
                     if item['method'] == 'PUT' and item['path'] == object_2]
        assert uploads_2 == ['undelivered', 201], uploads_2
        resume_2.close()
        record('kill_during_original_upload_before_remote_commit_leaves_no_partial_remote_object',
               'A kill inside the upload body leaves no remote object and no rewritten staged original; '
               'the only residue is a private transfer temporary that the next sweep never reuses.',
               {'exit': killed_2, 'remote_object_absent': True,
                'staged_sha256': digest(staged_2.read_bytes()), 'leftover_temporaries': leftovers_2,
                'put_outcomes': uploads_2, 'remote_sha256': digest(entries[object_2]),
                'staged_bytes': len(source_2)})

        # 3. An outbox row whose identical immutable object already exists is
        #    replayed conditionally and verified by GET instead of overwritten.
        device_3 = device('replay-existing-remote')
        counts_3 = counting(device_3)
        tag_3 = revision(2, shard=18, key='b' * 32)
        path_3 = publish_revision(tag_3)
        seed(device_3, 'replay', tag_3)
        before_3 = digest(entries[path_3])
        result_3 = step(device_3, shard=18)
        assert result_3['status'] == 0 and result_3['pushed'] == 1, result_3
        assert counts_3() == (1, 0)
        outcomes_3 = [item['status'] for item in requests
                      if item['method'] == 'PUT' and item['path'] == path_3]
        assert outcomes_3 == [412], outcomes_3
        assert digest(entries[path_3]) == before_3
        same_id_3 = [path for path in entries
                     if path.startswith('/dav/exreader-sync-v1/revisions/12/') and
                     path.split('/')[-1].startswith(tag_3['id'])]
        assert same_id_3 == [path_3], same_id_3
        record('replay_of_an_already_committed_immutable_revision_is_412_and_never_rewritten',
               'Publishing a row that is already on the server is answered 412 and acknowledged only '
               'after a byte-identical GET; the remote object count and digest never change.',
               {'put_outcomes': outcomes_3, 'remote_sha256': before_3,
                'object_count_for_id': len(same_id_3), 'pushed': result_3['pushed'],
                'outbox': counts_3()[1]})

        # 4. The verification GET streams a prefix and holds the connection, so
        #    the kill lands before any hash comparison or acknowledgement.
        device_4 = device('kill-verification-get')
        counts_4 = counting(device_4)
        tag_4 = revision(3, shard=18, key='c' * 32)
        path_4 = publish_revision(tag_4)
        seed(device_4, 'kill-verify', tag_4)
        held_4 = gate('GET', path_4, 'partial_body', partial=24)
        session_4 = Session(device_4)
        assert session_4.command('start')['code'] == 0
        assert held_4['event'].wait(120), 'the verification GET was never received'
        assert entries[path_4] == raw(tag_4) and counts_4() == (1, 1)
        killed_4 = session_4.kill()
        assert killed_4['returncode'] != 0, killed_4
        held_4['release'].set()
        assert counts_4() == (1, 1)
        resume_4 = Session(device_4)
        assert resume_4.command('start')['code'] == 0
        resume_4.wait(4)
        assert counts_4() == (1, 0) and entries[path_4] == raw(tag_4)
        outcomes_4 = [item['status'] for item in requests
                      if item['method'] == 'PUT' and item['path'] == path_4]
        assert outcomes_4 == [412, 412], outcomes_4
        resume_4.close()
        record('kill_during_verification_get_before_hash_keeps_remote_bytes_and_outbox',
               'A kill inside the verification GET body cannot acknowledge; the retained row is '
               'replayed after restart and the immutable remote bytes are unchanged.',
               {'exit': killed_4, 'outbox_after_kill': 1, 'put_outcomes': outcomes_4,
                'remote_sha256': digest(entries[path_4]), 'outbox_after_resume': 0})

        # 5. A verification GET that ends short of its declared length is a
        #    transport failure, never an acknowledgement authority.
        device_5 = device('truncated-verification-get')
        counts_5 = counting(device_5)
        tag_5 = revision(4, shard=18, key='d' * 32)
        path_5 = publish_revision(tag_5)
        seed(device_5, 'truncated', tag_5)
        held_5 = gate('GET', path_5, 'short_body_close')
        result_5 = step(device_5, shard=18, timeout=6000)
        assert held_5['event'].wait(60)
        assert result_5['status'] == 3 and result_5['dav_code'] == 3, result_5
        assert counts_5() == (1, 1) and entries[path_5] == raw(tag_5)
        retry_5 = step(device_5, shard=18)
        assert retry_5['status'] == 0 and counts_5() == (1, 0)
        record('truncated_verification_get_is_refused_without_acknowledgement',
               'A verification GET closed before its declared length is reported as a native transport '
               'failure with no acknowledgement and no remote mutation; the retry then acknowledges.',
               {'failure_status': result_5['status'], 'failure_dav_code': result_5['dav_code'],
                'failure_http_status': result_5['http_status'], 'outbox_after_failure': 1,
                'retry_status': retry_5['status'], 'outbox_after_retry': 0})

        # 6. The acknowledgement write is blocked by an exclusive database write
        #    lock held by this harness, which is an external boundary rather than
        #    a shared-module test hook.
        device_6 = device('kill-while-acknowledging')
        counts_6 = counting(device_6)
        prepare_6 = Session(device_6)
        assert prepare_6.command('start')['code'] == 0
        prepare_6.wait(4)
        prepare_6.close()
        assert counts_6() == (0, 0)
        tag_6 = revision(5, shard=18, key='e' * 32)
        path_6 = publish_revision(tag_6)
        seed(device_6, 'ack-window', tag_6)
        held_6 = gate('GET', path_6, 'before_response')
        session_6 = Session(device_6)
        assert session_6.command('start')['code'] == 0
        assert held_6['event'].wait(120), 'the verification GET was never received'
        holder = sqlite3.connect(str(device_6['db']), timeout=60, isolation_level=None)
        holder.execute('BEGIN IMMEDIATE')
        try:
            held_6['release'].set()
            time.sleep(.6)
            killed_6 = session_6.kill()
        finally:
            holder.execute('ROLLBACK')
            holder.close()
        assert killed_6['returncode'] != 0, killed_6
        state_6 = counts_6()
        assert entries[path_6] == raw(tag_6)
        assert state_6[0] == 1 and state_6[1] in (0, 1), state_6
        resume_6 = Session(device_6)
        assert resume_6.command('start')['code'] == 0
        resume_6.wait(4)
        assert counts_6() == (1, 0)
        same_id_6 = [path for path in entries
                     if path.startswith('/dav/exreader-sync-v1/revisions/12/') and
                     path.split('/')[-1].startswith(tag_6['id'])]
        assert same_id_6 == [path_6], same_id_6
        resume_6.close()
        record('kill_while_acknowledging_after_verified_get_never_duplicates_or_loses_work',
               'A kill while the acknowledgement is blocked by an external exclusive database write '
               'lock either leaves the row pending or already acknowledged; both states converge on '
               'one remote object, one history row and an empty outbox after restart.',
               {'exit': killed_6, 'outbox_after_kill': state_6[1], 'history_after_kill': state_6[0],
                'outbox_after_resume': 0, 'object_count_for_id': len(same_id_6),
                'remote_sha256': digest(entries[path_6]),
                'ack_window': 'external BEGIN IMMEDIATE, no shared test hook'})

        # 7. The process leaves without unwinding after the outbox row was
        #    acknowledged, while a discovery request is still in flight.
        device_7 = device('exit-after-ack')
        counts_7 = counting(device_7)
        tag_7 = revision(6, shard=18, key='f' * 32)
        seed(device_7, 'exit-after-ack', tag_7)
        path_7 = revision_path(tag_7)
        held_7 = gate('PROPFIND', '/dav/exreader-sync-v1/revisions/00/', 'before_response')
        session_7 = Session(device_7)
        assert session_7.command('start')['code'] == 0
        assert held_7['event'].wait(120), 'the first discovery request was never received'
        assert counts_7() == (1, 0), 'the outbox row was not acknowledged before discovery'
        assert entries[path_7] == raw(tag_7)
        exited_7 = session_7.abort()
        held_7['release'].set()
        assert exited_7['returncode'] == 7, exited_7
        assert counts_7() == (1, 0) and entries[path_7] == raw(tag_7)
        resume_7 = Session(device_7)
        assert resume_7.command('start')['code'] == 0
        resume_7.wait(4)
        assert counts_7() == (1, 0)
        uploads_7 = [item['status'] for item in requests
                     if item['method'] == 'PUT' and item['path'] == path_7]
        assert uploads_7 == [201], uploads_7
        same_id_7 = [path for path in entries
                     if path.startswith('/dav/exreader-sync-v1/revisions/12/') and
                     path.split('/')[-1].startswith(tag_7['id'])]
        assert same_id_7 == [path_7], same_id_7
        resume_7.close()
        record('abrupt_process_exit_after_outbox_commit_keeps_one_remote_object_and_no_pending_row',
               'An abrupt exit after the acknowledgement keeps the committed object and the empty '
               'outbox; the restart republishes nothing and keeps a single immutable history row.',
               {'exit': exited_7, 'outbox_after_exit': 0, 'put_outcomes': uploads_7,
                'object_count_for_id': len(same_id_7), 'remote_sha256': digest(entries[path_7]),
                'outbox_after_restart': 0})

        # 8. The original download is killed inside the body, before the local
        #    atomic publication of the cache identity.
        device_8 = device('kill-original-download')
        counts_8 = counting(device_8)
        source_8 = ('remote original for download\n' * 20000).encode()
        sha_8 = digest(source_8)
        book_8 = revision(1, shard=32, kind='book', key='txt:' + sha_8,
                          payload={'format': 'txt', 'source_sha256': sha_8, 'source_bytes': len(source_8),
                                   'title': 'Download fixture', 'author': '', 'favorite': False})
        publish_revision(book_8)
        object_8 = publish_object(sha_8, source_8)
        held_8 = gate('GET', object_8, 'partial_body', partial=48)
        killed_8 = subprocess.Popen(step_command(device_8, 32), env=environment,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding='utf-8')
        assert held_8['event'].wait(120), 'the original download was never received'
        assert not (device_8['cache'] / (sha_8 + '.txt')).exists()
        killed_8.kill()
        assert killed_8.wait(timeout=30) != 0
        held_8['release'].set()
        assert not (device_8['cache'] / (sha_8 + '.txt')).exists()
        leftovers_8 = sorted(item.name for item in device_8['cache'].iterdir())
        assert leftovers_8, 'the killed download left no observable private temporary'
        assert all(name.startswith('.reader-sync-') or name.startswith('.exr-webdav-')
                   for name in leftovers_8), leftovers_8
        assert counts_8() == (0, 0)
        retry_8 = step(device_8, shard=32)
        assert retry_8['status'] == 0 and retry_8['originals_verified'] == 1, retry_8
        published_8 = device_8['cache'] / (sha_8 + '.txt')
        assert digest(published_8.read_bytes()) == sha_8
        assert counts_8() == (1, 0) and entries[object_8] == source_8
        record('kill_during_original_download_leaves_no_published_cache_identity',
               'A kill inside the original body leaves no cache identity (no <sha>.<format> file) and '
               'no received revision; only private transfer temporaries remain, and the retry '
               'publishes the exact bytes atomically.',
               {'exit': {'pid': killed_8.pid,
                         'termination': 'TerminateProcess' if os.name == 'nt' else 'SIGKILL',
                         'returncode': killed_8.returncode},
                'cache_identity_absent': True, 'leftover_temporaries': leftovers_8,
                'history_after_kill': 0, 'cache_sha256': digest(published_8.read_bytes()),
                'originals_verified': retry_8['originals_verified'],
                'remote_sha256': digest(entries[object_8])})

        # 9. A bounded transfer timeout on the original download removes both
        #    private temporaries and keeps the reference pending.
        device_9 = device('timeout-original-download')
        counts_9 = counting(device_9)
        source_9 = ('timeout original bytes\n' * 20000).encode()
        sha_9 = digest(source_9)
        book_9 = revision(1, shard=32, kind='book', key='txt:' + sha_9,
                          payload={'format': 'txt', 'source_sha256': sha_9, 'source_bytes': len(source_9),
                                   'title': 'Timeout fixture', 'author': '', 'favorite': False})
        publish_revision(book_9)
        object_9 = publish_object(sha_9, source_9)
        held_9 = gate('GET', object_9, 'stall_before_headers')
        began_9 = time.monotonic()
        result_9 = step(device_9, shard=32, timeout=1500)
        elapsed_9 = round(time.monotonic() - began_9, 2)
        assert held_9['event'].wait(60)
        assert result_9['status'] == 3 and result_9['dav_code'] == 3, result_9
        assert result_9['http_status'] == 0, result_9
        assert elapsed_9 < 45, elapsed_9
        assert not list(device_9['cache'].iterdir()), list(device_9['cache'].iterdir())
        assert counts_9() == (0, 0)
        held_9['release'].set()
        retry_9 = step(device_9, shard=32)
        assert retry_9['status'] == 0, retry_9
        assert digest((device_9['cache'] / (sha_9 + '.txt')).read_bytes()) == sha_9
        record('original_download_timeout_removes_private_temp_and_keeps_pending_identity',
               'A transfer timeout inside the original download is reported as a bounded native '
               'transport failure, leaves no temporary and no partial identity, and the explicit '
               'retry publishes the exact bytes.',
               {'failure_status': result_9['status'], 'failure_dav_code': result_9['dav_code'],
                'failure_http_status': result_9['http_status'], 'elapsed_seconds': elapsed_9,
                'timeout_ms': 1500, 'leftover_temporaries': [],
                'cache_sha256': digest((device_9['cache'] / (sha_9 + '.txt')).read_bytes())})

        # 10. A published cache identity is re-verified on every later sweep and
        #     is never silently replaced by a re-download.
        device_10 = device('cached-original-identity')
        counts_10 = counting(device_10)
        source_10 = ('cached identity bytes\n' * 20000).encode()
        sha_10 = digest(source_10)
        book_10 = revision(1, shard=32, kind='book', key='txt:' + sha_10,
                           payload={'format': 'txt', 'source_sha256': sha_10, 'source_bytes': len(source_10),
                                    'title': 'Identity fixture', 'author': '', 'favorite': False})
        publish_revision(book_10)
        object_10 = publish_object(sha_10, source_10)
        assert step(device_10, shard=32)['status'] == 0
        cached_10 = device_10['cache'] / (sha_10 + '.txt')
        assert digest(cached_10.read_bytes()) == sha_10
        damaged_10 = bytearray(cached_10.read_bytes())
        damaged_10[0] ^= 0xFF
        cached_10.write_bytes(bytes(damaged_10))
        result_10 = step(device_10, shard=32)
        assert result_10['status'] == 5, result_10
        assert cached_10.read_bytes() == bytes(damaged_10)
        assert counts_10() == (1, 0) and entries[object_10] == source_10
        cached_10.write_bytes(source_10)
        assert step(device_10, shard=32)['status'] == 0
        record('cached_original_identity_is_reverified_before_reuse',
               'A same-length corrupted cache identity is refused with the hash status and is never '
               'overwritten behind the host, while the verified bytes keep the history unchanged.',
               {'corrupt_status': result_10['status'],
                'corrupt_cache_sha256': digest(bytes(damaged_10)),
                'expected_sha256': sha_10, 'cache_unchanged_after_refusal': True,
                'history': counts_10()[0]})

        # 11. A remote original whose bytes differ from its claimed identity is
        #     refused before it can become a local identity.
        device_11 = device('wrong-remote-original')
        counts_11 = counting(device_11)
        source_11 = ('wrong remote bytes\n' * 16000).encode()
        sha_11 = digest(source_11)
        book_11 = revision(1, shard=32, kind='book', key='txt:' + sha_11,
                           payload={'format': 'txt', 'source_sha256': sha_11, 'source_bytes': len(source_11),
                                    'title': 'Wrong bytes', 'author': '', 'favorite': False})
        publish_revision(book_11)
        object_11 = publish_object(sha_11, source_11)
        foreign_11 = b'X' + source_11[1:]
        with lock:
            entries[object_11] = foreign_11
        result_11 = step(device_11, shard=32)
        assert result_11['status'] == 5, result_11
        assert not (device_11['cache'] / (sha_11 + '.txt')).exists()
        assert counts_11() == (0, 0)
        assert entries[object_11] == foreign_11
        record('remote_original_with_wrong_bytes_is_never_published_as_local_identity',
               'A remote original with the right length but the wrong digest is refused with the hash '
               'status, publishes no cache identity and receives no revision.',
               {'failure_status': result_11['status'],
                'remote_sha256': digest(foreign_11), 'expected_sha256': sha_11,
                'cache_identity_absent': True, 'history': counts_11()[0]})

        # 12. Real 401 from the fixture is surfaced with no acknowledgement and
        #     no implicit replay.
        device_12 = device('real-401')
        counts_12 = counting(device_12)
        tag_12 = revision(7, shard=18, key='g' * 32)
        seed(device_12, 'real-401', tag_12)
        first_12 = len(requests)
        global_faults.append((401, {'WWW-Authenticate': 'Basic realm="resilience-fixture"'}))
        result_12 = step(device_12, shard=18)
        global_faults[:] = []
        staged_12 = list(requests[first_12:])
        assert result_12['status'] == 3 and result_12['dav_code'] == 6, result_12
        assert result_12['http_status'] == 401, result_12
        assert counts_12() == (1, 1)
        assert staged_12 and all(item['status'] == 401 for item in staged_12), staged_12
        quiet_12 = len(requests)
        time.sleep(.4)
        assert len(requests) == quiet_12
        retry_12 = step(device_12, shard=18)
        assert retry_12['status'] == 0 and counts_12() == (1, 0)
        record('real_401_is_reported_without_acknowledgement_or_implicit_retry',
               'A real 401 is reported as an authentication failure with the status preserved, no '
               'acknowledgement, no automatic replay, and the row is published only on an explicit retry.',
               {'failure_status': result_12['status'], 'failure_dav_code': result_12['dav_code'],
                'failure_http_status': result_12['http_status'],
                'rejected_requests': len(staged_12), 'outbox_after_failure': 1,
                'implicit_requests_during_wait': 0, 'retry_status': retry_12['status']})

        # 13. Real 403 is a permission failure, never a silent success.
        device_13 = device('real-403')
        counts_13 = counting(device_13)
        tag_13 = revision(8, shard=18, key='h' * 32)
        seed(device_13, 'real-403', tag_13)
        first_13 = len(requests)
        global_faults.append((403, {}))
        result_13 = step(device_13, shard=18)
        global_faults[:] = []
        staged_13 = requests[first_13:]
        assert result_13['status'] == 3 and result_13['dav_code'] == 5, result_13
        assert result_13['http_status'] == 403, result_13
        assert counts_13() == (1, 1)
        assert staged_13 and all(item['status'] == 403 for item in staged_13), staged_13
        quiet_13 = len(requests)
        time.sleep(.4)
        assert len(requests) == quiet_13
        retry_13 = step(device_13, shard=18)
        assert retry_13['status'] == 0 and counts_13() == (1, 0)
        record('real_403_is_reported_without_acknowledgement_or_implicit_retry',
               'A real 403 stays a reported failure with the status preserved, no acknowledgement and '
               'no implicit replay; the retained row is published by an explicit retry.',
               {'failure_status': result_13['status'], 'failure_dav_code': result_13['dav_code'],
                'failure_http_status': result_13['http_status'],
                'rejected_requests': len(staged_13), 'outbox_after_failure': 1,
                'retry_status': retry_13['status']})

        # 14. Real 429 with Retry-After is not followed by an implicit replay.
        device_14 = device('real-429')
        counts_14 = counting(device_14)
        tag_14 = revision(9, shard=18, key='i' * 32)
        seed(device_14, 'real-429', tag_14)
        path_14 = revision_path(tag_14)
        fault('PUT', path_14, 429, {'Retry-After': '2'})
        result_14 = step(device_14, shard=18, timeout=6000)
        assert result_14['status'] == 3 and result_14['dav_code'] == 5, result_14
        assert result_14['http_status'] == 429, result_14
        assert counts_14() == (1, 1) and path_14 not in entries
        quiet_14 = len(requests)
        time.sleep(2.5)
        assert len(requests) == quiet_14
        retry_14 = step(device_14, shard=18)
        assert retry_14['status'] == 0 and counts_14() == (1, 0)
        outcomes_14 = [item['status'] for item in requests
                       if item['method'] == 'PUT' and item['path'] == path_14]
        assert outcomes_14 == [429, 201], outcomes_14
        record('real_429_retry_after_is_not_followed_by_implicit_replay',
               'A real 429 with Retry-After is surfaced with no acknowledgement and no request during '
               'the advertised interval; the explicit retry then publishes the immutable bytes once.',
               {'failure_status': result_14['status'], 'failure_http_status': result_14['http_status'],
                'retry_after': 2, 'requests_during_retry_after': 0,
                'put_outcomes': outcomes_14, 'outbox_after_retry': 0})

        # 15. A real 503 during publication keeps the outbox and re-publishes on
        #     an explicit retry only.
        device_15 = device('real-503')
        counts_15 = counting(device_15)
        tag_15 = revision(10, shard=18, key='j' * 32)
        seed(device_15, 'real-503', tag_15)
        path_15 = revision_path(tag_15)
        fault('PUT', path_15, 503, {'Retry-After': '1'})
        result_15 = step(device_15, shard=18, timeout=6000)
        assert result_15['status'] == 3 and result_15['dav_code'] == 5, result_15
        assert result_15['http_status'] == 503, result_15
        assert path_15 not in entries and counts_15() == (1, 1)
        quiet_15 = len(requests)
        time.sleep(1.5)
        assert len(requests) == quiet_15
        retry_15 = step(device_15, shard=18)
        assert retry_15['status'] == 0 and counts_15() == (1, 0)
        outcomes_15 = [item['status'] for item in requests
                       if item['method'] == 'PUT' and item['path'] == path_15]
        assert outcomes_15 == [503, 201], outcomes_15
        assert entries[path_15] == raw(tag_15)
        record('real_503_during_publication_retains_outbox_and_republishes_on_explicit_retry',
               'A real 503 during publication is reported, commits nothing remotely, keeps the outbox '
               'row and is not retried implicitly; the explicit retry publishes the exact bytes once.',
               {'failure_status': result_15['status'], 'failure_http_status': result_15['http_status'],
                'remote_absent_after_failure': True, 'requests_during_retry_after': 0,
                'put_outcomes': outcomes_15, 'remote_sha256': digest(entries[path_15]),
                'outbox_after_retry': 0})

        # 16. A mid-sweep 503 keeps the completed shard progress and resumes at
        #     the failed shard on the next explicit start.
        device_16 = device('mid-sweep-503')
        counts_16 = counting(device_16)
        failed_path_16 = '/dav/exreader-sync-v1/revisions/28/'
        fault('PROPFIND', failed_path_16, 503, {'Retry-After': '1'})
        session_16 = Session(device_16)
        assert session_16.command('start')['code'] == 0
        failed_16 = session_16.wait(5)
        assert failed_16['status'] == 5 and failed_16['dav_code'] == 5, failed_16
        assert failed_16['http_status'] == 503, failed_16
        assert failed_16['completed_shards'] == 40 and failed_16['shard'] == 40, failed_16
        assert failed_16['sweeps'] == 0 and failed_16['attempt'] == 1, failed_16
        assert len([item for item in requests if item['path'] == failed_path_16]) == 1
        assert session_16.command('start')['code'] == 0
        finished_16 = session_16.wait(4)
        assert finished_16['sweeps'] == 1 and finished_16['completed_shards'] == 256, finished_16
        assert finished_16['attempt'] == 2, finished_16
        assert len([item for item in requests if item['path'] == failed_path_16]) == 2
        session_16.close()
        record('mid_sweep_503_keeps_completed_shards_and_resumes_at_the_failed_shard',
               'A real 503 in the middleware of the sweep keeps the 40 completed shards, reports the '
               'failed shard and resumes there on the next explicit start instead of restarting work.',
               {'failure_status': failed_16['status'],
                'failure_http_status': failed_16['http_status'],
                'completed_shards_at_failure': failed_16['completed_shards'],
                'shard_at_failure': failed_16['shard'], 'attempt_at_failure': failed_16['attempt'],
                'completed_shards_after_restart': finished_16['completed_shards'],
                'sweeps_after_restart': finished_16['sweeps'],
                'failed_path_requests': 2})

        # 17. A reset inside the PUT body is resolved by the verification GET,
        #     which is the only acknowledgement authority.
        device_17 = device('reset-during-put')
        counts_17 = counting(device_17)
        tag_17 = revision(11, shard=18, key='k' * 32)
        seed(device_17, 'reset-during-put', tag_17)
        path_17 = revision_path(tag_17)
        held_17 = gate('PUT', path_17, 'reset_mid_body', partial=32)
        result_17 = step(device_17, shard=18, timeout=6000)
        assert held_17['event'].wait(60)
        assert result_17['status'] == 3, result_17
        assert result_17['dav_code'] == 5 and result_17['http_status'] == 404, result_17
        assert path_17 not in entries and counts_17() == (1, 1)
        retry_17 = step(device_17, shard=18)
        assert retry_17['status'] == 0 and counts_17() == (1, 0)
        assert entries[path_17] == raw(tag_17)
        record('connection_reset_during_put_body_resolves_by_get_and_keeps_outbox',
               'A connection reset inside the PUT body is treated as an ambiguous transport outcome: '
               'nothing is committed, the verification GET reports the object absent and the outbox '
               'row stays until an explicit retry publishes it.',
               {'failure_status': result_17['status'], 'failure_dav_code': result_17['dav_code'],
                'failure_http_status': result_17['http_status'],
                'remote_absent_after_reset': True, 'outbox_after_failure': 1,
                'retry_status': retry_17['status'],
                'remote_sha256': digest(entries[path_17])})

        # 18. A bounded publication timeout leaves no remote object.
        device_18 = device('publication-timeout')
        counts_18 = counting(device_18)
        tag_18 = revision(12, shard=18, key='l' * 32)
        seed(device_18, 'publication-timeout', tag_18)
        path_18 = revision_path(tag_18)
        held_18 = gate('PUT', path_18, 'stall_before_headers')
        began_18 = time.monotonic()
        result_18 = step(device_18, shard=18, timeout=1200)
        elapsed_18 = round(time.monotonic() - began_18, 2)
        assert held_18['event'].wait(60)
        assert result_18['status'] == 3, result_18
        assert elapsed_18 < 30, elapsed_18
        assert path_18 not in entries and counts_18() == (1, 1)
        held_18['release'].set()
        retry_18 = step(device_18, shard=18)
        assert retry_18['status'] == 0 and counts_18() == (1, 0)
        assert entries[path_18] == raw(tag_18)
        record('bounded_publication_timeout_leaves_no_remote_object_and_keeps_outbox',
               'A stalling server is bounded by the configured transfer timeout instead of hanging, '
               'commits nothing, keeps the outbox row and lets an explicit retry publish the bytes.',
               {'failure_status': result_18['status'],
                'failure_http_status': result_18['http_status'],
                'elapsed_seconds': elapsed_18, 'timeout_ms': 1200,
                'remote_absent_after_timeout': True, 'outbox_after_failure': 1,
                'retry_status': retry_18['status'],
                'remote_sha256': digest(entries[path_18])})

        # 19. A foreign body already stored at the immutable path is never
        #     overwritten, and it blocks the acknowledgement.
        device_19 = device('foreign-immutable-bytes')
        counts_19 = counting(device_19)
        tag_19 = revision(13, shard=18, key='m' * 32)
        path_19 = revision_path(tag_19)
        foreign_19 = b' ' + raw(tag_19)[1:]
        publish_revision(tag_19, foreign_19)
        seed(device_19, 'foreign-bytes', tag_19)
        result_19 = step(device_19, shard=18)
        assert result_19['status'] == 5, result_19
        assert counts_19() == (1, 1)
        assert entries[path_19] == foreign_19
        outcomes_19 = [item['status'] for item in requests
                       if item['method'] == 'PUT' and item['path'] == path_19]
        assert outcomes_19 == [412], outcomes_19
        with lock:
            entries[path_19] = raw(tag_19)
        retry_19 = step(device_19, shard=18)
        assert retry_19['status'] == 0 and counts_19() == (1, 0)
        assert entries[path_19] == raw(tag_19)
        record('existing_immutable_object_with_foreign_bytes_is_not_overwritten_or_acked',
               'A different body already stored at the immutable path is preserved byte for byte, the '
               'acknowledgement is refused with the hash status, and only the correct bytes let the '
               'replay acknowledge.',
               {'failure_status': result_19['status'], 'put_outcomes': outcomes_19,
                'foreign_sha256': digest(foreign_19), 'expected_sha256': digest(raw(tag_19)),
                'foreign_bytes_preserved': True, 'outbox_after_failure': 1,
                'retry_status': retry_19['status'], 'outbox_after_retry': 0})

        # 20. The same account reopens after a forced kill without rebinding.
        device_20 = device('reopen-same-account')
        counts_20 = counting(device_20)
        prepare_20 = Session(device_20)
        assert prepare_20.command('start')['code'] == 0
        prepare_20.wait(4)
        prepare_20.close()
        manifests_20 = sorted(device_20['base'].glob('*.sync-account'))
        assert len(manifests_20) == 1, manifests_20
        manifest_20 = manifests_20[0]
        binding_20 = digest(manifest_20.read_bytes())
        tag_20 = revision(14, shard=18, key='n' * 32)
        seed(device_20, 'reopen', tag_20)
        path_20 = revision_path(tag_20)
        held_20 = gate('PUT', path_20, 'after_commit_hold')
        session_20 = Session(device_20)
        assert session_20.command('start')['code'] == 0
        assert held_20['event'].wait(120), 'the revision PUT was never received'
        killed_20 = session_20.kill()
        held_20['release'].set()
        assert killed_20['returncode'] != 0 and counts_20() == (1, 1)
        reopened_20 = Session(device_20)
        assert reopened_20.created == 0
        assert reopened_20.command('start')['code'] == 0
        finished_20 = reopened_20.wait(4)
        assert finished_20['status'] == 0, finished_20
        assert digest(manifest_20.read_bytes()) == binding_20
        assert counts_20() == (1, 0) and entries[path_20] == raw(tag_20)
        reopened_20.close()
        assert digest(manifest_20.read_bytes()) == binding_20
        record('same_account_reopen_after_forced_kill_resumes_without_rebinding',
               'After a forced kill the same account and root reopen with no rebinding, the binding '
               'bytes stay identical, the retained row is acknowledged once and the history is intact.',
               {'exit': killed_20, 'binding_sha256': binding_20,
                'binding_unchanged': True, 'outbox_after_resume': 0,
                'remote_sha256': digest(entries[path_20]),
                'pushed_on_resume': finished_20['pushed']})

        # 21. Another account on the same product store is refused after the
        #     kill, before any request.
        device_21 = device('reopen-other-account')
        counts_21 = counting(device_21)
        prepare_21 = Session(device_21)
        assert prepare_21.command('start')['code'] == 0
        prepare_21.wait(4)
        prepare_21.close()
        manifests_21 = sorted(device_21['base'].glob('*.sync-account'))
        assert len(manifests_21) == 1, manifests_21
        manifest_21 = manifests_21[0]
        binding_21 = digest(manifest_21.read_bytes())
        tag_21 = revision(15, shard=18, key='o' * 32)
        seed(device_21, 'reopen-other', tag_21)
        path_21 = revision_path(tag_21)
        held_21 = gate('PUT', path_21, 'after_commit_hold')
        session_21 = Session(device_21)
        assert session_21.command('start')['code'] == 0
        assert held_21['event'].wait(120), 'the revision PUT was never received'
        killed_21 = session_21.kill()
        held_21['release'].set()
        assert killed_21['returncode'] != 0 and counts_21() == (1, 1)
        before_21 = len(requests)
        other_21 = Session(dict(device_21, account=str(uuid.uuid4())))
        assert other_21.created == 0
        assert other_21.command('start')['code'] == 0
        refused_21 = other_21.wait(5)
        assert refused_21['status'] == 4, refused_21
        assert len(requests) == before_21, requests[before_21:]
        assert digest(manifest_21.read_bytes()) == binding_21
        other_21.close()
        assert counts_21() == (1, 1)
        record('different_account_after_forced_kill_is_refused_before_any_request',
               'A different account on the killed store is refused with the account status before any '
               'request, the binding is not rewritten and the retained outbox row is untouched.',
               {'exit': killed_21, 'refusal_status': refused_21['status'],
                'requests_after_refusal': 0, 'binding_unchanged': True,
                'outbox_after_refusal': 1})

        # Evidence integrity for the whole run.
        assert all(item['authorized'] for item in requests)
        assert all(item['if_none_match'] == '*' for item in requests if item['method'] == 'PUT')
        assert not any(item['method'] in ('GET', 'PUT') and item['path'].endswith(('.sqlite', '.db'))
                       for item in requests)
        assert [check['id'] for check in checks] == NEW_CHECKS, [c['id'] for c in checks]

        original = json.loads(arguments.original_report.read_text(encoding='utf-8'))
        assert original['accepted'] is True
        assert original['source_sha'] == os.environ['GITHUB_SHA']
        assert str(original['run_id']) == os.environ['GITHUB_RUN_ID']
        assert str(original['attempt']) == os.environ['GITHUB_RUN_ATTEMPT']
        assert sorted(original['checks']) == sorted(ORIGINAL_SESSION_CHECKS), original['checks']
        assert len(original['checks']) == 20

        (folder / 'requests.json').write_text(json.dumps(requests, indent=2), encoding='utf-8')
        for path in folder.rglob('*'):
            if path.is_file() and path.suffix != '.key':
                data = path.read_bytes()
                assert secret.encode() not in data, path
                assert authorization.encode() not in data, path
        report = {'accepted': True, 'source_sha': os.environ['GITHUB_SHA'],
                  'run_id': os.environ['GITHUB_RUN_ID'], 'attempt': os.environ['GITHUB_RUN_ATTEMPT'],
                  'platform': sys.platform, 'count': len(checks), 'checks': checks,
                  'uncovered': list(UNCOVERED_LIMITS),
                  'original_session_suite': {'count': len(original['checks']),
                                             'ids': list(ORIGINAL_SESSION_CHECKS),
                                             'consumer_sha256': original['consumer_sha256'],
                                             'source': 'build/session-evidence/result.json'},
                  'consumer_sha256': digest(consumer.read_bytes()),
                  'revision_consumer_sha256': digest(protocol.read_bytes()),
                  'fault_boundaries_accepted': True,
                  'original_session_suite_preserved': True,
                  'fixture_endpoint': 'IPv4 loopback with verified certificate IP SAN',
                  'certificate_san': 'DNS:localhost,IP:127.0.0.1',
                  'native_transport': 'platform native HTTPS' if os.name == 'nt' else sys.platform,
                  'sdk_changed': False, 'schema_changed': False,
                  'three_platform_accepted': False, 'host_ui_accepted': False,
                  'metadata_projection_accepted': False, 'complete_product': False,
                  'request_count': len(requests),
                  'duration_seconds': round(time.monotonic() - started, 2)}
        (folder / 'result.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps({'accepted': True, 'platform': sys.platform, 'checks': len(checks),
                          'source_sha': os.environ['GITHUB_SHA']}), flush=True)
    finally:
        cleanup()
        for certificate in certificates.glob('*.key'):
            certificate.unlink()


if __name__ == '__main__':
    main()
