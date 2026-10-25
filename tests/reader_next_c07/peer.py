"""Actions-only: authenticate the same-run actual macOS sender ZIP and prepare Android's peer inputs.

Writes build/c07/peer/{bundle,null-bundle,attestation.json,https-sent} in the layout consumed
unchanged by tests/reader_android_raw3/run_ui.py --apple-peer.
"""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[0] / 'reader_android_raw3'))
from bundle import verify, verify_null, parse  # noqa: E402
import fetch  # noqa: E402

assert os.environ.get('GITHUB_ACTIONS') == 'true'
PDF = '5627a430fa04cbe11d38eb2682e336ef21e147d445753ed46ed11a7d5e3167cc'


def main():
    out = Path('build/c07/peer')
    out.mkdir(parents=True, exist_ok=False)
    root = Path('build/c07/mac-sender')
    artifact, raw = fetch.download('c07-mac-sender', root)
    result = parse((root / 'result.json').read_bytes())
    ident = fetch.IDENTITY
    assert result['accepted'] and all(str(result[k]) == str(v) for k, v in ident.items())
    for name, declared in result['files'].items():
        data = (root / name).read_bytes()
        assert len(data) == declared['bytes'] and hashlib.sha256(data).hexdigest() == declared['sha256'], name
    verified = verify(lambda name: (root / 'sender-bundle' / name).read_bytes())
    manifest = verified['manifest']
    sender = manifest['sender']
    assert sender['platform'] == 'macos' and verified['originals'] == 4 and verified['reading_records'] == 11
    assert all(str(sender[k]) == str(v) for k, v in ident.items())
    assert hashlib.sha256((root / 'sender-bundle/proofs/program').read_bytes()).hexdigest() == sender['program_sha256']
    assert hashlib.sha256((root / 'sender-bundle/proofs/sdk.dylib').read_bytes()).hexdigest() == sender['sdk_dso_sha256']
    pdf = next(row for row in manifest['originals'] if row['role'] == 'pdf')
    assert pdf['bytes'] == 8845 and pdf['sha256'] == PDF
    # The four originals must be the frozen common bytes, not a lookalike.
    common = parse((Path('build/c07/common-fixtures/common.json')).read_bytes())['originals']
    assert {row['role']: row['sha256'] for row in common} == {row['role']: row['sha256'] for row in manifest['originals']}
    # What the real Mac Session actually PUT over HTTPS must be the same bytes Android will be served.
    sent = parse((root / 'https-sent/index.json').read_bytes())
    assert sent['actual_host_account_session'] and sent['tls_trust_checked'] and sent['completed_shards'] == 256
    for row in manifest['revisions']:
        match = [e for e in sent['entries'] if e['path'].endswith('/' + row['id'] + '-' + row['sha256'] + '.json')]
        assert len(match) == 1 and match[0]['sha256'] == row['sha256']
        assert (root / 'https-sent' / match[0]['file']).read_bytes() == (root / 'sender-bundle' / row['file']).read_bytes()
    for row in manifest['originals']:
        match = [e for e in sent['entries'] if e['sha256'] == row['sha256'] and '/objects/' in e['path']]
        assert len(match) == 1 and (root / 'https-sent' / match[0]['file']).read_bytes() == (root / 'sender-bundle' / row['file']).read_bytes()
    # Normal 11-record bundle consumed in place by the original Android runner.
    bundle = out / 'bundle'
    for name in verified['files'] + ['proofs/program', 'proofs/sdk.dylib']:
        target = bundle / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((root / 'sender-bundle' / name).read_bytes())
    # Mac NULL graph: extracted read-only from the actual producer database of this run; no wire rewritten.
    database_name = 'profiles/source-version-and-NULL-operations/reader-catalog.db'
    database = (root / database_name).read_bytes()
    identity = result['files'][database_name]
    assert len(database) == identity['bytes'] and hashlib.sha256(database).hexdigest() == identity['sha256']
    negative = out / 'null-bundle'
    negative.mkdir()
    (negative / 'origin-catalog.db').write_bytes(database)
    sidecars = {}
    for suffix in ('-wal', '-shm'):
        name = database_name + suffix
        if name in result['files']:
            body = (root / name).read_bytes()
            declared = result['files'][name]
            assert len(body) == declared['bytes'] and hashlib.sha256(body).hexdigest() == declared['sha256']
            (negative / ('origin-catalog.db' + suffix)).write_bytes(body)
            sidecars[suffix] = declared
    with tempfile.TemporaryDirectory() as temporary:
        inspected = Path(temporary) / 'catalog.db'
        inspected.write_bytes(database)
        for suffix in sidecars:
            (Path(temporary) / ('catalog.db' + suffix)).write_bytes((negative / ('origin-catalog.db' + suffix)).read_bytes())
        connection = sqlite3.connect(inspected.resolve().as_uri() + '?mode=ro', uri=True)
        try:
            rows = connection.execute('SELECT revision_id,entity_kind,entity_key,body_sha256,CAST(body_json AS BLOB) FROM reader_revisions').fetchall()
        finally:
            connection.close()
    retained = {}
    for rid, kind, key, digest, body in rows:
        assert isinstance(body, bytes) and hashlib.sha256(body).hexdigest() == digest
        wire = parse(body)
        assert (wire['id'], wire['entity_kind'], wire['entity_key']) == (rid, kind, key)
        retained[rid] = (wire, body, digest)
    nulls = [rid for rid, (wire, body, digest) in retained.items() if wire['entity_kind'] == 'annotation' and wire.get('payload')
             and wire['payload'].get('book_key') == pdf['book_key'] and wire['payload'].get('location', {}).get('anchor_version') == 3
             and wire['payload']['location']['selector']['exact'] == {'base64': None, 'size': 0}]
    null_id, = nulls
    null_wire = retained[null_id][0]
    needed, visiting = set(), set()

    def collect(rid):
        assert rid not in visiting and rid in retained
        if rid in needed:
            return
        visiting.add(rid)
        for parent in retained[rid][0]['parents']:
            collect(parent)
        visiting.remove(rid)
        needed.add(rid)
    collect(null_id)
    for rid, (wire, body, digest) in retained.items():
        if wire['entity_kind'] == 'book' and wire['entity_key'] == pdf['book_key']:
            collect(rid)
    declarations = []
    for rid in sorted(needed):
        wire, body, digest = retained[rid]
        name = 'revisions/' + rid + '.json'
        (negative / name).parent.mkdir(parents=True, exist_ok=True)
        (negative / name).write_bytes(body)
        declarations.append({k: wire[k] for k in ('id', 'entity_kind', 'entity_key', 'parents')} | {'file': name, 'bytes': len(body), 'sha256': digest, 'book_key': pdf['book_key']})
    original_path = negative / pdf['file']
    original_path.parent.mkdir(parents=True, exist_ok=True)
    original_path.write_bytes((root / 'sender-bundle' / pdf['file']).read_bytes())
    null_manifest = {'schema': 1, 'purpose': 'authentic-apple-null-negative', 'sender': sender,
                     'origin_database': {'file': database_name, **identity, 'sidecars': sidecars},
                     'originals': [pdf], 'revisions': declarations, 'null_revision': null_id,
                     'annotation_id': null_wire['payload']['annotation_id']}
    (negative / 'manifest.json').write_text(json.dumps(null_manifest, indent=2) + '\n')
    null_verified = verify_null(lambda name: (negative / name).read_bytes())
    attestation = {**ident, 'artifact': artifact, 'accepted': True, 'manifest_sha256': verified['manifest_sha256'],
                   'originals': verified['originals'], 'revisions': verified['revisions'], 'reading_records': verified['reading_records'],
                   'complete_graph': True, 'original_inventory_verified': True, 'same_run_producer': True, 'actual_native_sender': sender,
                   'null_negative': {k: v for k, v in null_verified.items() if k not in ('manifest', 'files')} | {'origin_database': null_manifest['origin_database']}}
    (out / 'attestation.json').write_text(json.dumps(attestation, indent=2) + '\n')
    print(json.dumps({k: v for k, v in attestation.items() if k != 'actual_native_sender'}), flush=True)


if __name__ == '__main__':
    main()
