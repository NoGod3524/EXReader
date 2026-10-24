# SPDX-License-Identifier: MIT
"""Cloud-only native HTTPS interoperability regression; original suite stays intact."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import json
import os
from pathlib import Path
import ssl
import subprocess
import sys
import threading


def main():
    p = argparse.ArgumentParser(); p.add_argument('--consumer', type=Path, required=True); p.add_argument('--output', type=Path, required=True)
    a = p.parse_args(); assert os.environ.get('GITHUB_ACTIONS') == 'true'
    folder = a.output.resolve(); folder.mkdir(parents=True)
    certs = folder / 'certificates'; certs.mkdir()
    key, cert = certs / 'compat.key', certs / 'compat.crt'
    subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1', '-keyout', str(key),
                    '-out', str(cert), '-subj', '/CN=localhost', '-addext', 'subjectAltName=DNS:localhost,IP:127.0.0.1'], check=True, capture_output=True)
    subprocess.run(['certutil', '-addstore', '-f', 'Root', str(cert)] if os.name == 'nt' else
                   ['sudo', 'cp', str(cert), '/usr/local/share/ca-certificates/reader-dav-compat.crt'], check=True, capture_output=True)
    if os.name != 'nt': subprocess.run(['sudo', 'update-ca-certificates'], check=True, capture_output=True)
    payload = '真实原生请求\n'.encode(); requests, checks = [], []

    def response(href, extra=False, pad=0):
        # Apache can split requested absent displayname into a 404 propstat.
        return ('<d:response><d:href>' + href + '</d:href><d:propstat><d:prop><d:resourcetype/>' +
                '<d:getcontentlength>' + str(len(payload)) + '</d:getcontentlength><d:getetag>fixture</d:getetag>' +
                '<d:x/>' * pad + '</d:prop><d:status>HTTP/1.1 200 OK</d:status></d:propstat>' +
                ('<d:propstat><d:prop><d:displayname/></d:prop><d:status>HTTP/1.1 404 Not Found</d:status></d:propstat>' if extra else '') + '</d:response>')
    def xml(rows): return ('<d:multistatus xmlns:d="DAV:">' + ''.join(rows) + '</d:multistatus>').encode()
    replies = {
        '/dav/': xml([response('/dav/a%20b.txt'), response('/dav/100%25.txt')]),
        '/dav/unicode/': xml([response('/dav/unicode/%E4%B9%A6%20%2B%25.txt')]),
        '/dav/root%25/': xml([response('/dav/root%25/child.txt')]),
        '/dav/ceiling/': xml([response('/dav/ceiling/%04d.txt' % n, extra=True) for n in range(2000)]),
        '/dav/overflow/': xml([response('/dav/overflow/%04d.txt' % n) for n in range(2001)]),
        '/dav/response-flood/': xml([response('/dav/response-flood/a.txt', pad=33)]),
        '/dav/outside-flood/': xml(['<d:x/>' * 129]),
        '/dav/deep/': xml(['<d:x>' * 33 + '</d:x>' * 33]),
        '/dav/invalid-utf8/': xml([response('/dav/invalid-utf8/%FF.txt')]),
    }
    assert replies['/dav/ceiling/'].count(b'<') // 2 > 20000 and len(replies['/dav/ceiling/']) < 4 * 1024 * 1024

    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'
        def log_message(self, *unused): pass
        def send(self, code, body):
            self.send_response(code); self.send_header('Content-Length', str(len(body))); self.end_headers()
            self.wfile.write(body)
        def do_PROPFIND(self):
            self.rfile.read(int(self.headers['Content-Length'])); requests.append((self.command, self.path))
            self.send(207, replies[self.path])
        def do_GET(self):
            requests.append((self.command, self.path)); self.send(200, payload)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler); server.daemon_threads = True
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); context.load_cert_chain(cert, key)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    root = 'https://localhost:' + str(server.server_port) + '/dav/'
    def invoke(name, resource='', status=0, action='list', url=root, entries=0):
        target = folder / name; target.mkdir()
        done = subprocess.run([str(a.consumer.resolve()), action, url, '', resource, str(target), 'download.txt',
                               '0', '0', str(entries), '10000', str((1 << 64) - 1)], capture_output=True, text=True, encoding='utf-8', timeout=30)
        assert done.returncode == 0, (name, done.stderr)
        value = json.loads(done.stdout); assert value['status'] == status, (name, value)
        if status: assert not value['entries'] and not value['published'] and not list(target.iterdir())
        (folder / (name + '.json')).write_text(done.stdout, encoding='utf-8'); return value
    def record(name): checks.append(name); print('PASS ' + name, flush=True)
    try:
        listing = invoke('names')
        assert [(x['resource'], x['display_name']) for x in listing['entries']] == [('a%20b.txt', 'a b.txt'), ('100%25.txt', '100%.txt')]
        record('missing_displayname_decodes_exactly_once_and_keeps_encoded_resources')
        value = invoke('literal-percent', '100%25.txt', action='download')
        assert value['published'] == 1 and (folder / 'literal-percent/download.txt').read_bytes() == payload
        assert requests[-1] == ('GET', '/dav/100%25.txt')
        record('literal_percent_download_reaches_native_transport_without_double_decoding')
        value = invoke('unicode', 'unicode/'); assert value['entries'][0]['display_name'] == '书 +%.txt'
        record('utf8_space_plus_percent_fallback_preserves_display_bytes')
        value = invoke('percent-root', url=root + 'root%25/'); assert value['entries'][0]['resource'] == 'child.txt'
        record('unambiguous_percent_in_configured_root_is_supported')
        value = invoke('ceiling', 'ceiling/'); assert len(value['entries']) == 2000
        record('two_propstat_2000_entry_listing_exceeds_old_global_limit_and_succeeds')
        invoke('overflow', 'overflow/', status=8); record('2001_entries_are_refused_without_partial_results')
        invoke('lowered', 'ceiling/', status=8, entries=2); record('lowered_entry_budget_is_enforced_during_xml_read')
        invoke('response-flood', 'response-flood/', status=8); record('one_response_cannot_consume_another_entries_xml_budget')
        invoke('outside-flood', 'outside-flood/', status=8); record('unrelated_xml_elements_have_a_separate_fixed_bound')
        invoke('depth', 'deep/', status=8); record('xml_depth_bound_remains_enforced')
        n = len(requests)
        for i, resource in enumerate(('a%252e.txt', 'a%25%32%65.txt', 'a%252F.txt', 'a%2F.txt', '%2e%2e/a.txt')):
            invoke('double-%d' % i, resource, status=1, action='download')
        assert len(requests) == n; record('second_encoded_escapes_separators_and_traversal_still_fail_before_network')
        invoke('bad-utf8', 'invalid-utf8/', status=1); record('fallback_does_not_accept_invalid_utf8')
        assert len(checks) == 12
        report = {'accepted': True, 'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
                  'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'platform': sys.platform, 'checks': checks, 'count': len(checks),
                  'consumer_sha256': hashlib.sha256(a.consumer.read_bytes()).hexdigest(), 'listing_bytes_ceiling': 4 * 1024 * 1024,
                  'entry_ceiling': 2000, 'xml_per_response_elements': 32, 'xml_outside_response_elements': 128,
                  'real_service_interop_accepted': False, 'complete_product': False}
        (folder / 'result.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8'); print(json.dumps(report), flush=True)
    finally:
        server.shutdown(); server.server_close()


if __name__ == '__main__': main()
