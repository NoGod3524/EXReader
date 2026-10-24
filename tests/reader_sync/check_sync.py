# SPDX-License-Identifier: MIT
"""Cloud-only real native TLS two-client immutable sync acceptance."""
import argparse
import base64
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import sqlite3
import ssl
import subprocess
import sys
import threading
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'webdav'))
from cloud_native import trust_fixture_certificates

AUTH = 'Basic ' + base64.b64encode(b'sync-user:sync-private-fixture').decode()
DISABLED = (1 << 64) - 1


def raw(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode()


def revision(number, shard=16, kind='tag', key='1' * 32, payload=None, parents=(), operation='put', mode='none'):
    return {'version': 1, 'id': '%02x%030x' % (shard, number), 'entity_kind': kind, 'entity_key': key,
            'operation': operation, 'location_kind': mode, 'parents': list(parents),
            'payload': None if operation == 'delete' else (payload if payload is not None else {'name': '书架'})}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--consumer', type=Path, required=True)
    p.add_argument('--revision-consumer', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    folder = a.output.resolve()
    folder.mkdir(parents=True)
    consumer, protocol = a.consumer.resolve(), a.revision_consumer.resolve()
    env = dict(os.environ, READER_TEST_AUTH=AUTH)
    certificates = folder / 'certificates'
    certificates.mkdir()

    def cert(name, host):
        key, certificate = certificates / (name + '.key'), certificates / (name + '.crt')
        san = 'DNS:' + host + (',IP:127.0.0.1' if host == 'localhost' else '')
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
                        '-keyout', str(key), '-out', str(certificate), '-subj', '/CN=' + host,
                        '-addext', 'subjectAltName=' + san], check=True, capture_output=True)
        return key, certificate

    trusted_key, trusted = cert('trusted', 'localhost')
    wrong_key, wrong = cert('wrong-host', 'wrong.example')
    untrusted_key, untrusted = cert('untrusted', 'localhost')
    trust_fixture_certificates((trusted, wrong), 'exr-sync-')
    entries, directories, requests, checks = {}, set(), [], []
    lock = threading.Lock()
    flags = {'disconnect': '', 'pause_get': '', 'redirect_write': False, 'redirect_put': False}
    committed, release = threading.Event(), threading.Event()
    foreign_port = 0

    def xml_entry(path, directory=False):
        size = 0 if directory else len(entries[path])
        return ('<d:response><d:href>' + path + '</d:href><d:propstat><d:prop><d:resourcetype>' +
                ('<d:collection/>' if directory else '') + '</d:resourcetype><d:getcontentlength>' + str(size) +
                '</d:getcontentlength><d:getetag>&quot;fixture&quot;</d:getetag></d:prop>' +
                '<d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>')

    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def log_message(self, *unused):
            pass

        def send(self, code, data=b'', headers=None):
            self.send_response(code)
            self.send_header('Connection', 'close')
            self.send_header('Content-Length', str(len(data)))
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.close_connection = True
            try:
                if data:
                    self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError, ssl.SSLError):
                pass

        def record(self):
            with lock:
                requests.append({'method': self.command, 'path': self.path, 'port': self.server.server_port,
                                 'credentials': self.headers.get('Authorization') == AUTH,
                                 'if_none_match': self.headers.get('If-None-Match'), 'depth': self.headers.get('Depth')})
            if self.server.server_port == foreign_port:
                self.send(200)
                return False
            if self.headers.get('Authorization') != AUTH:
                self.send(401)
                return False
            return True

        def do_MKCOL(self):
            if not self.record():
                return
            if flags['redirect_write']:
                self.send(307, headers={'Location': 'https://localhost:' + str(foreign_port) + '/dav/'})
                return
            with lock:
                if self.path in directories:
                    code = 405
                elif self.path.rsplit('/', 2)[0] + '/' not in directories:
                    code = 409
                else:
                    directories.add(self.path)
                    code = 201
            self.send(code)

        def do_PROPFIND(self):
            self.rfile.read(int(self.headers.get('Content-Length', 0)))
            if not self.record():
                return
            assert self.headers.get('Depth') == '1'
            with lock:
                if self.path not in directories:
                    data = None
                else:
                    children = [xml_entry(self.path, True)]
                    for name in sorted(directories):
                        if name != self.path and name.startswith(self.path) and '/' not in name[len(self.path):].rstrip('/'):
                            children.append(xml_entry(name, True))
                    for name in sorted(entries):
                        if name.startswith(self.path) and '/' not in name[len(self.path):]:
                            children.append(xml_entry(name))
                    data = ('<d:multistatus xmlns:d="DAV:">' + ''.join(children) + '</d:multistatus>').encode()
            self.send(404 if data is None else 207, data or b'')

        def do_PUT(self):
            count = int(self.headers.get('Content-Length', 0))
            assert 0 < count <= 128 * 1024 * 1024
            try:
                data = self.rfile.read(count)
            except (ConnectionResetError, ssl.SSLError):
                return
            if len(data) != count:
                self.close_connection = True
                return
            if not self.record():
                return
            assert self.headers.get('If-None-Match') == '*'
            if flags['redirect_put']:
                self.send(307, headers={'Location': 'https://localhost:' + str(foreign_port) + '/dav/changed'})
                return
            with lock:
                if self.path in entries:
                    code = 412
                elif self.path[:self.path.rfind('/') + 1] not in directories:
                    code = 409
                else:
                    entries[self.path] = data
                    code = 201
            if self.path == flags['disconnect']:
                flags['disconnect'] = ''
                self.close_connection = True
                try:
                    self.connection.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                self.connection.close()
                return
            self.send(code)

        def do_GET(self):
            if not self.record():
                return
            if self.path == flags['pause_get']:
                committed.set()
                release.wait(35)
                flags['pause_get'] = ''
            with lock:
                data = entries.get(self.path)
            self.send(404 if data is None else 200, data or b'')

    def server(key, certificate):
        service = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        service.daemon_threads = True
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certificate, key)
        service.socket = context.wrap_socket(service.socket, server_side=True)
        threading.Thread(target=service.serve_forever, daemon=True).start()
        return service

    main_server = server(trusted_key, trusted)
    foreign = server(trusted_key, trusted)
    foreign_port = foreign.server_port
    bad = server(untrusted_key, untrusted)
    wrong_server = server(wrong_key, wrong)
    port = main_server.server_port

    def root(name='dav', selected_port=port):
        directories.add('/' + name + '/')
        # Bind the bulk fixture's URL to the address actually listening. The
        # original 76/77-source suite still exercises DNS localhost. This avoids
        # a fresh IPv6-to-IPv4 fallback on every native Windows bulk request.
        return 'https://127.0.0.1:' + str(selected_port) + '/' + name + '/'

    def state(name):
        base = folder / name
        base.mkdir()
        cache, originals = base / 'cache', base / 'originals'
        cache.mkdir();originals.mkdir()
        return {'db': base / 'catalog.sqlite', 'cache': cache, 'originals': originals, 'position': base / 'current-reading.txt'}

    def rv(device, action, *args, expected=0):
        result = subprocess.run([str(protocol), action, str(device['db']), *map(str, args)],
                                capture_output=True, encoding='utf-8', errors='strict', timeout=180)
        assert result.returncode == 0, (action, result.stderr)
        value = json.loads(result.stdout)
        assert value['status'] == expected, (action, value)
        return value

    def wire(name, value):
        path = folder / (name + '.json')
        path.write_bytes(raw(value))
        return path

    def local(device, name, value):
        return rv(device, 'local', wire(name, value))

    def command(device, url, shard=16, after='-', limit=100, cancel=DISABLED):
        return [str(consumer), url, str(device['db']), str(device['cache']), str(device['originals']), str(shard),
                after or '-', str(limit), str(device['position']), str(cancel)]

    def sync(device, url=None, shard=16, after='-', limit=100, cancel=DISABLED, expected=0):
        result = subprocess.run(command(device, url or root(), shard, after, limit, cancel), env=env,
                                capture_output=True, encoding='utf-8', errors='strict', timeout=180)
        assert result.returncode == 0, (result.returncode, result.stderr)
        value = json.loads(result.stdout)
        assert value['status'] == expected, value
        if expected == 0:
            assert value['full_library_complete'] == 0 and value['shard_count'] == 256
        return value

    def record(name, details=None):
        assert name not in {c['id'] for c in checks}
        checks.append({'id': name, 'pass': True, 'details': details or {}})

    def counts(device):
        with sqlite3.connect(device['db']) as db:
            return tuple(db.execute('SELECT (SELECT count(*) FROM reader_revisions),(SELECT count(*) FROM reader_outbox)').fetchone())

    def remote(value, namespace='dav'):
        payload = raw(value)
        resource = '/' + namespace + '/exreader-sync-v1/revisions/' + value['id'][:2] + '/' + value['id'] + '-' + hashlib.sha256(payload).hexdigest() + '.json'
        parent = resource[:resource.rfind('/') + 1]
        parts = parent.strip('/').split('/')
        for n in range(1, len(parts) + 1):
            directories.add('/' + '/'.join(parts[:n]) + '/')
        entries[resource] = payload
        return resource

    try:
        da, db = state('设备A'), state('设备B')
        source = 'Original reading text 书\n'.encode() * 5000
        sha = hashlib.sha256(source).hexdigest()
        book_key = 'txt:' + sha
        book = revision(1, kind='book', key=book_key, payload={'format': 'txt', 'source_sha256': sha,
                        'source_bytes': len(source), 'title': '书', 'author': '作者', 'favorite': False})
        object_resource = '/dav/exreader-sync-v1/objects/' + sha[:2] + '/' + sha + '.txt'
        for device in (da, db):
            (device['originals'] / (sha + '.txt')).write_bytes(source)
            device['position'].write_text('chapter-7:UTF8-12345', encoding='utf-8')
        local(da, 'book', book)
        assert counts(da) == (1, 1)
        record('offline_original_revision_and_outbox_exist_before_any_network')
        va = sync(da)
        assert va['pushed'] == 1 and counts(da) == (1, 0) and entries[object_resource] == source
        puts = [r['path'] for r in requests if r['method'] == 'PUT']
        assert puts.index(object_resource) < next(n for n, path in enumerate(puts) if '/revisions/' in path)
        record('original_length_sha_verified_and_conditionally_published_before_referencing_revision')
        sync(db)
        assert counts(db) == (1, 0) and (db['cache'] / (sha + '.txt')).read_bytes() == source
        exported = folder / 'book-b-exact.json'
        rv(db, 'get', book['id'], exported)
        assert exported.read_bytes() == raw(book)
        record('two_native_clients_exchange_original_and_exact_revision_without_sqlite_file_upload')
        dc = state('already-exists')
        (dc['originals'] / (sha + '.txt')).write_bytes(source)
        local(dc, 'book-c', book)
        assert sync(dc)['pushed'] == 1 and counts(dc) == (1, 0)
        record('existing_412_original_and_revision_require_fresh_get_identity_before_ack')
        damaged = state('corrupt-remote-original')
        (damaged['originals'] / (sha + '.txt')).write_bytes(source)
        local(damaged, 'book-damaged', book)
        entries[object_resource] = b'X' + source[1:]
        sync(damaged, expected=5)
        assert counts(damaged) == (1, 1)
        entries[object_resource] = source
        record('412_corrupt_remote_original_never_acknowledges_or_replaces_local_history')
        wrong_local = state('corrupt-local-original')
        (wrong_local['originals'] / (sha + '.txt')).write_bytes(b'X' + source[1:])
        local(wrong_local, 'book-wrong-local', book)
        before = len([r for r in requests if r['method'] == 'PUT'])
        sync(wrong_local, expected=5)
        assert counts(wrong_local) == (1, 1) and before == len([r for r in requests if r['method'] == 'PUT'])
        record('local_original_corruption_is_refused_before_any_publication')
        missing_local = state('missing-local-original')
        local(missing_local, 'book-missing-local', book)
        v = sync(missing_local, root('missing-local'))
        assert v['pending_local_original'] == 1 and v['pushed'] == 0 and counts(missing_local)[1] == 1
        record('missing_private_original_stays_explicitly_pending_without_ack')
        removed_local = state('book-tombstone-without-local-original')
        book_wire = wire('known-book-before-local-removal', book)
        rv(removed_local, 'receive', book_wire, hashlib.sha256(book_wire.read_bytes()).hexdigest())
        book_delete = revision(2, kind='book', key=book_key, operation='delete', parents=[book['id']])
        local(removed_local, 'book-delete-without-bytes', book_delete)
        v = sync(removed_local)
        assert v['pushed'] == 1 and v['pending_local_original'] == 0 and counts(removed_local) == (2, 0)
        assert entries[object_resource] == source and rv(removed_local, 'heads', 'book', book_key)['state']['deleted']
        record('book_deletion_without_local_bytes_uses_verified_existing_remote_original_and_keeps_its_history')
        tag = revision(20, shard=18)
        local(da, 'tag-lost-response', tag)
        tag_path = '/dav/exreader-sync-v1/revisions/12/' + tag['id'] + '-' + hashlib.sha256(raw(tag)).hexdigest() + '.json'
        flags['disconnect'] = tag_path
        assert sync(da, shard=18)['pushed'] == 1 and counts(da)[1] == 0
        record('committed_put_with_lost_response_is_verified_by_get_before_ack')
        bad_revision = state('corrupt-existing-revision')
        local(bad_revision, 'bad-existing-revision', tag)
        entries[tag_path] = b' ' + raw(tag)[1:]
        sync(bad_revision, shard=18, expected=5)
        assert counts(bad_revision) == (1, 1)
        entries[tag_path] = raw(tag)
        record('412_corrupt_revision_cannot_ack_or_overwrite_immutable_local_original')
        killed = revision(21, shard=18, key='2' * 32)
        local(da, 'kill-after-remote-commit', killed)
        kill_path = '/dav/exreader-sync-v1/revisions/12/' + killed['id'] + '-' + hashlib.sha256(raw(killed)).hexdigest() + '.json'
        flags['pause_get'] = kill_path
        with (folder / 'killed-sync.log').open('wb') as log:
            process = subprocess.Popen(command(da, root(), shard=18), env=env, stdout=log, stderr=subprocess.STDOUT)
            try:
                assert committed.wait(40) and process.poll() is None
                process.kill();process.wait(timeout=20)
                assert process.returncode != 0 and counts(da)[1] == 1 and entries[kill_path] == raw(killed)
            finally:
                release.set()
                if process.poll() is None:
                    process.kill();process.wait(timeout=20)
        assert sync(da, shard=18)['pushed'] == 1 and counts(da)[1] == 0
        record('real_process_kill_after_remote_commit_before_ack_retries_original_history_and_outbox')
        location = {'mode': 'reflow_global', 'parser_version': '3.40.0', 'anchor_version': 1,
                    'selector': {'exact': 'Reading', 'prefix': '', 'suffix': ' text', 'start': 0, 'end': 7}}
        pa = revision(1, shard=32, kind='progress', key=book_key, mode='reflow_global', payload={'book_key': book_key, 'location': location})
        pb = revision(2, shard=32, kind='progress', key=book_key, mode='reflow_global', payload={'book_key': book_key, 'location': location})
        pa['display_time'], pb['display_time'] = '2999-12-31', '1900-01-01'
        local(da, 'progress-a', pa);local(db, 'progress-b', pb)
        sync(da, shard=32);sync(db, shard=32);sync(da, shard=32)
        for device in (da, db):
            heads = rv(device, 'heads', 'progress', book_key)
            assert heads['state']['heads'] == 2 and not heads['state']['projection_safe']
            assert device['position'].read_text(encoding='utf-8') == 'chapter-7:UTF8-12345'
        record('concurrent_progress_and_extreme_clocks_preserve_heads_without_mutating_current_reading')
        annotation_key = book_key + ':' + '3' * 32
        note_payload = {'book_key': book_key, 'annotation_id': '3' * 32, 'location': location, 'text': '备注'}
        na = revision(1, shard=33, kind='annotation', key=annotation_key, mode='reflow_global', payload=note_payload)
        nb = revision(2, shard=33, kind='annotation', key=annotation_key, mode='reflow_global', payload=note_payload)
        local(da, 'note-a', na);local(db, 'note-b', nb)
        sync(da, shard=33);sync(db, shard=33);sync(da, shard=33)
        deleted = revision(3, shard=33, kind='annotation', key=annotation_key, mode='reflow_global', operation='delete', parents=[na['id']])
        local(da, 'note-delete', deleted);sync(da, shard=33);sync(db, shard=33)
        for device in (da, db):
            heads = rv(device, 'heads', 'annotation', annotation_key)
            assert heads['state']['heads'] == 2 and not heads['state']['projection_safe']
        record('concurrent_annotation_edits_and_delete_tombstone_remain_visible_on_both_clients')
        pending = state('out-of-order-book')
        source2 = b'Out of order original book\n' * 100
        sha2 = hashlib.sha256(source2).hexdigest();key2 = 'txt:' + sha2
        pp = revision(1, shard=48, kind='progress', key=key2, mode='reflow_global', payload={'book_key': key2, 'location': location})
        remote(pp)
        v = sync(pending, shard=48)
        assert v['pending_metadata'] == 1 and counts(pending) == (1, 0) and not list(pending['cache'].iterdir())
        record('remote_nonbook_revision_without_verified_book_length_is_retained_and_pending')
        local_pending = state('local-missing-book-metadata')
        local(local_pending, 'local-pending-progress', pp)
        v = sync(local_pending, root('local-pending'), shard=48)
        assert v['pending_metadata'] == 1 and v['pushed'] == 0 and counts(local_pending) == (1, 1)
        record('local_nonbook_reference_without_book_length_keeps_outbox_pending_instead_of_assuming_zero')
        bp = revision(1, shard=49, kind='book', key=key2, payload={'format': 'txt', 'source_sha256': sha2,
                      'source_bytes': len(source2), 'title': 'Late', 'author': '', 'favorite': False})
        remote(bp)
        entries['/dav/exreader-sync-v1/objects/' + sha2[:2] + '/' + sha2 + '.txt'] = source2
        sync(pending, shard=49)
        v = sync(pending, shard=48)
        assert v['pending_metadata'] == 0 and v['originals_verified'] == 1 and counts(pending) == (2, 0)
        record('later_book_history_unlocks_original_length_sha_verification_on_the_next_sweep')
        conflicting = json.loads(raw(bp));conflicting['id'] = '%02x%030x' % (49, 2)
        conflicting['parents'] = [bp['id']];conflicting['payload']['source_bytes'] += 1
        conflict_path = remote(conflicting)
        v = sync(pending, shard=49, expected=4)
        assert v['revision_code'] == 4 and counts(pending) == (2, 0)
        del entries[conflict_path]
        record('conflicting_retained_book_length_is_refused_without_clock_selection_or_history_replacement')
        poisoned = state('bad-first-book-metadata')
        poison_url = root('first-invalid')
        first_bad = json.loads(raw(bp));first_bad['id'] = '%02x%030x' % (70, 1)
        first_bad['payload']['source_bytes'] += 1
        first_bad_path = remote(first_bad, 'first-invalid')
        entries['/first-invalid/exreader-sync-v1/objects/' + sha2[:2] + '/' + sha2 + '.txt'] = source2
        sync(poisoned, poison_url, shard=70, expected=5)
        assert counts(poisoned) == (0, 0)
        del entries[first_bad_path]
        first_good = json.loads(raw(bp));first_good['id'] = '%02x%030x' % (70, 2)
        remote(first_good, 'first-invalid')
        sync(poisoned, poison_url, shard=70)
        assert counts(poisoned) == (1, 0) and (poisoned['cache'] / (sha2 + '.txt')).read_bytes() == source2
        record('incorrect_first_book_length_is_rejected_before_history_adoption_and_cannot_poison_later_valid_metadata')
        child = revision(2, shard=50, key='4' * 32, parents=['%02x%030x' % (51, 1)])
        parent = revision(1, shard=51, key='4' * 32)
        remote(child);remote(parent)
        sync(pending, shard=50)
        assert rv(pending, 'heads', 'tag', '4' * 32)['state']['missing_parents'] == 1
        sync(pending, shard=51)
        assert rv(pending, 'heads', 'tag', '4' * 32)['state']['projection_safe']
        record('remote_parent_arriving_in_a_later_shard_recomputes_causal_completeness')
        cancelled_device = state('cancelled')
        local(cancelled_device, 'cancelled-tag', revision(77, shard=60))
        sync(cancelled_device, cancel=0, expected=6)
        assert counts(cancelled_device) == (1, 1)
        record('pre_cancel_has_no_ack_and_retains_offline_retry')
        mid = state('cancelled-mid-upload')
        big = b'large-original' * 400000
        big_sha = hashlib.sha256(big).hexdigest();big_key = 'txt:' + big_sha
        (mid['originals'] / (big_sha + '.txt')).write_bytes(big)
        big_book = revision(1, shard=61, kind='book', key=big_key, payload={'format': 'txt', 'source_sha256': big_sha,
                    'source_bytes': len(big), 'title': 'Big', 'author': '', 'favorite': False})
        local(mid, 'big-cancelled', big_book)
        sync(mid, shard=61, cancel=65536, expected=6)
        assert counts(mid) == (1, 1) and not list(mid['cache'].glob('.reader-sync-*.tmp'))
        record('native_upload_cancellation_removes_private_temporary_and_retains_outbox')
        assert sync(mid, shard=61)['pushed'] == 1
        record('fresh_process_retries_cancelled_original_and_reference_without_losing_bytes')
        offline = state('offline')
        local(offline, 'offline-tag', revision(1, shard=62))
        with socket.socket() as absent:
            absent.bind(('127.0.0.1', 0));absent_port = absent.getsockname()[1]
        sync(offline, root('offline', absent_port), shard=62, expected=3)
        assert counts(offline) == (1, 1)
        record('disconnected_endpoint_retains_exact_local_revision_and_retry_queue')
        redirect = state('redirect')
        local(redirect, 'redirect-tag', revision(1, shard=63))
        flags['redirect_write'] = True
        v = sync(redirect, root('redirect'), shard=63, expected=3)
        flags['redirect_write'] = False
        assert v['dav_code'] == 10 and not [r for r in requests if r['port'] == foreign_port]
        record('immutable_write_redirect_is_refused_before_foreign_origin_receives_credentials')
        flags['redirect_put'] = True
        v = sync(redirect, root('redirect'), shard=63, expected=3)
        flags['redirect_put'] = False
        assert v['dav_code'] == 10 and counts(redirect) == (1, 1) and not [r for r in requests if r['port'] == foreign_port]
        record('put_redirect_cannot_replay_body_or_credentials_to_another_origin')
        for name, selected_port in (('untrusted', bad.server_port), ('hostname', wrong_server.server_port)):
            device = state('tls-' + name)
            v = sync(device, root('tls', selected_port), expected=3)
            assert v['dav_code'] == 4
            record('native_tls_' + name + '_verification_remains_enforced')
        pages = state('bounded-cursor')
        page_url = root('pages')
        for n in (1, 3, 5):
            remote(revision(n, shard=64), 'pages')
        one = sync(pages, page_url, shard=64, limit=1)
        assert not one['shard_complete'] and one['remaining_in_shard'] == 2 and one['after']
        remote(revision(0, shard=64), 'pages')
        two = sync(pages, page_url, shard=64, after=one['after'], limit=1)
        three = sync(pages, page_url, shard=64, after=two['after'], limit=1)
        assert three['shard_complete'] and three['next_shard'] == 65 and not three['after'] and counts(pages) == (3, 0)
        sync(pages, page_url, shard=64)
        assert counts(pages) == (4, 0)
        record('bounded_per_shard_cursor_and_fresh_sweeps_discover_insertions_before_old_cursor')
        bulk = state('2202-bookshelf-entries')
        bulk_url = root('bulk')
        for n in range(2202):
            remote(revision(n + 10000, shard=n % 256, key='%032x' % (n + 1)), 'bulk')
        for shard in range(256):
            v = sync(bulk, bulk_url, shard=shard, limit=20)
            assert v['shard_complete'] and v['remaining_in_shard'] == 0
        assert counts(bulk) == (2202, 0)
        record('2202_real_remote_revisions_across_all_256_shards_are_not_truncated_at_2000', {'received': 2202, 'shards': 256})
        overflow = state('shard-overflow')
        overflow_url = root('overflow')
        for n in range(2001):
            remote(revision(n + 1, shard=0, key='%032x' % (n + 1)), 'overflow')
        sync(overflow, overflow_url, shard=0, expected=7)
        assert counts(overflow) == (0, 0)
        record('single_shard_over_2000_rejects_entire_listing_instead_of_silent_partial_sync')
        original_count = counts(db)
        sync(db, root('missing-collection'), shard=255)
        assert counts(db) == original_count
        record('missing_remote_collection_never_means_local_deletion')
        assert all(r['if_none_match'] == '*' for r in requests if r['method'] == 'PUT')
        assert not any(r['path'].endswith(('.sqlite', '.db')) for r in requests)
        record('all_writes_are_conditional_immutable_objects_never_running_sqlite_files')
        # Credential values are not serialized into request evidence, payloads,
        # database bytes or native consumer stdout. Only origin-scoped booleans.
        secret = b'sync-private-fixture'
        for device in (da, db, dc, pending, bulk):
            assert secret not in device['db'].read_bytes()
        assert all(secret not in value and AUTH.encode() not in value for value in entries.values())
        record('credentials_are_absent_from_payloads_and_product_databases')
        assert len(checks) == 33, len(checks)
        (folder / 'requests.json').write_text(json.dumps(requests, indent=2), encoding='utf-8')
        report = {'accepted': True, 'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
                  'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'platform': sys.platform, 'count': len(checks),
                  'checks': checks, 'remote_objects': len(entries), 'conditional_put_requests': sum(r['method'] == 'PUT' for r in requests),
                  'shards': 256, 'entries_per_shard_ceiling': 2000, 'namespace_discovery_ceiling': 512000,
                  'full_library_complete': False, 'host_projection_or_ui_accepted': False, 'complete_product': False}
        (folder / 'result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'accepted': True, 'checks': len(checks), 'source_sha': os.environ['GITHUB_SHA']}))
    finally:
        release.set()
        for service in (main_server, foreign, bad, wrong_server):
            service.shutdown();service.server_close()
        for key in certificates.glob('*.key'):
            key.unlink()


if __name__ == '__main__':
    main()
