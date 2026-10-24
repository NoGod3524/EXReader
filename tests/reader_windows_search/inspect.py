"""Read a preserved test artifact in Actions; never grant acceptance."""
import hashlib
import io
import json
import os
import sqlite3
import tempfile
from pathlib import Path
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
from check_parallel_integration import download_artifact_zip, fetch, require

require(os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only')
identity = int(os.environ['INSPECT_ARTIFACT'])
meta = fetch('actions/artifacts/%d' % identity)
require(not meta['expired'] and meta['size_in_bytes'] > 0, 'expired or empty artifact')
require(meta['name'].startswith('reader-windows-search-initial-'), 'unexpected artifact family')
with tempfile.TemporaryFile() as stream:
    download_artifact_zip(identity, stream);stream.seek(0);raw = stream.read()
require(len(raw) == meta['size_in_bytes'] and 'sha256:' + hashlib.sha256(raw).hexdigest() == meta['digest'], 'ZIP differs')
print(json.dumps({'diagnostic_only': True, 'accepted': False, 'artifact_id': identity,
                  'source': meta['workflow_run']['head_sha'], 'run': meta['workflow_run']['id'],
                  'bytes': len(raw), 'digest': meta['digest']}), flush=True)
with zipfile.ZipFile(io.BytesIO(raw)) as bundle:
    for name in bundle.namelist():
        if name.endswith(('application.log', 'search-ui.json')):
            print('PRESERVED', name, bundle.read(name).decode('utf-8', errors='replace')[-16000:], flush=True)
        if name.endswith('profile/library.sqlite'):
            with tempfile.TemporaryDirectory() as scratch:
                database = Path(scratch) / 'library.sqlite';database.write_bytes(bundle.read(name))
                with sqlite3.connect('file:' + database.as_posix() + '?mode=ro', uri=True) as connection:
                    print('PRESERVED SDK rows', connection.execute('SELECT id,format,title,position FROM books').fetchall(), flush=True)
