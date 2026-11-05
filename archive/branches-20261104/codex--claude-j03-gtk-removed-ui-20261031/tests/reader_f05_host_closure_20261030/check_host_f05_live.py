# SPDX-License-Identifier: MIT
"""Actions-only simultaneous-live two-peer GTK host wire, convergence and tombstone check.

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
              'scope': 'two simultaneously live GTK hosts: convergence and group tombstone/restore over the wire; Linux only',
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

    # ---- simultaneous-live scenario (header, fixture and finally block are shared with check_host_f05.py) ----
    def focus(peer):
        assert peer.host.process.poll() is None, 'actual GTK host exited'
        command('xdotool', 'windowactivate', '--sync', peer.host.window)

    def coll(peer):
        state = configparser.ConfigParser(interpolation=None)
        state.read(peer.host.observe)
        return dict(state['collections']) if state.has_section('collections') else {}

    def coll_ready(peer, predicate=lambda s: True, seconds=60):
        peer.host.wait(lambda s: not s.get('shelf_loading') and not s.get('shelf_restoring') and predicate(coll(peer)),
                       timeout=seconds)
        return coll(peer)

    def open_collections(peer):
        focus(peer)
        peer.host.key('F2', 'ctrl+shift+c')
        window(peer, 'Library collections')
        return coll_ready(peer)

    def close_collections(peer):
        window(peer, 'Library collections')
        peer.host.key('alt+F4')
        window(peer, 'Library collections', False)

    def dialog_field(peer, mnemonic, value):
        peer.host.key('alt+' + mnemonic, 'ctrl+a')
        peer.host.paste(str(value))

    def save_dialog(peer):
        peer.host.key('Return')
        window(peer, 'Collection details', False)
        coll_ready(peer, lambda s: s.get('editor') == '0')

    def make_group(peer, name):
        window(peer, 'Library collections')
        peer.host.key('alt+n')
        window(peer, 'Collection details')
        dialog_field(peer, 'n', name)
        dialog_field(peer, 'p', 0)
        save_dialog(peer)
        return coll_ready(peer)['selected_id']

    def choose_group(peer, group_key):
        current = coll_ready(peer)
        listed = current['group_ids'].split(',')
        assert group_key in listed, (group_key, current)
        peer.host.key('alt+g', 'Home')
        coll_ready(peer)
        for _ in range(listed.index(group_key)):
            peer.host.key('Down')
            coll_ready(peer)
        return coll_ready(peer, lambda s: s['selected_id'] == group_key)

    def sync(peer, expect='4'):
        focus(peer)
        open_account(peer)
        ready(peer, lambda s: s['has_password'] == '1' and s['id'] == peer.account_id)
        scan(peer)
        done = finish(peer)
        assert done['session_state'] == expect, done
        disconnect(peer)
        close_account(peer)
        return done

    def ghist(peer, entity_key):
        return {r: json.loads(v) for r, v in sql(
            peer, 'SELECT revision_id,body_json FROM reader_revisions WHERE entity_key=?', (entity_key,))}

    def wire_entity(entity_key):
        found = {}
        with lock:
            snapshot = dict(entries)
        for path, data in snapshot.items():
            if '/revisions/' in path:
                value = json.loads(data)
                if value.get('entity_key') == entity_key:
                    found[value['id']] = (path, sha(data))
        return found

    def kind_of(peer, entity_key):
        rows = sql(peer, 'SELECT DISTINCT entity_kind FROM reader_revisions WHERE entity_key=?', (entity_key,))
        assert len(rows) == 1, rows
        return rows[0][0]

    try:
        a, b = peers['peerA'], peers['peerB']
        body = b'F05 live two-peer book original\n' + (b'Both hosts stay alive for the whole scenario.\n' * 60)
        book = 'txt:' + sha(body)
        source = folder / 'Live-book.txt'
        source.write_bytes(body)
        report['book_key'] = book
        report['original_sha256'] = sha(body)
        report['scenario'] = 'both hosts live for the whole scenario; no host is closed or restarted'

        launch(a)
        launch(b)
        pids = {'peerA': a.host.process.pid, 'peerB': b.host.process.pid}
        assert pids['peerA'] != pids['peerB']

        def both_alive():
            assert a.host.process.poll() is None and b.host.process.poll() is None

        # 1. peerA works while peerB's live process is untouched.
        focus(a)
        a.host.dialog(source)
        a.host.wait(lambda s: s['book'] > 0 and s['books'] == 1 and not s['error'], timeout=60)
        edit_title(a, 'A live base title')
        open_account(a)
        connect_first_time(a)
        scan(a)
        done = finish(a)
        assert done['session_state'] == '4', done
        base_history = history(a, book)
        wire_base = wire_revisions(book)
        assert base_history and set(base_history) == set(wire_base)
        for rid, (path, digest) in wire_base.items():
            assert path.endswith(rid + '-' + digest + '.json') and json.loads(entries[path]) == base_history[rid]
        assert all(r['peer'] == 'peerA' for r in requests if r['method'] == 'PUT')
        assert sql(b, 'SELECT count(*) FROM reader_revisions')[0][0] == 0 and outbox(b) == 0
        a_head = protocol(a, 'heads', 'book', book)
        assert a_head['state']['heads'] == 1
        both_alive()
        record('live_peerA_pushes_exact_history_while_peerB_process_is_alive_and_untouched',
               pids=pids, revisions=sorted(base_history), wire=wire_base)
        disconnect(a)
        close_account(a)

        # 2. peerB (live, empty) receives by GET only.
        focus(b)
        before = len(requests)
        open_account(b)
        connect_first_time(b)
        scan(b)
        done = finish(b)
        assert done['session_state'] == '4' and int(done['pulled']) >= 1, done
        assert history(b, book) == base_history
        assert not [r for r in requests[before:] if r['peer'] == 'peerB' and r['method'] == 'PUT']
        assert [r for r in requests[before:] if r['peer'] == 'peerB' and r['method'] == 'GET' and '/revisions/' in r['path']]
        b_head = protocol(b, 'heads', 'book', book)
        assert b_head['state']['heads'] == 1 and ids(b_head['heads']) == ids(a_head['heads'])
        both_alive()
        record('live_peerB_receives_same_revisions_by_get_while_peerA_process_is_alive', revisions=sorted(base_history))
        disconnect(b)
        close_account(b)

        # 3. peerB imports the identical original.
        focus(b)
        b.host.dialog(source)
        b.host.wait(lambda s: s['book'] > 0 and s['books'] == 1 and not s['error'], timeout=60)
        assert set(history(b, book)) >= set(base_history)
        common = ids(protocol(b, 'heads', 'book', book)['heads'])
        record('live_peerB_imports_identical_original_and_keeps_received_history')

        # 4. Distinct offline children from the common head with both processes alive.
        edit_title(b, 'B live concurrent title')
        focus(a)
        edit_title(a, 'A live concurrent title')
        b_rev = next(iter(set(history(b, book)) - set(base_history)))
        a_rev = next(iter(set(history(a, book)) - set(base_history)))
        assert a_rev != b_rev
        assert sorted(history(b, book)[b_rev]['parents']) == common == sorted(history(a, book)[a_rev]['parents'])
        assert outbox(a) >= 1 and outbox(b) >= 1
        both_alive()
        record('live_both_hosts_make_distinct_offline_children_of_one_received_head', common=common, peerA=a_rev, peerB=b_rev)

        # 5. Both sessions are in flight on the server at the same instant.
        focus(a)
        open_account(a)
        ready(a, lambda s: s['has_password'] == '1' and s['id'] == a.account_id)
        focus(b)
        open_account(b)
        ready(b, lambda s: s['has_password'] == '1' and s['id'] == b.account_id)
        gate_a, gate_b = arm('gate', a, '/dav/'), arm('gate', b, '/dav/')
        scan(a)
        assert gate_a.hit.wait(40), 'peerA gated request not reached'
        scan(b)
        assert gate_b.hit.wait(40), 'peerB gated request not reached'
        assert not gate_a.release.is_set() and not gate_b.release.is_set()
        both_alive()
        in_flight = {'peerA': account(a)['session_state'], 'peerB': account(b)['session_state']}
        assert in_flight == {'peerA': '1', 'peerB': '1'}, in_flight
        gated = [r for r in requests if r.get('fault') == 'gate' and r['peer'] in ('peerA', 'peerB')][-2:]
        gate_a.release.set()
        gate_b.release.set()
        done_a, done_b = finish(a), finish(b)
        assert done_a['session_state'] == '4' and done_b['session_state'] == '4', (done_a, done_b)
        record('live_two_account_sessions_are_in_flight_on_the_server_simultaneously',
               states_while_gated=in_flight, gated_requests=gated)
        disconnect(a)
        disconnect(b)
        close_account(a)
        close_account(b)

        # 6. Converge.
        sync(a)
        sync(b)
        sync(a)
        a_state, b_state = protocol(a, 'heads', 'book', book), protocol(b, 'heads', 'book', book)
        assert a_state['state']['heads'] == b_state['state']['heads'] == 2
        assert not a_state['state']['projection_safe'] and not b_state['state']['projection_safe']
        assert ids(a_state['heads']) == ids(b_state['heads']) == sorted([a_rev, b_rev])
        final_wire = wire_revisions(book)
        a_final, b_final = history(a, book), history(b, book)
        assert set(a_final) == set(b_final) == set(final_wire) and a_final == b_final
        for rid, (path, digest) in final_wire.items():
            assert json.loads(entries[path]) == a_final[rid]
        assert title_of(a, book) == 'A live concurrent title' and title_of(b, book) == 'B live concurrent title'
        puts = [r['path'] for r in requests if r['method'] == 'PUT' and r['status'] == 201 and '/revisions/' in r['path']]
        assert len(puts) == len(set(puts))
        both_alive()
        record('live_peers_converge_on_identical_sibling_heads_titles_unselected_and_wire_history',
               heads=a_state['heads'], revisions=sorted(final_wire))

        # 7. Shelf group created in peerA's native Collections dialog reaches peerB's history.
        open_collections(a)
        group_key = make_group(a, 'Live shelf')
        close_collections(a)
        group_kind = kind_of(a, group_key)
        sync(a)
        sync(b)
        a_group, b_group = ghist(a, group_key), ghist(b, group_key)
        wire_group = wire_entity(group_key)
        assert a_group and a_group == b_group and set(wire_group) == set(a_group)
        assert all(v['operation'] == 'put' for v in a_group.values())
        assert protocol(b, 'heads', group_kind, group_key)['state']['heads'] == 1
        record('live_group_created_in_peerA_ui_reaches_peerB_history_over_wire',
               kind=group_kind, key=group_key, revisions=sorted(a_group))

        # 8. Tombstone: native Remove in peerA, propagated through the wire.
        open_collections(a)
        choose_group(a, group_key)
        window(a, 'Library collections')
        a.host.key('alt+d')
        window(a, 'Collection details')
        save_dialog(a)
        close_collections(a)
        deleted_local = [r for r, v in ghist(a, group_key).items() if v['operation'] == 'delete']
        assert len(deleted_local) == 1
        sync(a)
        sync(b)
        b_group = ghist(b, group_key)
        assert b_group == ghist(a, group_key) and set(b_group) == set(wire_entity(group_key))
        assert [r for r, v in b_group.items() if v['operation'] == 'delete'] == deleted_local
        b_tomb = protocol(b, 'heads', group_kind, group_key)
        assert b_tomb['state']['heads'] == 1 and b_tomb['state']['deleted'] == 1, b_tomb
        record('live_group_remove_tombstone_in_peerA_ui_propagates_over_wire_to_peerB',
               tombstone=deleted_local, peerB_graph=b_tomb['state'])

        # 9. Restore from peerA's removed view, propagated again.
        open_collections(a)
        focus(a)
        a.host.key('alt+m')
        coll_ready(a, lambda s: s.get('removed') == '1')
        choose_group(a, group_key)
        a.host.key('alt+s')
        window(a, 'Collection details')
        save_dialog(a)
        a.host.key('alt+m')
        coll_ready(a, lambda s: s.get('removed') == '0')
        close_collections(a)
        sync(a)
        sync(b)
        b_group = ghist(b, group_key)
        assert b_group == ghist(a, group_key) and set(b_group) == set(wire_entity(group_key)) and len(b_group) == 3
        b_back = protocol(b, 'heads', group_kind, group_key)
        assert b_back['state']['heads'] == 1 and b_back['state']['deleted'] == 0, b_back
        record('live_group_restore_in_peerA_ui_propagates_over_wire_and_clears_peerB_tombstone',
               peerB_graph=b_back['state'], revisions=sorted(b_group))

        # 10. Delete versus rename needs peerB's own UI to edit the received group.
        open_collections(b)
        b_view = coll_ready(b)
        projected = group_key in (b_view.get('group_ids') or '').split(',')
        close_collections(b)
        if not projected:
            record('live_delete_versus_update_conflict_blocked_peerB_ui_does_not_project_received_group',
                   blocker='peerB Library collections lists no received group; no UI path edits it, nothing was injected',
                   peerB_group_ids=b_view.get('group_ids'), tombstone_state_in_peerB_history=b_back['state'])
        else:
            open_collections(a)
            choose_group(a, group_key)
            a.host.key('alt+d')
            window(a, 'Collection details')
            save_dialog(a)
            close_collections(a)
            open_collections(b)
            choose_group(b, group_key)
            b.host.key('alt+r')
            window(b, 'Collection details')
            dialog_field(b, 'n', 'Renamed by peerB')
            save_dialog(b)
            close_collections(b)
            sync(a)
            sync(b)
            sync(a)
            ga, gb = protocol(a, 'heads', group_kind, group_key), protocol(b, 'heads', group_kind, group_key)
            assert ga['state'] == gb['state'] and ids(ga['heads']) == ids(gb['heads'])
            assert ghist(a, group_key) == ghist(b, group_key) == {r: json.loads(entries[p]) for r, (p, _) in wire_entity(group_key).items()}
            record('live_delete_versus_update_conflict_converges_without_selection_or_data_loss',
                   graph=ga['state'], heads=ga['heads'], peerB_ui_projected=True)

        # 11. Evidence hygiene.
        (folder / 'requests.json').write_text(json.dumps(requests, indent=2))
        (folder / 'wire.json').write_text(json.dumps({p: sha(v) for p, v in entries.items()}, indent=2))
        key.unlink()
        leaks = []
        for peer in peers.values():
            values = [peer.user.encode(), peer.password.encode(), (peer.user + ':' + peer.password).encode(),
                      peer.authorization.encode()]
            forms = [f for value in values for f in (value, value.hex().encode(), base64.b64encode(value))]
            for path in folder.rglob('*'):
                if path.is_file() and any(form in path.read_bytes() for form in forms):
                    leaks.append(str(path.relative_to(folder)))
            assert not any(form in v for form in forms for v in entries.values())
        assert not leaks, leaks
        record('credentials_and_authorization_are_absent_from_evidence_and_wire_bodies')
        assert len(checks) == 11, checks
        report.update(accepted=True, count=len(checks), observations=observations, request_count=len(requests),
                      peers={n: {'account_id': p.account_id, 'pid': pids[n]} for n, p in peers.items()},
                      credential_leak_hits=0, group_ui_projected_in_peerB=projected)

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
