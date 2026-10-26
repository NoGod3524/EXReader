"""Authenticate this run's independent normal-flow evidence, never old suites."""
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import zipfile

out = Path('build/cloud-ui-summary'); out.mkdir(parents=True, exist_ok=True)
result = dict(accepted=False, source=os.environ['GITHUB_SHA'], run=os.environ['GITHUB_RUN_ID'],
              attempt=os.environ['GITHUB_RUN_ATTEMPT'], problems=[], scope='normal cloud UI only')
try:
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    assert os.environ['WINDOWS_RESULT'] == 'success'
    artifact = os.environ['ARTIFACT_ID']; digest = os.environ['ARTIFACT_DIGEST'].removeprefix('sha256:')
    api = 'repos/%s/actions/artifacts/%s' % (os.environ['GITHUB_REPOSITORY'], artifact)
    meta = json.loads(subprocess.check_output(['gh', 'api', api], text=True))
    assert str(meta['workflow_run']['id']) == result['run'] and meta['workflow_run']['head_sha'] == result['source']
    assert meta['name'] == 'windows-cloud-ui-%s-%s' % (result['run'], result['attempt']) and not meta['expired']
    raw = subprocess.check_output(['gh', 'api', api + '/zip'], timeout=360)
    assert len(raw) == meta['size_in_bytes'] and hashlib.sha256(raw).hexdigest() == digest and meta['digest'] == 'sha256:' + digest
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        assert len(z.namelist()) == len(set(z.namelist()))
        def read(path): return z.read(path)
        def sha(path): return hashlib.sha256(read(path)).hexdigest()
        report = json.loads(read('cloud-ui/report.json'))
        built = json.loads(read('c09/report.json'))
        assert report['accepted'] and not report['problems'] and report['source_sha'] == result['source']
        assert str(report['run_id']) == result['run'] and str(report['attempt']) == result['attempt']
        assert built['source_sha'] == result['source'] and str(built['run_id']) == result['run'] and str(built['attempt']) == result['attempt']
        assert built['cloud_content_bound'] and built['program_sha256'] == report['program_sha256'] == sha('c09/package/EXReader/EXReader.exe')
        assert report['probe_sha256'] == sha('cloud-readback/cloud-probe.exe')
        assert report['font_sha256'] == sha('c09/package/EXReader/Reader.otf')
        mapping = read('c09/wave3-host/windows-host.map').decode('utf-8', errors='replace')
        assert 'exr_webdav_download_observed' in mapping and 'reader_cloud_import' in mapping
        expected = {'authenticated-https-listing', 'no-implicit-selection', 'directory-navigation',
                    'public-sdk-original-readback', 'duplicate-preserves-state', 'http-failure-preserves-state',
                    'cancel-listing-preserves-state', 'unauthorized-preserves-state', 'authenticated-downloads', 'fixtures-unchanged'}
        inputs = [('One text.txt','sample.txt'),('Two webpage.html','sample.html'),('Three fiction.fb2','sample.fb2'),('Four EPUB.epub','sample.epub'),('Five document.docx','sample.docx'),('Six richtext.rtf','sample.rtf'),('Seven mobi.mobi','sample.mobi'),('Eight PDF.pdf','pdf-public-text.pdf'),('Nine comic.cbz','comic.cbz')]
        expected.update('import-' + fixture for _, fixture in inputs)
        assert set(report['checks']) == expected and len(report['checks']) == len(expected)
        assert report['inputs'] == {name: hashlib.sha256((Path('tests/fixtures') / fixture).read_bytes()).hexdigest() for name, fixture in inputs}
        audit = report['public_readback']; assert audit['ok'] == 1 and len(audit['books']) == len(inputs)
        assert all(book['read_ok'] == 1 for book in audit['books'])
        assert {sha('cloud-ui/readback/book-%d.bin' % book['id']) for book in audit['books']} == set(report['inputs'].values())
        assert report['server']['base'].startswith('https://127.0.0.1:')
        assert report['server']['certificate_sha256'] == sha('cloud-ui/certificates/server.crt')
        assert report['server']['implementation_sha256'] == hashlib.sha256(Path('tests/reader_windows_account/check_account_ui.py').read_bytes()).hexdigest()
        assert any(r['method'] == 'PROPFIND' and r['authenticated'] for r in report['requests'])
        assert sum(r['method'] == 'GET' and r['authenticated'] for r in report['requests']) >= len(inputs)
        assert read('cloud-ui/cloud-receipts.bmp').startswith(b'BM')
        result.update(accepted=True, checks=report['checks'], program_sha256=report['program_sha256'], probe_sha256=report['probe_sha256'],
                      server=report['server'], artifact=dict(id=artifact, digest=digest, size=meta['size_in_bytes']),
                      build_accepted=built['accepted'], build_failures=built['failures'],
                      dependencies={p: subprocess.check_output(['git', 'rev-parse', result['source'] + ':' + p], text=True).strip()
                                    for p in ('apps/reader/cloud-import', 'extras/webdav', 'extras/sideload', 'apps/reader/desktop', 'src', 'include')})
except Exception as error:
    result['problems'].append(type(error).__name__ + ': ' + str(error))
(out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result), flush=True)
if not result['accepted']: raise SystemExit('Normal cloud UI evidence rejected')
