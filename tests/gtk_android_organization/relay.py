"""Actions-only relay of bytes authored by real apps, never synthetic revisions.

Each job runs a separate HTTPS endpoint. State persists through same-run Actions
artifacts, not through a continuously available or concurrent network service.
"""
import base64
import hashlib
import json
import importlib.util
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location('d23_relay_service', ROOT / 'tests/reader_d23_relay/relay.py')
_service = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_service)
Dav = _service.Dav


def identity():
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'GitHub Actions only'
    return {key: os.environ[value] for key, value in (
        ('source_sha', 'GITHUB_SHA'), ('run_id', 'GITHUB_RUN_ID'),
        ('attempt', 'GITHUB_RUN_ATTEMPT'))}


def load(path, phase=None):
    raw = Path(path).read_bytes()
    state = json.loads(raw)
    assert state['schema'] == 1
    assert all(state[key] == value for key, value in identity().items())
    if phase is not None:
        assert state['phase'] == phase
    assert state['data']['passed'] is True
    for path, value in state['entries'].items():
        assert path.startswith('/dav/exreader-sync-v1/')
        body = base64.b64decode(value['body'], validate=True)
        assert hashlib.sha256(body).hexdigest() == value['sha256']
    return state, hashlib.sha256(raw).hexdigest()


def start(folder, previous=None, certificate=None, key=None):
    identity()
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    cert = folder / 'cert.pem'
    private = folder / 'key.pem'
    if certificate is not None:
        assert key is not None
        shutil.copyfile(certificate, cert)
        shutil.copyfile(key, private)
    else:
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048',
            '-nodes', '-days', '1', '-keyout', str(private), '-out', str(cert),
            '-subj', '/CN=127.0.0.1', '-addext',
            'subjectAltName=IP:127.0.0.1'], check=True, capture_output=True)
    if sys.platform.startswith('linux') and certificate is None:
        subprocess.run(['sudo','cp',str(cert),'/usr/local/share/ca-certificates/exr-organization-relay.crt'],check=True)
        subprocess.run(['sudo','update-ca-certificates'],check=True,capture_output=True)
    if sys.platform == 'darwin':
        sys.path.insert(0, str(ROOT / 'tests/webdav'))
        from cloud_native import trust_fixture_certificates
        trust_fixture_certificates((cert,), 'apple-android-relay-')
    user, password = 'relay-fixture', secrets.token_hex(32)
    authorization = 'Basic ' + base64.b64encode((user + ':' + password).encode()).decode()
    dav = Dav(cert, private, authorization)
    dav.certificate_sha256 = hashlib.sha256(cert.read_bytes()).hexdigest()
    dav.prior_entries, dav.prior_directories, dav.previous_sha256 = {}, set(), None
    dav.previous = None
    if previous is not None:
        state, dav.previous_sha256 = load(previous)
        dav.previous = state
        dav.directories = set(state['directories'])
        dav.entries = {path: base64.b64decode(value['body'], validate=True)
                       for path, value in state['entries'].items()}
        dav.prior_entries, dav.prior_directories = dict(dav.entries), set(dav.directories)
    return dav, user, password


def save(dav, folder, phase, data):
    folder = Path(folder)
    assert phase in ('gtk-first', 'android', 'gtk-return', 'android-final')
    assert data['passed'] is True and data['checks']
    assert dav.prior_directories.issubset(dav.directories)
    assert all(dav.entries.get(path) == body for path, body in dav.prior_entries.items())
    assert dav.requests and all(row['authenticated'] for row in dav.requests)
    snapshot = {'schema': 1, **identity(), 'phase': phase,
        'previous_sha256': dav.previous_sha256,
        'server': {'base': dav.base,
            'certificate_sha256': dav.certificate_sha256,
            'implementation_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'dav_implementation_sha256': hashlib.sha256((ROOT / 'tests/reader_d23_relay/relay.py').read_bytes()).hexdigest()},
        'directories': sorted(dav.directories),
        'entries': {path: {'sha256': hashlib.sha256(body).hexdigest(),
                         'body': base64.b64encode(body).decode()}
                    for path, body in sorted(dav.entries.items())},
        'data': data}
    (folder / 'state.json').write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding='utf-8')
    (folder / 'requests.json').write_text(json.dumps(dav.requests, indent=2), encoding='utf-8')
    dav.server.shutdown()
    dav.server.server_close()
    (folder / 'key.pem').unlink(missing_ok=True)
