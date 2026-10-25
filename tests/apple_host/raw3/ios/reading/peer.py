"""Read the fixed real macOS ZIP only inside Actions; never rewrite its wires."""
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import sqlite3
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / 'tools'))
from check_parallel_integration import fetch, download_artifact_zip

SOURCE = '15dab6b2270dc296ed6239db67ced2e22d255e65'
RUN, ATTEMPT, ARTIFACT = 40196978163, 1, 12600789926
ZIP_SHA = '92be56ffa04d7c334d4811a42821a314089b4f8ae01746f0dfdf456b5eab9bd5'


def load(directory, resources):
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    run = fetch('actions/runs/' + str(RUN))
    assert run['head_sha'] == SOURCE and run['conclusion'] == 'success'
    jobs = fetch(f'actions/runs/{RUN}/attempts/{ATTEMPT}/jobs?per_page=100')['jobs']
    assert {job['id'] for job in jobs if job['conclusion'] == 'success'} == {121179826434, 121186031984}
    artifact = fetch('actions/artifacts/' + str(ARTIFACT))
    assert artifact['name'] == 'apple-raw3-native-40196978163-1' and not artifact['expired']
    assert artifact['size_in_bytes'] == 77056135 and artifact['digest'] == 'sha256:' + ZIP_SHA
    assert artifact['workflow_run']['head_sha'] == SOURCE and artifact['workflow_run']['id'] == RUN
    assert datetime.fromisoformat(artifact['expires_at'].replace('Z', '+00:00')) > datetime.now(timezone.utc)
    raw = download_artifact_zip(ARTIFACT)
    assert len(raw) == 77056135 and hashlib.sha256(raw).hexdigest() == ZIP_SHA
    directory.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        assert len(archive.namelist()) == len(set(archive.namelist()))
        for name in archive.namelist():
            path = PurePosixPath(name)
            assert not path.is_absolute() and '..' not in path.parts and '\\' not in name and ':' not in name
        result = json.loads(archive.read('result.json'))
        assert result['accepted'] and (result['source_sha'], result['run_id'], result['attempt']) == (SOURCE, str(RUN), str(ATTEMPT))
        for name, entry in result['files'].items():
            data = archive.read(name)
            assert len(data) == entry['bytes'] and hashlib.sha256(data).hexdigest() == entry['sha256']
        manifest_bytes = archive.read('sender-bundle/manifest.json')
        manifest = json.loads(manifest_bytes)
        assert len(manifest['reading_records']) == 11 and len(manifest['originals']) == 4
        originals = {}
        for row in manifest['originals']:
            data = archive.read('sender-bundle/' + row['file'])
            assert len(data) == row['bytes'] and hashlib.sha256(data).hexdigest() == row['sha256']
            originals[row['book_key']] = (row, data)
            if row['format'] == 'txt': (resources / 'RetainedMacRecords.txt').write_bytes(data)
        database_name = 'profiles/source-version-and-NULL-operations/reader-catalog.db'
        database = directory / 'original-mac-operations.db'
        database.write_bytes(archive.read(database_name))
        # The native producer closed the connection before inventory/upload.
        # Copy any retained WAL/SHM too so a readonly read sees that exact state.
        for suffix in ('-wal', '-shm'):
            if database_name + suffix in result['files']:
                Path(str(database) + suffix).write_bytes(archive.read(database_name + suffix))
    connection = sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True)
    try:
        values = connection.execute('SELECT revision_id,CAST(body_json AS BLOB),body_sha256 FROM reader_revisions ORDER BY revision_id').fetchall()
        books = connection.execute('SELECT book_key FROM reader_books ORDER BY book_key').fetchall()
    finally:
        connection.close()
    wires, ids, null_ids, versions = [], {row[0] for row in values}, [], set()
    for revision, wire, expected in values:
        assert hashlib.sha256(wire).hexdigest() == expected
        value = json.loads(wire)
        assert value['id'] == revision and value['version'] == 1 and set(value['parents']) <= ids
        location = (value.get('payload') or {}).get('location')
        if location:
            versions.add(location['anchor_version'])
            if location['anchor_version'] == 3 and location['selector']['exact']['base64'] is None: null_ids.append(revision)
        wires.append((revision, expected, wire))
    assert len(null_ids) == 1 and {1, 2, 3} <= versions and len(books) == 2
    assert all(row[0] in originals for row in books)
    proof = {'source_sha': SOURCE, 'run_id': RUN, 'attempt': ATTEMPT, 'artifact_id': ARTIFACT, 'zip_sha256': ZIP_SHA,
             'manifest_sha256': hashlib.sha256(manifest_bytes).hexdigest(), 'sender_revision_count': len(manifest['revisions']),
             'operations_database_sha256': result['files'][database_name]['sha256'],
             'operations_revision_count': len(wires), 'null_revision_ids': null_ids,
             'wire_sha256': {revision: sha for revision, sha, wire in wires},
             'book_keys': [row[0] for row in books], 'source_versions': sorted(versions)}
    (directory / 'peer.json').write_text(json.dumps(proof, indent=2) + '\n')
    print(json.dumps(proof), flush=True)
    return proof, wires, {key: originals[key] for key, in books}
