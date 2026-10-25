# SPDX-License-Identifier: MIT
"""Cloud-only real native HTTPS acceptance of EXReaderCloudImport.

Drives the installed `cloud-probe` consumer against a local TLS WebDAV service
(temporary CA trusted by the runner), then reads every stored original back
with a separate process that owns its own SDK handle. Every positive and
negative case is a named entry in result.json; the script exits non-zero on the
first violated assertion, so a produced report is never itself a pass.
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
import ssl
import subprocess
import sys
import threading
import time
from urllib.parse import quote, unquote
from xml.sax.saxutils import escape

AUTH = 'Basic ' + base64.b64encode(b'fixture-user:fixture-password').decode()
MIB = 1024 * 1024
# reader_cloud_status names, then exr_webdav_status values
DAV = dict(zip(['OK', 'ARG', 'MEMORY', 'IO', 'TLS', 'HTTP', 'AUTH', 'CANCELLED', 'LIMIT', 'FORMAT', 'REDIRECT', 'EXISTS'], range(12)))
NINE = [  # remote display name, fixture, importer format hint
    ('文本 书 #1.txt', 'sample.txt', 'TXT'),
    ('网页 & 页面.html', 'sample.html', 'HTML'),
    ('小说 FB2.fb2', 'sample.fb2', 'FB2'),
    ('中文 书名.epub', 'sample.epub', 'EPUB'),
    ('文档 (1).docx', 'sample.docx', 'DOCX'),
    ('富文本.rtf', 'sample.rtf', 'RTF'),
    ('旧版 mobi.mobi', 'sample.mobi', 'MOBI'),
    ('kf8 基础.azw3', 'kf8-basic.azw3', 'MOBI'),
    ('公开 文本.pdf', 'pdf-public-text.pdf', 'PDF'),
    ('漫画 一.cbz', 'comic.cbz', 'CBZ'),
]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def trust(certificates):
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'fixture trust is cloud only'
    for certificate in certificates:
        if os.name == 'nt':
            command = ['certutil', '-addstore', '-f', 'Root', str(certificate)]
        elif sys.platform == 'darwin':
            command = ['sudo', 'security', 'add-trusted-cert', '-d', '-r', 'trustRoot',
                       '-k', '/Library/Keychains/System.keychain', str(certificate)]
        else:
            command = ['sudo', 'cp', str(certificate), '/usr/local/share/ca-certificates/exr-cloud-' + certificate.name]
        subprocess.run(command, check=True, capture_output=True)
    if os.name != 'nt' and sys.platform != 'darwin':
        subprocess.run(['sudo', 'update-ca-certificates'], check=True, capture_output=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--probe', type=Path, required=True)
    parser.add_argument('--cxx', type=Path, required=True)
    parser.add_argument('--review-probe', type=Path, required=True)
    parser.add_argument('--fixtures', type=Path, required=True)
    parser.add_argument('--module-prefix', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'Cloud execution only'
    folder = args.output.resolve()
    folder.mkdir(parents=True)
    probe_exe = args.probe.resolve()
    fixtures = args.fixtures.resolve()
    prefix = args.module_prefix.resolve()
    assert (prefix / 'include/reader_cloud_import.h').is_file()
    installed = {str(p.relative_to(prefix)): {'bytes': p.stat().st_size, 'sha256': sha(p.read_bytes())}
                 for p in sorted(prefix.rglob('*')) if p.is_file()}

    certs = folder / 'certificates'
    certs.mkdir()

    def certificate(name, host):
        key, cert = certs / (name + '.key'), certs / (name + '.crt')
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1', '-keyout', str(key),
                        '-out', str(cert), '-subj', '/CN=' + host, '-addext', 'subjectAltName=DNS:' + host],
                       capture_output=True, check=True)
        return key, cert

    key, trusted = certificate('trusted', 'localhost')
    bad_key, untrusted = certificate('untrusted', 'localhost')
    wrong_key, wrong_host = certificate('wrong-host', 'wrong.example')
    trust((trusted, wrong_host))

    def fx(name):
        return (fixtures / name).read_bytes()

    sample_epub = fx('sample.epub')
    # path -> (kind, data, declared length shown in the listing)
    files = {}

    def add(path, data, kind='file', declared=None):
        files[path] = (kind, data, len(data) if declared is None else declared)

    for display, fixture, _ in NINE:
        add('/dav/books/' + display, fx(fixture))
    add('/dav/a/same.epub', sample_epub)
    add('/dav/b/same.epub', fx('complex-text.epub'))
    add('/dav/dup/副本 复制.epub', sample_epub)
    add('/dav/bad/corrupt.epub', b'PK\x03\x04 this is not a valid EPUB package\n' * 8)
    add('/dav/err/redirect-same.epub', b'', 'redirect:/dav/books/' + quote('中文 书名.epub'))
    add('/dav/err/redirect-foreign.epub', b'', 'redirect:@foreign')
    add('/dav/err/redirect-http.epub', b'', 'redirect:@downgrade')
    add('/dav/err/short.epub', sample_epub, 'short')
    add('/dav/err/liar.epub', sample_epub, 'file', len(sample_epub) + 7)
    add('/dav/err/big.txt', b'a' * (33 * MIB), 'chunked')
    add('/dav/err/slow.epub', sample_epub * 400, 'slow')
    add('/dav/err/missing.epub', b'x', 'status:404')
    add('/dav/err/broken.epub', b'x', 'status:500')
    add('/dav/err/pdf-edge.pdf', fx('pdf-public-text.pdf'))

    requests = []
    lock = threading.Lock()
    ports = {}

    def children(directory):
        rows, seen = [], set()
        for path, (kind, data, declared) in sorted(files.items()):
            if not path.startswith(directory):
                continue
            rest = path[len(directory):]
            if '/' in rest:
                head = rest.split('/', 1)[0] + '/'
                if head not in seen:
                    seen.add(head)
                    rows.append((directory + head, True, 0))
            else:
                rows.append((path, False, declared))
        return rows

    def entry(path, collection, size):
        name = path.rstrip('/').rsplit('/', 1)[-1]
        return ('<d:response><d:href>' + quote(path) + '</d:href><d:propstat><d:prop><d:displayname>' + escape(name) +
                '</d:displayname><d:resourcetype>' + ('<d:collection/>' if collection else '') + '</d:resourcetype>' +
                ('' if collection else '<d:getcontentlength>' + str(size) + '</d:getcontentlength>') +
                '<d:getetag>&quot;f&quot;</d:getetag></d:prop><d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>')

    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def log_message(self, *unused):
            pass

        def send(self, code, data=b'', headers=None):
            self.send_response(code)
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            if data:
                try:
                    self.wfile.write(data)
                except (BrokenPipeError, ConnectionResetError, ssl.SSLError):
                    self.close_connection = True

        def record(self):
            if self.command == 'PROPFIND':
                self.rfile.read(int(self.headers.get('Content-Length', 0)))
            with lock:
                requests.append({'method': self.command, 'path': self.path, 'port': self.server.server_port,
                                 'authorization_present': 'Authorization' in self.headers,
                                 'fixture_credentials': self.headers.get('Authorization') == AUTH})
            if self.server.server_port == ports['foreign']:
                self.send(200, sample_epub)
                return False
            if self.headers.get('Authorization') != AUTH:
                self.send(401, headers={'WWW-Authenticate': 'Basic realm="fixture"'})
                return False
            return True

        def do_PROPFIND(self):
            if not self.record():
                return
            path = unquote(self.path)
            if not path.endswith('/'):
                return self.send(404)
            rows = children(path)
            if path != '/dav/' and not rows:
                return self.send(404)
            body = '<?xml version="1.0"?><d:multistatus xmlns:d="DAV:">' + entry(path, True, 0) + ''.join(
                entry(p, c, s) for p, c, s in rows) + '</d:multistatus>'
            self.send(207, body.encode())

        def do_GET(self):
            if not self.record():
                return
            item = files.get(unquote(self.path))
            if not item:
                return self.send(404)
            kind, data, _ = item
            if kind.startswith('redirect:'):
                target = kind.split(':', 1)[1]
                if target == '@foreign':
                    target = 'https://localhost:%d/dav/books/x.epub' % ports['foreign']
                elif target == '@downgrade':
                    target = 'http://localhost:%d/dav/books/x.epub' % ports['foreign']
                return self.send(302, headers={'Location': target})
            if kind.startswith('status:'):
                return self.send(int(kind.split(':', 1)[1]))
            if kind == 'short':
                self.send_response(200)
                self.send_header('Content-Length', str(len(data) + 4096))
                self.end_headers()
                self.wfile.write(data[:len(data) // 2])
                self.wfile.flush()
                self.close_connection = True
                return
            if kind in ('chunked', 'slow'):
                self.send_response(200)
                self.send_header('Transfer-Encoding', 'chunked')
                self.end_headers()
                try:
                    for offset in range(0, len(data), 65536):
                        chunk = data[offset:offset + 65536]
                        self.wfile.write(('%x\r\n' % len(chunk)).encode() + chunk + b'\r\n')
                        if kind == 'slow':
                            self.wfile.flush()
                            time.sleep(.01)
                    self.wfile.write(b'0\r\n\r\n')
                except (BrokenPipeError, ConnectionResetError, ssl.SSLError):
                    self.close_connection = True
                return
            self.send(200, data)

    servers = []
    for private_key, cert in ((key, trusted), (key, trusted), (bad_key, untrusted), (wrong_key, wrong_host)):
        server = ThreadingHTTPServer(('localhost', 0), Handler)
        server.daemon_threads = True
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert, private_key)
        server.socket = context.wrap_socket(server.socket, server_side=True)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
    ports.update(zip(('main', 'foreign', 'untrusted', 'wrong'), [s.server_port for s in servers]))
    root = 'https://localhost:%d/dav/' % ports['main']
    checks = []
    counter = [0]

    def record(name, **info):
        checks.append({'id': name, 'pass': True, **info})

    def spec_run(name, spec):
        counter[0] += 1
        case = folder / ('%03d-%s' % (counter[0], re.sub(r'[^A-Za-z0-9_.-]', '_', name)))
        case.mkdir()
        (case / 'spec.txt').write_text(''.join('%s=%s\n' % (k, v) for k, v in spec.items()), encoding='utf-8', newline='\n')
        executable = args.review_probe.resolve() if spec.get('review') else probe_exe
        environment = dict(os.environ, READER_CLOUD_FAIL_ALLOC=str(spec.get('fail_alloc', 0)))
        result = subprocess.run([str(executable), str(case / 'spec.txt')], capture_output=True, timeout=170, env=environment)
        (case / 'stdout.json').write_bytes(result.stdout)
        (case / 'stderr.log').write_bytes(result.stderr)
        if 'auth' in spec:
            spec = dict(spec, auth='<redacted>')
            (case / 'spec.txt').write_text(''.join('%s=%s\n' % (k, v) for k, v in spec.items()), encoding='utf-8', newline='\n')
        assert result.returncode == 0, (name, result.returncode, result.stderr[-400:])
        return json.loads(result.stdout.decode('utf-8')), case

    def listing(name, resource='', auth=AUTH, url=root):
        value, _ = spec_run('list-' + name, {'cmd': 'list', 'root': url, 'auth': auth, 'resource': resource})
        assert value['list_status'] == 0, (name, value)
        return {e['display_name']: e for e in value['entries']}

    def readback(case_dir, library):
        out = case_dir / 'readback'
        out.mkdir(exist_ok=True)
        value, _ = spec_run('readback', {'cmd': 'readback', 'library': library, 'out': out})
        assert value['ok'] == 1, value
        for book in value['books']:
            assert book['read_ok'] == 1, book
            book['sha256'] = sha((out / ('book-%d.bin' % book['id'])).read_bytes())
        return value['books']

    def transfer(name, entry, display=None, listed=True, root_url=root, auth=AUTH, library=None, **extra):
        staging = folder / ('staging-%03d' % (counter[0] + 1))
        staging.mkdir()
        lib = library or str(folder / ('library-%03d.db' % (counter[0] + 1)))
        spec = {'cmd': 'transfer', 'root': root_url, 'auth': auth, 'resource': entry['resource'] if isinstance(entry, dict) else entry,
                'name': display if display is not None else entry['display_name'], 'staging': staging, 'library': lib,
                'expected': entry['bytes'] if listed and isinstance(entry, dict) and entry.get('has_size') else 0}
        spec.update(extra)
        value, case = spec_run(name, spec)
        assert not list(staging.glob('.exr-webdav-*')), (name, 'temporary download file leaked')
        value['_staging'], value['_library'], value['_case'] = staging, lib, case
        return value

    def staging_empty(value, name):
        assert not list(value['_staging'].iterdir()), (name, 'staging file leaked', list(value['_staging'].iterdir()))

    try:
        # ---- 1. directory browsing -> selection -> download -> SDK import (nine formats) ----
        books = listing('books', 'books/')
        library = str(folder / 'nine.db')
        expected_originals = {}
        first_epub_id = None
        for display, fixture, fmt in NINE:
            entry_ = books[display]
            result = transfer('format_' + fixture, entry_, library=library)
            assert result['download_status'] == 'ok' and result['import_status'] == 'ok', (display, result)
            data = fx(fixture)
            assert result['committed'] == 1 and result['created'] == 1 and result['staging_removed'] == 1
            assert result['staged_bytes'] == len(data) and result['staged_sha256'] == sha(data)
            assert re.fullmatch(r'cloud-[0-9a-f]{16}\.[a-z0-9]+', result['staged_file']), result['staged_file']
            assert display not in result['staged_file'] and result['staged_name'] == display
            assert result['consumed'] == 1 and result['staging_file_exists'] == 0
            staging_empty(result, display)
            expected_originals[result['book_id']] = (data, display)
            if fixture == 'sample.epub':
                first_epub_id = result['book_id']
            record('format_' + fixture, format=fmt, bytes=len(data), book_id=result['book_id'], created=True)
        (folder / 'nine-readback').mkdir()
        stored = readback(folder / 'nine-readback', library)
        assert len(stored) == len(NINE) and {b['id'] for b in stored} == set(expected_originals), stored
        for book in stored:
            data, display = expected_originals[book['id']]
            assert book['sha256'] == sha(data) and book['bytes'] == len(data), (display, book)
            assert book['title'] == os.path.splitext(display)[0], (display, book['title'])
        record('independent_sdk_readback_nine_originals_and_unicode_titles', count=len(stored))

        # ---- 2. same name, different content; duplicates preserved ----
        a, b = listing('a', 'a/')['same.epub'], listing('b', 'b/')['same.epub']
        library = str(folder / 'same-name.db')
        ra, rb = transfer('same_name_a', a, library=library), transfer('same_name_b', b, library=library)
        assert ra['import_status'] == rb['import_status'] == 'ok' and ra['created'] == rb['created'] == 1
        assert ra['book_id'] != rb['book_id'] and ra['staged_file'] != rb['staged_file']
        (folder / 'same-readback').mkdir()
        stored = {x['id']: x for x in readback(folder / 'same-readback', library)}
        assert stored[ra['book_id']]['sha256'] == sha(sample_epub) and stored[rb['book_id']]['sha256'] == sha(fx('complex-text.epub'))
        record('same_remote_name_different_content_keeps_both')
        copy = listing('dup', 'dup/')['副本 复制.epub']
        dup = transfer('duplicate_bytes', copy, library=library, title='不同的标题')
        assert dup['import_status'] == 'ok' and dup['committed'] == 1 and dup['created'] == 0 and dup['book_id'] == ra['book_id'], dup
        staging_empty(dup, 'duplicate')
        for mode in ('flip', 'truncate', 'append', 'delete'):
            failed = transfer('duplicate_then_' + mode, copy, library=library, tamper=mode)
            assert failed['import_status'] == ('io' if mode == 'delete' else 'corrupt'), (mode, failed)
            assert failed['committed'] == 0 and failed['consumed'] == 1
            staging_empty(failed, mode)
        cancelled = transfer('duplicate_then_cancel', copy, library=library, cancel_import_poll=1)
        assert cancelled['import_status'] == 'cancelled' and cancelled['committed'] == 0
        staging_empty(cancelled, 'duplicate cancel')
        (folder / 'dup-readback').mkdir()
        stored = {x['id']: x for x in readback(folder / 'dup-readback', library)}
        assert set(stored) == {ra['book_id'], rb['book_id']}, stored
        assert stored[ra['book_id']]['title'] == 'same' and stored[ra['book_id']]['sha256'] == sha(sample_epub)
        record('duplicate_keeps_existing_book_title_and_survives_every_failure_cleanup')

        # Root review: invalid WebDAV input must also be safe without diagnostics.
        before = len(requests)
        invalid = transfer('invalid_resource_null_error', '../outside.epub', display='safe.epub', listed=False, null_error=1)
        assert invalid['download_status'] == 'argument' and invalid['staged'] == 0 and len(requests) == before, invalid
        staging_empty(invalid, 'invalid resource with NULL diagnostics')
        record('invalid_webdav_argument_allows_null_error_without_network')

        blocked = transfer('cleanup_refused_after_commit', copy, block_cleanup=1)
        assert blocked['import_status'] == 'ok' and blocked['committed'] == 1 and blocked['created'] == 1, blocked
        assert blocked['staging_removed'] == 0 and blocked['consumed'] == 0 and blocked['staging_file_exists'] == 1, blocked
        assert blocked['blocked_discard_retained'] == 1 and blocked['cleanup_retry_consumed'] == 1 and blocked['cleanup_retry_file_exists'] == 0, blocked
        staging_empty(blocked, 'cleanup retry')
        stored = readback(blocked['_case'], blocked['_library'])
        assert len(stored) == 1 and stored[0]['sha256'] == sha(sample_epub), stored
        record('real_cleanup_refusal_keeps_receipt_and_owned_retry_without_deleting_sdk_book')

        for allocation in (1, 2, 3):
            before = len(requests)
            failed = transfer('prepublish_oom_' + str(allocation), copy, review=1, fail_alloc=allocation)
            assert failed['download_status'] == 'memory' and failed['staged'] == 0 and len(requests) == before, failed
            staging_empty(failed, 'prepublication allocation failure')
        record('all_owned_download_allocations_fail_before_network_without_published_orphans')

        for explicit in (False, True):
            title = 'Exact explicit title' if explicit else ''
            baseline = transfer('title_allocation_baseline_' + str(explicit), copy, review=1, title=title)
            allocation = baseline['review_before_import'] + 1
            failed = transfer('title_allocation_failure_' + str(explicit), copy, review=1, title=title, fail_alloc=allocation)
            assert failed['download_status'] == 'ok' and failed['import_status'] == 'memory' and failed['committed'] == 0, failed
            assert failed['import_message'] and failed['consumed'] == 1 and failed['staging_removed'] == 1, failed
            assert not readback(failed['_case'], failed['_library']), failed
            staging_empty(failed, 'title allocation failure')
        record('explicit_and_derived_title_oom_never_silently_import_with_other_metadata')

        # ---- 3. corruption after download and invalid books ----
        for mode, status in (('flip', 'corrupt'), ('truncate', 'corrupt'), ('append', 'corrupt'), ('delete', 'io')):
            lib = str(folder / ('tamper-%s.db' % mode))
            failed = transfer('tamper_' + mode, books['中文 书名.epub'], library=lib, tamper=mode)
            assert failed['download_status'] == 'ok' and failed['import_status'] == status, (mode, failed)
            assert failed['committed'] == 0 and failed['staging_removed'] == 1
            staging_empty(failed, mode)
            (folder / ('tamper-%s-readback' % mode)).mkdir()
            assert readback(folder / ('tamper-%s-readback' % mode), lib) == []
            record('corrupted_after_download_' + mode, status=status)
        bad = listing('bad', 'bad/')['corrupt.epub']
        invalid = transfer('invalid_book_sdk_rejects', bad)
        assert invalid['download_status'] == 'ok' and invalid['import_status'] == 'import' and invalid['committed'] == 0, invalid
        assert invalid['import_sdk'] != 0
        staging_empty(invalid, 'invalid')
        (folder / 'invalid-readback').mkdir()
        assert readback(folder / 'invalid-readback', invalid['_library']) == []
        record('invalid_book_rejected_by_sdk_without_row_or_leftover')

        # ---- 4. network refusals; none may leave a file or a foreign request ----
        err = listing('err', 'err/')
        before_foreign = len([r for r in requests if r['port'] == ports['foreign']])
        for name, spec_ in (
            ('redirect_foreign_origin', dict(entry=err['redirect-foreign.epub'])),
            ('redirect_downgrade', dict(entry=err['redirect-http.epub'])),
            ('untrusted_certificate', dict(entry=err['missing.epub'], root_url='https://localhost:%d/dav/' % ports['untrusted'])),
            ('hostname_mismatch', dict(entry=err['missing.epub'], root_url='https://localhost:%d/dav/' % ports['wrong'])),
        ):
            entry_ = spec_.pop('entry')
            result = transfer(name, entry_, **spec_)
            assert result['download_status'] == 'remote' and result['staged'] == 0, (name, result)
            expected_code = DAV['REDIRECT'] if name.startswith('redirect') else DAV['TLS']
            assert result['download_webdav'] == expected_code, (name, result)
            assert 'import_status' not in result
            staging_empty(result, name)
            record(name, webdav_status=expected_code)
        assert len([r for r in requests if r['port'] == ports['foreign']]) == before_foreign, 'foreign origin contacted'
        result = transfer('missing_credentials', books['中文 书名.epub'], auth='')
        assert result['download_status'] == 'remote' and result['download_webdav'] == DAV['AUTH'] and result['download_http'] == 401, result
        staging_empty(result, 'auth')
        record('http_401_requires_credentials')
        for name, code in (('missing', 404), ('broken', 500)):
            result = transfer('http_' + name, err[name + '.epub'])
            assert result['download_status'] == 'remote' and result['download_webdav'] == DAV['HTTP'] and result['download_http'] == code, result
            staging_empty(result, name)
            record('http_error_' + str(code))
        short = transfer('short_read', err['short.epub'])
        assert short['download_status'] == 'remote' and short['download_webdav'] == DAV['IO'] and short['staged'] == 0, short
        staging_empty(short, 'short')
        record('short_read_removes_partial_file')
        liar = transfer('listing_length_mismatch', err['liar.epub'])
        assert liar['download_status'] == 'length' and liar['staged'] == 0, liar
        staging_empty(liar, 'liar')
        record('received_length_differs_from_listing')
        redirected = transfer('same_origin_redirect_succeeds', err['redirect-same.epub'], listed=False)
        assert redirected['download_status'] == 'ok' and redirected['import_status'] == 'ok', redirected
        record('same_origin_redirect_followed')

        # ---- 5. byte ceilings ----
        big_listing = err['big.txt']
        pre = len(requests)
        result = transfer('txt_declared_over_32mib', big_listing)
        assert result['download_status'] == 'limit' and len(requests) == pre, 'declared oversize must not touch the network'
        staging_empty(result, 'big declared')
        record('reflow_format_declared_over_32_mib_refused_before_request')
        result = transfer('txt_streaming_over_32mib', big_listing, listed=False)
        assert result['download_status'] == 'limit' and result['staged'] == 0, result
        staging_empty(result, 'big stream')
        record('reflow_format_stream_over_32_mib_stopped_and_cleaned')
        pre = len(requests)
        result = transfer('epub_declared_over_128mib', books['中文 书名.epub'], listed=False, expected=128 * MIB + 1)
        assert result['download_status'] == 'limit' and len(requests) == pre, result
        record('streaming_format_declared_over_128_mib_refused_before_request')
        result = transfer('request_limit_lowers_ceiling', books['中文 书名.epub'], listed=False, max=512)
        assert result['download_status'] == 'limit' and result['staged'] == 0, result
        staging_empty(result, 'lowered')
        record('request_limit_may_lower_ceiling')
        result = transfer('import_limit_lowers_ceiling', books['文本 书 #1.txt'], max_input=8)
        assert result['download_status'] == 'ok' and result['import_status'] == 'limit' and result['committed'] == 0, result
        staging_empty(result, 'import limit')
        record('import_limit_may_lower_ceiling')

        # ---- 6. cancellation ----
        pre = len(requests)
        result = transfer('cancel_before_network', books['中文 书名.epub'], cancel_before=1)
        assert result['download_status'] == 'cancelled' and len(requests) == pre, result
        record('cancel_before_network')
        result = transfer('cancel_during_stream', err['slow.epub'], listed=False, cancel_net=65536)
        assert result['download_status'] == 'cancelled' and result['staged'] == 0, result
        staging_empty(result, 'stream cancel')
        record('cancel_during_download_removes_temporary')
        result = transfer('cancel_between_phases', books['中文 书名.epub'], tamper='discard')
        assert result['staged'] == 1 and result['discarded'] == 1 and result['discard_nulled'] == 1 and result['file_after_discard'] == 0, result
        staging_empty(result, 'between')
        assert not os.path.exists(result['_library'])
        record('cancel_between_phases_discard_never_opens_library')
        for display in ('中文 书名.epub', '公开 文本.pdf', '文本 书 #1.txt', '漫画 一.cbz'):
            polls = transfer('measure_polls_' + display, books[display])['polls']
            assert polls >= 3, polls
            seen = set()
            for at in sorted({1, 2, 3, polls - 1, polls, polls + 1}):
                if at < 1:
                    continue
                run = transfer('cancel_import_%d_%s' % (at, display), books[display], cancel_import_poll=at)
                staging_empty(run, 'sweep')
                (folder / ('sweep-%03d' % counter[0])).mkdir()
                stored = readback(folder / ('sweep-%03d' % counter[0]), run['_library'])
                if run['import_status'] == 'cancelled':
                    assert run['committed'] == 0 and stored == [], (display, at, run, stored)
                    seen.add('cancelled')
                else:
                    assert run['import_status'] == 'ok' and run['committed'] == 1 and len(stored) == 1, (display, at, run)
                    assert stored[0]['sha256'] == sha(fx(next(f for d, f, _ in NINE if d == display))), (display, at)
                    seen.add('committed')
            assert 'cancelled' in seen and 'committed' in seen, (display, seen, polls)
            record('cancel_sweep_commit_boundary_' + display, polls=polls, outcomes=sorted(seen))

        # ---- 7. credentials and origin ----
        assert all(not r['authorization_present'] or r['port'] == ports['main'] for r in requests), 'credentials left their origin'
        assert not any(r['port'] == ports['foreign'] for r in requests), 'foreign origin was contacted'
        record('credentials_stay_at_configured_origin_and_no_foreign_request')
        smoke, _ = spec_run('selftest', {'cmd': 'selftest'})
        assert smoke['selftest'] == 1
        cpp = subprocess.run([str(args.cxx.resolve())], capture_output=True, text=True, encoding='utf-8')
        assert cpp.returncode == 0 and 'cloud-import-cpp ok' in cpp.stdout, cpp
        record('independent_c_and_cpp_consumers_from_installed_package')
        text = ''.join(p.read_text(encoding='utf-8', errors='replace') for p in folder.rglob('*') if p.is_file() and p.suffix in ('.json', '.log', '.txt'))
        assert AUTH not in text and 'fixture-password' not in text, 'credential leaked into evidence'
        record('no_credentials_in_evidence')

        report = {'accepted': True, 'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
                  'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'platform': sys.platform, 'checks': checks, 'count': len(checks),
                  'probe_sha256': sha(probe_exe.read_bytes()),
                  'review_probe_sha256': sha(args.review_probe.resolve().read_bytes()), 'installed_files': installed,
                  'tls': 'native certificate and hostname verification against a runner-trusted temporary CA',
                  'scope': 'desktop WebDAV download plus sideload import adapter; no host UI, no mobile or device claim, '
                           'no real user cloud provider',
                  'complete_product': False}
        (folder / 'requests.json').write_text(json.dumps(requests, indent=1), encoding='utf-8')
        (folder / 'result.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
        print(json.dumps({'accepted': True, 'checks': len(checks), 'source_sha': report['source_sha']}))
    finally:
        for server in servers:
            server.shutdown()
            server.server_close()
        for private_key in certs.glob('*.key'):
            private_key.unlink()


if __name__ == '__main__':
    main()
