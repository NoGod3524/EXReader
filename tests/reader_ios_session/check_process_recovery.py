# SPDX-License-Identifier: MIT
"""Actions-only UIKit process termination, retained outbox and nonblocking close."""
import argparse
import base64
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import signal
import sqlite3
import ssl
import subprocess
import sys
import threading
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'reader_sync'))
from check_sync import raw, revision
from cloud_native import trust_fixture_certificates


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--revision-consumer', required=True, type=Path)
    parser.add_argument('--native-binary', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    out = args.output.resolve(); out.mkdir(parents=True)
    docs = Path(os.environ['EXR_DAV_IOS_CONTAINER']) / 'Documents'
    work = docs / 'termination-work'; work.mkdir()
    for name in ('cache', 'originals'): (work / name).mkdir()
    database, cache, originals = work / 'product.sqlite', work / 'cache', work / 'originals'
    certs = out / 'certificates'; certs.mkdir()
    key, cert = certs / 'server.key', certs / 'server.crt'
    subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
                    '-keyout', str(key), '-out', str(cert), '-subj', '/CN=localhost',
                    '-addext', 'subjectAltName=DNS:localhost,IP:127.0.0.1'], check=True, capture_output=True)
    trust_fixture_certificates((cert,), 'ios-process-')
    secret = uuid.uuid4().hex
    authorization = 'Basic ' + base64.b64encode(('ios-session:' + secret).encode()).decode()
    account = str(uuid.uuid4())
    entries, directories, requests, checks, events = {}, {'/dav/'}, [], [], []
    gate, release = threading.Event(), threading.Event()
    flags = {'hold_get': True, 'hold_list': False}
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'
        def log_message(self, *unused): pass
        def send(self, status, data=b''):
            self.send_response(status); self.send_header('Content-Length', str(len(data)))
            self.send_header('Connection', 'close'); self.end_headers(); self.close_connection = True
            try: self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError, ssl.SSLError): pass
        def allowed(self):
            authenticated = self.headers.get('Authorization') == authorization
            with lock: requests.append({'method': self.command, 'path': self.path, 'authenticated': authenticated})
            if not authenticated: self.send(401)
            return authenticated
        def do_MKCOL(self):
            if not self.allowed(): return
            with lock:
                exists = self.path in directories; directories.add(self.path)
            self.send(405 if exists else 201)
        def do_PUT(self):
            body = self.rfile.read(int(self.headers['Content-Length']))
            if not self.allowed(): return
            assert self.headers.get('If-None-Match') == '*'
            with lock:
                exists = self.path in entries
                if not exists: entries[self.path] = body
                requests[-1]['status'] = 412 if exists else 201
            self.send(412 if exists else 201)
        def do_GET(self):
            if not self.allowed(): return
            if flags['hold_get'] and '/revisions/' in self.path:
                flags['hold_get'] = False; gate.set(); release.wait(15)
            with lock: data = entries.get(self.path)
            self.send(404 if data is None else 200, data or b'')
        def do_PROPFIND(self):
            self.rfile.read(int(self.headers.get('Content-Length', 0)))
            if not self.allowed(): return
            assert self.headers.get('Depth') == '1'
            if flags['hold_list'] and '/revisions/' in self.path:
                flags['hold_list'] = False; gate.set(); release.wait(15)
            with lock:
                exists = self.path in directories
                children = [(p, True, 0) for p in directories if p.startswith(self.path) and
                            (p == self.path or '/' not in p[len(self.path):].rstrip('/'))]
                children += [(p, False, len(data)) for p, data in entries.items() if p.startswith(self.path) and '/' not in p[len(self.path):]]
            if not exists: self.send(404); return
            rows = ['<d:response><d:href>' + path + '</d:href><d:propstat><d:prop><d:resourcetype>' +
                    ('<d:collection/>' if directory else '') + '</d:resourcetype><d:getcontentlength>' + str(size) +
                    '</d:getcontentlength></d:prop><d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>'
                    for path, directory, size in sorted(children)]
            self.send(207, ('<d:multistatus xmlns:d="DAV:">' + ''.join(rows) + '</d:multistatus>').encode())

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler); server.daemon_threads = True
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); tls.load_cert_chain(cert, key)
    server.socket = tls.wrap_socket(server.socket, server_side=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    root = 'https://127.0.0.1:' + str(server.server_port) + '/dav/'
    udid, bundle = os.environ['EXR_DAV_IOS_UDID'], 'org.exreader.session.probe'

    def record(name):
        assert name not in checks; checks.append(name); print('PASS ' + name, flush=True)
    def counts():
        with sqlite3.connect(database) as db:
            return db.execute('SELECT (SELECT count(*) FROM reader_revisions),(SELECT count(*) FROM reader_outbox),(SELECT count(*) FROM reader_tags)').fetchone()
    def wait_for(predicate, seconds=15):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            value = predicate()
            if value: return value
            time.sleep(.02)
        raise AssertionError('bounded iOS lifecycle observation expired')

    class App:
        def __init__(self):
            subprocess.run(['xcrun', 'simctl', 'terminate', udid, bundle], capture_output=True)
            for name in ('commands.fifo', 'responses.fifo', 'completion.json', 'live-ticks.json'):
                (docs / name).unlink(missing_ok=True)
            os.mkfifo(docs / 'commands.fifo', 0o600); os.mkfifo(docs / 'responses.fifo', 0o600)
            request = {'mode': 'session-controls', 'authorization': authorization,
                       'arguments': ['ReaderSessionProbe', root, str(database), str(cache), str(originals), account, '3000']}
            (docs / 'request.json').write_text(json.dumps(request), encoding='utf-8')
            launched = subprocess.run(['xcrun', 'simctl', 'launch', udid, bundle], check=True, capture_output=True, text=True)
            self.pid = int(re.search(r':\s*(\d+)\s*$', launched.stdout).group(1))
            self.read_fd = os.open(docs / 'responses.fifo', os.O_RDONLY | os.O_NONBLOCK)
            self.write_fd = None; self.buffer = b''
            def connect():
                try: self.write_fd = os.open(docs / 'commands.fifo', os.O_WRONLY | os.O_NONBLOCK); return True
                except OSError: return False
            wait_for(connect)
            self.created = self.line(15)
            events.append({'event': 'launch', 'pid': self.pid, 'create': self.created['create']})
            assert self.created['create'] == 0 and not (docs / 'request.json').exists()
        def line(self, timeout=3):
            deadline = time.monotonic() + timeout
            while b'\n' not in self.buffer:
                assert time.monotonic() < deadline, 'native UIKit control response deadline'
                os.kill(self.pid, 0)
                try: self.buffer += os.read(self.read_fd, 65536)
                except BlockingIOError: pass
                time.sleep(.005)
            row, self.buffer = self.buffer.split(b'\n', 1)
            value = json.loads(row); events.append({'event': 'response', 'pid': self.pid, 'value': value})
            return value
        def command(self, command):
            os.write(self.write_fd, (command + '\n').encode()); return self.line()
        def state(self, expected, timeout=90):
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                value = self.command('observe')
                if value['state'] == expected: return value
                assert value['state'] not in (5, 7), value
                time.sleep(.02)
            raise AssertionError(('iOS state deadline', expected, value))
        def ticks(self):
            return wait_for(lambda: json.loads((docs / 'live-ticks.json').read_text())['main_thread_ticks']
                            if (docs / 'live-ticks.json').is_file() else False)
        def fds_close(self):
            if self.write_fd is not None: os.close(self.write_fd); self.write_fd = None
            if self.read_fd is not None: os.close(self.read_fd); self.read_fd = None
        def close(self):
            assert self.command('close')['code'] == 0
            self.state(7, 10)
            assert self.command('destroy')['code'] == 0
            done = wait_for(lambda: json.loads((docs / 'completion.json').read_text()) if (docs / 'completion.json').is_file() else None)
            assert done['code'] == 0 and done['main_thread_ticks'] > 0
            events.append({'event': 'closed', 'pid': self.pid, **done}); self.fds_close()

    apps = []
    try:
        wire = raw(revision(991, key='d' * 32)); seed = work / 'seed.json'; seed.write_bytes(wire)
        seeded = subprocess.run([str(args.revision_consumer.resolve()), 'local', str(database), str(seed)], capture_output=True, text=True, timeout=20)
        assert seeded.returncode == 0 and json.loads(seeded.stdout)['status'] == 0
        assert counts() == (1, 1, 0)
        first = App(); apps.append(first)
        assert first.command('start')['code'] == 0 and gate.wait(8)
        assert counts() == (1, 1, 0) and list(entries.values()) == [wire]
        record('native_put_commits_before_get_verification_without_premature_ack')
        ticks = first.ticks(); time.sleep(.25)
        assert first.ticks() > ticks and first.command('observe')['state'] == 1
        assert first.command('destroy')['code'] == 2 and first.command('start')['code'] == 2
        record('uikit_main_loop_and_nonblocking_controls_survive_a_blocked_native_request')
        os.kill(first.pid, signal.SIGKILL)
        def absent():
            try: os.kill(first.pid, 0); return False
            except ProcessLookupError: return True
        wait_for(absent); first.fds_close(); release.set()
        events.append({'event': 'SIGKILL', 'pid': first.pid})
        assert counts() == (1, 1, 0)
        record('actual_uikit_process_sigkill_preserves_history_and_unacked_outbox')
        second = App(); apps.append(second)
        assert second.pid != first.pid and second.command('start')['code'] == 0
        done = second.state(4)
        assert done['completed_shards'] == 256 and done['sweeps'] == 1 and not done['full_library_complete']
        assert counts() == (1, 0, 0) and list(entries.values()) == [wire]
        assert any(r.get('status') == 412 for r in requests)
        record('same_account_new_process_retries_immutable_put_verifies_get_and_acks_once')
        second.close()
        record('uikit_close_observes_closed_before_destroy_and_keeps_the_main_loop_live')
        third = App(); apps.append(third)
        release.clear(); gate.clear(); flags['hold_list'] = True
        assert third.command('start')['code'] == 0 and gate.wait(8)
        before = third.ticks(); began = time.monotonic()
        assert third.command('close')['code'] == 0 and time.monotonic() - began < 1
        time.sleep(.25); assert third.ticks() > before
        release.set(); third.state(7, 10)
        assert third.command('destroy')['code'] == 0
        completion = wait_for(lambda: json.loads((docs / 'completion.json').read_text()) if (docs / 'completion.json').is_file() else None)
        assert completion['code'] == 0 and completion['main_thread_ticks'] > before
        third.fds_close()
        record('close_during_native_transfer_cancels_asynchronously_and_joins_only_after_closed')
        assert all(r['authenticated'] for r in requests)
        binding = Path(str(database) + '.sync-account').read_bytes()
        assert secret.encode() not in binding and authorization.encode() not in binding
        assert counts() == (1, 0, 0)
        record('process_recovery_never_persists_authorization_or_projects_remote_metadata')
        report = {'accepted': True, 'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
                  'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'execution_platform': 'ios-simulator-uikit',
                  'checks': checks, 'count': len(checks), 'events': events, 'native_processes': len(apps),
                  'consumer_sha256': hashlib.sha256(args.native_binary.read_bytes()).hexdigest(),
                  'physical_device_execution': False, 'host_ui_accepted': False, 'six_platform_accepted': False, 'complete_product': False}
        for path in work.rglob('*'):
            if path.is_file():
                data = path.read_bytes(); assert secret.encode() not in data and authorization.encode() not in data
        (out / 'result.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        (out / 'native-requests.json').write_text(json.dumps(requests, indent=2), encoding='utf-8')
        print(json.dumps(report), flush=True)
    finally:
        release.set()
        for app in apps: app.fds_close()
        subprocess.run(['xcrun', 'simctl', 'terminate', udid, bundle], capture_output=True)
        (docs / 'request.json').unlink(missing_ok=True)
        if (docs / 'fault-stderr.log').is_file():
            data = (docs / 'fault-stderr.log').read_bytes()
            assert secret.encode() not in data and authorization.encode() not in data
            (out / 'fault-stderr.log').write_bytes(data)
        server.shutdown(); server.server_close()


if __name__ == '__main__': main()
