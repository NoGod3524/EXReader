"""Read actual GTK SDK originals from the authenticated run using public SDK APIs."""
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import zipfile
assert os.environ.get('GITHUB_ACTIONS') == 'true'
repo = 'repos/' + os.environ['GITHUB_REPOSITORY'] + '/'
artifact_id = int(os.environ.get('VERIFY_ARTIFACT', '12681039806'))
source = os.environ.get('VERIFY_SOURCE', '034a4a38d3818f1b24889aeeb04d6f3167ef4095')
run_id = int(os.environ.get('VERIFY_RUN', '40388334083'))
artifact = json.loads(subprocess.check_output(['gh', 'api', repo + 'actions/artifacts/' + str(artifact_id)]))
raw = subprocess.check_output(['gh', 'api', repo + 'actions/artifacts/' + str(artifact_id) + '/zip'])
assert artifact['workflow_run']['head_sha'] == source and artifact['workflow_run']['id'] == run_id
assert len(raw) == artifact['size_in_bytes'] and 'sha256:' + hashlib.sha256(raw).hexdigest() == artifact['digest']
out = Path('build/android-gtk-sdk-originals');out.mkdir(parents=True, exist_ok=True)
report = {'accepted': False, 'run_id': run_id, 'source_sha': source, 'books': []}
try:
    with zipfile.ZipFile(io.BytesIO(raw)) as z, tempfile.TemporaryDirectory() as temp:
        names = z.namelist(); assert len(names) == len(set(names))
        def read(suffix):
            name, = [n for n in names if n == suffix or n.endswith('/' + suffix)]
            return z.read(name)
        manifest = json.loads(read('sender/bundle/manifest.json'))
        desktop = json.loads(read('android-real-dav/gtk/result.json'))
        assert desktop['accepted'] is True and desktop['source_sha'] == report['source_sha']
        folder = Path(temp)
        for suffix in ('library.sqlite', 'library.sqlite-wal', 'library.sqlite-shm'):
            matches = [n for n in names if n.endswith('/android-real-dav/gtk/profile/' + suffix)]
            assert len(matches) <= 1
            if matches: (folder / suffix).write_bytes(z.read(matches[0]))
        assert (folder / 'library.sqlite').is_file()
        for original in manifest['originals']:
            row, = [b for b in desktop['books'] if b['role'] == original['role'] and b['book_key'] == original['book_key']]
            target = folder / (original['role'] + '.bin')
            process = subprocess.run(['source/build/interop-sdk-inspect/received-sdk-inspect',
                                      str(folder / 'library.sqlite'), str(row['sdk_book_id']), str(target)],
                                     capture_output=True, text=True, timeout=120)
            assert process.returncode == 0, process.stderr
            observed = json.loads(process.stdout); data = target.read_bytes()
            assert data == read('sender/bundle/' + original['file'])
            assert len(data) == original['bytes'] and hashlib.sha256(data).hexdigest() == original['sha256']
            report['books'].append({'role': original['role'], 'book_key': original['book_key'],
                                    'sdk_book_id': row['sdk_book_id'], 'bytes': len(data),
                                    'sha256': original['sha256'], 'sdk_inspector': observed})
    report['accepted'] = True
finally:
    (out / 'result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report, ensure_ascii=False), flush=True)
sys.exit(0 if report['accepted'] else 1)
