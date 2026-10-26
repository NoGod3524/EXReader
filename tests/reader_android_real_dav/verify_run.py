"""Independently authenticate the exact completed two-application run in Actions."""
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
sys.path.insert(0, 'tests/reader_android_record_interop')
from bundle import verify
RUN = 40388334083
SOURCE = '034a4a38d3818f1b24889aeeb04d6f3167ef4095'
ARTIFACT = 12681039806
repo = 'repos/' + os.environ['GITHUB_REPOSITORY'] + '/'
def api(path): return json.loads(subprocess.check_output(['gh', 'api', repo + path]))
record = api('actions/runs/' + str(RUN))
jobs = api('actions/runs/%d/attempts/1/jobs?per_page=100' % RUN)['jobs']
artifact = api('actions/artifacts/' + str(ARTIFACT))
assert record['head_sha'] == SOURCE and record['run_attempt'] == 1 and record['conclusion'] == 'success'
job, = [j for j in jobs if j['name'] == 'android']
assert job['head_sha'] == SOURCE and job['conclusion'] == 'success'
assert artifact['workflow_run']['head_sha'] == SOURCE and artifact['workflow_run']['id'] == RUN and not artifact['expired']
rawzip = subprocess.check_output(['gh', 'api', repo + 'actions/artifacts/%d/zip' % ARTIFACT])
assert len(rawzip) == artifact['size_in_bytes'] and 'sha256:' + hashlib.sha256(rawzip).hexdigest() == artifact['digest']
with zipfile.ZipFile(io.BytesIO(rawzip)) as z:
    names = z.namelist(); assert len(names) == len(set(names))
    def read(suffix):
        name, = [n for n in names if n == suffix or n.endswith('/' + suffix)]
        info = z.getinfo(name); assert 0 < info.file_size <= 160 * 1024 * 1024
        return z.read(name)
    checked = verify(lambda name: read('sender/bundle/' + name))
    m = checked['manifest']; sender = m['sender']
    assert sender['source_sha'] == SOURCE and sender['run_id'] == str(RUN) and sender['attempt'] == '1'
    apk = read('examples/android/app/build/outputs/apk/debug/app-debug.apk')
    assert hashlib.sha256(apk).hexdigest() == sender['apk_sha256']
    with zipfile.ZipFile(io.BytesIO(apk)) as android:
        assert hashlib.sha256(android.read('lib/x86_64/libexreader.so')).hexdigest() == sender['sdk_dso_sha256']
    desktop_exe = read('interop-gtk-package/EXReader-Linux/bin/exreader-linux')
    desktop = json.loads(read('android-real-dav/gtk/result.json'))
    sync = json.loads(read('android-real-dav/sync-report.json'))
    result = json.loads(read('android-real-dav/result.json'))
    for report in (desktop, sync, result):
        assert report['source_sha'] == SOURCE and report['run_id'] == str(RUN) and report['attempt'] == '1'
    assert desktop['accepted'] and desktop['actual_desktop_sync'] and desktop['actual_desktop_receive']
    assert desktop['program_sha256'] == hashlib.sha256(desktop_exe).hexdigest() == result['gtk_program_sha256']
    assert sync['passed'] and all(x['pass'] for x in sync['checks']) and result['android_activity_sync'] and result['actual_desktop_receive']
    assert result['desktop_receiver'] is False and result['bidirectional'] is False
    selected = {r['revision_id']: r for r in m['reading_records']}
    found = {}
    for book in desktop['books']:
        for rid, match in book['resolutions'].items():
            assert rid in selected and selected[rid]['role'] == book['role'] and match['status'] == 0 and match['state'] == 1
            assert match['start'] == int(selected[rid]['capture']['numbers'][2]) and match['end'] == int(selected[rid]['capture']['numbers'][3])
            found[rid] = match
    assert len(desktop['books']) == 4 and set(found) == set(selected) and len(found) == 11
    with tempfile.TemporaryDirectory() as temp:
        prefix = 'android-real-dav/gtk/profile/'
        for name in names:
            if prefix in name:
                suffix = name.split(prefix, 1)[1]
                if suffix in ('library.sqlite.product.sqlite', 'library.sqlite.product.sqlite-wal', 'library.sqlite.product.sqlite-shm'):
                    (Path(temp) / suffix).write_bytes(z.read(name))
        db = sqlite3.connect(Path(temp) / 'library.sqlite.product.sqlite')
        for row in m['revisions']:
            data, = db.execute('SELECT CAST(body_json AS BLOB) FROM reader_revisions WHERE revision_id=?', (row['id'],)).fetchone()
            assert data == read('sender/bundle/' + row['file'])
        for row in m['originals']:
            assert db.execute('SELECT count(*) FROM reader_local_books WHERE book_key=?', (row['book_key'],)).fetchone() == (1,)
        db.close()
    access = read('android-real-dav/server/apache/http/access.log').decode().splitlines()
    app = [line for line in access if 'exreader-interop-independent/1' not in line]
    assert any('\tPUT ' in line and '\t201\t' in line for line in app)
    assert any('\tGET ' in line and '\t200\t' in line for line in app)
summary = {'accepted': True, 'source_sha': SOURCE, 'run_id': RUN, 'attempt': 1, 'artifact_id': ARTIFACT,
           'artifact_digest': artifact['digest'], 'android_apk_sha256': sender['apk_sha256'],
           'android_sdk_sha256': sender['sdk_dso_sha256'], 'gtk_program_sha256': desktop['program_sha256'],
           'originals': len(m['originals']), 'revisions': len(m['revisions']), 'found': len(found),
           'service_app_requests': len(app), 'legacy_desktop_receiver_field_incorrect': True,
           'actual_desktop_receive': True, 'bidirectional': False, 'organization_accepted': False}
out = Path('build/android-gtk-verified');out.mkdir(parents=True, exist_ok=True)
(out / 'result.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps(summary))
