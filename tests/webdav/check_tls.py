# SPDX-License-Identifier: MIT
"""Cloud-only real native HTTPS/WebDAV installed-consumer checks."""
import argparse
import base64
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import shutil
import ssl
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit
import zipfile

AUTH = 'Basic ' + base64.b64encode(b'fixture-user:fixture-password').decode()
OK, ARG, MEMORY, IO, TLS, HTTP, AUTH_REQUIRED, CANCELLED, LIMIT, FORMAT, REDIRECT, EXISTS = range(12)
DISABLED_CANCEL = (1 << 64) - 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--consumer', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'Cloud execution only'
    folder = args.output.resolve()
    folder.mkdir(parents=True)
    consumer = args.consumer.resolve()
    certificates = folder / 'certificates'
    certificates.mkdir()

    def certificate(name, host):
        key, cert = certificates / (name + '.key'), certificates / (name + '.crt')
        result = subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
                                 '-keyout', str(key), '-out', str(cert), '-subj', '/CN=' + host,
                                 '-addext', 'subjectAltName=DNS:' + host], capture_output=True, check=True)
        (certificates / (name + '.log')).write_bytes(result.stderr)
        return key, cert

    key, trusted = certificate('trusted', 'localhost')
    bad_key, untrusted = certificate('untrusted', 'localhost')
    wrong_key, wrong_host = certificate('wrong-host', 'wrong.example')
    if os.name == 'nt':
        for cert in (trusted, wrong_host):
            subprocess.run(['certutil', '-addstore', '-f', 'Root', str(cert)], check=True, capture_output=True)
    else:
        for cert in (trusted, wrong_host):
            subprocess.run(['sudo', 'cp', str(cert), '/usr/local/share/ca-certificates/exr-dav-' + cert.name], check=True)
        subprocess.run(['sudo', 'update-ca-certificates'], check=True, capture_output=True)

    fixture = io.BytesIO()
    with zipfile.ZipFile(fixture, 'w') as book:
        book.writestr('mimetype', 'application/epub+zip')
        book.writestr('META-INF/container.xml', '<container/>')
        book.writestr('chapter.txt', bytes(range(256)) * 4096)
    payload = fixture.getvalue()
    (folder / 'source.epub').write_bytes(payload)
    requests = []
    lock = threading.Lock()
    foreign_port = 0

    def response(href, collection=False, prefix='d'):
        return ('<' + prefix + ':response><' + prefix + ':href>' + href + '</' + prefix + ':href>'
                '<' + prefix + ':propstat><' + prefix + ':prop><' + prefix + ':displayname>书 &amp; Book</' + prefix + ':displayname>'
                '<' + prefix + ':resourcetype>' + ('<' + prefix + ':collection/>' if collection else '') + '</' + prefix + ':resourcetype>'
                '<' + prefix + ':getcontentlength>' + str(len(payload)) + '</' + prefix + ':getcontentlength>'
                '<' + prefix + ':getetag>&quot;fixture&quot;</' + prefix + ':getetag></' + prefix + ':prop>'
                '<' + prefix + ':status>HTTP/1.1 200 OK</' + prefix + ':status></' + prefix + ':propstat></' + prefix + ':response>')

    def listing(rows):
        return ('<?xml version="1.0"?><d:multistatus xmlns:d="DAV:">' + ''.join(rows) + '</d:multistatus>').encode()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def log_message(self, *unused):
            pass

        def send(self, code, data=b'', headers=None):
            self.send_response(code)
            for name, value in (headers or {}).items():
                self.send_header(name, value)
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            if data:
                try:
                    self.wfile.write(data)
                except (BrokenPipeError, ConnectionResetError, ssl.SSLError):
                    self.close_connection = True

        def record(self):
            if self.command == 'PROPFIND':
                count = int(self.headers.get('Content-Length', 0))
                assert count < 4096
                self.rfile.read(count)
            with lock:
                requests.append({'method': self.command, 'path': self.path, 'port': self.server.server_port,
                                 'authorization_present': 'Authorization' in self.headers,
                                 'fixture_credentials': self.headers.get('Authorization') == AUTH,
                                 'depth': self.headers.get('Depth')})
            if self.server.server_port == foreign_port:
                self.send(200, payload)
                return False
            if self.headers.get('Authorization') != AUTH:
                self.send(401, headers={'WWW-Authenticate': 'Basic realm="fixture"'})
                return False
            return True

        def do_PROPFIND(self):
            if not self.record():
                return
            assert self.headers.get('Depth') == '1'
            if self.path == '/dav/':
                self.send(207, listing([response('/dav/', True), response('/dav/book.epub'), response('/dav/folder/', True), response('/dav/%E4%B9%A6.epub')]))
            elif self.path == '/dav/folder/':
                self.send(207, listing([response('/dav/folder/', True), response('child.epub')]))
            elif self.path == '/dav/alias/':
                self.send(207, listing([response('/dav/alias/a.epub')]).replace(b'd:', b'x:').replace(b'xmlns:d', b'xmlns:x'))
            elif self.path == '/dav/default/':
                self.send(207, listing([response('/dav/default/a.epub')]).replace(b'd:', b'').replace(b'xmlns:d', b'xmlns'))
            elif self.path.startswith('/dav/invalid-'):
                cases = {
                    '/dav/invalid-escape/': listing([response('/outside.epub')]),
                    '/dav/invalid-origin/': listing([response('https://localhost:' + str(foreign_port) + '/dav/a.epub')]),
                    '/dav/invalid-traversal/': listing([response('/dav/invalid-traversal/%2e%2e/a.epub')]),
                    '/dav/invalid-depth/': listing([response('/dav/invalid-depth/a/b.epub')]),
                    '/dav/invalid-duplicate/': listing([response('/dav/invalid-duplicate/a.epub')] * 2),
                    '/dav/invalid-xml/': b'<d:multistatus xmlns:d="DAV:"><d:response>',
                    '/dav/invalid-dtd/': b'<!DOCTYPE a [<!ENTITY x SYSTEM "file:///unused">]><d:multistatus xmlns:d="DAV:">&x;</d:multistatus>',
                    '/dav/invalid-namespace/': listing([]).replace(b'DAV:', b'urn:other'),
                    '/dav/invalid-missing-href/': listing([response('/dav/a.epub')]).replace(b'<d:href>/dav/a.epub</d:href>', b''),
                }
                self.send(207, cases[self.path])
            elif self.path == '/dav/large-list/':
                self.send(207, listing([response('/dav/large-list/' + str(i) + '.epub') for i in range(20)]))
            else:
                self.send(500)

        def do_GET(self):
            if not self.record():
                return
            redirects = {'/dav/same.epub': '/dav/book.epub', '/dav/loop.epub': '/dav/loop.epub',
                         '/dav/outside.epub': '/outside.epub', '/dav/foreign.epub': 'https://localhost:' + str(foreign_port) + '/dav/book.epub',
                         '/dav/downgrade.epub': 'http://localhost:' + str(foreign_port) + '/dav/book.epub'}
            if self.path in redirects:
                self.send(302, headers={'Location': redirects[self.path]})
            elif self.path.startswith('/dav/error'):
                self.send(int(self.path.rsplit('error', 1)[1]))
            elif self.path in ('/dav/book.epub', '/dav/%E4%B9%A6.epub'):
                self.send(200, payload)
            elif self.path in ('/dav/chunked.epub', '/dav/slow.epub'):
                self.send_response(200)
                self.send_header('Transfer-Encoding', 'chunked')
                self.end_headers()
                try:
                    for offset in range(0, len(payload), 8192):
                        chunk = payload[offset:offset + 8192]
                        self.wfile.write(('%x\r\n' % len(chunk)).encode() + chunk + b'\r\n')
                        self.wfile.flush()
                        if self.path == '/dav/slow.epub':
                            time.sleep(.02)
                    self.wfile.write(b'0\r\n\r\n')
                except (BrokenPipeError, ConnectionResetError, ssl.SSLError):
                    pass
            elif self.path == '/dav/broken.epub':
                self.send_response(200)
                self.send_header('Content-Length', str(len(payload)))
                self.end_headers()
                self.wfile.write(payload[:65536])
                self.close_connection = True
            else:
                self.send(404)

    servers = []
    for private_key, cert in ((key, trusted), (key, trusted), (bad_key, untrusted), (wrong_key, wrong_host)):
        server = ThreadingHTTPServer(('localhost', 0), Handler)
        server.daemon_threads = True
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert, private_key)
        server.socket = context.wrap_socket(server.socket, server_side=True)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
    port, foreign_port, untrusted_port, wrong_port = [s.server_port for s in servers]
    root = 'https://localhost:' + str(port) + '/dav/'
    checks = []

    def run(name, expected=OK, action='get', resource='book.epub', root_url=root, auth=AUTH,
            maximum=0, listing_bytes=0, entries=0, timeout=0, cancel=DISABLED_CANCEL, filename='book.epub', prepare=None):
        case = folder / name
        case.mkdir()
        downloads = case / 'downloads'
        downloads.mkdir()
        if prepare:
            prepare(downloads)
        result = subprocess.run([str(consumer), action, root_url, auth, resource, str(downloads), filename,
                                 str(maximum), str(listing_bytes), str(entries), str(timeout), str(cancel)],
                                capture_output=True, timeout=140, encoding='utf-8', errors='strict')
        (case / 'stdout.json').write_text(result.stdout, encoding='utf-8')
        (case / 'stderr.log').write_text(result.stderr, encoding='utf-8')
        assert result.returncode == 0, (name, result.returncode, result.stderr)
        value = json.loads(result.stdout)
        assert value['status'] == expected, (name, expected, value)
        assert not list(downloads.glob('.exr-webdav-*')), (name, 'temporary file leak')
        if action == 'list':
            assert not list(downloads.iterdir()) and not value['published']
            if expected != OK:
                assert value['entries'] == []
        elif expected == OK:
            target = downloads / filename
            assert value['published'] == 1 and value['bytes'] == len(payload)
            assert hashlib.sha256(target.read_bytes()).digest() == hashlib.sha256(payload).digest()
        else:
            assert not value['published'] and value['bytes'] == 0
            if not prepare:
                assert not list(downloads.iterdir())
        checks.append({'id': name, 'pass': True, 'expected_status': expected, 'observed': value})
        return value

    try:
        result = run('https_depth_one', action='list', resource='')
        assert [r['resource'] for r in result['entries']] == ['book.epub', 'folder/', '%E4%B9%A6.epub']
        assert result['entries'][0]['display_name'] == '书 & Book'
        assert result['entries'][1]['collection'] == 1
        run('nested_collection_relative_href', action='list', resource='folder/')
        run('namespace_alias', action='list', resource='alias/')
        run('default_namespace', action='list', resource='default/')
        run('native_https_download')
        run('encoded_unicode_remote_and_local', resource='%E4%B9%A6.epub', filename='书籍.epub')
        run('chunked_bounded_stream', resource='chunked.epub')
        run('same_origin_redirect', resource='same.epub')
        for name in ('loop', 'outside', 'foreign', 'downgrade'):
            run('redirect_' + name, REDIRECT, resource=name + '.epub')
        run('untrusted_certificate', TLS, root_url='https://localhost:' + str(untrusted_port) + '/dav/')
        run('hostname_verification', TLS, root_url='https://localhost:' + str(wrong_port) + '/dav/')
        run('missing_credentials', AUTH_REQUIRED, auth='')
        for code in (401, 403, 404, 500, 507):
            run('server_' + str(code), AUTH_REQUIRED if code == 401 else HTTP, resource='error' + str(code))
        result = run('same_client_error_recovery', action='recover')
        assert result['first_status'] == HTTP
        run('declared_length_budget', LIMIT, maximum=65536)
        run('chunked_length_budget', LIMIT, resource='chunked.epub', maximum=65536)
        run('cancel_before_connect', CANCELLED, cancel=0)
        run('cancel_during_stream', CANCELLED, resource='slow.epub', cancel=65536)
        run('entire_transfer_timeout', IO, resource='slow.epub', timeout=100)
        run('truncated_transfer', IO, resource='broken.epub')
        run('listing_byte_budget', LIMIT, action='list', resource='', listing_bytes=128)
        run('listing_entry_budget', LIMIT, action='list', resource='large-list/', entries=2)
        run('listing_cancel', CANCELLED, action='list', resource='large-list/', cancel=128)
        for bad, status in (('escape', REDIRECT), ('origin', REDIRECT), ('traversal', ARG), ('depth', FORMAT),
                            ('duplicate', FORMAT), ('xml', FORMAT), ('dtd', FORMAT), ('namespace', FORMAT), ('missing-href', FORMAT)):
            run('listing_reject_' + bad, status, action='list', resource='invalid-' + bad + '/')
        for i, resource in enumerate(('../book.epub', '%2e%2e/book.epub', 'a%2Fbook.epub', 'a%5cbook.epub',
                                      'a%252ebook.epub', 'a%00.epub', '//other/a.epub', '/book.epub',
                                      'a?token=value', 'a#fragment', 'a b.epub', '%GG.epub', 'https://other/a.epub')):
            run('input_resource_reject_' + str(i), ARG, resource=resource)
        for i, url in enumerate(('http://localhost/dav/', 'https://user:secret@localhost/dav/',
                                 root[:-1], root + '?token=secret', root + '%2e%2e/')):
            run('root_reject_' + str(i), ARG, root_url=url)
        for i, filename in enumerate(('../book.epub', 'a/b.epub', 'a\\b.epub', 'a:stream', '.', 'a.', 'CON.txt', 'LPT1.epub', 'a?.epub')):
            run('local_name_reject_' + str(i), ARG, filename=filename)
        def existing(downloads):
            (downloads / 'book.epub').write_bytes(b'keep original')
        run('existing_destination_kept', EXISTS, prepare=existing)
        assert (folder / 'existing_destination_kept/downloads/book.epub').read_bytes() == b'keep original'
        if os.name != 'nt':
            outside = folder / 'symlink-target.epub'
            outside.write_bytes(b'keep linked target')
            run('symlink_destination_kept', EXISTS, prepare=lambda d: (d / 'book.epub').symlink_to(outside))
            assert outside.read_bytes() == b'keep linked target'
        assert not any(row['port'] == foreign_port for row in requests), 'Foreign origin was contacted'
        assert all(not row['authorization_present'] or row['port'] == port for row in requests), 'Credentials left their origin'
        checks.append({'id': 'all_observed_credentials_remain_at_configured_origin', 'pass': True})
        checks.append({'id': 'foreign_redirect_makes_no_foreign_request', 'pass': True})
        assert all(AUTH not in path.read_text(encoding='utf-8', errors='replace') and 'fixture-password' not in path.read_text(encoding='utf-8', errors='replace')
                   for path in folder.rglob('*') if path.is_file() and path.suffix in ('.json', '.log'))
        report = {'accepted': True, 'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
                  'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'platform': sys.platform, 'checks': checks,
                  'count': len(checks), 'tls_verification': 'native certificate and hostname verification',
                  'consumer_sha256': hashlib.sha256(consumer.read_bytes()).hexdigest(),
                  'original_sha256': hashlib.sha256(payload).hexdigest(), 'original_bytes': len(payload),
                  'scope': 'read-only HTTPS WebDAV book source; no sync protocol, credentials persistence, host UI or mobile claim',
                  'complete_product': False}
        (folder / 'requests.json').write_text(json.dumps(requests, indent=2), encoding='utf-8')
        (folder / 'result.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
        print(json.dumps({'accepted': True, 'checks': len(checks), 'source_sha': report['source_sha']}))
    finally:
        for server in servers:
            server.shutdown()
            server.server_close()
        # Keys are ephemeral fixture infrastructure, not delivery artifacts.
        for private_key in certificates.glob('*.key'):
            private_key.unlink()


if __name__ == '__main__':
    main()
