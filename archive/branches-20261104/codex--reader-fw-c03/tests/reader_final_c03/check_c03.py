# SPDX-License-Identifier: MIT
"""C03: account / import / sync fault-boundary review through installed public APIs.

Drives two unchanged installed consumers against hostile temporary-HTTPS WebDAV
fixtures created inside the job:

  * cloud-probe (EXReaderWebDAV + EXReaderCloudImport + SDK sideload) for
    redirect / path / TLS / credential / symlink / interruption / cancellation
    boundaries of the download -> stage -> import path;
  * resilience-consumer `step` (EXReaderSync + Revisions + product catalog) for
    corrupt wire, unknown version, hash/id mismatch, escaping listings, wrong
    account namespace and credential-less pulls.

Every case is a named entry in result.json. Failures are kept (accepted=false)
with the raw observation; nothing is converted into an expected rejection unless
the public contract says the input must be refused.
"""
import argparse
import base64
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import shutil
import socket
import sqlite3
import ssl
import struct
import subprocess
import sys
import threading
import time
import traceback
import uuid
from urllib.parse import unquote
from xml.sax.saxutils import escape

DAV = dict(zip(['OK', 'ARG', 'MEMORY', 'IO', 'TLS', 'HTTP', 'AUTH', 'CANCELLED', 'LIMIT', 'FORMAT', 'REDIRECT', 'EXISTS'], range(12)))
SECRET = uuid.uuid4().hex
AUTH = 'Basic ' + base64.b64encode(('c03-user:' + SECRET).encode()).decode()
WRONG_AUTH = 'Basic ' + base64.b64encode(('c03-user:wrong-' + SECRET).encode()).decode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def raw(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode()


def revision(number, shard=18, kind='tag', key='a' * 32, payload=None):
    return {'version': 1, 'id': '%02x%030x' % (shard, number), 'entity_kind': kind, 'entity_key': key,
            'operation': 'put', 'location_kind': 'none', 'parents': [],
            'payload': payload if payload is not None else {'name': '书架'}}


def trust(certificates):
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'fixture trust is cloud only'
    for certificate in certificates:
        subprocess.run(['sudo', 'cp', str(certificate), '/usr/local/share/ca-certificates/c03-' + certificate.name],
                       check=True, capture_output=True)
    subprocess.run(['sudo', 'update-ca-certificates'], check=True, capture_output=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--probe', type=Path, required=True)
    parser.add_argument('--resilience', type=Path, required=True)
    parser.add_argument('--fixtures', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'Cloud execution only'
    folder = args.output.resolve()
    folder.mkdir(parents=True)
    work = (folder.parent / 'c03-work').resolve()
    work.mkdir()
    probe, resilience = args.probe.resolve(), args.resilience.resolve()
    good_epub = (args.fixtures / 'sample.epub').read_bytes()
    other_epub = (args.fixtures / 'complex-text.epub').read_bytes()
    assert sha(good_epub) != sha(other_epub)

    certs = work / 'certificates'
    certs.mkdir()

    def certificate(name, host):
        key, cert = certs / (name + '.key'), certs / (name + '.crt')
        san = 'DNS:' + host + (',IP:127.0.0.1' if host == 'localhost' else '')
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1', '-keyout', str(key),
                        '-out', str(cert), '-subj', '/CN=' + host, '-addext', 'subjectAltName=' + san],
                       capture_output=True, check=True)
        return key, cert

    key, trusted = certificate('trusted', 'localhost')
    bad_key, untrusted = certificate('untrusted', 'localhost')
    wrong_key, wrong_host = certificate('wrong-host', 'wrong.example')
    trust((trusted, wrong_host))

    lock = threading.Lock()
    requests = []           # part A fixture trace (never contains credential values)
    sync_requests = []      # part B fixture trace
    ports = {}
    entries, directories = {}, {'/dav/'}
    redirects, stalls, extra_hrefs = {}, set(), {}

    def entry_xml(href, collection, size):
        return ('<d:response><d:href>' + escape(href) + '</d:href><d:propstat><d:prop><d:resourcetype>' +
                ('<d:collection/>' if collection else '') + '</d:resourcetype>' +
                ('' if collection else '<d:getcontentlength>' + str(size) + '</d:getcontentlength>') +
                '</d:prop><d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>')

    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def log_message(self, *unused):
            pass

        def send(self, code, data=b'', headers=None):
            try:
                self.send_response(code)
                for k, v in (headers or {}).items():
                    self.send_header(k, v)
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                if data:
                    self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError, ssl.SSLError, OSError):
                self.close_connection = True

        def note(self):
            role = self.server.role
            row = {'role': role, 'method': self.command, 'path': self.path, 'authorized': self.headers.get('Authorization') == AUTH,
                   'authorization_present': 'Authorization' in self.headers}
            with lock:
                (sync_requests if role == 'sync' else requests).append(row)
            return row

        def gate(self):
            row = self.note()
            if self.command in ('PROPFIND', 'PUT', 'MKCOL'):
                try:
                    self.rfile.read(int(self.headers.get('Content-Length', 0)))
                except (ConnectionResetError, ssl.SSLError, OSError):
                    pass
            if self.server.role == 'foreign':
                self.send(200, good_epub)
                return False
            if not row['authorized']:
                self.send(401, headers={'WWW-Authenticate': 'Basic realm="c03"'})
                return False
            return True

        def listing_body(self, path):
            rows = [entry_xml(path, True, 0)]
            if self.server.role == 'sync':
                with lock:
                    for name in sorted(directories):
                        if name != path and name.startswith(path) and '/' not in name[len(path):].rstrip('/'):
                            rows.append(entry_xml(name, True, 0))
                    for name in sorted(entries):
                        if name.startswith(path) and '/' not in name[len(path):]:
                            rows.append(entry_xml(name, False, len(entries[name])))
                    for href in extra_hrefs.get(path, []):
                        rows.append(entry_xml(href, False, 1))
            elif path == '/dav/hostile/':
                rows.append(entry_xml('/dav/hostile/good.epub', False, len(good_epub)))
                for href in ('/dav/hostile/../../etc/passwd', '/dav/hostile/%2e%2e/secret.epub', '/outside/a.epub',
                             'https://evil.example/dav/hostile/b.epub', '/dav/hostile/a%2fb.epub',
                             '/dav/hostile/a%5cb.epub'):
                    rows.append(entry_xml(href, False, 10))
            return ('<?xml version="1.0"?><d:multistatus xmlns:d="DAV:">' + ''.join(rows) + '</d:multistatus>').encode()

        def do_PROPFIND(self):
            if not self.gate():
                return
            path = unquote(self.path)
            if self.server.role == 'sync':
                with lock:
                    known = path in directories
                if not known:
                    return self.send(404)
            elif path not in ('/dav/', '/dav/hostile/'):
                return self.send(404)
            self.send(207, self.listing_body(path))

        def do_MKCOL(self):
            if self.gate():
                self.send(405)

        def do_PUT(self):
            if self.gate():
                self.send(403)

        def do_DELETE(self):
            if self.gate():
                self.send(403)

        def do_GET(self):
            if not self.gate():
                return
            path = self.path
            if self.server.role == 'sync':
                with lock:
                    where, body = redirects.get(path), entries.get(path)
                    stall = path in stalls
                if stall:
                    time.sleep(8)
                    return self.send(200, body or b'')
                if where:
                    return self.send(302, headers={'Location': where})
                return self.send(404) if body is None else self.send(200, body)
            if path == '/dav/books/good.epub' or path.startswith('/outside/'):
                return self.send(200, good_epub)
            if path == '/dav/err/other.epub':
                return self.send(200, other_epub)
            where = None
            if path == '/dav/err/redir-out.epub':
                where = '/outside/secret.epub'
            elif path == '/dav/err/loop-a.epub':
                where = '/dav/err/loop-b.epub'
            elif path == '/dav/err/loop-b.epub':
                where = '/dav/err/loop-a.epub'
            elif path == '/dav/err/redir-foreign.epub':
                where = 'https://127.0.0.1:%d/foreign/x.epub' % ports['foreign']
            elif path == '/dav/err/redir-http.epub':
                where = 'http://127.0.0.1:%d/dav/books/good.epub' % ports['foreign']
            elif re.fullmatch(r'/dav/err/chain-\d\.epub', path):
                n = int(path[-6])
                where = '/dav/err/chain-%d.epub' % (n + 1)
            if where:
                return self.send(302, headers={'Location': where})
            if path == '/dav/err/reset.epub':
                try:
                    self.send_response(200)
                    self.send_header('Content-Length', str(len(good_epub) * 4))
                    self.end_headers()
                    self.wfile.write(good_epub[:len(good_epub) // 2])
                    self.wfile.flush()
                    self.connection.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack('ii', 1, 0))
                    self.connection.close()
                except (OSError, ssl.SSLError):
                    pass
                self.close_connection = True
                return
            if path == '/dav/err/stall.epub':
                time.sleep(8)
                return self.send(200, good_epub)
            if path == '/dav/err/slow.epub':
                big = good_epub * 400
                try:
                    self.send_response(200)
                    self.send_header('Transfer-Encoding', 'chunked')
                    self.end_headers()
                    for offset in range(0, len(big), 65536):
                        chunk = big[offset:offset + 65536]
                        self.wfile.write(('%x\r\n' % len(chunk)).encode() + chunk + b'\r\n')
                        self.wfile.flush()
                        time.sleep(.01)
                    self.wfile.write(b'0\r\n\r\n')
                except (BrokenPipeError, ConnectionResetError, ssl.SSLError, OSError):
                    self.close_connection = True
                return
            self.send(404)

    servers = []
    for role, private_key, cert in (('main', key, trusted), ('foreign', key, trusted), ('untrusted', bad_key, untrusted),
                                    ('wrong', wrong_key, wrong_host), ('sync', key, trusted)):
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        server.daemon_threads = True
        server.role = role
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert, private_key)
        server.socket = context.wrap_socket(server.socket, server_side=True)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
        ports[role] = server.server_port
    root = 'https://127.0.0.1:%d/dav/' % ports['main']
    checks, failures, counter = [], [], [0]

    def record(name, **info):
        checks.append({'id': name, 'pass': True, **info})
        print('PASS ' + name, flush=True)

    def run_case(name, body):
        try:
            info = body()
            record(name, **(info or {}))
        except BaseException as exc:  # keep the raw failure; continue to collect evidence
            if isinstance(exc, KeyboardInterrupt):
                raise
            failures.append({'id': name, 'pass': False, 'error': repr(exc), 'trace': traceback.format_exc()[-1800:]})
            print('FAIL ' + name + ': ' + repr(exc), flush=True)

    # ---------------- part A: cloud-probe ----------------
    def spec_run(name, spec):
        counter[0] += 1
        case = folder / ('%03d-%s' % (counter[0], re.sub(r'[^A-Za-z0-9_.-]', '_', name)))
        case.mkdir()
        private_spec = work / ('spec-%03d.txt' % counter[0])
        private_spec.write_text(''.join('%s=%s\n' % (k, v) for k, v in spec.items()), encoding='utf-8', newline='\n')
        redacted = dict(spec)
        if 'auth' in redacted:
            redacted['auth'] = '<redacted>'
        (case / 'spec.txt').write_text(''.join('%s=%s\n' % (k, v) for k, v in redacted.items()), encoding='utf-8', newline='\n')
        started = time.monotonic()
        result = subprocess.run([str(probe), str(private_spec)], capture_output=True, timeout=170,
                                env=dict(os.environ, READER_CLOUD_FAIL_ALLOC='0'))
        (case / 'stdout.json').write_bytes(result.stdout)
        (case / 'stderr.log').write_bytes(result.stderr)
        assert result.returncode == 0, (name, result.returncode, result.stderr[-400:])
        value = json.loads(result.stdout.decode('utf-8'))
        value['_elapsed'] = time.monotonic() - started
        return value

    def transfer(name, resource, display='good.epub', auth=AUTH, url=root, import_=1, **extra):
        counter_next = counter[0] + 1
        staging = work / ('staging-%03d' % counter_next)
        staging.mkdir()
        library = work / ('library-%03d.db' % counter_next)
        spec = {'cmd': 'transfer', 'root': url, 'auth': auth, 'resource': resource, 'name': display,
                'staging': staging, 'library': library, 'expected': 0, 'import': import_}
        spec.update(extra)
        before = len(requests)
        value = spec_run(name, spec)
        value['_staging'], value['_library'], value['_new'] = staging, library, requests[before:]
        assert not list(staging.glob('.exr-webdav-*')), (name, 'temporary download file leaked')
        return value

    def refused(value, name):
        assert value.get('download_status') not in (None, 'ok') or value.get('create', 0) != 0, (name, value)
        assert value.get('staged', 0) == 0, (name, value)
        assert 'committed' not in value or value['committed'] == 0, (name, value)
        assert not list(value['_staging'].iterdir()), (name, 'staging file leaked')
        assert not value['_library'].exists(), (name, 'library opened/written on a refused transfer')

    def a_control():
        value = transfer('control', 'books/good.epub')
        assert value['download_status'] == 'ok' and value['import_status'] == 'ok' and value['committed'] == 1, value
        assert value['staged_sha256'] == sha(good_epub) and re.fullmatch(r'cloud-[0-9a-f]{16}\.epub', value['staged_file'])
        assert not list(value['_staging'].iterdir())
        return {'book_id': value['book_id'], 'sha256': sha(good_epub)}

    run_case('control_valid_download_and_import_over_verified_tls', a_control)

    TRAVERSAL = ['../x.epub', 'books/../../x.epub', 'books/%2e%2e/x.epub', 'books/%2E%2E%2Fx.epub', 'books/a%2fb.epub',
                 'books/a%5cb.epub', 'books\\x.epub', 'books/a%00.epub', 'https://evil.example/x.epub',
                 'books/x.epub?a=1', 'books/x.epub#f', 'books/./x.epub']

    def a_traversal():
        seen = {}
        for resource in TRAVERSAL:
            value = transfer('traversal', resource, display='safe.epub')
            refused(value, resource)
            assert not value['_new'], (resource, 'ambiguous resource reached the network', value['_new'])
            seen[resource] = value.get('download_status', 'create-' + str(value.get('create')))
        return {'refused_before_network': seen}

    run_case('resource_path_traversal_and_ambiguous_encodings_refused_before_any_request', a_traversal)

    def a_display_name():
        names = ['../../escape.epub', 'a/b/escape.epub', 'a\\b\\escape.epub', 'CON.epub', '..']
        used = []
        for display in names:
            value = transfer('displayname', 'books/good.epub', display=display, format='EPUB')
            assert value['download_status'] == 'ok' and value['import_status'] == 'ok', (display, value)
            assert re.fullmatch(r'cloud-[0-9a-f]{16}\.epub', value['staged_file']) and value['staged_name'] == display, value
            assert not list(value['_staging'].iterdir())
            used.append(value['staged_file'])
        stray = [p for base in (folder.parent, work, folder) for p in base.glob('**/escape*') if p.is_file()]
        assert not stray, stray
        return {'staged_files_are_generated_names': used}

    run_case('remote_display_name_never_becomes_a_local_path', a_display_name)

    def a_symlink():
        target = work / 'symlink-target'
        target.mkdir()
        link = work / 'staging-link'
        os.symlink(target, link, target_is_directory=True)
        library = work / 'library-symlink.db'
        value = spec_run('symlink_staging', {'cmd': 'transfer', 'root': root, 'auth': AUTH, 'resource': 'books/good.epub',
                                             'name': 'good.epub', 'staging': link, 'library': library, 'expected': 0})
        assert value.get('download_status') not in (None, 'ok') and value.get('staged', 0) == 0, value
        assert not list(target.iterdir()), ('symlinked staging directory was written through', list(target.iterdir()))
        assert not library.exists()
        return {'download_status': value['download_status'], 'download_webdav': value.get('download_webdav')}

    run_case('symlinked_staging_directory_is_not_written_through', a_symlink)

    def a_credentials():
        out = {}
        for label, auth in (('missing', ''), ('wrong_password', WRONG_AUTH)):
            value = transfer('auth-' + label, 'books/good.epub', auth=auth)
            refused(value, label)
            assert value['download_webdav'] == DAV['AUTH'] and value['download_http'] == 401, value
            assert all(not r['authorized'] for r in value['_new']), value['_new']
            out[label] = value['download_http']
        return out

    run_case('missing_or_wrong_credentials_get_401_without_any_product_write', a_credentials)

    def a_redirects():
        out = {}
        before_foreign = len([r for r in requests if r['role'] == 'foreign'])
        for label, resource in (('outside_root_same_origin', 'err/redir-out.epub'), ('loop', 'err/loop-a.epub'),
                                ('budget', 'err/chain-0.epub'), ('foreign_origin', 'err/redir-foreign.epub'),
                                ('https_to_http', 'err/redir-http.epub')):
            value = transfer('redirect-' + label, resource)
            refused(value, label)
            assert value['download_webdav'] == DAV['REDIRECT'], (label, value)
            out[label] = value['download_webdav']
        assert not [r for r in requests if r['path'].startswith('/outside/')], 'redirect left the configured collection'
        assert len([r for r in requests if r['role'] == 'foreign']) == before_foreign, 'foreign origin contacted'
        assert all(not r['authorization_present'] for r in requests if r['role'] == 'foreign')
        return out

    run_case('redirects_outside_root_loop_budget_foreign_origin_and_downgrade_are_refused', a_redirects)

    def a_tls():
        out = {}
        for label, role in (('untrusted_certificate', 'untrusted'), ('hostname_mismatch', 'wrong')):
            value = transfer('tls-' + label, 'books/good.epub', url='https://127.0.0.1:%d/dav/' % ports[role])
            refused(value, label)
            assert value['download_webdav'] == DAV['TLS'], (label, value)
            out[label] = value['download_webdav']
        assert not [r for r in requests if r['role'] in ('untrusted', 'wrong')], 'a request was served over failed TLS'
        return out

    run_case('untrusted_certificate_and_hostname_mismatch_fail_closed_with_no_http_request', a_tls)

    def a_interruptions():
        out = {}
        value = transfer('net-reset', 'err/reset.epub')
        refused(value, 'reset')
        out['reset_webdav'] = value['download_webdav']
        value = transfer('net-stall', 'err/stall.epub', timeout=2000)
        refused(value, 'stall')
        assert value['_elapsed'] < 40, value['_elapsed']
        out['stall_webdav'] = value['download_webdav']
        out['stall_seconds'] = round(value['_elapsed'], 2)
        value = transfer('net-cancel', 'err/slow.epub', cancel_net=65536)
        refused(value, 'cancel')
        assert value['download_status'] == 'cancelled', value
        return out

    run_case('connection_reset_stall_and_cancel_leave_no_partial_file_library_or_row', a_interruptions)

    def a_wrong_original():
        value = transfer('wrong-original', 'err/other.epub', import_=0)
        assert value['download_status'] == 'ok' and value['staged'] == 1, value
        assert value['staged_sha256'] == sha(other_epub) and value['staged_sha256'] != sha(good_epub)
        # The host's recorded identity is good_epub: it must discard, not import.
        discarded = transfer('wrong-original-discard', 'err/other.epub', tamper='discard')
        assert discarded['staged'] == 1 and discarded['discarded'] == 1 and discarded['file_after_discard'] == 0, discarded
        assert not list(discarded['_staging'].iterdir()) and not discarded['_library'].exists()
        return {'served_sha256': sha(other_epub), 'recorded_sha256': sha(good_epub)}

    run_case('server_serving_a_different_original_is_detected_by_hash_and_discarded_unimported', a_wrong_original)

    def a_unsupported():
        value = transfer('unsupported', 'books/good.epub', display='payload.exe')
        assert value.get('download_status') != 'ok' or value.get('import_status') != 'ok', value
        assert value.get('committed', 0) == 0 and not list(value['_staging'].iterdir()), value
        return {'download_status': value.get('download_status'), 'import_status': value.get('import_status')}

    run_case('unsupported_extension_never_commits_a_book', a_unsupported)

    def a_hostile_listing():
        spec = {'cmd': 'list', 'root': root, 'auth': AUTH, 'resource': 'hostile/'}
        before = len(requests)
        value = spec_run('hostile-listing', spec)
        names = [e['resource'] for e in value.get('entries', [])]
        unsafe = [n for n in names if n.startswith('/') or '..' in n or '://' in n or '\\' in n or '%2f' in n.lower() or '%5c' in n.lower()]
        assert not unsafe, ('listing returned an escaping resource', unsafe)
        assert not [r for r in requests[before:] if r['path'].startswith('/outside/')]
        return {'list_status': value['list_status'], 'accepted_resources': names}

    run_case('hostile_listing_hrefs_cannot_escape_the_configured_collection', a_hostile_listing)

    # ---------------- part B: sync step ----------------
    sync_base = work / 'sync'
    sync_base.mkdir()

    def device(name):
        space = name
        base = sync_base / name
        base.mkdir()
        (base / 'cache').mkdir()
        (base / 'originals').mkdir()
        with lock:
            for parts in (space, space + '/exreader-sync-v1', space + '/exreader-sync-v1/revisions',
                          space + '/exreader-sync-v1/revisions/12', space + '/exreader-sync-v1/objects'):
                directories.add('/' + parts + '/')
        return {'space': space, 'base': base, 'db': base / 'product.sqlite', 'cache': base / 'cache',
                'originals': base / 'originals', 'url': 'https://127.0.0.1:%d/%s/' % (ports['sync'], space)}

    def rev_path(spec, value_id, body_sha):
        return '/' + spec['space'] + '/exreader-sync-v1/revisions/' + value_id[:2] + '/' + value_id + '-' + body_sha + '.json'

    def publish(spec, value_id, body, name_sha=None):
        path = rev_path(spec, value_id, name_sha or sha(body))
        with lock:
            entries[path] = body
        return path

    def counts(spec):
        if not spec['db'].exists():
            return (0, 0)
        with sqlite3.connect(str(spec['db'])) as database:
            return tuple(database.execute('SELECT (SELECT count(*) FROM reader_revisions),(SELECT count(*) FROM reader_outbox)').fetchone())

    def step(spec, auth=AUTH, timeout=15000, shard=18):
        env = dict(os.environ)
        env.pop('READER_TEST_AUTH', None)
        if auth is not None:
            env['READER_TEST_AUTH'] = auth
        before = len(sync_requests)
        result = subprocess.run([str(resilience), 'step', spec['url'], str(spec['db']), str(spec['cache']), str(spec['originals']),
                                 str(shard), '-', '100', str(timeout)], env=env, capture_output=True, encoding='utf-8', timeout=240)
        assert result.returncode == 0, (result.returncode, result.stderr[-400:])
        value = json.loads(result.stdout)
        value['_requests'] = sync_requests[before:]
        (spec['base'] / ('step-%d.json' % len(list(spec['base'].glob('step-*.json'))))).write_text(
            json.dumps({k: v for k, v in value.items() if k != '_requests'}), encoding='utf-8')
        return value

    def no_remote_write(value):
        bad = [r for r in value['_requests'] if r['method'] not in ('PROPFIND', 'GET')]
        assert not bad, ('unannounced remote write/mutation', bad)

    def untouched_local(spec, expect):
        assert counts(spec) == expect, ('local history/outbox changed', counts(spec), expect)
        assert not list(spec['cache'].iterdir()) and not list(spec['originals'].iterdir()), 'private file created by a refused pull'

    def b_control():
        spec = device('control')
        tag = revision(1)
        publish(spec, tag['id'], raw(tag))
        value = step(spec)
        assert value['status'] == 0 and value['pulled'] == 1, value
        assert counts(spec) == (1, 0)
        no_remote_write(value)
        return {'status': value['status'], 'pulled': value['pulled']}

    run_case('sync_control_valid_revision_is_pulled_over_verified_tls', b_control)

    def b_bad_wire(label, make):
        def body():
            spec = device(label)
            path = make(spec)
            value = step(spec)
            assert value['pulled'] == 0, ('a hostile revision was accepted', value)
            untouched_local(spec, (0, 0))
            no_remote_write(value)
            fetched = any(r['method'] == 'GET' and r['path'] == path for r in value['_requests'])
            assert any(r['method'] == 'PROPFIND' for r in value['_requests']), 'listing never requested'
            return {'status': value['status'], 'revision_code': value['revision_code'], 'dav_code': value['dav_code'], 'body_fetched': fetched}
        return body

    def corrupt(spec):
        data = b'{"version":1,"id":"12000000000000000000000000000001","entity_kind":'
        return publish(spec, '12' + '0' * 29 + '1', data)

    def unknown_version(spec):
        tag = revision(2)
        tag['version'] = 2
        return publish(spec, tag['id'], raw(tag))

    def name_hash_mismatch(spec):
        tag = revision(3)
        return publish(spec, tag['id'], raw(tag), name_sha=sha(b'not the body'))

    def id_mismatch(spec):
        tag = revision(4)
        return publish(spec, '12' + '0' * 29 + '9', raw(tag))

    def unknown_field(spec):
        tag = revision(5)
        tag['unexpected'] = True
        return publish(spec, tag['id'], raw(tag))

    def oversize(spec):
        tag = revision(6, payload={'name': 'x' * (1024 * 1024 + 8)})
        return publish(spec, tag['id'], raw(tag))

    for label, make in (('corrupt_json', corrupt), ('unknown_version', unknown_version), ('body_hash_differs_from_name', name_hash_mismatch),
                        ('id_differs_from_name', id_mismatch), ('unknown_field', unknown_field), ('oversize_revision', oversize)):
        run_case('hostile_remote_wire_' + label + '_is_refused_without_local_or_remote_write', b_bad_wire(label, make))

    def b_listing_escape():
        spec = device('listing_escape')
        prefix = '/' + spec['space'] + '/exreader-sync-v1/revisions/12/'
        extra_hrefs[prefix] = [prefix + '../../../../outside/' + '12' + '0' * 29 + '1-' + '0' * 64 + '.json',
                               prefix + '%2e%2e/%2e%2e/outside.json', 'https://evil.example/x-' + '0' * 64 + '.json']
        value = step(spec)
        assert not [r for r in sync_requests if r['path'].startswith('/outside') or 'evil.example' in r['path']], 'escaping listing href was fetched'
        untouched_local(spec, (0, 0))
        no_remote_write(value)
        return {'status': value['status'], 'requests': len(value['_requests'])}

    run_case('hostile_sync_listing_hrefs_are_never_fetched_outside_the_account_prefix', b_listing_escape)

    def b_redirect():
        spec = device('redirect')
        tag = revision(7)
        path = rev_path(spec, tag['id'], sha(raw(tag)))
        with lock:
            entries[path] = raw(tag)
            redirects[path] = '/outside-secret.json'
        value = step(spec)
        assert value['pulled'] == 0, value
        assert not [r for r in sync_requests if r['path'].startswith('/outside')], 'redirect target outside root was requested'
        untouched_local(spec, (0, 0))
        no_remote_write(value)
        return {'status': value['status'], 'dav_code': value['dav_code']}

    run_case('sync_get_redirect_outside_root_is_not_followed', b_redirect)

    def b_credentials():
        spec = device('no_credentials')
        tag = revision(8)
        publish(spec, tag['id'], raw(tag))
        value = step(spec, auth=None)
        assert value['status'] != 0 and value['dav_code'] == DAV['AUTH'] and value['http_status'] == 401, value
        assert all(not r['authorization_present'] for r in value['_requests']), value['_requests']
        assert not [r for r in value['_requests'] if r['method'] == 'GET'], 'revision body fetched without credentials'
        untouched_local(spec, (0, 0))
        wrong = step(spec, auth=WRONG_AUTH)
        assert wrong['status'] != 0 and wrong['http_status'] == 401, wrong
        untouched_local(spec, (0, 0))
        return {'missing_http': value['http_status'], 'wrong_http': wrong['http_status']}

    run_case('sync_without_or_with_wrong_credentials_gets_401_and_pulls_nothing', b_credentials)

    def b_stall():
        spec = device('stall')
        tag = revision(9)
        path = publish(spec, tag['id'], raw(tag))
        with lock:
            stalls.add(path)
        started = time.monotonic()
        value = step(spec, timeout=1500)
        elapsed = time.monotonic() - started
        assert value['status'] != 0 and value['pulled'] == 0 and elapsed < 40, (value, elapsed)
        untouched_local(spec, (0, 0))
        return {'status': value['status'], 'elapsed_seconds': round(elapsed, 2)}

    run_case('sync_network_stall_times_out_with_no_local_write', b_stall)

    def b_accounts():
        a, b = device('acct_a'), device('acct_b')
        tag = revision(10)
        publish(a, tag['id'], raw(tag))
        first = step(a)
        assert first['status'] == 0 and counts(a) == (1, 0), first
        empty = step(b)
        assert empty['status'] == 0 and empty['pulled'] == 0 and counts(b) == (0, 0), empty
        assert all(r['path'].startswith('/acct_b/') for r in empty['_requests']), empty['_requests']
        # Account A's database pointed at account B's (empty) namespace must keep its history.
        cross = dict(a, url=b['url'])
        crossed = step(cross)
        assert counts(a) == (1, 0), ('local history changed by a foreign empty namespace', counts(a))
        assert all(r['path'].startswith('/acct_b/') for r in crossed['_requests'])
        no_remote_write(crossed)
        return {'a_pull': first['pulled'], 'b_pull': empty['pulled'], 'cross_status': crossed['status']}

    run_case('account_namespaces_are_isolated_and_empty_foreign_namespace_never_deletes_history', b_accounts)

    # ---------------- evidence, secret scan, report ----------------
    for server in servers:
        server.shutdown()
        server.server_close()
    shutil.copytree(sync_base, folder / 'sync', ignore=shutil.ignore_patterns('*.sqlite-wal', '*.sqlite-shm'), dirs_exist_ok=True)
    (folder / 'requests-cloud.json').write_text(json.dumps(requests, indent=1), encoding='utf-8')
    (folder / 'requests-sync.json').write_text(json.dumps(sync_requests, indent=1), encoding='utf-8')
    for private_key in certs.glob('*.key'):
        private_key.unlink()
    try:
        shutil.copytree(certs, folder / 'certificates')
    except OSError:
        pass
    leaked = []
    for path in folder.rglob('*'):
        if path.is_file() and path.suffix in ('.json', '.log', '.txt'):
            text = path.read_text(encoding='utf-8', errors='replace')
            if AUTH in text or SECRET in text or base64.b64encode(('c03-user:' + SECRET).encode()).decode() in text:
                leaked.append(str(path.relative_to(folder)))
    if leaked:
        failures.append({'id': 'no_credentials_in_evidence', 'pass': False, 'error': 'credential text found in ' + str(leaked)})
    else:
        record('no_credentials_in_evidence')

    report = {'accepted': not failures, 'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
              'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'platform': sys.platform, 'checks': checks, 'count': len(checks),
              'failures': failures, 'probe_sha256': sha(probe.read_bytes()), 'resilience_consumer_sha256': sha(resilience.read_bytes()),
              'tls': 'native certificate + hostname verification against a runner-trusted temporary CA; no verification disabled',
              'scope': 'Linux only; installed public WebDAV/CloudImport/Sync APIs against local hostile fixtures; no device, '
                       'no real cloud provider',
              'pending': ['platform credential store locked/denied state (reader-credentials workflow owns it; needs OS keyring)',
                          'staged-file symlink swap between download and import (needs a new native probe)',
                          'Windows/macOS/Android/Apple execution', 'real third-party WebDAV servers (reader-webdav-interop owns them)'],
              'complete_product': False}
    (folder / 'result.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps({'accepted': report['accepted'], 'checks': len(checks), 'failures': len(failures)}))
    return 0 if not failures else 1


if __name__ == '__main__':
    sys.exit(main())
