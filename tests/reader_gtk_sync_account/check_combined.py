# SPDX-License-Identifier: MIT
"""Actions-only real GTK account controls, Secret Service and native TLS DAV."""
import argparse
import base64
import configparser
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import sqlite3
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
from check_linux_host import Session, command
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'reader_sync'))
from check_sync import raw, revision


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('payload', 'metadata-consumer', 'revision-consumer', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    for name in ('receive-fixtures', 'reading-probe', 'inspect-consumer'):
        parser.add_argument('--' + name, type=Path)
    args = parser.parse_args()
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    folder = args.output.resolve();folder.mkdir()
    checks, requests, entries, directories, devices = [], [], {}, {'/dav/', '/other/'}, []
    blocked, release = threading.Event(), threading.Event()
    flags = {'pause': False, 'http': 0}
    lock = threading.Lock()
    user, password = 'u' + secrets.token_hex(20), 'p' + secrets.token_hex(30)
    authorization = 'Basic ' + base64.b64encode((user + ':' + password).encode()).decode()
    report = {'accepted': False, 'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
              'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'checks': checks, 'count': 0,
              'program_sha256': hashlib.sha256((args.payload / 'bin/exreader-linux').read_bytes()).hexdigest(),
              'scope': 'GTK secure credentials, sync and read-only status after cancel, failure and retry',
              'owner_page_limit': 50, 'copy_chunk_limit': 65536, 'original_limit': 128 * 1024 * 1024,
              'remote_sdk_import_accepted': False, 'remote_projection_accepted': False, 'complete_product': False}
    private = Path(tempfile.mkdtemp(prefix='gtk-account-', dir=os.environ.get('RUNNER_TEMP')))
    secret_home, runtime = private / 'home', private / 'run'
    secret_home.mkdir(mode=0o700);runtime.mkdir(mode=0o700)
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
            key, value = line.split('=', 1);credential_env[key] = value
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
        alias = dbus('/org/freedesktop/secrets', 'org.freedesktop.Secret.Service.ReadAlias', 'default')
    collection = re.search(r"'(/org/freedesktop/secrets/collection/[^']+)'", alias)
    assert collection, 'no temporary default secret collection'
    # Give only actual application processes this isolated platform store.
    os.environ.update(credential_env)
    certs = folder / 'certificates';certs.mkdir()
    key, certificate = certs / 'server.key', certs / 'server.crt'
    subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1', '-keyout', str(key),
                    '-out', str(certificate), '-subj', '/CN=localhost', '-addext', 'subjectAltName=IP:127.0.0.1'],
                   check=True, capture_output=True)
    trust = '/usr/local/share/ca-certificates/exreader-gtk-account.crt'
    subprocess.run(['sudo', 'cp', str(certificate), trust], check=True, capture_output=True)
    subprocess.run(['sudo', 'update-ca-certificates'], check=True, capture_output=True)

    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def log_message(self, *unused):
            pass

        def send(self, code, data=b''):
            self.send_response(code);self.send_header('Content-Length', str(len(data)))
            self.send_header('Connection', 'close');self.end_headers();self.close_connection = True
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError, ssl.SSLError):
                pass

        def authorized(self):
            if self.command == 'PROPFIND':
                self.rfile.read(int(self.headers.get('Content-Length', 0)))
            with lock:
                requests.append({'method': self.command, 'path': self.path,
                                 'authenticated': self.headers.get('Authorization') == authorization})
            if self.headers.get('Authorization') != authorization:
                self.send(401);return False
            if flags['http']:
                self.send(flags['http']);return False
            return True

        def do_MKCOL(self):
            if not self.authorized(): return
            with lock:
                exists = self.path in directories;directories.add(self.path)
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
                flags['pause'] = False;blocked.set();release.wait(25)
            with lock:
                children = [(p, True, 0) for p in directories if p.startswith(self.path) and
                            (p == self.path or '/' not in p[len(self.path):].rstrip('/'))]
                children += [(p, False, len(b)) for p, b in entries.items() if p.startswith(self.path) and '/' not in p[len(self.path):]]
                exists = self.path in directories
            if not exists:
                self.send(404);return
            rows = ['<d:response><d:href>' + p + '</d:href><d:propstat><d:prop><d:resourcetype>' +
                    ('<d:collection/>' if is_dir else '') + '</d:resourcetype><d:getcontentlength>' + str(size) +
                    '</d:getcontentlength></d:prop><d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>'
                    for p, is_dir, size in children]
            self.send(207, ('<d:multistatus xmlns:d="DAV:">' + ''.join(rows) + '</d:multistatus>').encode())

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler);server.daemon_threads = True
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(certificate, key)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    root = 'https://127.0.0.1:' + str(server.server_port) + '/dav/'

    def new_host(name):
        place = folder / name;place.mkdir()
        device = Session((args.payload / 'bin/exreader-linux').resolve(), (args.payload / 'Reader.otf').resolve(), place)
        devices.append(device);return device

    host = new_host('primary')

    def sql(query, values=()):
        with sqlite3.connect(host.folder / 'profile/library.sqlite.product.sqlite') as db:
            return db.execute(query, values).fetchall()

    def protocol(action, *values):
        done = subprocess.run([str(args.revision_consumer.resolve()), action,
                               str(host.folder / 'profile/library.sqlite.product.sqlite'), *map(str, values)],
                              capture_output=True, text=True, timeout=45)
        assert done.returncode == 0, 'installed revision consumer failed'
        value = json.loads(done.stdout);assert value['status'] == 0, value
        return value

    def account():
        state = configparser.ConfigParser(interpolation=None);state.read(host.observe)
        return dict(state['account']) if state.has_section('account') else {}

    def ready(predicate=lambda state: True, seconds=90):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            assert host.process.poll() is None, 'actual GTK host exited'
            current = account()
            if current and not int(current['owner_busy']) and not int(current['preparing']) and not host.read().get('busy') and predicate(current):
                return current
            time.sleep(.1)
        raise TimeoutError('Account controls did not reach the expected state: ' + repr(account()))

    def window(present=True):
        end = time.monotonic() + 30
        while time.monotonic() < end:
            found = subprocess.run(['xdotool', 'search', '--onlyvisible', '--all', '--pid', str(host.process.pid),
                                    '--name', '^Account and Sync$'], capture_output=True, text=True, timeout=5)
            if bool(found.stdout.strip()) == present:
                if present:
                    selected = found.stdout.splitlines()[-1];command('xdotool', 'windowactivate', '--sync', selected);return selected
                return None
            time.sleep(.1)
        raise TimeoutError('Native Account and Sync dialog visibility differs')

    def open_account(menu=False):
        command('xdotool', 'windowactivate', '--sync', host.window);host.key('F2')
        host.wait(lambda s: not s.get('shelf_loading') and not s.get('shelf_restoring'), timeout=60)
        host.key('alt+m', 'Down', 'Return') if menu else host.key('ctrl+shift+a')
        target = window();ready(lambda s: s['visible'] == '1');return target

    def close_account():
        window();host.key('alt+F4');window(False)
        ready(lambda s: s['visible'] == '0' and s['session_present'] == '0')

    def field(mnemonic, value):
        window()
        host.key('alt+' + mnemonic, 'ctrl+a');host.paste(value)

    def fill(remember=False, url=root):
        field('w', url);field('u', user);field('p', password);host.key('alt+m' if remember else 'alt+h')

    def record(name):
        assert name not in checks;checks.append(name)
        current = account();assert int(current.get('max_page_rows', 0)) <= 50
        print(json.dumps({'check': name, 'pass': True}), flush=True)

    def capture_status(expected_phase, expected_reason=None):
        def wave():
            value = configparser.ConfigParser(interpolation=None); value.read(host.observe)
            return dict(value['wave3'])
        before = wave(); current = account()
        before_requests = len(requests)
        before_rows = sql('SELECT * FROM reader_outbox ORDER BY rowid')
        window(); host.key('alt+v')
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            value = wave()
            if int(value['sync_refreshes']) > int(before['sync_refreshes']) and value['sync_busy'] == '0':
                break
            assert host.process.poll() is None
            time.sleep(.1)
        else:
            raise TimeoutError('status capture did not finish: ' + repr(wave()))
        text = value['sync_text'].replace('\\n', '\n')
        assert value['sync_code'] == '0' and value['sync_view_visible'] == '1', value
        assert 'Phase: ' + expected_phase + '\n' in text, text
        if expected_reason is not None:
            assert 'Reason: ' + expected_reason + '\n' in text, text
        assert ('Resumable: yes' if expected_phase in ('cancelled', 'failed') else 'Resumable: no') in text
        assert 'Pending records: ' in text and 'Whole library synchronized: no' in text
        assert len(requests) == before_requests and sql('SELECT * FROM reader_outbox ORDER BY rowid') == before_rows
        assert account()['attempt'] == current['attempt'] and account()['session_state'] == current['session_state']
        assert user not in text and password not in text and root not in text
        record('status_' + expected_phase + '_capture_is_read_only')

    def disconnect():
        window()
        host.key('alt+d');return ready(lambda s: s['session_present'] == '0' and s['form_enabled'] == '1')

    def scan():
        window();host.key('alt+s')

    def retry_scan():
        window();previous = int(account()['attempt']);host.key('alt+t')
        return ready(lambda s: int(s['attempt']) > previous and s['session_state'] in ('4', '5'), seconds=180)

    def pause_next():
        blocked.clear();release.clear();flags['pause'] = True

    def start_preparing():
        window()
        command('xdotool', 'key', '--clearmodifiers', 'alt+s')
        end = time.monotonic() + 5
        while time.monotonic() < end:
            if account().get('preparing') == '1':
                return
            assert account().get('session_present') == '0', 'preparation unexpectedly passed before close input'
            time.sleep(.002)
        raise TimeoutError('Local preparation did not start')

    try:
        originals = {}
        host.launch()
        for index in range(52):
            body = ('Native local original %02d\n' % index).encode() + ('Book bytes kept unchanged.\n' * 40).encode()
            source = folder / ('Local-%02d.txt' % index);source.write_bytes(body)
            originals[hashlib.sha256(body).hexdigest()] = body
            host.dialog(source);host.wait(lambda s: s['book'] > 0 and not s['error'], timeout=60)
            assert sql('SELECT count(*) FROM reader_local_books') == [(index + 1,)]
            assert host.read()['books'] <= 150
        host.close()
        assert sql('SELECT count(*) FROM reader_local_books') == [(52,)]
        first = sql('SELECT book_key FROM reader_books ORDER BY book_key LIMIT 1')[0][0]
        sql("UPDATE reader_books SET title='Edited local title',author='Edited author',sort_title='custom-sort',favorite=1 WHERE book_key=?", (first,))
        baseline = sql('SELECT book_key,title,author,sort_title,favorite FROM reader_books ORDER BY book_key')
        host.launch();target = open_account(menu=True)
        assert ready()['password_visible'] == '0' and ready()['credential_status'] == '1'
        command('import', '-window', target, folder / '01-native-empty-account.png')
        record('real_more_menu_and_keyboard_open_masked_native_account_controls')
        fill(True);host.key('alt+a');saved = ready(lambda s: s['bound'] == '1' and s['credential_status'] == '0')
        identity = saved['id'];assert str(uuid.UUID(identity)) == identity and saved['root'] == root
        config = configparser.ConfigParser(interpolation=None);config.read(host.folder / 'profile/account.ini')
        assert config.sections() == ['account'] and dict(config['account']) == {'id': identity, 'root': root}
        assert 'saved in system secure storage' in saved['notice'] and not requests
        record('explicit_remember_uses_real_secret_service_and_persists_only_uuid_and_exact_root')
        close_account();host.close();host.launch();open_account()
        loaded = ready(lambda s: s['credential_status'] == '0' and s['has_password'] == '1')
        assert loaded['has_user'] == '1' and loaded['remember'] == '1' and loaded['id'] == identity and loaded['password_visible'] == '0'
        record('new_actual_process_loads_saved_credentials_with_the_same_stable_account_id')
        start_preparing();command('xdotool', 'key', '--clearmodifiers', 'alt+F4');window(False)
        ready(lambda s: s['session_present'] == '0' and s['visible'] == '0')
        assert not requests and account()['session_generation'] == '0'
        record('back_during_local_preparation_cancels_owner_work_before_network_start')
        open_account();start_preparing();command('wmctrl', '-ic', hex(int(host.window)))
        close_code = host.process.wait(timeout=35);host.log.close()
        assert close_code == 0, {'close_exit': close_code, 'account': account(), 'http_requests': len(requests)}
        assert not requests, {'unexpected_http_requests': len(requests), 'account': account()}
        record('main_window_close_during_preparation_retires_queued_owner_work_before_shutdown')
        host.launch();open_account()
        scan();done = ready(lambda s: s['session_state'] in ('4', '5'), seconds=180)
        assert done['session_state'] == '4', done
        assert done['seen'] == '52' and int(done['prepared']) + int(done['existing']) == 52 and done['pending'] == '0' and done['failed'] == '0'
        assert done['max_page_rows'] == '50' and done['completed_shards'] == '256'
        assert sql("SELECT count(*) FROM reader_revisions WHERE entity_kind='book'") == [(52,)]
        staged = host.folder / 'profile/sync-originals'
        assert {p.name for p in staged.iterdir()} == {digest + '.txt' for digest in originals}
        for digest, body in originals.items():
            path = staged / (digest + '.txt');assert path.read_bytes() == body and path.stat().st_mode & 0o777 == 0o600
            assert entries['/dav/exreader-sync-v1/objects/' + digest[:2] + '/' + digest + '.txt'] == body
        assert sql('SELECT book_key,title,author,sort_title,favorite FROM reader_books ORDER BY book_key') == baseline
        assert sql('SELECT count(*) FROM reader_outbox') == [(0,)]
        assert all(r['authenticated'] for r in requests)
        record('default_scan_stages_all_52_exact_originals_in_50_row_owner_pages_and_preserves_edited_metadata')
        assert done['full_library_complete'] == '0' and 'does not mean those books are readable' in done['notice']
        record('finished_ui_reports_record_scan_only_without_claiming_readable_remote_books')
        generation = int(done['session_generation']);disconnect()
        assert int(account()['closed_generation']) == generation
        record('disconnect_polls_closed_before_destroy_and_only_then_reenables_credentials')
        remote_body = b'Remote records are not SDK books\n';digest = hashlib.sha256(remote_body).hexdigest()
        remote = revision(99991, shard=0, kind='book', key='txt:' + digest, payload={
            'format': 'txt', 'source_sha256': digest, 'source_bytes': len(remote_body), 'title': 'Remote pending import', 'author': '', 'favorite': False})
        payload = raw(remote);path = '/dav/exreader-sync-v1/revisions/00/' + remote['id'] + '-' + hashlib.sha256(payload).hexdigest() + '.json'
        directories.add('/dav/exreader-sync-v1/revisions/00/');entries[path] = payload
        entries['/dav/exreader-sync-v1/objects/' + digest[:2] + '/' + digest + '.txt'] = remote_body
        pause_next();scan();assert blocked.wait(40)
        capture_status('syncing', 'none')
        ticks = int(account()['ticks']);time.sleep(.7)
        assert int(account()['ticks']) > ticks and account()['cancel_enabled'] == '1'
        window();host.key('alt+c');ready(lambda s: s['cancel_requested'] == '1', seconds=5);release.set()
        cancelled = ready(lambda s: s['session_state'] in ('3', '4', '5'))
        assert cancelled['session_state'] == '3' and cancelled['retry_enabled'] == '1'
        record('real_paused_tls_scan_leaves_gtk_responsive_and_cancel_is_nonblocking')
        capture_status('cancelled')
        retried = retry_scan()
        assert retried['session_state'] == '4' and int(retried['attempt']) == 2 and int(retried['pulled']) >= 1
        assert sql('SELECT count(*) FROM reader_books') == [(52,)] and sql('SELECT count(*) FROM reader_local_books') == [(52,)]
        with sqlite3.connect(host.folder / 'profile/library.sqlite') as db:
            assert db.execute('SELECT count(*) FROM books').fetchone() == (52,)
        assert sql("SELECT count(*) FROM reader_revisions WHERE entity_key=?", ('txt:' + digest,)) == [(1,)]
        record('explicit_retry_keeps_same_handle_and_remote_history_without_projecting_or_importing_it')
        disconnect();flags['http'] = 503;scan()
        failed = ready(lambda s: s['session_state'] == '5');assert failed['retry_enabled'] == '1'
        capture_status('failed', 'server')
        flags['http'] = 0;recovered = retry_scan();assert recovered['session_state'] == '4', recovered
        record('server_failure_is_visible_and_only_explicit_retry_resumes_the_scan')
        capture_status('sweep-complete', 'none')
        disconnect()
        parent = sql("SELECT revision_id FROM reader_revisions WHERE entity_kind='book' AND entity_key=?", (first,))[0][0]
        first_digest = first.split(':', 1)[1]
        for index, title in enumerate(('Unselected branch one', 'Unselected branch two')):
            conflict = revision(20001 + index, shard=64 + index, kind='book', key=first, parents=(parent,), payload={
                'format': 'txt', 'source_sha256': first_digest, 'source_bytes': len(originals[first_digest]),
                'title': title, 'author': 'Concurrent branch', 'favorite': bool(index)})
            wire = folder / ('local-conflict-%d.json' % index);wire.write_bytes(raw(conflict));protocol('local', wire)
        before_heads = protocol('heads', 'book', first)
        assert before_heads['state']['heads'] == 2 and not before_heads['state']['projection_safe']
        conflict_history = sql("SELECT revision_id,body_json FROM reader_revisions WHERE entity_kind='book' AND entity_key=? ORDER BY revision_id", (first,))
        remote_tag = revision(99992, shard=0, kind='tag', key='9' * 32, payload={'name': 'Received while a local book has conflicts'})
        wire = raw(remote_tag)
        entries['/dav/exreader-sync-v1/revisions/00/' + remote_tag['id'] + '-' + hashlib.sha256(wire).hexdigest() + '.json'] = wire
        scan();conflicted = ready(lambda s: s['session_state'] in ('4', '5'), seconds=180)
        assert conflicted['session_state'] == '4' and conflicted['seen'] == '52' and conflicted['bootstraps'] == '0', conflicted
        after_heads = protocol('heads', 'book', first)
        assert after_heads['state'] == before_heads['state'] and after_heads['heads'] == before_heads['heads']
        assert sql("SELECT revision_id,body_json FROM reader_revisions WHERE entity_kind='book' AND entity_key=? ORDER BY revision_id", (first,)) == conflict_history
        assert sql('SELECT book_key,title,author,sort_title,favorite FROM reader_books ORDER BY book_key') == baseline
        assert (staged / (first_digest + '.txt')).read_bytes() == originals[first_digest]
        assert sql('SELECT count(*) FROM reader_revisions WHERE revision_id=?', (remote_tag['id'],)) == [(1,)]
        assert sql('SELECT count(*) FROM reader_outbox') == [(0,)]
        report['conflict_fixture'] = {'book_key': first, 'original_sha256': first_digest, 'source_bytes': len(originals[first_digest]),
                                      'heads': before_heads['heads'], 'graph': before_heads['state'],
                                      'received_revision_id': remote_tag['id'], 'product_metadata_preserved': True,
                                      'bootstrap_or_projection_performed': False}
        record('verified_local_book_with_two_heads_stages_original_without_selecting_or_projecting_and_still_receives_remote_records')
        if args.receive_fixtures:
            from receive_checks import run_receive_checks
            report['received'] = run_receive_checks(locals())
            report.update(scope='GTK explicit SAFE receive, stable original import and public reading-state resolution',
                          remote_sdk_import_accepted=True, remote_projection_accepted=True)
        disconnect();before = len(requests);field('w', root.replace('/dav/', '/other/'));host.key('alt+a')
        refused = ready(lambda s: 'bound to its account and exact root' in s['notice'])
        assert refused['root'] == root and len(requests) == before
        field('w', root);record('changing_exact_root_is_refused_without_network_or_rebinding')
        first_file = next(staged.iterdir());retained = first_file.read_bytes();first_file.write_bytes(b'kept unknown original')
        before = len(requests);scan();refused = ready(lambda s: s['stage_status'] != '0')
        assert refused['session_present'] == '0' and len(requests) == before and first_file.read_bytes() == b'kept unknown original'
        first_file.write_bytes(retained);record('mismatching_existing_private_original_is_never_overwritten_and_prevents_network_start')
        pause_next();scan();assert blocked.wait(40)
        generation = int(account()['session_generation']);window();host.key('alt+F4')
        ready(lambda s: s['closing'] == '1' or (s['visible'] == '0' and s['session_present'] == '0'
              and int(s['closed_generation']) == generation), seconds=5)
        assert host.process.poll() is None
        release.set();window(False);ready(lambda s: s['session_present'] == '0')
        assert int(account()['closed_generation']) == generation
        open_account();assert ready()['has_password'] == '1'
        record('back_waits_asynchronously_for_closed_and_reopening_loads_credentials')
        window();host.key('alt+f');assert ready(lambda s: s['has_password'] == '0')['has_user'] == '0'
        close_account();host.close();host.launch();open_account()
        assert ready()['credential_status'] == '1' and ready()['has_password'] == '0' and ready()['id'] == identity
        record('forget_deletes_real_system_record_and_restart_keeps_nonsecret_binding_only')
        close_account();host.close()
        catalog = host.folder / 'profile/library.sqlite.product.sqlite';journal = Path(str(catalog) + '.commands.pending')
        seeded = subprocess.run([str(args.metadata_consumer.resolve()), 'group', str(catalog), str(journal), '1', '-',
                                 'Unfinished group', '-', '0', '0', 'stage'], capture_output=True, text=True, timeout=30)
        assert seeded.returncode == 0 and json.loads(seeded.stdout)['status'] == 0 and journal.exists()
        pending_bytes = journal.read_bytes();before = len(requests)
        host.launch();open_account();fill();scan()
        refused = ready(lambda s: s['stage_status'] != '0')
        assert 'earlier library edit recovery' in refused['notice'] and journal.read_bytes() == pending_bytes and len(requests) == before
        close_account();host.close()
        abandoned = subprocess.run([str(args.metadata_consumer.resolve()), 'abandon', str(catalog), str(journal)],
                                   capture_output=True, text=True, timeout=30)
        assert abandoned.returncode == 0 and json.loads(abandoned.stdout)['status'] == 0
        record('durable_pending_metadata_refuses_staging_without_overwriting_the_journal')
        config['account']['id'] = str(uuid.uuid4())
        with (host.folder / 'profile/account.ini').open('w') as output: config.write(output)
        host.launch();open_account();fill();before = len(requests);scan()
        mismatch = ready(lambda s: s['session_state'] == '5')
        assert mismatch['session_status'] == '4' and len(requests) == before
        disconnect();close_account();host.close()
        record('native_product_binding_rejects_a_different_uuid_before_any_http')
        dbus('/org/freedesktop/secrets', 'org.freedesktop.Secret.Service.Lock', "@ao ['" + collection.group(1) + "']")
        assert 'true' in dbus(collection.group(1), 'org.freedesktop.DBus.Properties.Get', 'org.freedesktop.Secret.Collection', 'Locked')
        host = new_host('unavailable');host.launch();open_account();assert ready()['credential_status'] == '2'
        fill(True);host.key('alt+a');unavailable = ready(lambda s: s['credential_status'] == '2' and s['bound'] == '1')
        assert 'credentials were not saved' in unavailable['notice'] and unavailable['session_present'] == '0'
        record('locked_real_secret_service_reports_unavailable_and_does_not_claim_credentials_saved')
        window();host.key('alt+h');scan();done = ready(lambda s: s['session_state'] in ('4', '5'), seconds=120)
        assert done['session_state'] == '4' and done['remember'] == '0'
        record('explicit_session_only_choice_still_scans_with_secure_storage_unavailable')
        disconnect();close_account();host.close();host.launch();open_account()
        assert ready()['credential_status'] == '2' and ready()['has_password'] == '0' and ready()['has_user'] == '0'
        record('session_only_credentials_are_absent_after_actual_process_restart')
        fill();pause_next();scan();assert blocked.wait(30)
        generation = int(account()['session_generation']);command('wmctrl', '-ic', hex(int(host.window)))
        deadline = time.monotonic() + 5
        while host.process.poll() is None and account()['closing'] != '1' and int(account()['closed_generation']) != generation:
            assert time.monotonic() < deadline, 'main close request was not observed'
            time.sleep(.05)
        release.set();close_code = host.process.wait(timeout=35);host.log.close()
        assert close_code == 0, {'close_exit': close_code, 'account': account()}
        assert int(account()['closed_generation']) == generation and account()['session_present'] == '0'
        record('application_close_defers_sdk_owner_shutdown_until_native_session_closed')
        (folder / 'requests.json').write_text(json.dumps(requests, indent=2))
        (folder / 'wire.json').write_text(json.dumps({path: hashlib.sha256(body).hexdigest() for path, body in entries.items()}, indent=2))
        key.unlink()
        values = [user.encode(), password.encode(), (user + ':' + password).encode(), authorization.encode()]
        forms = [f for value in values for f in (value, value.hex().encode(), base64.b64encode(value))]
        for path in folder.rglob('*'):
            if path.is_file():
                data = path.read_bytes();assert not any(form in data for form in forms), 'credential leak in ' + str(path.relative_to(folder))
        assert not any(form in body for form in forms for body in entries.values())
        record('credentials_and_authorization_are_absent_from_profiles_product_databases_wire_and_all_evidence')
        expected_checks = 52 if args.receive_fixtures else 27
        assert len(checks) == expected_checks, len(checks)
        report.update(accepted=True, count=len(checks), local_originals=52, credential_leak_hits=0,
                      actual_secret_service='temporary unlocked then locked GNOME collection', native_https=True)
    finally:
        release.set()
        for device in devices:
            if device.process and device.process.poll() is None:
                device.process.kill();device.process.wait(timeout=15)
            if device.log and not device.log.closed: device.log.close()
        server.shutdown();server.server_close();key.unlink(missing_ok=True)
        try:
            os.kill(int(keyring_pid), signal.SIGTERM)
        except ProcessLookupError:
            pass
        os.kill(int(bus_pid), signal.SIGTERM)
        shutil.rmtree(private, ignore_errors=True)
        os.environ.clear();os.environ.update(original_env)
        (folder / 'result.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({'accepted': report['accepted'], 'checks': len(checks), 'source_sha': os.environ['GITHUB_SHA'],
                      'run_id': os.environ['GITHUB_RUN_ID'], 'attempt': os.environ['GITHUB_RUN_ATTEMPT'],
                      'received': report.get('received')}))


if __name__ == '__main__':
    main()
