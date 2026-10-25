"""Actions-only reset-peer regression through the installed public WebDAV ABI."""
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import signal
import socket
import ssl
import struct
import subprocess
import sys
import threading

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests/webdav'))
from cloud_native import trust_fixture_certificates


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--probe', type=Path, required=True)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--profile', required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only'
    args.out.mkdir(parents=True)
    private = args.out.parent / 'tls-private'
    private.mkdir()
    key, cert = private / 'server.key', private / 'server.crt'
    subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
                    '-keyout', str(key), '-out', str(cert), '-subj', '/CN=localhost',
                    '-addext', 'subjectAltName=DNS:localhost,IP:127.0.0.1'],
                   check=True, capture_output=True)
    trust_fixture_certificates([cert], 'webdav-sigpipe-')
    payload = (ROOT / 'tests/fixtures/sample.epub').read_bytes()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def log_message(self, *unused):
            pass

        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-Length', str(len(payload) * 4))
            self.end_headers()
            try:
                self.wfile.write(payload[:len(payload) // 2])
                self.wfile.flush()
                # Same hostile reset as the unchanged C03 failure: no graceful
                # replacement and no subprocess signal-disposition workaround.
                linger = struct.pack('HH' if os.name == 'nt' else 'ii', 1, 0)
                self.connection.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, linger)
                self.connection.close()
            except (OSError, ssl.SSLError):
                pass
            self.close_connection = True

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.daemon_threads = True
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    root = 'https://127.0.0.1:%d/dav/' % server.server_port
    checks, controls = [], []
    modes = ['default'] if os.name == 'nt' else ['default', 'handler', 'pending', 'blocked']
    probe = args.probe.resolve()
    try:
        for mode in modes:
            for attempt in range(6 if mode == 'default' else 3):
                directory = (args.out / ('%s-%d' % (mode, attempt))).resolve()
                result = subprocess.run([str(probe), mode, root, str(directory), 'reset.epub'],
                                        capture_output=True, text=True, timeout=30)
                (args.out / ('%s-%d.stdout.log' % (mode, attempt))).write_text(result.stdout, encoding='utf-8')
                (args.out / ('%s-%d.stderr.log' % (mode, attempt))).write_text(result.stderr, encoding='utf-8')
                assert result.returncode == 0, (mode, attempt, result.returncode, result.stderr, result.stdout)
                observed = json.loads(result.stdout)
                assert observed['ok'] is True and observed['status'] != 0, observed
                assert observed['published'] == 0 and observed['bytes'] == 0 and not list(directory.iterdir()), observed
                assert all(observed[name] is True for name in ('thread_mask_preserved', 'process_handler_preserved',
                           'pending_signal_contract', 'other_thread_handler_live', 'temporary_files_removed')), observed
                checks.append(dict(name='%s-reset-%d' % (mode, attempt), passed=True, observed=observed))
        if args.baseline:
            assert sys.platform.startswith('linux'), 'Original SIGPIPE reproduction is Linux-specific evidence'
            for attempt in range(8):
                directory = (args.out / ('baseline-default-%d' % attempt)).resolve()
                result = subprocess.run([str(args.baseline.resolve()), 'default', root, str(directory), 'reset.epub'],
                                        capture_output=True, text=True, timeout=30)
                controls.append(dict(attempt=attempt, returncode=result.returncode,
                                     sigpipe=result.returncode == -signal.SIGPIPE))
            assert any(c['sigpipe'] for c in controls), 'Original module did not reproduce the SIGPIPE regression'
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)
        key.unlink()
    report = dict(accepted=True, source_sha=os.environ['GITHUB_SHA'], run_id=os.environ['GITHUB_RUN_ID'],
                  attempt=os.environ['GITHUB_RUN_ATTEMPT'], profile=args.profile, checks=checks,
                  baseline_source='0889f7d1e9a537c6c1b05456547e016b26e1cd85' if args.baseline else None,
                  original_sigpipe_controls=controls, consumer_sha256=digest(probe),
                  complete_product=False, physical_device_execution=False,
                  scope='installed WebDAV reset-peer and signal-boundary candidate; no SDK or host grant')
    (args.out / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
