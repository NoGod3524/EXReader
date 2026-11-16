#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""F10 TLS on a private CA beyond loopback (Actions runners only).

A fresh CA signs one server certificate whose only name is a DNS SAN. The
origin listens on the runner's non-loopback IPv4 address and is reached
through names mapped in the hosts file, never through localhost/127.0.0.1.
The product clients (given as --probe=LABEL,EXE[,ARG...]) receive
accept=URL / refuse=URL cases and must exit 0 only when each case matches:

  phase untrusted  CA absent from the platform store: the handshake must be
                   refused and no HTTP request may reach the origin
  phase trusted    CA installed in the platform store: the SAN name succeeds
                   and the origin sees the request arrive from the
                   non-loopback address, while a second name that maps to
                   the same address but is absent from the SAN is refused

The script changes the hosts file, the platform trust store and (Windows)
the firewall, and restores all three, so it refuses to run outside Actions.
Private keys stay in --secrets, outside the uploaded --output directory.
"""
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import sys
import threading
import time

HOST = 'exr-f10.test'
OTHER = 'exr-f10-other.test'
MARK = '# exreader-f10-private-tls'
LISTING = (b'<?xml version="1.0" encoding="utf-8"?><D:multistatus xmlns:D="DAV:"><D:response>'
           b'<D:href>/dav/</D:href><D:propstat><D:prop><D:resourcetype><D:collection/></D:resourcetype>'
           b'</D:prop><D:status>HTTP/1.1 200 OK</D:status></D:propstat></D:response></D:multistatus>')


def run(command, **options):
    return subprocess.run([str(part) for part in command], capture_output=True, text=True, **options)


def must(command, **options):
    result = run(command, **options)
    if result.returncode:
        raise RuntimeError('%s exited %d: %s' % (command[0], result.returncode, (result.stderr or result.stdout).strip()))
    return result


def routed_address():
    """The local IPv4 address a public destination would be reached from."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(('192.0.2.1', 9))  # TEST-NET-1; a UDP connect sends nothing
        return probe.getsockname()[0]
    finally:
        probe.close()


def make_certificates(secrets, public):
    """CA plus one leaf: SAN DNS:HOST only, serverAuth. Returns public paths."""
    ca_key, ca_crt = secrets / 'ca.key', public / 'ca.crt'
    key, request, crt = secrets / 'server.key', secrets / 'server.csr', public / 'server.crt'
    ca_name = 'EXReader F10 private test CA ' + os.urandom(6).hex()
    ca_conf, leaf_conf, extensions = secrets / 'ca.cnf', secrets / 'leaf.cnf', secrets / 'leaf.ext'
    ca_conf.write_text('[req]\ndistinguished_name=dn\nx509_extensions=v3\nprompt=no\n[dn]\nCN=%s\n[v3]\n'
                       'basicConstraints=critical,CA:TRUE\nkeyUsage=critical,keyCertSign,cRLSign\n'
                       'subjectKeyIdentifier=hash\n' % ca_name)
    leaf_conf.write_text('[req]\ndistinguished_name=dn\nprompt=no\n[dn]\nCN=%s\n' % HOST)
    extensions.write_text('subjectAltName=DNS:%s\nbasicConstraints=critical,CA:FALSE\n'
                          'keyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\n' % HOST)
    must(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-sha256', '-days', '2', '-config', ca_conf,
          '-keyout', ca_key, '-out', ca_crt])
    must(['openssl', 'req', '-new', '-newkey', 'rsa:2048', '-nodes', '-sha256', '-config', leaf_conf,
          '-keyout', key, '-out', request])
    must(['openssl', 'x509', '-req', '-sha256', '-days', '2', '-in', request, '-CA', ca_crt, '-CAkey', ca_key,
          '-CAcreateserial', '-extfile', extensions, '-out', crt])
    return ca_name, ca_crt, crt, key


def fingerprint(certificate):
    der = ssl.PEM_cert_to_DER_cert(certificate.read_text())
    return hashlib.sha256(der).hexdigest()


class Origin:
    """HTTPS origin that records handshakes and requests with their peers."""

    def __init__(self, address, certificate, key):
        self.events, self.lock = [], threading.Lock()
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(str(certificate), str(key))
        origin = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'

            def setup(self):
                peer = self.client_address[0]
                self.request.settimeout(20)
                try:
                    self.request = context.wrap_socket(self.request, server_side=True)
                except (OSError, ssl.SSLError) as error:
                    origin.record(kind='handshake_failed', peer=peer, error='%s: %s' % (type(error).__name__, error))
                    raise
                origin.record(kind='handshake_completed', peer=peer, protocol=self.request.version())
                super().setup()

            def log_message(self, *unused):
                pass

            def answer(self):
                length = int(self.headers.get('Content-Length') or 0)
                if length:
                    self.rfile.read(length)
                origin.record(kind='request', peer=self.client_address[0], method=self.command, path=self.path,
                              host=self.headers.get('Host', ''),
                              authorization_sent=self.headers.get('Authorization') is not None)
                body = LISTING if self.command == 'PROPFIND' else b''
                self.send_response(207 if self.command == 'PROPFIND' else 405)
                self.send_header('Content-Type', 'application/xml; charset=utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Connection', 'close')
                self.end_headers()
                self.wfile.write(body)
                self.close_connection = True

            do_PROPFIND = do_GET = do_HEAD = do_OPTIONS = answer

        class Server(ThreadingHTTPServer):
            daemon_threads = True

            def handle_error(self, request, client_address):
                pass  # refused handshakes are recorded by Handler.setup

        self.server = Server((address, 0), Handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def record(self, **event):
        with self.lock:
            event['index'] = len(self.events)
            self.events.append(event)

    def mark(self):
        with self.lock:
            return len(self.events)

    def since(self, mark):
        time.sleep(0.5)  # let handler threads finish recording
        with self.lock:
            return list(self.events[mark:])

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def hosts_path():
    if os.name == 'nt':
        return Path(os.environ['SystemRoot']) / 'System32' / 'drivers' / 'etc' / 'hosts'
    return Path('/etc/hosts')


def map_names(address):
    lines = ''.join('%s %s %s\n' % (address, name, MARK) for name in (HOST, OTHER))
    if os.name == 'nt':
        with open(hosts_path(), 'a', encoding='ascii') as handle:
            handle.write('\n' + lines)
    else:
        must(['sudo', 'tee', '-a', hosts_path()], input='\n' + lines)


def unmap_names():
    kept = ''.join(line for line in hosts_path().read_text(encoding='utf-8', errors='replace').splitlines(True)
                   if MARK not in line)
    if os.name == 'nt':
        hosts_path().write_text(kept, encoding='utf-8')
    else:
        must(['sudo', 'tee', hosts_path()], input=kept)


def trust(ca):
    if os.name == 'nt':
        must(['certutil', '-addstore', '-f', 'Root', ca])
    else:
        must(['sudo', 'cp', ca, '/usr/local/share/ca-certificates/exreader-f10-private-tls.crt'])
        must(['sudo', 'update-ca-certificates'])


def untrust(ca_name):
    if os.name == 'nt':
        run(['certutil', '-delstore', 'Root', ca_name])
    else:
        run(['sudo', 'rm', '-f', '/usr/local/share/ca-certificates/exreader-f10-private-tls.crt'])
        run(['sudo', 'update-ca-certificates', '--fresh'])


def firewall(port, enable):
    if os.name != 'nt':
        return
    name = 'name=exreader-f10-private-tls'
    if enable:
        must(['netsh', 'advfirewall', 'firewall', 'add', 'rule', name, 'dir=in', 'action=allow', 'protocol=TCP',
              'localport=%d' % port])
    else:
        run(['netsh', 'advfirewall', 'firewall', 'delete', 'rule', name])


def python_client(address, port, name, ca):
    """Reference TLS client: which verification result does this origin give?"""
    context = ssl.create_default_context(cafile=str(ca) if ca else None)
    try:
        with socket.create_connection((address, port), timeout=10) as raw:
            with context.wrap_socket(raw, server_hostname=name) as secure:
                return 'verified ' + secure.version()
    except ssl.SSLCertVerificationError as error:
        return 'refused: ' + (error.verify_message or str(error))
    except (OSError, ssl.SSLError) as error:
        return 'error: %s' % error


def run_probes(probes, cases, output, phase):
    results = []
    for label, command in probes:
        completed = run(command + cases, timeout=180)
        (output / ('%s-%s.txt' % (phase, label))).write_text(completed.stdout + completed.stderr, encoding='utf-8')
        results.append({'probe': label, 'command': [Path(command[0]).name] + command[1:] + cases,
                        'exit': completed.returncode, 'output': completed.stdout.strip()})
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--secrets', type=Path, required=True)
    parser.add_argument('--probe', action='append', required=True, metavar='LABEL,EXE[,ARG...]')
    arguments = parser.parse_args()
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        sys.exit('refusing to change the hosts file and the trust store outside GitHub Actions')
    output, secrets = arguments.output.resolve(), arguments.secrets.resolve()
    output.mkdir(parents=True, exist_ok=True)
    secrets.mkdir(parents=True, exist_ok=True)
    probes = [(probe[0], [str(Path(probe[1]).resolve())] + probe[2:])
              for probe in (value.split(',') for value in arguments.probe)]
    checks = []

    def check(name, passed, detail):
        checks.append({'name': name, 'pass': bool(passed), 'detail': detail})
        print('%s %s: %s' % ('PASS' if passed else 'FAIL', name, detail), flush=True)

    address = routed_address()
    check('origin_address_is_not_loopback', not address.startswith('127.') and address != '0.0.0.0', address)
    ca_name, ca, certificate, key = make_certificates(secrets, output)
    origin = Origin(address, certificate, key)
    url, other_url = 'https://%s:%d/dav/' % (HOST, origin.port), 'https://%s:%d/dav/' % (OTHER, origin.port)
    report = {'probe': 'private-tls', 'source_sha': os.environ.get('GITHUB_SHA'), 'run_id': os.environ.get('GITHUB_RUN_ID'),
              'attempt': os.environ.get('GITHUB_RUN_ATTEMPT'), 'platform': sys.platform, 'address': address,
              'port': origin.port, 'name': HOST, 'other_name': OTHER, 'ca_subject': ca_name,
              'ca_sha256': fingerprint(ca), 'server_sha256': fingerprint(certificate),
              'server_subject_alt_name': 'DNS:' + HOST, 'phases': {}}
    trusted = False
    try:
        firewall(origin.port, True)
        map_names(address)
        resolved = {name: sorted({item[4][0] for item in socket.getaddrinfo(name, origin.port, socket.AF_INET)})
                    for name in (HOST, OTHER)}
        check('names_resolve_to_the_non_loopback_address', all(value == [address] for value in resolved.values()),
              json.dumps(resolved))
        # The harness itself, through Python's verifier, before any product client runs.
        reference = {'ca_given_san_name': python_client(address, origin.port, HOST, ca),
                     'ca_given_other_name': python_client(address, origin.port, OTHER, ca),
                     'system_store_before_trust': python_client(address, origin.port, HOST, None)}
        report['reference_client'] = reference
        check('reference_client_agrees_with_the_fixture',
              reference['ca_given_san_name'].startswith('verified') and
              reference['ca_given_other_name'].startswith('refused') and
              reference['system_store_before_trust'].startswith('refused'), json.dumps(reference))

        mark = origin.mark()
        results = run_probes(probes, ['refuse=' + url], output, 'untrusted')
        events = origin.since(mark)
        report['phases']['untrusted'] = {'cases': ['refuse=' + url], 'probes': results, 'origin_events': events}
        for result in results:
            check('untrusted_ca_refused_by_' + result['probe'], result['exit'] == 0, 'exit=%d' % result['exit'])
        requests = [event for event in events if event['kind'] == 'request']
        check('untrusted_ca_no_request_reached_origin', not requests,
              'requests=%d handshakes_failed=%d' % (len(requests), sum(e['kind'] == 'handshake_failed' for e in events)))

        trust(ca)
        trusted = True
        for label, command in probes:
            mark = origin.mark()
            results = run_probes([(label, command)], ['accept=' + url, 'refuse=' + other_url], output, 'trusted')
            events = origin.since(mark)
            report['phases']['trusted-' + label] = {'cases': ['accept=' + url, 'refuse=' + other_url],
                                                    'probes': results, 'origin_events': events}
            check('trusted_ca_accepted_and_other_name_refused_by_' + label, results[0]['exit'] == 0,
                  'exit=%d' % results[0]['exit'])
            requests = [event for event in events if event['kind'] == 'request']
            arrived = [event for event in requests if event['host'].split(':')[0].lower() == HOST]
            check('trusted_request_arrived_from_non_loopback_peer_' + label,
                  bool(arrived) and all(event['peer'] == address for event in arrived),
                  'requests=%d peers=%s' % (len(arrived), sorted({event['peer'] for event in arrived})))
            check('other_name_request_never_reached_origin_' + label,
                  not [event for event in requests if event['host'].split(':')[0].lower() == OTHER],
                  'hosts=%s' % sorted({event['host'] for event in requests}))
            check('no_credential_sent_' + label, not any(event['authorization_sent'] for event in requests),
                  'requests=%d' % len(requests))
    except Exception as error:
        check('harness_completed', False, '%s: %s' % (type(error).__name__, error))
    finally:
        if trusted:
            untrust(ca_name)
        unmap_names()
        firewall(origin.port, False)
        origin.close()
    report['checks'] = checks
    report['accepted'] = bool(checks) and all(item['pass'] for item in checks)
    (output / 'result.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print('private-tls checks=%d failed=%d accepted=%s' % (len(checks), sum(not item['pass'] for item in checks),
                                                          report['accepted']), flush=True)
    return 0 if report['accepted'] else 1


if __name__ == '__main__':
    sys.exit(main())
