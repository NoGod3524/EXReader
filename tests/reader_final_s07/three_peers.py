# SPDX-License-Identifier: MIT
"""Actions-only three-peer fault regression on the frozen public raw7 module.

Three native peers talk to one controlled HTTPS WebDAV origin on IPv4 loopback
with a certificate carrying a verified IP SAN:

    sender          publishes the genuine public-SDK capture graph
    receiver-one    receives it, then produces the newer head and the ordered pair
    receiver-two    receives it, and is served a child before its parent

Two old MAX2 consumers (legacy1 / legacy2) and one MAX2 receiver share the same
server root. Every wire movement is a real native HTTPS request from an
installed frozen consumer process; no fixture opens SQLite, no fixture writes a
revision row, and no fixture ever composes a successful wire. The only bytes
the fixture itself places on the origin are the refusal inputs of item 6: one
real v3 capture with the single field anchor_version changed to an unknown
version, and one real v3 capture served to the MAX2 consumers. Both are
recorded with their exact bytes and SHA-256.

The fault gates are server side only: a reset before the body is read, a
committed body whose response is withheld, and a dropped verification GET.
Each gate is consumed once per (method, resource) and logged.
"""
import argparse
import base64
import hashlib
import json
import os
import socket
import ssl
import subprocess
import sys
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'webdav'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from cloud_native import trust_fixture_certificates
from checks import CHECKS, EXPECTED, GAPS

PDF_SHA = '5627a430fa04cbe11d38eb2682e336ef21e147d445753ed46ed11a7d5e3167cc'
PDF_BYTES = 8845
BOOK = 'pdf:' + PDF_SHA
COLLECTION = 'exreader-sync-v1'
NAMESPACES = ('dav', 'unknown', 'raw3', 'legacy1', 'legacy2')
SUFFIX = '.exe' if os.name == 'nt' else ''
TXT = b'A real public SDK text capture has enough context for stable matching.'
BOOKMARK = 'b' * 32
OLD_ID = '00000000000000000000000000000300'
NEWER_ID = '00000000000000000000000000000600'
PARENT_ID = '00000000000000000000000000000500'
CHILD_ID = '00000000000000000000000000000400'
LEGACY_BOOK_ID = '00000000000000000000000000009999'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def leaf_name(path):
    return path.rsplit('/', 1)[-1]


def revision_path(namespace, revision_id, body):
    return ('/' + namespace + '/' + COLLECTION + '/revisions/' + revision_id[:2] + '/'
            + revision_id + '-' + digest(body) + '.json')


def object_path(namespace, sha, extension):
    return '/' + namespace + '/' + COLLECTION + '/objects/' + sha[:2] + '/' + sha + '.' + extension


def inventory(remote, namespace):
    """Remote immutable object count per revision ID for one namespace."""
    prefix = '/' + namespace + '/' + COLLECTION + '/revisions/'
    with remote.lock:
        paths = [path for path in remote.entries if path.startswith(prefix)]
    counts = {}
    for path in paths:
        name = leaf_name(path)
        if len(name) != 102 or not name.endswith('.json'):
            continue
        counts[name[:32]] = counts.get(name[:32], 0) + 1
    return counts


def statuses(remote, method, path):
    with remote.lock:
        return [item['status'] for item in remote.requests if item['method'] == method and item['path'] == path]


class Remote:
    """Whole-object WebDAV origin with one-shot faults and a full request trace."""

    def __init__(self, authorization):
        self.authorization = authorization
        self.lock = threading.Lock()
        self.entries = {}
        self.dirs = {'/'}
        self.requests = []
        self.faults = {}
        self.planned = []
        self.faulted = []
        self.port = 0
        self.server = None

    def namespace(self, name):
        self.ensure('/' + name + '/')

    def ensure(self, folder):
        current = ''
        for part in [item for item in folder.strip('/').split('/') if item]:
            current += '/' + part
            with self.lock:
                self.dirs.add(current + '/')

    def fault(self, method, path, name):
        with self.lock:
            self.faults.setdefault((method, path), []).append(name)
            self.planned.append({'method': method, 'path': path, 'fault': name})

    def take(self, method, path):
        with self.lock:
            queue = self.faults.get((method, path))
            if not queue:
                return None
            name = queue.pop(0)
            self.faulted.append({'method': method, 'path': path, 'fault': name})
            return name

    def record(self, method, path, authenticated, status, body=None):
        with self.lock:
            self.requests.append({'method': method, 'path': path, 'authenticated': bool(authenticated),
                                  'status': status, 'bytes': 0 if body is None else len(body),
                                  'sha256': None if body is None else digest(body)})

    def publish(self, namespace, body):
        """Place one refusal-input object, exactly as another actor would."""
        parsed = json.loads(body.decode('utf-8'))
        path = revision_path(namespace, parsed['id'], body)
        self.ensure(path.rsplit('/', 1)[0] + '/')
        with self.lock:
            self.entries[path] = body
        return path

    def listing(self, folder):
        with self.lock:
            exists = folder in self.dirs
            children = [(item, True, 0) for item in self.dirs
                        if item != folder and item.startswith(folder)
                        and '/' not in item[len(folder):].rstrip('/')]
            children += [(item, False, len(body)) for item, body in self.entries.items()
                         if item.startswith(folder) and '/' not in item[len(folder):]]
        return exists, sorted(children)


def serve(remote, certificate, key):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def log_message(self, *arguments):
            pass

        def drop(self):
            self.close_connection = True
            try:
                self.connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                self.connection.close()
            except OSError:
                pass

        def respond(self, code, body=b'', declared=None):
            self.send_response(code)
            self.send_header('Content-Length', str(len(body) if declared is None else declared))
            self.send_header('Connection', 'close')
            self.end_headers()
            self.close_connection = True
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError, ssl.SSLError):
                pass

        def authorized(self, method):
            if self.headers.get('Authorization') == remote.authorization:
                return True
            remote.record(method, self.path, False, 401)
            self.respond(401)
            return False

        def do_MKCOL(self):
            if not self.authorized('MKCOL'):
                return
            with remote.lock:
                exists = self.path in remote.dirs
                parent = self.path.rstrip('/').rsplit('/', 1)[0] + '/'
                if parent not in remote.dirs and not exists:
                    code = 409
                else:
                    remote.dirs.add(self.path)
                    code = 405 if exists else 201
            remote.record('MKCOL', self.path, True, code)
            self.respond(code)

        def do_PUT(self):
            path = self.path
            fault = remote.take('PUT', path)
            if fault == 'reset_before_commit':
                remote.record('PUT', path, self.headers.get('Authorization') == remote.authorization,
                              'reset_before_commit')
                self.drop()
                return
            length = int(self.headers.get('Content-Length', 0) or 0)
            body = self.rfile.read(length) if length else b''
            if not self.authorized('PUT'):
                return
            if self.headers.get('If-None-Match') != '*':
                remote.record('PUT', path, True, 'missing-if-none-match', body)
                self.respond(428)
                return
            with remote.lock:
                exists = path in remote.entries
                if not exists:
                    remote.entries[path] = body
            code = 412 if exists else 201
            remote.record('PUT', path, True, code, body)
            if fault == 'commit_then_drop':
                self.drop()
                return
            self.respond(code)

        def do_GET(self):
            fault = remote.take('GET', self.path)
            if not self.authorized('GET'):
                return
            with remote.lock:
                body = remote.entries.get(self.path)
            if fault == 'drop':
                remote.record('GET', self.path, True, 'drop')
                self.drop()
                return
            if body is None:
                remote.record('GET', self.path, True, 404)
                self.respond(404)
                return
            remote.record('GET', self.path, True, 200, body)
            if fault == 'truncate':
                self.respond(200, body[:len(body) // 2], declared=len(body))
                return
            self.respond(200, body)

        def do_PROPFIND(self):
            length = int(self.headers.get('Content-Length', 0) or 0)
            if length:
                self.rfile.read(length)
            if not self.authorized('PROPFIND'):
                return
            if self.headers.get('Depth') != '1':
                remote.record('PROPFIND', self.path, True, 'depth')
                self.respond(400)
                return
            exists, children = remote.listing(self.path)
            if not exists:
                remote.record('PROPFIND', self.path, True, 404)
                self.respond(404)
                return
            rows = []
            for item, folder, size in children:
                rows.append('<d:response><d:href>' + item + '</d:href><d:propstat><d:prop><d:resourcetype>'
                            + ('<d:collection/>' if folder else '')
                            + '</d:resourcetype><d:getcontentlength>' + str(size)
                            + '</d:getcontentlength></d:prop><d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>')
            body = ('<d:multistatus xmlns:d="DAV:">' + ''.join(rows) + '</d:multistatus>').encode('utf-8')
            remote.record('PROPFIND', self.path, True, 207)
            self.respond(207, body)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.daemon_threads = True
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(str(certificate), str(key))
    server.socket = context.wrap_socket(server.socket, server_side=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    remote.server = server
    remote.port = server.server_port


class Harness:
    def __init__(self, arguments):
        self.arguments = arguments
        self.output = arguments.output.resolve()
        self.output.mkdir(parents=True)
        self.logs = self.output / 'logs'
        self.logs.mkdir()
        self.certificates = self.output / 'certificates'
        self.certificates.mkdir()
        self.core = arguments.core.resolve()
        self.programs = arguments.programs.resolve()
        self.old_revision = arguments.old_revision.resolve()
        self.old_sync = arguments.old_sync.resolve()
        self.old_command = arguments.old_command.resolve()
        self.devices = self.output / 'devices'
        self.devices.mkdir()
        self.checks = []
        self.operations = []
        self.secret = uuid.uuid4().hex
        self.authorization = 'Basic ' + base64.b64encode(('s07:' + self.secret).encode('utf-8')).decode('ascii')
        self.environment = dict(os.environ, READER_TEST_AUTH=self.authorization)
        self.remote = Remote(self.authorization)

    def program(self, name):
        return self.programs / ('raw-' + name + SUFFIX)

    def device(self, name):
        folder = self.devices / name
        (folder / 'cache').mkdir(parents=True)
        (folder / 'originals').mkdir()
        return folder

    def url(self, namespace):
        return 'https://127.0.0.1:' + str(self.remote.port) + '/' + namespace + '/'

    def call(self, argv, name, expected=None, timeout=300):
        command = [str(item) for item in argv]
        process = subprocess.run(command, env=self.environment, capture_output=True,
                                 encoding='utf-8', errors='strict', timeout=timeout)
        (self.logs / (name + '.log')).write_text(process.stdout + process.stderr, encoding='utf-8')
        self.operations.append({'name': name, 'argv': command[1:], 'returncode': process.returncode})
        assert process.returncode == 0, (name, process.returncode, process.stdout[-3000:], process.stderr[-3000:])
        value = None
        for line in reversed(process.stdout.strip().splitlines()):
            candidate = line.strip()
            if candidate.startswith('{') and candidate.endswith('}'):
                value = json.loads(candidate)
                break
        if expected is not None:
            assert value is not None, (name, process.stdout[-2000:])
            assert value['status'] == expected, (name, value)
        return value

    def sync(self, device, name, namespace='dav', shard=0, after='-', limit=100, expected=0, program=None):
        executable = program if program is not None else self.program('sync')
        return self.call([executable, self.url(namespace), device / 'catalog.sqlite', device / 'cache',
                          device / 'originals', shard, after, limit, 'inert-current-position',
                          str(2 ** 64 - 1)], name, expected)

    def revision(self, device, action, *tail, expected=0, name=None, program=None):
        executable = program if program is not None else self.program('revision')
        label = name if name is not None else device.name + '-' + action
        return self.call([executable, action, device / 'catalog.sqlite', *tail], label, expected)

    def outbox(self, device, name=None, program=None):
        return self.revision(device, 'outbox', 100, name=name or device.name + '-outbox', program=program)

    def heads(self, device, kind, key, name=None, program=None):
        return self.revision(device, 'heads', kind, key, name=name or device.name + '-heads', program=program)

    def retained(self, device, revision_id, name, program=None):
        path = self.output / (name + '.json')
        self.revision(device, 'get', revision_id, path, name=name, program=program)
        return path.read_bytes()

    def book(self, device, revision_id, parents, title, key, fmt, source_sha, source_bytes,
             name=None, program=None):
        executable = program if program is not None else self.program('commands')
        title_file = self.output / ('title-' + revision_id + '.txt')
        title_file.write_text(title, encoding='utf-8')
        author_file = self.output / 'author.txt'
        author_file.write_text('', encoding='utf-8')
        sort_file = self.output / ('sort-' + revision_id + '.txt')
        sort_file.write_text(title, encoding='utf-8')
        return self.call([executable, 'book', device / 'catalog.sqlite', revision_id,
                          parents if parents else '-', '0', key, fmt, source_sha, source_bytes, '0',
                          title_file, author_file, sort_file],
                         name or (device.name + '-book-' + revision_id), 0)

    def cursor_below(self, namespace, path):
        prefix = '/' + namespace + '/' + COLLECTION + '/revisions/'
        folder = prefix + path[len(prefix):].split('/', 1)[0] + '/'
        with self.remote.lock:
            candidates = [item for item in self.remote.entries
                          if item.startswith(folder) and item < path]
        if not candidates:
            return '-'
        return leaf_name(max(candidates))

    def published(self, name, actual):
        assert CHECKS[len(self.checks)] == name, (name, len(self.checks), CHECKS[len(self.checks)])
        self.checks.append({'name': name, 'expected': EXPECTED[name], 'actual': actual})
        print('PASS ' + name, flush=True)


def compare(harness, device, tag, source):
    table = []
    for revision_id in sorted(source):
        body = harness.retained(device, revision_id, tag + '-get-' + revision_id)
        assert body == source[revision_id], (tag, revision_id, 'bytes')
        table.append({'id': revision_id, 'sha256': digest(body), 'bytes': len(body)})
    return table


def scenario(harness):
    remote = harness.remote
    key = harness.certificates / 'server.key'
    certificate = harness.certificates / 'server.crt'
    subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
                    '-keyout', str(key), '-out', str(certificate), '-subj', '/CN=localhost',
                    '-addext', 'subjectAltName=DNS:localhost,IP:127.0.0.1'], check=True, capture_output=True)
    trust_fixture_certificates((certificate,), 'reader-final-s07-')
    for namespace in NAMESPACES:
        remote.namespace(namespace)
    serve(remote, certificate, key)

    sender = harness.device('sender')
    first = harness.device('receiver-one')
    second = harness.device('receiver-two')
    legacy_one = harness.device('legacy-one')
    legacy_two = harness.device('legacy-two')
    legacy_receiver = harness.device('legacy-receiver')
    peers = ((sender, 'sender'), (first, 'receiver-one'), (second, 'receiver-two'))

    packet = harness.core / 'actual/packet'
    original = (harness.core / 'actual/original.pdf').read_bytes()
    assert len(original) == PDF_BYTES and digest(original) == PDF_SHA
    harness.call([harness.program('bootstrap'), 'seed', sender, packet], 'bootstrap-seed')
    expected = sender / 'expected'
    capture = {path.name: path.read_bytes() for path in expected.glob('*.json')}
    assert len(capture) == len(list(packet.glob('*.json'))) + 2, len(capture)
    source = {}
    for name, body in capture.items():
        parsed = json.loads(body.decode('utf-8'))
        assert parsed['id'] + '.json' == name, name
        source[parsed['id']] = body
    assert len(source) == 11, sorted(source)
    (sender / 'originals' / (PDF_SHA + '.pdf')).write_bytes(original)
    harness.published('real_capture_graph_and_original_identity_bootstrap', {
        'capture_wires': len(list(packet.glob('*.json'))),
        'exported_wires': len(source),
        'revision_ids': sorted(source),
        'typed_metadata_wires': ['00000000000000000000000000001000', '00000000000000000000000000001001'],
        'pdf_bytes': len(original),
        'pdf_sha256': digest(original),
        'book_identity_bytes': 8845,
    })

    # 2. A real connection reset before the remote commit, then an explicit retry.
    pdf_object = object_path('dav', PDF_SHA, 'pdf')
    remote.fault('PUT', pdf_object, 'reset_before_commit')
    failed = harness.sync(sender, 'sender-push-reset', expected=3)
    assert failed['dav_code'] == 5 and failed['http_status'] == 404, failed
    assert failed['pushed'] == 0 and failed['pulled'] == 0, failed
    absent_after_reset = pdf_object not in remote.entries
    assert absent_after_reset
    retained_outbox = harness.outbox(sender, name='sender-outbox-after-reset')
    assert sorted(item['id'] for item in retained_outbox['outbox']) == sorted(source), retained_outbox
    retried = harness.sync(sender, 'sender-push-retry')
    # The same step also re-reads the shard it just published: every received
    # leaf is an exact no-op, so pulled equals the leaf count and pushed is the
    # whole retained outbox.
    assert retried['pushed'] == len(source), retried
    assert retried['pulled'] == len(source), retried
    assert harness.outbox(sender, name='sender-outbox-after-retry')['outbox'] == []
    counts = inventory(remote, 'dav')
    for revision_id, body in source.items():
        path = revision_path('dav', revision_id, body)
        assert remote.entries.get(path) == body, (revision_id, 'remote bytes')
        assert counts.get(revision_id) == 1, (revision_id, counts.get(revision_id))
    assert remote.entries.get(pdf_object) == original
    harness.published('network_reset_before_commit_then_explicit_retry_publishes_exactly_once', {
        'failed_status': failed['status'], 'failed_dav_code': failed['dav_code'],
        'failed_http_status': failed['http_status'],
        'reset_put_outcomes': statuses(remote, 'PUT', pdf_object),
        'remote_object_absent_after_reset': absent_after_reset,
        'outbox_rows_after_reset': len(retained_outbox['outbox']),
        'retry_pushed': retried['pushed'],
        'outbox_rows_after_retry': 0,
        'remote_revision_objects': len(counts),
        'remote_original_bytes': len(remote.entries[pdf_object]),
        'remote_original_sha256': digest(remote.entries[pdf_object]),
    })

    # 3. Response lost, newer head received, then the old request retried.
    harness.sync(first, 'receiver-one-pull-all')
    compare(harness, first, 'receiver-one-initial', source)
    head = harness.heads(sender, 'book', BOOK, name='sender-book-head')
    assert head['state']['heads'] == 1, head
    base_head = head['heads'][0]['id']
    created = harness.book(sender, OLD_ID, base_head, 's07 old request', BOOK, 'pdf', PDF_SHA, PDF_BYTES,
                           name='sender-create-old')
    assert created['created'] == 1 and created['applied'] == 1, created
    old_wire = harness.retained(sender, OLD_ID, 'sender-old-wire')
    assert json.loads(old_wire.decode('utf-8'))['parents'] == [base_head]
    pending = harness.outbox(sender, name='sender-outbox-before-lost')
    assert [item['id'] for item in pending['outbox']] == [OLD_ID], pending
    old_path = revision_path('dav', OLD_ID, old_wire)
    remote.fault('PUT', old_path, 'commit_then_drop')
    remote.fault('GET', old_path, 'drop')
    lost = harness.sync(sender, 'sender-push-response-lost', expected=3)
    assert lost['dav_code'] == 3 and lost['http_status'] == 0, lost
    assert lost['pushed'] == 0 and lost['pulled'] == 0, lost
    committed_after_loss = remote.entries.get(old_path) == old_wire
    assert committed_after_loss
    assert [item['id'] for item in harness.outbox(sender, name='sender-outbox-after-lost')['outbox']] == [OLD_ID]
    harness.sync(first, 'receiver-one-pull-committed-old')
    head = harness.heads(first, 'book', BOOK, name='receiver-one-head-old')
    assert head['heads'][0]['id'] == OLD_ID, head
    newer = harness.book(first, NEWER_ID, OLD_ID, 's07 newer head', BOOK, 'pdf', PDF_SHA, PDF_BYTES,
                         name='receiver-one-create-newer')
    assert newer['created'] == 1, newer
    newer_wire = harness.retained(first, NEWER_ID, 'receiver-one-newer-wire')
    assert json.loads(newer_wire.decode('utf-8'))['parents'] == [OLD_ID]
    assert harness.sync(first, 'receiver-one-push-newer')['pushed'] == 1
    assert remote.entries.get(revision_path('dav', NEWER_ID, newer_wire)) == newer_wire
    harness.sync(sender, 'sender-pull-newer-head')
    heads_before = harness.heads(sender, 'book', BOOK, name='sender-heads-before-retry')
    assert heads_before['state']['heads'] == 1 and heads_before['heads'][0]['id'] == NEWER_ID, heads_before
    assert heads_before['state']['revisions'] == 3, heads_before
    pending_before = harness.outbox(sender, name='sender-outbox-before-retry')
    assert [item['id'] for item in pending_before['outbox']] == [OLD_ID], pending_before
    retry = harness.sync(sender, 'sender-retry-old-request')
    assert retry['pushed'] == 1, retry
    heads_after = harness.heads(sender, 'book', BOOK, name='sender-heads-after-retry')
    assert heads_after == heads_before, (heads_before, heads_after)
    assert harness.outbox(sender, name='sender-outbox-after-retry-old')['outbox'] == []
    assert harness.retained(sender, OLD_ID, 'sender-old-wire-after-retry') == old_wire
    assert remote.entries.get(old_path) == old_wire
    counts = inventory(remote, 'dav')
    assert counts.get(OLD_ID) == 1 and counts.get(NEWER_ID) == 1, counts
    harness.published('response_lost_newer_head_then_old_request_retry_keeps_head_and_outbox', {
        'lost_status': lost['status'], 'lost_dav_code': lost['dav_code'],
        'lost_http_status': lost['http_status'],
        'lost_put_outcomes': statuses(remote, 'PUT', old_path),
        'lost_get_outcomes': statuses(remote, 'GET', old_path),
        'remote_committed_after_lost_response': committed_after_loss,
        'outbox_rows_after_loss': 1,
        'newer_head_revision_id': NEWER_ID,
        'heads_before_retry': heads_before['heads'], 'heads_after_retry': heads_after['heads'],
        'history_before_retry': heads_before['state']['revisions'],
        'history_after_retry': heads_after['state']['revisions'],
        'outbox_rows_after_retry': 0,
        'retry_put_outcomes': statuses(remote, 'PUT', old_path),
        'remote_object_count_old': counts.get(OLD_ID),
        'remote_object_count_newer': counts.get(NEWER_ID),
        'old_wire_unchanged': harness.retained(sender, OLD_ID, 'sender-old-wire-proof') == old_wire,
    })

    # 4. Out-of-order parent graph: the child is served alone, then the parent.
    harness.sync(second, 'receiver-two-pull-all')
    compare(harness, second, 'receiver-two-initial', {**source, OLD_ID: old_wire, NEWER_ID: newer_wire})
    head = harness.heads(first, 'book', BOOK, name='receiver-one-head-before-pair')
    assert head['heads'][0]['id'] == NEWER_ID, head
    made_parent = harness.book(first, PARENT_ID, NEWER_ID, 's07 ordered parent', BOOK, 'pdf', PDF_SHA,
                               PDF_BYTES, name='receiver-one-create-parent')
    assert made_parent['created'] == 1, made_parent
    parent_wire = harness.retained(first, PARENT_ID, 'receiver-one-parent-wire')
    assert json.loads(parent_wire.decode('utf-8'))['parents'] == [NEWER_ID]
    made_child = harness.book(first, CHILD_ID, PARENT_ID, 's07 ordered child', BOOK, 'pdf', PDF_SHA,
                              PDF_BYTES, name='receiver-one-create-child')
    assert made_child['created'] == 1, made_child
    child_wire = harness.retained(first, CHILD_ID, 'receiver-one-child-wire')
    assert json.loads(child_wire.decode('utf-8'))['parents'] == [PARENT_ID]
    assert harness.sync(first, 'receiver-one-push-pair')['pushed'] == 2
    child_path = revision_path('dav', CHILD_ID, child_wire)
    parent_path = revision_path('dav', PARENT_ID, parent_wire)
    assert remote.entries.get(child_path) == child_wire and remote.entries.get(parent_path) == parent_wire
    assert child_path < parent_path, (child_path, parent_path)
    cursor = harness.cursor_below('dav', child_path)
    delivered = harness.sync(second, 'receiver-two-pull-child', after=cursor, limit=1)
    assert delivered['pulled'] == 1 and delivered['after'] == leaf_name(child_path), delivered
    assert statuses(remote, 'GET', child_path)[-1] == 200
    assert harness.retained(second, CHILD_ID, 'receiver-two-child-wire') == child_wire
    incomplete = harness.heads(second, 'book', BOOK, name='receiver-two-heads-child-only')
    assert incomplete['state']['missing_parents'] == 1, incomplete
    assert incomplete['state']['heads'] == 2 and incomplete['state']['projection_safe'] == 0, incomplete
    child_head = [item for item in incomplete['heads'] if item['id'] == CHILD_ID]
    assert len(child_head) == 1 and child_head[0]['complete'] == 0, incomplete
    completed = harness.sync(second, 'receiver-two-pull-parent', after=leaf_name(child_path), limit=1)
    assert completed['pulled'] == 1 and completed['after'] == leaf_name(parent_path), completed
    assert harness.retained(second, PARENT_ID, 'receiver-two-parent-wire') == parent_wire
    done = harness.heads(second, 'book', BOOK, name='receiver-two-heads-complete')
    assert done['state']['missing_parents'] == 0 and done['state']['heads'] == 1, done
    assert done['heads'][0]['id'] == CHILD_ID and done['heads'][0]['complete'] == 1, done
    assert done['state']['revisions'] == 5, done
    harness.published('out_of_order_parent_graph_child_before_parent_then_complete', {
        'child_revision_id': CHILD_ID, 'parent_revision_id': PARENT_ID,
        'child_leaf_sorts_before_parent': child_path < parent_path,
        'cursor_used': cursor,
        'delivered_first': delivered['after'], 'delivered_pulled': delivered['pulled'],
        'missing_parents_before_parent': incomplete['state']['missing_parents'],
        'heads_before_parent': incomplete['state']['heads'],
        'projection_safe_before_parent': incomplete['state']['projection_safe'],
        'child_head_complete_before_parent': child_head[0]['complete'],
        'heads_after_parent': done['state']['heads'],
        'missing_parents_after_parent': done['state']['missing_parents'],
        'history_after_parent': done['state']['revisions'],
        'child_wire_sha256': digest(child_wire), 'parent_wire_sha256': digest(parent_wire),
    })

    # 5. Duplicate wire delivery to both receivers.
    before_heads = harness.heads(second, 'book', BOOK, name='receiver-two-heads-before-duplicate')
    trace_start = len(remote.requests)
    duplicate = harness.sync(second, 'receiver-two-pull-duplicate', after=cursor, limit=1)
    assert duplicate['pulled'] == 1, duplicate
    assert harness.retained(second, CHILD_ID, 'receiver-two-child-duplicate') == child_wire
    duplicate_heads = harness.heads(second, 'book', BOOK, name='receiver-two-heads-after-duplicate')
    assert duplicate_heads == before_heads
    assert harness.outbox(second, name='receiver-two-outbox-after-duplicate')['outbox'] == []
    window = remote.requests[trace_start:]
    assert window and not [item for item in window if item['method'] == 'PUT'], window
    first_before = harness.heads(first, 'book', BOOK, name='receiver-one-heads-before-duplicate')
    harness.sync(first, 'receiver-one-pull-duplicate')
    assert harness.heads(first, 'book', BOOK, name='receiver-one-heads-after-duplicate') == first_before
    assert harness.retained(first, CHILD_ID, 'receiver-one-child-duplicate') == child_wire
    whole = harness.sync(second, 'receiver-two-pull-whole-shard-again')
    assert harness.heads(second, 'book', BOOK, name='receiver-two-heads-after-second-sweep') == before_heads
    counts = inventory(remote, 'dav')
    assert counts.get(CHILD_ID) == 1, counts
    harness.published('duplicate_wire_receive_is_idempotent_for_both_receivers', {
        'duplicate_pulled': duplicate['pulled'],
        'duplicate_receive_created': 0,
        'heads_before': before_heads['state'], 'heads_after': duplicate_heads['state'],
        'head_ids_before': [item['id'] for item in before_heads['heads']],
        'head_ids_after': [item['id'] for item in duplicate_heads['heads']],
        'history_unchanged': before_heads['state']['revisions'] == duplicate_heads['state']['revisions'],
        'outbox_after_duplicate': 0,
        'window_requests': len(window),
        'window_puts': len([item for item in window if item['method'] == 'PUT']),
        'window_gets': len([item for item in window if item['method'] == 'GET']),
        'remote_object_count_child': counts.get(CHILD_ID),
        'second_receiver_repeat_sweep_pulled': whole['pulled'],
        'duplicate_wire_sha256': digest(child_wire),
    })

    # 6. Unknown anchor version: over the real network and on direct receive.
    capture_id = '00000000000000000000000000000064'
    captured = source[capture_id]
    assert b'"anchor_version":3' in captured
    unknown_body = captured.replace(b'"anchor_version":3', b'"anchor_version":4')
    assert unknown_body.count(b'"anchor_version":4') == 1
    assert len(unknown_body) == len(captured) and unknown_body != captured
    unknown_path = remote.publish('unknown', unknown_body)
    progress_before = harness.heads(second, 'progress', BOOK, name='receiver-two-progress-before-unknown')
    refused = harness.sync(second, 'receiver-two-pull-unknown', namespace='unknown', expected=4)
    assert refused['revision_code'] == 4, refused
    assert statuses(remote, 'GET', unknown_path)[-1] == 200
    # The receiver already holds the genuine v3 wire of this ID: a refused
    # unknown version must leave those exact bytes, never overwrite them.
    assert harness.retained(second, capture_id, 'receiver-two-retained-unknown') == captured
    assert harness.heads(second, 'progress', BOOK, name='receiver-two-progress-after-unknown') == progress_before
    assert harness.outbox(second, name='receiver-two-outbox-after-unknown')['outbox'] == []
    unknown_file = harness.output / 'unknown-anchor-wire.json'
    unknown_file.write_bytes(unknown_body)
    direct = harness.revision(second, 'receive', unknown_file, digest(unknown_body), expected=4,
                              name='receiver-two-receive-unknown')
    assert direct['created'] == 0, direct
    raw3_path = remote.publish('raw3', captured)
    legacy_before = harness.heads(legacy_one, 'annotation', BOOK + ':' + BOOKMARK,
                                  name='legacy-one-heads-before-raw3', program=harness.old_revision)
    legacy_refused = harness.sync(legacy_one, 'legacy-one-pull-raw3', namespace='raw3', expected=4,
                                  program=harness.old_sync)
    assert legacy_refused['revision_code'] == 4, legacy_refused
    assert statuses(remote, 'GET', raw3_path)[-1] == 200
    harness.revision(legacy_one, 'get', capture_id, harness.output / 'absent-legacy.json', expected=12,
                     name='legacy-one-get-raw3', program=harness.old_revision)
    assert harness.heads(legacy_one, 'annotation', BOOK + ':' + BOOKMARK,
                         name='legacy-one-heads-after-raw3', program=harness.old_revision) == legacy_before
    assert harness.outbox(legacy_one, name='legacy-one-outbox-after-raw3',
                          program=harness.old_revision)['outbox'] == []
    capture_file = harness.output / 'raw3-wire.json'
    capture_file.write_bytes(captured)
    legacy_direct = harness.revision(legacy_one, 'receive', capture_file, digest(captured), expected=4,
                                     name='legacy-one-receive-raw3', program=harness.old_revision)
    assert legacy_direct['created'] == 0, legacy_direct
    legacy_unknown = harness.revision(legacy_one, 'receive', unknown_file, digest(unknown_body), expected=4,
                                      name='legacy-one-receive-unknown', program=harness.old_revision)
    assert legacy_unknown['created'] == 0, legacy_unknown
    harness.published('unknown_anchor_version_refused_over_network_and_direct_receive', {
        'source_capture_wire_sha256': digest(captured),
        'unknown_anchor_wire_sha256': digest(unknown_body),
        'unknown_anchor_mutation': 'payload.location.anchor_version 3 -> 4, no other byte',
        'unknown_anchor_bytes': len(unknown_body),
        'raw_network_status': refused['status'], 'raw_network_revision_code': refused['revision_code'],
        'raw_network_get_status': statuses(remote, 'GET', unknown_path)[-1],
        'raw_direct_receive_status': direct['status'], 'raw_direct_receive_created': direct['created'],
        'raw_history_unchanged': progress_before['state'],
        'max2_network_status': legacy_refused['status'],
        'max2_network_revision_code': legacy_refused['revision_code'],
        'max2_direct_raw3_status': legacy_direct['status'],
        'max2_direct_unknown_status': legacy_unknown['status'],
        'max2_history_unchanged': legacy_before['state'],
    })

    # 7. Old MAX2 consumers coexist with the raw peers on the same origin.
    txt_sha = digest(TXT)
    for device in (legacy_one, legacy_two):
        harness.book(device, LEGACY_BOOK_ID, '', 'compatibility', 'txt:' + txt_sha, 'txt', txt_sha,
                     str(len(TXT)), name=device.name + '-legacy-book', program=harness.old_command)
        (device / 'originals' / (txt_sha + '.txt')).write_bytes(TXT)
    v1 = (harness.core / 'candidate-legacy/v1-wire.json').read_bytes()
    v2 = (harness.core / 'candidate-legacy/v2-wire.json').read_bytes()
    assert json.loads(v1.decode('utf-8'))['payload']['location']['anchor_version'] == 1
    assert json.loads(v2.decode('utf-8'))['payload']['location']['anchor_version'] == 2
    v1_file = harness.output / 'legacy1-wire.json'
    v1_file.write_bytes(v1)
    v2_file = harness.output / 'legacy2-wire.json'
    v2_file.write_bytes(v2)
    harness.revision(legacy_one, 'local', v1_file, name='legacy-one-local-v1', program=harness.old_revision)
    harness.revision(legacy_two, 'local', v2_file, name='legacy-two-local-v2', program=harness.old_revision)
    pushed_one = harness.sync(legacy_one, 'legacy-one-push-v1', namespace='legacy1', program=harness.old_sync)
    pushed_two = harness.sync(legacy_two, 'legacy-two-push-v2', namespace='legacy2', program=harness.old_sync)
    assert pushed_one['pushed'] == 2 and pushed_two['pushed'] == 2, (pushed_one, pushed_two)
    pulled_one = harness.sync(legacy_receiver, 'legacy-receiver-pull-v1', namespace='legacy1',
                              program=harness.old_sync)
    assert pulled_one['pulled'] == 2, pulled_one
    again = harness.sync(legacy_receiver, 'legacy-receiver-pull-v1-again', namespace='legacy1',
                         program=harness.old_sync)
    assert again['pending_metadata'] == 0 and again['originals_verified'] >= 1, again
    received = harness.retained(legacy_receiver, json.loads(v1.decode('utf-8'))['id'],
                                'legacy-received-v1', program=harness.old_revision)
    assert received == v1
    assert (legacy_receiver / 'cache' / (txt_sha + '.txt')).read_bytes() == TXT
    legacy_heads = harness.heads(legacy_receiver, 'annotation', 'txt:' + txt_sha + ':' + BOOKMARK,
                                 name='legacy-receiver-heads', program=harness.old_revision)
    assert legacy_heads['state']['revisions'] == 1 and legacy_heads['state']['heads'] == 1, legacy_heads
    assert legacy_heads['heads'][0]['complete'] == 1, legacy_heads
    assert inventory(remote, 'legacy1') == {json.loads(v1.decode('utf-8'))['id']: 1, LEGACY_BOOK_ID: 1}
    assert inventory(remote, 'legacy2') == {json.loads(v2.decode('utf-8'))['id']: 1, LEGACY_BOOK_ID: 1}
    assert remote.entries[object_path('legacy1', txt_sha, 'txt')] == TXT
    assert harness.outbox(legacy_receiver, name='legacy-receiver-outbox',
                          program=harness.old_revision)['outbox'] == []
    harness.published('legacy_max2_consumers_coexist_without_corruption', {
        'legacy1_wire_sha256': digest(v1), 'legacy2_wire_sha256': digest(v2),
        'legacy1_anchor_version': 1, 'legacy2_anchor_version': 2,
        'legacy1_pushed': pushed_one['pushed'], 'legacy2_pushed': pushed_two['pushed'],
        'legacy_receiver_pulled': pulled_one['pulled'],
        'legacy_receiver_pending_metadata': again['pending_metadata'],
        'legacy_receiver_originals_verified': again['originals_verified'],
        'received_wire_exact': received == v1,
        'received_original_exact': (legacy_receiver / 'cache' / (txt_sha + '.txt')).read_bytes() == TXT,
        'legacy_heads': legacy_heads['state'],
        'remote_legacy1_objects': inventory(remote, 'legacy1'),
        'remote_legacy2_objects': inventory(remote, 'legacy2'),
        'remote_raw3_objects': len(inventory(remote, 'dav')),
        'txt_sha256': txt_sha,
    })

    # 8. Exact bytes, IDs, parents and original hash after a cross-process reopen.
    for device, tag in peers:
        harness.sync(device, tag + '-final-pull')
    everything = {**source, OLD_ID: old_wire, NEWER_ID: newer_wire, PARENT_ID: parent_wire, CHILD_ID: child_wire}
    table = []
    for revision_id in sorted(everything):
        body = everything[revision_id]
        parsed = json.loads(body.decode('utf-8'))
        row = {'id': revision_id, 'kind': parsed['entity_kind'], 'operation': parsed['operation'],
               'sha256': digest(body), 'bytes': len(body), 'parents': parsed['parents'], 'peers': {}}
        for device, tag in peers:
            held = harness.retained(device, revision_id, tag + '-final-' + revision_id)
            assert held == body, (revision_id, tag)
            row['peers'][tag] = {'sha256': digest(held), 'bytes': len(held), 'equal': True}
        table.append(row)
    assert json.loads(newer_wire)['parents'] == [OLD_ID]
    assert json.loads(parent_wire)['parents'] == [NEWER_ID]
    assert json.loads(child_wire)['parents'] == [PARENT_ID]
    assert json.loads(old_wire)['parents'] == [base_head]
    reopens = {}
    for device, tag in peers:
        harness.call([harness.program('bootstrap'), 'check', device, expected], tag + '-cross-process-reopen')
        assert harness.outbox(device, name=tag + '-outbox-final')['outbox'] == []
        cached = (device / 'cache' / (PDF_SHA + '.pdf')).read_bytes()
        assert cached == original
        assert not list(device.rglob('.reader-sync-*.tmp'))
        reopens[tag] = {'cached_original_sha256': digest(cached), 'cached_original_bytes': len(cached),
                        'outbox': 0, 'transfer_temporaries': 0}
    harness.published('exact_wire_ids_parents_and_original_hash_after_cross_process_reopen', {
        'wires': table, 'wire_count': len(table),
        'chain': [base_head, OLD_ID, NEWER_ID, PARENT_ID, CHILD_ID],
        'reopens': reopens,
        'original_sha256': PDF_SHA, 'original_bytes': PDF_BYTES,
    })

    assert [item['name'] for item in harness.checks] == CHECKS, [item['name'] for item in harness.checks]
    assert all(item['authenticated'] for item in remote.requests), 'unauthenticated request'
    assert len(remote.faulted) == 3, remote.faulted
    for path in harness.output.rglob('*'):
        if path.is_file() and path.suffix != '.key':
            assert harness.secret.encode('utf-8') not in path.read_bytes(), path
    return {
        'accepted': True,
        'scope': 'three-peer temporary HTTPS regression on the frozen public raw7 module',
        'source_sha': os.environ['GITHUB_SHA'],
        'run_id': os.environ['GITHUB_RUN_ID'],
        'attempt': os.environ['GITHUB_RUN_ATTEMPT'],
        'platform': sys.platform,
        'checks': harness.checks,
        'count': len(harness.checks),
        'wires': {revision_id: digest(body) for revision_id, body in sorted(everything.items())},
        'original': {'sha256': PDF_SHA, 'bytes': PDF_BYTES},
        'remote': {
            'revision_objects': {namespace: inventory(remote, namespace) for namespace in NAMESPACES},
            'object_keys': sorted(path for path in remote.entries if '/objects/' in path),
            'faults': remote.faulted,
            'fault_plan': remote.planned,
            'requests': len(remote.requests),
            'all_authenticated': True,
        },
        'gaps': GAPS,
        'operations': harness.operations,
        'adopted': False,
        'actual_hosts': False,
        'physical_device': False,
        'complete_product': False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--programs', type=Path, required=True)
    parser.add_argument('--core', type=Path, required=True)
    parser.add_argument('--old-revision', type=Path, required=True)
    parser.add_argument('--old-sync', type=Path, required=True)
    parser.add_argument('--old-command', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    arguments = parser.parse_args()
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only'
    harness = Harness(arguments)
    try:
        result = scenario(harness)
    finally:
        if harness.remote.server is not None:
            harness.remote.server.shutdown()
            harness.remote.server.server_close()
    (harness.output / 'result.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    summary = {key: value for key, value in result.items()
               if key not in ('operations', 'remote')}
    summary['remote'] = {key: value for key, value in result['remote'].items() if key != 'requests'}
    print(json.dumps(summary), flush=True)


if __name__ == '__main__':
    main()
