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
    parser.add_argument('--command-consumer', type=Path, required=True)
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
              'scope': 'native Receive and group delete versus update; native book delete and restart restore; Linux only',
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
        body = b'F05 remaining native UI original\n' * 64
        book = 'txt:' + sha(body)
        source = folder / 'Remaining-book.txt'
        source.write_bytes(body)
        report['book_key'] = book
        report['original_sha256'] = sha(body)
        report['scenario'] = 'native Receive then offline group delete versus update; no database planting'
        launch(a)
        launch(b)
        pids = {'peerA': a.host.process.pid, 'peerB': b.host.process.pid}
        focus(a)
        a.host.dialog(source)
        a.host.wait(lambda s: s['book'] > 0 and s['books'] == 1 and not s['error'], timeout=60)
        edit_title(a, 'Remaining baseline book')
        for peer in (a, b):
            open_account(peer)
            connect_first_time(peer)
            scan(peer)
            assert finish(peer)['session_state'] == '4'
            disconnect(peer)
            close_account(peer)
        focus(b)
        b.host.dialog(source)
        b.host.wait(lambda s: s['book'] > 0 and s['books'] == 1 and not s['error'], timeout=60)
        open_collections(a)
        group_key = make_group(a, 'Remaining conflict shelf')
        close_collections(a)
        group_kind = kind_of(a, group_key)
        sync(a)
        sync(b)
        assert ghist(a, group_key) == ghist(b, group_key)
        open_collections(b)
        before_view = coll_ready(b)
        before_projected = group_key in before_view.get('group_ids', '').split(',')
        close_collections(b)
        # Existing native Receive books is an explicit user projection action.
        open_account(b)
        scan(b)
        assert finish(b)['session_state'] == '4'
        b.host.key('alt+r')
        projection = ready(b, lambda s: int(s.get('receive_seen', '0')) > 0, seconds=180)
        disconnect(b)
        close_account(b)
        open_collections(b)
        after_view = coll_ready(b)
        assert group_key in after_view.get('group_ids', '').split(','), after_view
        close_collections(b)
        record('native_receive_projects_received_group_into_peerB_collections',
               before_projected=before_projected, after_group_ids=after_view.get('group_ids'),
               account=projection, group_key=group_key)
        common = ids(protocol(a, 'heads', group_kind, group_key)['heads'])
        assert common == ids(protocol(b, 'heads', group_kind, group_key)['heads'])
        baseline_history = ghist(a, group_key)
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
        dialog_field(b, 'n', 'PeerB offline update retained')
        save_dialog(b)
        close_collections(b)
        ah, bh = ghist(a, group_key), ghist(b, group_key)
        ar = next(iter(set(ah) - set(baseline_history)))
        br = next(iter(set(bh) - set(baseline_history)))
        assert ah[ar]['operation'] == 'delete' and bh[br]['operation'] == 'put'
        assert sorted(ah[ar]['parents']) == sorted(bh[br]['parents']) == common
        record('native_delete_and_rename_create_distinct_siblings_of_exact_common_head',
               delete_revision=ar, update_revision=br, common=common)
        sync(a)
        sync(b)
        sync(a)
        ga, gb = protocol(a, 'heads', group_kind, group_key), protocol(b, 'heads', group_kind, group_key)
        assert ga['state'] == gb['state']
        assert ga['state']['heads'] == 2 and not ga['state']['projection_safe']
        assert ids(ga['heads']) == ids(gb['heads']) == sorted([ar, br])
        wire = wire_entity(group_key)
        assert ghist(a, group_key) == ghist(b, group_key)
        assert set(wire) == set(ghist(a, group_key))
        assert all(json.loads(entries[p]) == ghist(a, group_key)[r] for r, (p, _) in wire.items())
        assert any(r['peer'] == 'peerB' and r['method'] == 'GET' and '/revisions/' in r['path'] for r in requests)
        record('native_delete_versus_update_converges_without_automatic_winner',
               graph=ga['state'], heads=ga['heads'], wire=wire)
        # Boundary input uses the installed public typed-command consumer, not SQL writes.
        # This is explicitly setup by another API client; deletion/restoration below remain real GTK.
        hard_kill(a)
        long_title, long_author, long_sort = 'T' * 5000, 'A' * 5000, 'Different stable sort'
        title_file, author_file, sort_file = folder / 'long-title.txt', folder / 'long-author.txt', folder / 'long-sort.txt'
        title_file.write_text(long_title)
        author_file.write_text(long_author)
        sort_file.write_text(long_sort)
        book_parents = ids(protocol(a, 'heads', kind_of(a, book), book)['heads'])
        prepared = subprocess.run([str(args.command_consumer.resolve()), 'book', str(db_path(a)),
                                   '-', ','.join(book_parents), '0', book, 'txt', sha(body),
                                   str(len(body)), '1', str(title_file), str(author_file), str(sort_file)],
                                  capture_output=True, text=True, timeout=45)
        assert prepared.returncode == 0
        prepared_value = json.loads(prepared.stdout)
        assert prepared_value['status'] == 3 and prepared_value['revision_status'] == 5 and not prepared_value['created'] and not prepared_value['applied'], prepared_value
        assert ids(protocol(a, 'heads', kind_of(a, book), book)['heads']) == book_parents
        record('over_4096_characters_is_rejected_without_new_revision', rejected_characters=5000)
        long_title, long_author = chr(0x4e66) * 4096, chr(0x4eba) * 4096
        title_file.write_text(long_title)
        author_file.write_text(long_author)
        prepared = subprocess.run([str(args.command_consumer.resolve()), 'book', str(db_path(a)), '-', ','.join(book_parents), '0', book, 'txt', sha(body), str(len(body)), '1', str(title_file), str(author_file), str(sort_file)], capture_output=True, text=True, timeout=45)
        assert prepared.returncode == 0
        prepared_value = json.loads(prepared.stdout)
        assert prepared_value['status'] == 0 and prepared_value['applied'], prepared_value
        exact_metadata = (long_title, long_author, long_sort, 1)
        assert sql(a, 'SELECT title,author,sort_title,favorite FROM reader_books WHERE book_key=?', (book,)) == [exact_metadata]
        launch(a)
        # Real GTK deletion, process restart, retained-book selection and restore.
        focus(a)
        a.host.key('F2', 'ctrl+e')
        window(a, 'Book details')
        a.host.key('alt+d')
        window(a, 'Confirm book operation')
        a.host.key('alt+o')
        window(a, 'Confirm book operation', False)
        window(a, 'Book details', False)
        a.host.wait(lambda s: s['books'] == 0 and not s['error'], timeout=60)
        assert sql(a, 'SELECT deleted FROM reader_books WHERE book_key=?', (book,)) == [(1,)]
        deleted_history = ghist(a, book)
        deleted_heads = protocol(a, 'heads', kind_of(a, book), book)
        assert deleted_heads['state']['heads'] == 1
        delete_id = ids(deleted_heads['heads'])[0]
        assert deleted_history[delete_id]['operation'] == 'delete'
        record('native_book_delete_retains_tombstone_and_revision_history', revision=delete_id)
        hard_kill(a)
        launch(a)
        focus(a)
        a.host.key('F2')
        a.host.wait(lambda s: s['books'] == 0 and not s['error'], timeout=60)
        a.host.key('ctrl+shift+d')
        window(a, 'Removed books')
        a.host.key('Home', 'Return')
        window(a, 'Book details')
        a.host.key('alt+r')
        window(a, 'Confirm book operation')
        a.host.key('alt+o')
        window(a, 'Confirm book operation', False)
        window(a, 'Book details', False)
        a.host.wait(lambda s: s['books'] == 1 and not s['error'], timeout=60)
        assert sql(a, 'SELECT deleted FROM reader_books WHERE book_key=?', (book,)) == [(0,)]
        restored = ghist(a, book)
        new_ids = set(restored) - set(deleted_history)
        assert len(new_ids) == 1
        restore_id = next(iter(new_ids))
        assert restored[restore_id]['operation'] == 'restore'
        assert restored[restore_id]['parents'] == [delete_id]
        assert set(deleted_history).issubset(restored)
        record('native_removed_books_restore_after_restart_preserves_delete_parent',
               restore_revision=restore_id, deleted_revision=delete_id)
        assert sql(a, 'SELECT title,author,sort_title,favorite FROM reader_books WHERE book_key=?', (book,)) == [exact_metadata]
        record('restore_preserves_4096_multibyte_fields_and_distinct_sort_exactly', title_bytes=12288, author_bytes=12288, setup='installed public typed command; no SQL mutation')
        report['book_delete_restore'] = {'accepted': True, 'delete_revision': delete_id,
                                        'restore_revision': restore_id, 'restart': True}

        report['complete_f05'] = False
        (folder / 'requests.json').write_text(json.dumps(requests, indent=2))
        (folder / 'wire.json').write_text(json.dumps({p: sha(v) for p, v in entries.items()}, indent=2))
        key.unlink()
        leaks = []
        for peer in peers.values():
            values = [peer.user.encode(), peer.password.encode(), (peer.user + ':' + peer.password).encode(), peer.authorization.encode()]
            forms = [f for value in values for f in (value, value.hex().encode(), base64.b64encode(value))]
            for path in folder.rglob('*'):
                if path.is_file() and any(form in path.read_bytes() for form in forms):
                    leaks.append(str(path.relative_to(folder)))
            assert not any(form in v for form in forms for v in entries.values())
        assert not leaks, leaks
        record('synthetic_credentials_absent_from_preserved_evidence')
        assert len(checks) == 8
        report.update(accepted=True, count=len(checks), observations=observations,
                      request_count=len(requests), credential_leak_hits=0,
                      peers={n: {'account_id': p.account_id, 'pid': pids[n]} for n, p in peers.items()})

    except Exception as failure:
        report['failure'] = repr(failure)
        report['failure_states'] = {n: p.host.read() for n, p in peers.items()}
        visible = subprocess.run(['wmctrl', '-lpG'], capture_output=True, text=True, timeout=10)
        (folder / 'failure-windows.txt').write_text(visible.stdout + visible.stderr)
        subprocess.run(['import', '-window', 'root', str(folder / 'failure-desktop.png')], timeout=15, check=False)
        raise

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
