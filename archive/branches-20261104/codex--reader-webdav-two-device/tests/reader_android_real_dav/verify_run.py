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
RUN = int(os.environ.get('VERIFY_RUN', '40388334083'))
SOURCE = os.environ.get('VERIFY_SOURCE', '034a4a38d3818f1b24889aeeb04d6f3167ef4095')
ARTIFACT = int(os.environ.get('VERIFY_ARTIFACT', '12681039806'))
BIDIRECTIONAL = os.environ.get('VERIFY_BIDIRECTIONAL') == 'true'
EXPANDED = os.environ.get('VERIFY_EXPANDED') == 'true'
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
    assert result['desktop_receiver'] is BIDIRECTIONAL and result['bidirectional'] is BIDIRECTIONAL
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
        if BIDIRECTIONAL:
            reverse = result['gtk_reverse_records']
            if EXPANDED:
                expected = {(role, kind) for role in ('txt', 'epub', 'pdf', 'cbz') for kind in ('progress', 'bookmark')}
                expected |= {(role, 'highlight') for role in ('txt', 'epub', 'pdf')}
                assert len(reverse) == 11 and {(row['role'], row['kind']) for row in reverse} == expected
            else:
                assert len(reverse) == 2 and {row['kind'] for row in reverse} == {'progress', 'annotation'}
            assert reverse == desktop['reverse_records'] and desktop['gtk_reverse_uploaded'] is True
            for row in reverse:
                wire = read('android-real-dav/gtk/' + row['file'])
                assert hashlib.sha256(wire).hexdigest() == row['sha256']
                stored, = db.execute('SELECT CAST(body_json AS BLOB) FROM reader_revisions WHERE revision_id=?', (row['id'],)).fetchone()
                assert stored == wire
                envelope = json.loads(wire)
                assert envelope['id'] == row['id'] and envelope['entity_kind'] == ('progress' if row['kind'] == 'progress' else 'annotation')
                assert envelope['payload']['location']['parser_version'] == '3.41.0'
                if EXPANDED:
                    loc = envelope['payload']['location']
                    assert envelope['payload']['book_key'] == row['book_key'] and loc['mode'] == row['mode']
                    assert loc['selector']['start'] == row['start'] and loc['selector']['end'] == row['end']
                    assert (row['end'] > row['start']) == (row['kind'] == 'highlight')
                    if row['mode'] == 'epub_chapter': assert loc['part'] == row['part'] and loc['part_path'] == row['part_path']
                    if row['mode'] == 'fixed_page': assert loc['page'] == row['page'] and loc['page_id'] == row['page_id']
            reverse_report = json.loads(read('android-real-dav/reverse-record-report.json'))
            reverse_sync = json.loads(read('android-real-dav/reverse-sync-report.json'))
            assert reverse_report['source_sha'] == SOURCE and reverse_report['run_id'] == str(RUN) and reverse_report['attempt'] == '1'
            assert reverse_report['passed'] is True and reverse_sync['passed'] is True
            matches = {item['revision_id']: item for item in reverse_report['resolutions']}
            assert set(matches) == {row['id'] for row in reverse}
            for row in reverse:
                match = matches[row['id']]
                assert match['found'] is True and match['start'] == row['start'] and match['end'] == row['end']
                if EXPANDED: assert match['role'] == row['role'] and match['kind'] == row['kind'] and match['mode'] == {'reflow_global': 1, 'epub_chapter': 2, 'fixed_page': 3}[row['mode']]
            assert b'RECORD_INTEROP_SENDER_PASS' in read('android-real-dav/reverse-record-instrumentation.txt')
            assert b'HOST_SYNC_UI_PASS interop-send' in read('android-real-dav/reverse-sync-instrumentation.txt')
        for row in m['originals']:
            assert db.execute('SELECT count(*) FROM reader_local_books WHERE book_key=?', (row['book_key'],)).fetchone() == (1,)
        db.close()
    access = read('android-real-dav/server/apache/http/access.log').decode().splitlines()
    app = [line for line in access if 'exreader-interop-independent/1' not in line]
    assert any('\tPUT ' in line and '\t201\t' in line for line in app)
    assert any('\tGET ' in line and '\t200\t' in line for line in app)
    if BIDIRECTIONAL:
        for row in reverse:
            leaf = row['id'] + '-' + row['sha256'] + '.json'
            assert any('\tPUT ' in line and leaf in line and '\t201\t' in line for line in app)
            assert any('\tGET ' in line and leaf in line and '\t200\t' in line for line in app)
summary = {'accepted': True, 'source_sha': SOURCE, 'run_id': RUN, 'attempt': 1, 'artifact_id': ARTIFACT,
           'artifact_digest': artifact['digest'], 'android_apk_sha256': sender['apk_sha256'],
           'android_sdk_sha256': sender['sdk_dso_sha256'], 'gtk_program_sha256': desktop['program_sha256'],
           'originals': len(m['originals']), 'revisions': len(m['revisions']), 'found': len(found),
           'service_app_requests': len(app), 'legacy_desktop_receiver_field_incorrect': not BIDIRECTIONAL,
           'actual_desktop_receive': True, 'bidirectional': BIDIRECTIONAL, 'reverse_record_count': (11 if EXPANDED else 2) if BIDIRECTIONAL else 0,
           'reverse_scope': ('four-format progress/bookmark and TXT/EPUB/PDF highlight' if EXPANDED else 'TXT progress and bookmark') if BIDIRECTIONAL else None, 'organization_accepted': False}
out = Path('build/android-gtk-verified');out.mkdir(parents=True, exist_ok=True)
(out / 'result.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps(summary))
