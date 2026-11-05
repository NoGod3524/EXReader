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
import sqlite3
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
    loaded = load(previous) if previous is not None else None
    fixture_trust = trust_desktop(cert, 'f04-apple') if sys.platform == 'darwin' else None
    user, password = 'relay-fixture', secrets.token_hex(32)
    authorization = 'Basic ' + base64.b64encode((user + ':' + password).encode()).decode()
    try:
        dav = Dav(cert, private, authorization)
    except BaseException:
        if fixture_trust: untrust_desktop(fixture_trust)
        private.unlink(missing_ok=True)
        raise
    dav.fixture_trust = fixture_trust
    dav.certificate_sha256 = hashlib.sha256(cert.read_bytes()).hexdigest()
    dav.prior_entries, dav.prior_directories, dav.previous_sha256 = {}, set(), None
    dav.previous = None
    if previous is not None:
        state, dav.previous_sha256 = loaded
        dav.previous = state
        dav.directories = set(state['directories'])
        dav.entries = {path: base64.b64decode(value['body'], validate=True)
                       for path, value in state['entries'].items()}
        dav.prior_entries, dav.prior_directories = dict(dav.entries), set(dav.directories)
    return dav, user, password


def save(dav, folder, phase, data):
    folder = Path(folder)
    contract = json.loads((Path(__file__).resolve().parent / 'contract.json').read_text())
    assert phase in contract['phases']
    assert data['passed'] is True and data['checks']
    assert data.get('f04_stage') in ('iphone-android-reading-v1', 'six-host-reading-preparation-v2')
    assert data.get('sdk_version') == '3.42.0'
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
    if getattr(dav, 'fixture_trust', None):
        untrust_desktop(dav.fixture_trust); dav.fixture_trust = None


def retained_rows(database):
    """Read exact stored wires only; never open an SDK owner or write a database."""
    database = Path(database).resolve()
    assert database.is_file()
    with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as db:
        db.execute("PRAGMA query_only=ON")
        rows = db.execute("SELECT revision_id,body_json FROM reader_revisions "
                          "WHERE entity_kind IN ('progress','annotation') ORDER BY revision_id").fetchall()
    result = []
    for revision, wire in rows:
        body = wire.encode("utf-8") if isinstance(wire, str) else bytes(wire)
        value = json.loads(body)
        assert value["id"] == revision
        result.append({"revision_id": revision, "raw_base64": base64.b64encode(body).decode(),
                       "sha256": hashlib.sha256(body).hexdigest()})
    return result


def trust_desktop(certificate, prefix):
    """Ephemeral Actions runner trust; identity returned for exact cleanup."""
    identity()
    certificate = Path(certificate).resolve()
    if os.name == "nt":
        fingerprint = subprocess.check_output(["openssl", "x509", "-in", str(certificate),
                        "-noout", "-fingerprint", "-sha1"], text=True).strip().split("=", 1)[1].replace(":", "")
        assert len(fingerprint) == 40 and all(c in "0123456789ABCDEFabcdef" for c in fingerprint)
        subprocess.run(["certutil", "-addstore", "-f", "Root", str(certificate)],
                       check=True, capture_output=True)
        return {"kind": "windows", "fingerprint": fingerprint}
    if sys.platform.startswith("linux"):
        target = "/usr/local/share/ca-certificates/" + prefix + ".crt"
        subprocess.run(["sudo", "cp", str(certificate), target], check=True, capture_output=True)
        subprocess.run(["sudo", "update-ca-certificates"], check=True, capture_output=True)
        return {"kind": "linux", "path": target}
    if sys.platform == "darwin":
        fingerprint = subprocess.check_output(["openssl", "x509", "-in", str(certificate),
                        "-noout", "-fingerprint", "-sha1"], text=True).strip().split("=", 1)[1].replace(":", "")
        assert len(fingerprint) == 40 and all(c in "0123456789ABCDEFabcdef" for c in fingerprint)
        subprocess.run(["sudo", "security", "add-trusted-cert", "-d", "-r", "trustRoot",
                        "-k", "/Library/Keychains/System.keychain", str(certificate)],
                       check=True, capture_output=True)
        return {"kind": "macos", "fingerprint": fingerprint}
    raise AssertionError("Unsupported desktop fixture trust platform")


def untrust_desktop(trust):
    identity()
    if trust["kind"] == "windows":
        subprocess.run(["certutil", "-delstore", "Root", trust["fingerprint"]],
                       check=True, capture_output=True)
    elif trust["kind"] == "linux":
        assert trust["path"] in ("/usr/local/share/ca-certificates/f04-gtk.crt",)
        subprocess.run(["sudo", "rm", "--", trust["path"]], check=True, capture_output=True)
        subprocess.run(["sudo", "update-ca-certificates"], check=True, capture_output=True)
    elif trust["kind"] == "macos":
        subprocess.run(["sudo", "security", "delete-certificate", "-Z", trust["fingerprint"],
                        "/Library/Keychains/System.keychain"], check=True, capture_output=True)
    else:
        raise AssertionError("Unknown fixture trust identity")


def input_metadata(state):
    """Protocol data for a real receiver, selected from immutable service bytes."""
    wires = []
    for path, item in state["entries"].items():
        if "/revisions/" in path:
            raw = base64.b64decode(item["body"], validate=True)
            assert hashlib.sha256(raw).hexdigest() == item["sha256"]
            wires.append(json.loads(raw))
    original = json.loads((Path(__file__).resolve().parent / "contract.json").read_text())["original"]
    key = original["format"] + ":" + original["sha256"]
    def head(kind):
        history = [v for v in wires if v["entity_kind"] == kind and v["entity_key"] == key]
        parents = {p for v in history for p in v["parents"]}
        heads = [v for v in history if v["id"] not in parents]
        assert len(heads) == 1 and heads[0].get("payload"), "receiver requires SAFE unique " + kind
        assert all(p in {v["id"] for v in history} for v in history for p in v["parents"])
        return heads[0]
    progress, book = head("progress"), head("book")
    location = progress["payload"]["location"]
    assert location["mode"] == "epub_chapter"
    translated = dict(location["selector"], part=location["part"], path=location["part_path"],
                      head=progress["id"])
    return dict(original_sha256=original["sha256"], original_bytes=original["bytes"],
                book_identity=key, location=translated, remote_title=book["payload"]["title"])


def finish_cleanup(actions, report, destination):
    """Attempt every independent cleanup; do not replace an active test failure."""
    active_failure = sys.exc_info()[0] is not None
    failures = []
    for label, action in actions:
        try:
            action()
        except BaseException as error:
            failures.append({"action": label, "error": type(error).__name__ + ": " + str(error)})
    report["cleanup_errors"] = failures
    if failures or active_failure:
        report["passed"] = False
        # A snapshot sealed before app-close must not remain admissible if the
        # producer subsequently failed. Remove only this phase's own result.
        try:
            Path(destination).with_name("state.json").unlink(missing_ok=True)
        except BaseException as error:
            failures.append({"action": "invalidate-failed-state", "error": type(error).__name__ + ": " + str(error)})
    try:
        Path(destination).write_text(json.dumps(report, ensure_ascii=False, indent=2))
    except BaseException as error:
        failures.append({"action": "write-result", "error": type(error).__name__ + ": " + str(error)})
        report["passed"] = False
        try:
            Path(destination).with_name("state.json").unlink(missing_ok=True)
        except BaseException as invalidation:
            failures.append({"action": "invalidate-unreported-state", "error": type(invalidation).__name__ + ": " + str(invalidation)})
    if failures and not active_failure:
        raise RuntimeError("F04 cleanup failed: " + json.dumps(failures))
