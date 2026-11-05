"""Actions-only authentication of the already successful historical producer ZIP."""
import hashlib
import io
import json
import os
from pathlib import Path
import urllib.parse
import urllib.request
import zipfile

assert os.environ.get('GITHUB_ACTIONS') == 'true'
REPO = 'NoGod3524/EXReader'
RUN = 40730939382
SOURCE = '7549bc5a34c98606a899d558b3ec81b4d18b3371'
ARTIFACT = 12835602597
SIZE = 20125020
DIGEST = '674b093f9d92941dbc80248bd4b2fd816bb4180c68dc657b9e32b00b94ba16ca'
MANIFEST = '3d3b78ba016103aee555088de2ef324184107e27b3d9384030fa9e09e27be1f0'
out = Path('build/android340-sender-sealed')
out.mkdir(parents=True, exist_ok=True)

class Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        parsed = urllib.parse.urlparse(newurl)
        assert parsed.scheme == 'https'
        redirected = super().redirect_request(request, fp, code, msg, headers, newurl)
        if parsed.hostname != 'api.github.com':
            redirected.remove_header('Authorization')
        return redirected

opener = urllib.request.build_opener(Redirect())
def fetch(path, binary=False):
    request = urllib.request.Request(f'https://api.github.com/repos/{REPO}/{path}', headers={
        'Authorization': 'Bearer ' + os.environ['GH_TOKEN'], 'Accept': 'application/vnd.github+json'})
    with opener.open(request, timeout=120) as response:
        data = response.read()
    return data if binary else json.loads(data)

def sha(data):
    return hashlib.sha256(data).hexdigest()

run = fetch(f'actions/runs/{RUN}')
assert run['head_sha'] == SOURCE and run['run_attempt'] == 1 and run['conclusion'] == 'success'
assert run['head_branch'] == 'codex/dot-android340-sender-evidence'
item = fetch(f'actions/artifacts/{ARTIFACT}')
assert item['workflow_run']['id'] == RUN and item['workflow_run']['head_sha'] == SOURCE
assert not item['expired'] and item['size_in_bytes'] == SIZE and item['digest'] == 'sha256:' + DIGEST
raw = fetch(f'actions/artifacts/{ARTIFACT}/zip', binary=True)
assert len(raw) == SIZE and sha(raw) == DIGEST
with zipfile.ZipFile(io.BytesIO(raw)) as archive:
    names = archive.namelist()
    assert len(names) == len(set(names))
    assert all(not name.startswith('/') and '..' not in Path(name).parts for name in names)
    manifest_raw = archive.read('manifest.json')
    assert sha(manifest_raw) == MANIFEST
    manifest = json.loads(manifest_raw)
    result = json.loads(archive.read('result.json'))
    assert manifest['accepted'] is True and result['accepted'] is True
    assert manifest['source_sha'] == SOURCE and manifest['run_id'] == str(RUN) and manifest['attempt'] == '1'
    assert manifest['sdk_version'] == '3.40.0' and manifest['sender']['parser_version'] == 'exreader-sdk-3.40.0'
    assert manifest['historical_host_sha'] == '047648865e509d5835b7d6e1389681e314d94e28'
    assert manifest['sdk_sha'] == '9854061be331fe603a1822d9b2b36ee357154927'
    entries = []
    for row in manifest['originals'] + manifest['revisions'] + manifest['original_capture_requests'] + [manifest['sender']['apk'], manifest['sender']['test_apk']]:
        data = archive.read(row['file'])
        assert len(data) == row['bytes'] and sha(data) == row['sha256']
        entries.append(row)
    ui = json.loads(archive.read('ui/report.json'))
    assert ui['passed'] is True and ui['source_sha'] == SOURCE and len(ui['checks']) == 4
    assert all(check['pass'] is True for check in ui['checks'])
    before = json.loads(archive.read('state/before.json'))
    after = json.loads(archive.read('state/after.json'))
    assert before['reader_revisions'] == after['reader_revisions']
    revisions = {row[0]: row[4].encode('utf-8') for row in before['reader_revisions']}
    requests = json.loads(archive.read('https/requests.json'))
    assert len(manifest['originals']) == 1 and len(manifest['revisions']) == 5
    for row in manifest['revisions']:
        assert archive.read(row['file']) == revisions[row['id']]
        assert any(request['method'] == 'PUT' and request['path'] == row['remote_path']
                   and request.get('body_sha256') == row['sha256'] and request.get('response') == 201
                   and request.get('stored') is True for request in requests)
        assert all(parent in revisions for parent in row['parents'])
    assert len({request['authorization_sha256'] for request in requests}) == 1
    file_inventory = [{'file': name, 'bytes': len(archive.read(name)), 'sha256': sha(archive.read(name))}
                      for name in names if not name.endswith('/')]
    handoff = {'accepted': True, 'scope': manifest['scope'], 'producer': manifest,
               'retrieval': {'repository': REPO, 'run_id': RUN, 'attempt': 1, 'source_sha': SOURCE,
                   'artifact_id': ARTIFACT, 'artifact_bytes': SIZE, 'artifact_sha256': DIGEST,
                   'manifest_sha256': MANIFEST, 'expires_at': item['expires_at'],
                   'artifact_url': f'https://github.com/{REPO}/actions/runs/{RUN}/artifacts/{ARTIFACT}'},
               'seal': {'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
                        'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'no_rebuild': True},
               'checks': ui['checks'], 'inventory': file_inventory,
               'receiver_contract': 'Artifact-root manifest.json; preserve every original wire byte and parent. Scope strictly TXT. Do not relabel parser, invent EPUB/PDF/CBZ records, or infer receiver acceptance.'}
    (out / 'handoff.json').write_text(json.dumps(handoff, ensure_ascii=False, indent=2) + '\n')
    (out / 'manifest.json').write_bytes(manifest_raw)
    summary = {key: handoff[key] for key in ('accepted', 'scope', 'retrieval', 'seal', 'checks', 'receiver_contract')}
    summary.update(originals=manifest['originals'], revisions=manifest['revisions'], original_capture_requests=manifest['original_capture_requests'],
                   sender=manifest['sender'], reading_records=manifest['reading_records'])
    print(json.dumps(summary, ensure_ascii=False), flush=True)
