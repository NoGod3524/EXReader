"""Actions-only read of one retained failed UI artifact; grants no acceptance."""
import hashlib
import io
import json
import os
from pathlib import PurePosixPath
import urllib.error
import urllib.parse
import urllib.request
import zipfile

assert os.environ.get('GITHUB_ACTIONS') == 'true'
run = 40086660647
source = '170d1f77d6e320c75fca25b047dbf117bd1d0c5f'
artifact = 12558040607
size = 69860674
digest = 'sha256:19e39b25a0fc65b89f6572f9e8ee49b3955cc3fe52b3d6b178653ddad6ca40e5'
api = 'https://api.github.com/repos/NoGod3524/EXReader'
headers = {'Authorization': 'Bearer ' + os.environ['GH_TOKEN'], 'Accept': 'application/vnd.github+json', 'User-Agent': 'EXReader-host-ui-inspect'}

def read_json(path):
    with urllib.request.urlopen(urllib.request.Request(api + path, headers=headers), timeout=60) as response:
        return json.load(response)

identity = read_json('/actions/runs/' + str(run))
metadata = read_json('/actions/artifacts/' + str(artifact))
assert identity['head_sha'] == source and identity['conclusion'] == 'failure' and identity['run_attempt'] == 1
assert metadata['workflow_run']['id'] == run and metadata['workflow_run']['head_sha'] == source
assert metadata['size_in_bytes'] == size and metadata['digest'] == digest and not metadata['expired']

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, stream, code, message, headers, url):
        return None

try:
    response = urllib.request.build_opener(NoRedirect).open(urllib.request.Request(api + '/actions/artifacts/' + str(artifact) + '/zip', headers=headers), timeout=60)
except urllib.error.HTTPError as error:
    assert error.code == 302
    location = error.headers['Location']
    target = urllib.parse.urlparse(location)
    assert target.scheme == 'https' and target.hostname and not target.username and not target.password
    response = urllib.request.urlopen(location, timeout=60)
with response:
    raw = response.read(size + 1)
assert len(raw) == size and 'sha256:' + hashlib.sha256(raw).hexdigest() == digest
archive = zipfile.ZipFile(io.BytesIO(raw))
names = archive.namelist()
assert len(names) == len(set(names)) and sum(item.file_size for item in archive.infolist()) < 1024**3
for name in names:
    path = PurePosixPath(name)
    assert not path.is_absolute() and '..' not in path.parts and '\\' not in name
for phase in ('first', 'secure-reopen', 'session-reopen', 'semantics'):
    found = [name for name in names if name.endswith('/ui/' + phase + '-report.json')]
    assert len(found) == 1
    report = json.loads(archive.read(found[0]))
    assert report['source_sha'] == source and report['run_id'] == str(run) and report['attempt'] == '1'
    print(json.dumps({'diagnostic_only': True, 'accepted': False, 'phase': phase,
                      'passed': report['passed'], 'checks': report['checks'],
                      'failure_class': report.get('failure_class'), 'failure': report.get('failure'),
                      'observations': report.get('observations', [])}, ensure_ascii=False), flush=True)
