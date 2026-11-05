import hashlib, io, json, os, urllib.error, urllib.parse, urllib.request, zipfile
from pathlib import PurePosixPath
assert os.environ.get('GITHUB_ACTIONS') == 'true'
api = 'https://api.github.com/repos/NoGod3524/EXReader'
run, artifact, size = 40417367269, 12697280724, 108135836
source = '3e51b5a6cf59cfc5a4c032b497c6e86cbf40f118'
digest = 'sha256:1c2f4dd5c985e435b74cac7096a8ac41b38c756da07110187de0b2a4949d42de'
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
original = read('/session-android/roundtrip/original-owner.txt').decode('utf-8', errors='replace')
adapted = read('/session-android/roundtrip-current/original-owner.txt').decode('utf-8', errors='replace')
assert 'FAILURES' in original and 'OK (18 tests)' in adapted and 'FAILURES' not in adapted
original_report = json.loads(read('/session-android/roundtrip/result.json'))
adapted_report = json.loads(read('/session-android/roundtrip-current/result.json'))
ui = json.loads(read('/host-session-android/ui-current/result.json'))
for report in (original_report, adapted_report, ui):
    assert report['source_sha'] == source and report['run_id'] == str(run) and report['attempt'] == '1'
assert original_report['accepted'] is False and adapted_report['accepted'] is True
assert ui['accepted'] is True and ui['checks'] == 16 and len(ui['phases']) == 4
expected = ('membershipNeedsExplicitBookBootstrap', 'publicSdkBootstrapKeepsCurrentProductTitle', 'shelfAndSeriesMembershipOrder', 'missingAndDeletedDependenciesRefused')
assert all(name in original for name in expected)
checks = {item['name']: item['passed'] for item in adapted_report['checks']}
assert checks.get('adapted_owner_17_plus_auto_bootstrap_and_two_process_phases') is True
print(json.dumps({'artifact': artifact, 'source': source, 'run': run, 'attempt': 1,
    'overall_run': 'failure', 'original_failed_cases': list(expected),
    'adapted_owner_cases': 18, 'adapted_roundtrip_accepted': True,
    'host_sync_checks': ui['checks'], 'host_sync_phases': len(ui['phases']),
    'scope': 'API-34 x86_64 emulator; not original-suite or six-platform acceptance'}, indent=2))
