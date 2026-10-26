import hashlib, io, json, os, urllib.error, urllib.parse, urllib.request, zipfile
from pathlib import PurePosixPath
assert os.environ.get('GITHUB_ACTIONS') == 'true'
api = 'https://api.github.com/repos/NoGod3524/EXReader'
run, artifact, size = 40415259935, 12697245942, 130101080
source = '4d0d9d549f8412f3453b1e5a87485f5ae80bbe65'
digest = 'sha256:72db46a5a11470909b3e898415ed1a9e74a2198ea31176de312b1887aacdd245'
headers = {'Authorization': 'Bearer ' + os.environ['GH_TOKEN'], 'Accept': 'application/vnd.github+json', 'User-Agent': 'EXReader-owner-evidence-audit'}
def get_json(path):
    with urllib.request.urlopen(urllib.request.Request(api + path, headers=headers), timeout=60) as response:
        return json.load(response)
identity = get_json('/actions/runs/' + str(run))
metadata = get_json('/actions/artifacts/' + str(artifact))
assert identity['head_sha'] == source and identity['run_attempt'] == 1 and identity['conclusion'] == 'failure'
assert metadata['workflow_run']['id'] == run and metadata['workflow_run']['head_sha'] == source
assert metadata['size_in_bytes'] == size and metadata['digest'] == digest and not metadata['expired']
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, stream, code, message, headers, url): return None
try:
    response = urllib.request.build_opener(NoRedirect).open(urllib.request.Request(api + '/actions/artifacts/' + str(artifact) + '/zip', headers=headers), timeout=60)
except urllib.error.HTTPError as error:
    assert error.code == 302
    location = error.headers['Location']
    target = urllib.parse.urlparse(location)
    assert target.scheme == 'https' and target.hostname and not target.username and not target.password
    response = urllib.request.urlopen(location, timeout=60)
with response: raw = response.read(size + 1)
assert len(raw) == size and 'sha256:' + hashlib.sha256(raw).hexdigest() == digest
archive = zipfile.ZipFile(io.BytesIO(raw)); names = archive.namelist()
assert len(names) == len(set(names)) and sum(item.file_size for item in archive.infolist()) < 1024**3
for name in names:
    path = PurePosixPath(name)
    assert not path.is_absolute() and '..' not in path.parts and '\\' not in name
def read(suffix):
    matches = [name for name in names if name.endswith(suffix)]
    assert len(matches) == 1, (suffix, matches)
    return archive.read(matches[0])
original = json.loads(read('original-sync/first-report.json'))
original_result = json.loads(read('original-sync/result.json'))
adapted = json.loads(read('sync-341/result.json'))
provenance = json.loads(read('candidate/provenance.json'))
for report in (original, original_result, adapted):
    assert report['source_sha'] == source and report['run_id'] == str(run) and report['attempt'] == '1'
assert original['passed'] is False and original['failed_check'] == 'explicit_receive_preserves_sdk_and_product'
assert original['failure'] == 'same shared public SDK provider' and original_result['accepted'] is False
assert adapted['accepted'] is True and adapted['checks'] == 16 and len(adapted['phases']) == 4
assert all(phase['passed'] is True and all(check['pass'] is True for check in phase['checks']) for phase in adapted['phases'])
assert provenance['source'] == source and provenance['original_unchanged'] is True
assert provenance['changes'] == ['class and runner names', 'strict SDK 3.40.0 to 3.41.0']
print(json.dumps({'artifact': artifact, 'source': source, 'run': run, 'attempt': 1,
    'overall_run': 'failure', 'original_failed_check': original['failed_check'],
    'original_failure': original['failure'], 'adapted_checks': adapted['checks'],
    'adapted_phases': len(adapted['phases']), 'adapter_changes': provenance['changes'],
    'scope': 'API-34 x86_64 emulator; not original-suite or six-platform acceptance'}, indent=2))
