# SPDX-License-Identifier: MIT
"""Actions-only real-host two-peer F05 wire, cancel, kill/restart and conflict check.

Two independent profiles of the actual GTK host (exreader-linux) are driven only
through native controls (import chooser, Book details, Account and Sync). Both
connect, in turn, to one controlled native-HTTPS WebDAV fixture. Nothing is
planted: the receiving profile obtains the other peer's history only from
GET responses served by the fixture, and local product databases are opened
read-only for observation. The fixture injects a gated request, a partial PUT
body reset and a committed-but-unanswered PUT; the host process is SIGKILLed
at the last boundary and restarted from the same profile.

Provenance: the harness helpers (TLS fixture, Secret Service, account driving)
are adapted from tests/linux_host/check_account_ui.py and
tests/linux_host/check_metadata_ui.py, which are not modified.
"""
import argparse
import base64
import configparser
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import socket
import sqlite3
import ssl
import struct
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
from check_linux_host import Session, command


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--payload', type=Path, required=True)
    parser.add_argument('--revision-consumer', type=Path, required=True)
    parser.add_argument('--build-json', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    folder = args.output.resolve()
    folder.mkdir(parents=True)
    checks, observations, devices = [], {}, []
    lock = threading.Lock()
    requests, entries, directories = [], {}, {'/dav/'}
    faults = []
    binary = (args.payload / 'bin/exreader-linux').resolve()
    report = {'accepted': False, 'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
              'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'runner_os': os.environ.get('RUNNER_OS'),
              'runner_image': os.environ.get('ImageVersion'), 'program_sha256': sha(binary.read_bytes()),
              'build_json_sha256': sha(args.build_json.read_bytes()),
              'revision_consumer_sha256': sha(args.revision_consumer.read_bytes()),
              'host': 'actual GTK exreader-linux, two independent profiles', 'checks': checks, 'count': 0,
              'scope': 'two-peer host wire conflict, cancel, partial body, kill and restart; Linux GTK only',
              'database_planting': False, 'six_platform_claim': False, 'complete_product': False}

    private = Path(tempfile.mkdtemp(prefix='f05-host-', dir=os.environ.get('RUNNER_TEMP')))
    secret_home, runtime = private / 'home', private / 'run'
    secret_home.mkdir(mode=0o700)
    runtime.mkdir(mode=0o700)
    original_env = dict(os.environ)
    credential_env = {k: v for k, v in os.environ.items() if not k.startswith(('DBUS_', 'GNOME_KEYRING', 'XDG_'))}
    credential_env.update(HOME=str(secret_home), XDG_RUNTIME_DIR=str(runtime), XDG_DATA_HOME=str(secret_home / '.local/share'),
                          XDG_CONFIG_HOME=str(secret_home / '.config'), XDG_CACHE_HOME=str(secret_home / '.cache'),
                          NO_AT_BRIDGE='1')
    bus = subprocess.run(['dbus-daemon', '--session', '--fork', '--print-address=1', '--print-pid=1',
                          '--address=unix:path=' + str(runtime / 'bus')], capture_output=True, text=True,
                         env=credential_env, check=True, timeout=30)
    address, bus_pid = bus.stdout.splitlines()[:2]
    credential_env['DBUS_SESSION_BUS_ADDRESS'] = address
    daemon = subprocess.run(['gnome-keyring-daemon', '--daemonize', '--unlock', '--components=secrets'],
                            input=secrets.token_hex(24), capture_output=True, text=True, env=credential_env,
                            check=True, timeout=60)
    for line in daemon.stdout.splitlines():
        if '=' in line:
            key_name, value = line.split('=', 1)
            credential_env[key_name] = value
    keyring_pid = subprocess.run(['pgrep', '-u', str(os.getuid()), '-n', 'gnome-keyring-d'],
                                 capture_output=True, text=True, check=True, timeout=5).stdout.strip()

    def dbus(path, method, *values):
        done = subprocess.run(['gdbus', 'call', '--session', '--dest', 'org.freedesktop.secrets', '--object-path', path,
                               '--method', method, *values], env=credential_env, capture_output=True, text=True, timeout=30)
        assert done.returncode == 0, 'temporary Secret Service operation failed'
        return done.stdout

    deadline = time.monotonic() + 30
    while True:
        probe = subprocess.run(['gdbus', 'call', '--session', '--dest', 'org.freedesktop.DBus', '--object-path',
                                '/org/freedesktop/DBus', '--method', 'org.freedesktop.DBus.NameHasOwner',
                                'org.freedesktop.secrets'], env=credential_env, capture_output=True, text=True, timeout=5)
        if 'true' in probe.stdout:
            break
        assert time.monotonic() < deadline, 'temporary Secret Service did not start'
        time.sleep(.1)
    alias = dbus('/org/freedesktop/secrets', 'org.freedesktop.Secret.Service.ReadAlias', 'default')
    if 'collection/' not in alias:
        dbus('/org/freedesktop/secrets', 'org.freedesktop.Secret.Service.SetAlias', 'default',
             "objectpath '/org/freedesktop/secrets/collection/login'")
    os.environ.update(credential_env)

    certs = folder / 'certificates'
    certs.mkdir()
    key, certificate = certs / 'server.key', certs / 'server.crt'
    subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1', '-keyout', str(key),
                    '-out', str(certificate), '-subj', '/CN=localhost', '-addext', 'subjectAltName=IP:127.0.0.1'],
                   check=True, capture_output=True)
    subprocess.run(['sudo', 'cp', str(certificate), '/usr/local/share/ca-certificates/exreader-f05-host.crt'],
                   check=True, capture_output=True)
    subprocess.run(['sudo', 'update-ca-certificates'], check=True, capture_output=True)

    class Peer:
        def __init__(self, name):
            self.name = name
            self.user = name + secrets.token_hex(10)
            self.password = 'p' + secrets.token_hex(24)
            self.authorization = 'Basic ' + base64.b64encode((self.user + ':' + self.password).encode()).decode()
            place = folder / name
            place.mkdir()
            self.host = Session(binary, (args.payload / 'Reader.otf').resolve(), place)
            devices.append(self.host)
            self.account_id = None

    peers = {n: Peer(n) for n in ('peerA', 'peerB')}
    by_authorization = {p.authorization: p for p in peers.values()}

    class Fault:
        def __init__(self, kind, peer, contains):
            self.kind, self.peer, self.contains = kind, peer, contains
            self.hit, self.release, self.consumed = threading.Event(), threading.Event(), False
            self.seen = None

    def arm(kind, peer, contains):
        fault = Fault(kind, peer, contains)
        with lock:
            faults.append(fault)
        return fault

    def take(peer, method, path):
        with lock:
            for fault in faults:
                if (not fault.consumed and fault.peer is peer and path.find(fault.contains) >= 0 and
                        ((fault.kind == 'gate' and method == 'PROPFIND') or
                         (fault.kind in ('partial', 'commit_withhold') and method == 'PUT'))):
                    fault.consumed = True
                    return fault
        return None

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

        def reset(self):
            self.close_connection = True
            try:
                self.request.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack('ii', 1, 0))
                self.request.close()
            except OSError:
                pass

        def peer(self):
            return by_authorization.get(self.headers.get('Authorization'))

        def note(self, peer, status, size=0, fault=None):
            with lock:
                requests.append({'n': len(requests), 'method': self.command, 'path': self.path,
                                 'peer': peer.name if peer else None, 'status': status, 'bytes': size,
                                 'fault': fault, 't': round(time.monotonic(), 3)})

        def do_MKCOL(self):
            peer = self.peer()
            if not peer:
                self.note(None, 401)
                return self.send(401)
            with lock:
                exists = self.path in directories
                directories.add(self.path)
            self.note(peer, 405 if exists else 201)
            self.send(405 if exists else 201)

        def do_PUT(self):
            size = int(self.headers['Content-Length'])
            peer = self.peer()
            fault = take(peer, 'PUT', self.path) if peer else None
            if fault and fault.kind == 'partial':
                self.rfile.read(max(1, size // 2))
                self.note(peer, 'partial-reset', size // 2, 'partial')
                fault.hit.set()
                fault.release.wait(60)
                return self.reset()
            body = self.rfile.read(size)
            if not peer:
                self.note(None, 401, size)
                return self.send(401)
            assert self.headers.get('If-None-Match') == '*'
            with lock:
                exists = self.path in entries
                if not exists:
                    entries[self.path] = body
            if fault and fault.kind == 'commit_withhold':
                self.note(peer, 'committed-unanswered', size, 'commit_withhold')
                fault.hit.set()
                fault.release.wait(60)
                return self.reset()
            self.note(peer, 412 if exists else 201, size)
            self.send(412 if exists else 201)

        def do_GET(self):
            peer = self.peer()
            if not peer:
                self.note(None, 401)
                return self.send(401)
            with lock:
                body = entries.get(self.path)
            self.note(peer, 404 if body is None else 200, len(body or b''))
            self.send(404 if body is None else 200, body or b'')

        def do_PROPFIND(self):
            self.rfile.read(int(self.headers.get('Content-Length', 0)))
            peer = self.peer()
            if not peer:
                self.note(None, 401)
                return self.send(401)
            fault = take(peer, 'PROPFIND', self.path)
            if fault:
                self.note(peer, 'gated', 0, 'gate')
                fault.hit.set()
                fault.release.wait(60)
            with lock:
                children = [(p, True, 0) for p in directories if p.startswith(self.path) and
                            (p == self.path or '/' not in p[len(self.path):].rstrip('/'))]
                children += [(p, False, len(b)) for p, b in entries.items()
                             if p.startswith(self.path) and '/' not in p[len(self.path):]]
                exists = self.path in directories
            if not exists:
                self.note(peer, 404)
                return self.send(404)
            rows = ['<d:response><d:href>' + p + '</d:href><d:propstat><d:prop><d:resourcetype>' +
                    ('<d:collection/>' if is_dir else '') + '</d:resourcetype><d:getcontentlength>' + str(size) +
                    '</d:getcontentlength></d:prop><d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>'
                    for p, is_dir, size in children]
            self.note(peer, 207)
            self.send(207, ('<d:multistatus xmlns:d="DAV:">' + ''.join(rows) + '</d:multistatus>').encode())

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.daemon_threads = True
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certificate, key)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    root = 'https://127.0.0.1:' + str(server.server_port) + '/dav/'

    # ----- observation helpers (product databases are only read) -----
    def db_path(peer):
        return peer.host.folder / 'profile/library.sqlite.product.sqlite'

    def sql(peer, query, values=()):
        with sqlite3.connect('file:' + str(db_path(peer)) + '?mode=ro', uri=True) as db:
            return db.execute(query, values).fetchall()

    def protocol(peer, action, *values):
        done = subprocess.run([str(args.revision_consumer.resolve()), action, str(db_path(peer)), *map(str, values)],
                              capture_output=True, text=True, timeout=45)
        assert done.returncode == 0, 'installed revision consumer failed'
        value = json.loads(done.stdout)
        assert value['status'] == 0, value
        return value

    def ids(heads):
        return sorted(x['id'] if isinstance(x, dict) else x for x in heads)

    def history(peer, book):
        return {r: json.loads(b) for r, b in sql(
            peer, "SELECT revision_id,body_json FROM reader_revisions WHERE entity_kind='book' AND entity_key=?", (book,))}

    def wire_revisions(book):
        found = {}
        with lock:
            snapshot = dict(entries)
        for path, body in snapshot.items():
            if '/revisions/' in path:
                value = json.loads(body)
                if value.get('kind') == 'book' and value.get('key') == book or \
                        (value.get('entity_kind') == 'book' and value.get('entity_key') == book):
                    found[value['id']] = (path, sha(body))
        return found

    def uploads(peer, since=0):
        with lock:
            return [r for r in requests if r['n'] >= since and r['peer'] == peer.name and r['method'] == 'PUT'
                    and r['status'] in (201, 412, 'committed-unanswered') and '/revisions/' in r['path']]

    # ----- real host drivers -----
    def account(peer):
        state = configparser.ConfigParser(interpolation=None)
        state.read(peer.host.observe)
        return dict(state['account']) if state.has_section('account') else {}

    def ready(peer, predicate=lambda state: True, seconds=90):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            assert peer.host.process.poll() is None, 'actual GTK host exited'
            current = account(peer)
            if (current and not int(current['owner_busy']) and not int(current['preparing']) and
                    not peer.host.read().get('busy') and predicate(current)):
                return current
            time.sleep(.1)
        raise TimeoutError('Account controls did not reach the expected state: ' + repr(account(peer)))

    def window(peer, title, present=True):
        end = time.monotonic() + 35
        while time.monotonic() < end:
            assert peer.host.process.poll() is None, 'actual host exited'
            found = subprocess.run(['xdotool', 'search', '--onlyvisible', '--all', '--pid', str(peer.host.process.pid),
                                    '--name', '^' + title + '$'], capture_output=True, text=True, timeout=5)
            if bool(found.stdout.strip()) == present:
                if present:
                    selected = found.stdout.splitlines()[-1]
                    command('xdotool', 'windowactivate', '--sync', selected)
                    return selected
                return None
            time.sleep(.1)
        raise TimeoutError('Native window visibility differs: ' + title)

    def launch(peer):
        peer.host.launch()

    def open_account(peer):
        command('xdotool', 'windowactivate', '--sync', peer.host.window)
        peer.host.key('F2')
        peer.host.wait(lambda s: not s.get('shelf_loading') and not s.get('shelf_restoring'), timeout=60)
        peer.host.key('ctrl+shift+a')
        target = window(peer, 'Account and Sync')
        ready(peer, lambda s: s['visible'] == '1')
        return target

    def field(peer, mnemonic, value):
        window(peer, 'Account and Sync')
        peer.host.key('alt+' + mnemonic, 'ctrl+a')
        peer.host.paste(value)

    def connect_first_time(peer):
        field(peer, 'w', root)
        field(peer, 'u', peer.user)
        field(peer, 'p', peer.password)
        peer.host.key('alt+m', 'alt+a')
        saved = ready(peer, lambda s: s['bound'] == '1' and s['credential_status'] == '0')
        peer.account_id = saved['id']
        assert str(uuid.UUID(peer.account_id)) == peer.account_id and saved['root'] == root
        return saved

    def scan(peer):
        window(peer, 'Account and Sync')
        peer.host.key('alt+s')

    def finish(peer, seconds=180):
        return ready(peer, lambda s: s['session_state'] in ('3', '4', '5'), seconds=seconds)

    def retry(peer):
        window(peer, 'Account and Sync')
        previous = int(account(peer)['attempt'])
        peer.host.key('alt+t')
        return previous

    def retry_done(peer, previous, seconds=180):
        return ready(peer, lambda s: int(s['attempt']) > previous and s['session_state'] in ('3', '4', '5'), seconds=seconds)

    def disconnect(peer):
        window(peer, 'Account and Sync')
        peer.host.key('alt+d')
        return ready(peer, lambda s: s['session_present'] == '0' and s['form_enabled'] == '1')

    def close_account(peer):
        window(peer, 'Account and Sync')
        peer.host.key('alt+F4')
        window(peer, 'Account and Sync', False)
        ready(peer, lambda s: s['visible'] == '0' and s['session_present'] == '0')

    def record(name, **evidence):
        assert name not in checks
        checks.append(name)
        if evidence:
            observations[name] = evidence
        print(json.dumps({'check': name, 'pass': True}), flush=True)

    def edit_title(peer, title):
        command('xdotool', 'windowactivate', '--sync', peer.host.window)
        peer.host.key('F2', 'ctrl+e')
        window(peer, 'Book details')
        peer.host.key('alt+t', 'ctrl+a')
        peer.host.paste(title)
        peer.host.key('Return')
        window(peer, 'Book details', False)
        peer.host.wait(lambda s: s['error'] == 0)

    def title_of(peer, book):
        return sql(peer, 'SELECT title FROM reader_books WHERE book_key=?', (book,))[0][0]

    def outbox(peer):
        return sql(peer, 'SELECT count(*) FROM reader_outbox')[0][0]

    def hard_kill(peer):
        peer.host.process.kill()
        peer.host.process.wait(timeout=15)
        assert peer.host.process.returncode != 0
        peer.host.log.close()

    try:
        a, b = peers['peerA'], peers['peerB']
        body = b'F05 host two-peer book original\n' + (b'Identical bytes on both devices.\n' * 60)
        book = 'txt:' + sha(body)
        source = folder / 'Shared-book.txt'
        source.write_bytes(body)
        report['book_key'] = book
        report['original_sha256'] = sha(body)

        # 1. Peer A: real import, real metadata save, real scan to the wire.
        launch(a)
        a.host.dialog(source)
        a.host.wait(lambda s: s['book'] > 0 and s['books'] == 1 and not s['error'], timeout=60)
        edit_title(a, 'A base title')
        assert outbox(a) >= 1
        open_account(a)
        connect_first_time(a)
        scan(a)
        done = finish(a)
        assert done['session_state'] == '4', done
        base_history = history(a, book)
        wire_base = wire_revisions(book)
        assert base_history and set(base_history) == set(wire_base), (set(base_history), set(wire_base))
        for rid, (path, digest) in wire_base.items():
            assert path.endswith(rid + '-' + digest + '.json')
            assert json.loads(entries[path]) == base_history[rid]
        assert all(r['peer'] == 'peerA' for r in requests if r['method'] == 'PUT')
        assert outbox(a) == 0
        a_head = protocol(a, 'heads', 'book', book)
        assert a_head['state']['heads'] == 1
        record('peerA_real_import_edit_and_scan_put_exact_history_to_https_wire',
               revisions=sorted(base_history), wire=wire_base, heads=a_head['state'])
        disconnect(a)
        close_account(a)
        a.host.close()

        # 2. Peer B: empty independent profile receives that history only from GET responses.
        launch(b)
        assert sql(b, 'SELECT count(*) FROM reader_revisions')[0][0] == 0
        before = len(requests)
        open_account(b)
        connect_first_time(b)
        scan(b)
        done = finish(b)
        assert done['session_state'] == '4' and int(done['pulled']) >= 1, done
        received = history(b, book)
        assert set(received) == set(base_history) and received == base_history
        assert not [r for r in requests[before:] if r['peer'] == 'peerB' and r['method'] == 'PUT']
        assert [r for r in requests[before:] if r['peer'] == 'peerB' and r['method'] == 'GET' and '/revisions/' in r['path']]
        b_head = protocol(b, 'heads', 'book', book)
        assert b_head['state']['heads'] == 1 and ids(b_head['heads']) == ids(a_head['heads'])
        record('peerB_independent_profile_receives_same_revisions_via_get_without_local_planting',
               revisions=sorted(received), heads=b_head['state'])
        disconnect(b)
        close_account(b)

        # 3. Peer B imports the identical original through the real chooser.
        b.host.dialog(source)
        b.host.wait(lambda s: s['book'] > 0 and s['books'] == 1 and not s['error'], timeout=60)
        assert sql(b, 'SELECT count(*) FROM reader_local_books')[0][0] == 1
        assert set(history(b, book)) >= set(base_history)
        record('peerB_imports_identical_original_and_keeps_received_history')
        common = ids(protocol(b, 'heads', 'book', book)['heads'])

        # 4. Concurrent offline edits from the same received head.
        edit_title(b, 'B concurrent title')
        b_new = set(history(b, book)) - set(base_history)
        assert len(b_new) == 1
        b_rev = next(iter(b_new))
        b_parents = history(b, book)[b_rev]['parents']
        assert sorted(b_parents) == sorted(common) and outbox(b) >= 1
        b.host.close()
        launch(a)
        edit_title(a, 'A concurrent title')
        a_new = set(history(a, book)) - set(base_history)
        assert len(a_new) == 1
        a_rev = next(iter(a_new))
        assert sorted(history(a, book)[a_rev]['parents']) == sorted(common) and outbox(a) >= 1
        assert a_rev != b_rev
        a.host.close()
        record('both_peers_make_distinct_offline_children_of_one_received_head',
               common=common, peerA=a_rev, peerB=b_rev)

        # 5. Peer B scan: cancel at a gated real request, then partial body reset, then commit without answer + SIGKILL.
        launch(b)
        open_account(b)
        gate = arm('gate', b, '/dav/')
        scan(b)
        assert gate.hit.wait(40), 'gated request not reached'
        ticks = int(account(b)['ticks'])
        time.sleep(.7)
        assert int(account(b)['ticks']) > ticks and account(b)['cancel_enabled'] == '1'
        window(b, 'Account and Sync')
        b.host.key('alt+c')
        ready(b, lambda s: s['cancel_requested'] == '1', seconds=5)
        gate.release.set()
        cancelled = finish(b)
        assert cancelled['session_state'] == '3' and cancelled['retry_enabled'] == '1', cancelled
        assert b_rev not in {i for i in wire_revisions(book)} and outbox(b) >= 1
        record('peerB_cancel_at_gated_wire_request_leaves_remote_unchanged_and_outbox_pending',
               account={k: cancelled[k] for k in ('session_state', 'attempt', 'pulled', 'pushed') if k in cancelled})

        partial = arm('partial', b, '/revisions/')
        previous = retry(b)
        assert partial.hit.wait(60), 'partial PUT not reached'
        time.sleep(.3)
        partial.release.set()
        failed = retry_done(b, previous)
        assert failed['session_state'] == '5', failed
        assert b_rev not in wire_revisions(book) and outbox(b) >= 1
        record('peerB_partial_put_body_reset_stores_nothing_and_explicit_retry_state_is_visible',
               account={k: failed[k] for k in ('session_state', 'session_status', 'attempt') if k in failed})

        committed = arm('commit_withhold', b, '/revisions/')
        previous = retry(b)
        assert committed.hit.wait(60), 'committed PUT not reached'
        assert b_rev in wire_revisions(book)
        wire_b = wire_revisions(book)[b_rev]
        hard_kill(b)
        committed.release.set()
        assert outbox(b) >= 1
        record('peerB_host_process_sigkill_after_remote_commit_before_acknowledgement',
               revision=b_rev, wire=wire_b, outbox_after_kill=outbox(b))

        # 6. Restart the same profile: no duplicate wire object, local row or stuck outbox.
        before_requests = len(requests)
        local_before = sql(b, "SELECT count(*) FROM reader_revisions WHERE revision_id=?", (b_rev,))[0][0]
        launch(b)
        open_account(b)
        ready(b, lambda s: s['has_password'] == '1' and s['id'] == b.account_id)
        scan(b)
        done = finish(b)
        assert done['session_state'] == '4', done
        assert wire_revisions(book)[b_rev] == wire_b
        assert len([p for p in entries if b_rev in p]) == 1
        assert sql(b, "SELECT count(*) FROM reader_revisions WHERE revision_id=?", (b_rev,))[0][0] == local_before == 1
        assert outbox(b) == 0
        retry_puts = [r for r in requests[before_requests:] if r['peer'] == 'peerB' and r['method'] == 'PUT'
                      and b_rev in r['path']]
        record('peerB_restart_is_idempotent_one_wire_object_one_local_row_and_outbox_acknowledged',
               put_statuses_after_restart=[r['status'] for r in retry_puts], wire=wire_b)
        disconnect(b)
        close_account(b)
        b.host.close()

        # 7. Peer A receives B and pushes its own sibling.
        launch(a)
        open_account(a)
        ready(a, lambda s: s['has_password'] == '1' and s['id'] == a.account_id)
        scan(a)
        done = finish(a)
        assert done['session_state'] == '4', done
        a_state = protocol(a, 'heads', 'book', book)
        assert a_state['state']['heads'] == 2 and not a_state['state']['projection_safe'], a_state
        assert ids(a_state['heads']) == sorted([a_rev, b_rev])
        assert title_of(a, book) == 'A concurrent title'
        assert outbox(a) == 0 and a_rev in wire_revisions(book)
        record('peerA_wire_receive_of_peerB_sibling_yields_two_heads_without_selecting_or_projecting',
               graph=a_state['state'], heads=a_state['heads'], local_title=title_of(a, book))
        disconnect(a)
        close_account(a)
        a.host.close()

        # 8. Peer B pulls A; both peers converge on identical sibling heads and wire history.
        launch(b)
        open_account(b)
        ready(b, lambda s: s['has_password'] == '1' and s['id'] == b.account_id)
        scan(b)
        done = finish(b)
        assert done['session_state'] == '4', done
        b_state = protocol(b, 'heads', 'book', book)
        assert b_state['state']['heads'] == 2 and not b_state['state']['projection_safe'], b_state
        assert ids(b_state['heads']) == ids(a_state['heads'])
        assert title_of(b, book) == 'B concurrent title'
        final_wire = wire_revisions(book)
        a_final, b_final = history(a, book), history(b, book)
        assert set(a_final) == set(b_final) == set(final_wire), (set(a_final), set(b_final), set(final_wire))
        assert a_final == b_final
        for rid, (path, digest) in final_wire.items():
            assert json.loads(entries[path]) == a_final[rid]
        puts = [(r['peer'], r['path']) for r in requests if r['method'] == 'PUT' and r['status'] in (201, 'committed-unanswered')
                and '/revisions/' in r['path']]
        assert len(puts) == len({p for _, p in puts})
        record('both_peers_converge_on_identical_sibling_heads_titles_unselected_and_wire_history',
               heads=b_state['heads'], revisions=sorted(final_wire))
        disconnect(b)
        close_account(b)
        b.host.close()

        # 9. Evidence hygiene.
        (folder / 'requests.json').write_text(json.dumps(requests, indent=2))
        (folder / 'wire.json').write_text(json.dumps({p: sha(v) for p, v in entries.items()}, indent=2))
        key.unlink()
        secrets_found = []
        for peer in peers.values():
            values = [peer.user.encode(), peer.password.encode(), (peer.user + ':' + peer.password).encode(),
                      peer.authorization.encode()]
            forms = [f for value in values for f in (value, value.hex().encode(), base64.b64encode(value))]
            for path in folder.rglob('*'):
                if path.is_file():
                    data = path.read_bytes()
                    if any(form in data for form in forms):
                        secrets_found.append(str(path.relative_to(folder)))
            assert not any(form in v for form in forms for v in entries.values())
        assert not secrets_found, secrets_found
        record('credentials_and_authorization_are_absent_from_evidence_and_wire_bodies')
        assert len(checks) == 11, checks
        report.update(accepted=True, count=len(checks), observations=observations,
                      peers={n: {'account_id': p.account_id} for n, p in peers.items()},
                      request_count=len(requests), fixture_root_scheme='https', credential_leak_hits=0)
    finally:
        for fault in faults:
            fault.release.set()
        for device in devices:
            if device.process and device.process.poll() is None:
                device.process.kill()
                device.process.wait(timeout=15)
            if device.log and not device.log.closed:
                device.log.close()
        server.shutdown()
        server.server_close()
        key.unlink(missing_ok=True)
        try:
            os.kill(int(keyring_pid), signal.SIGTERM)
        except ProcessLookupError:
            pass
        os.kill(int(bus_pid), signal.SIGTERM)
        shutil.rmtree(private, ignore_errors=True)
        os.environ.clear()
        os.environ.update(original_env)
        report['checks'] = checks
        report['count'] = len(checks)
        if not report.get('request_count'):
            (folder / 'requests.json').write_text(json.dumps(requests, indent=2))
        (folder / 'result.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({'accepted': report['accepted'], 'checks': len(checks), 'source_sha': report['source_sha'],
                      'run_id': report['run_id'], 'attempt': report['attempt']}))


if __name__ == '__main__':
    main()
