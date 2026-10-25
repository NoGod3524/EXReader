"""Actions-only retained failure diagnosis; neither rebuilds nor grants acceptance."""
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import urllib.error
import urllib.parse
import urllib.request
import zipfile

assert os.environ.get('GITHUB_ACTIONS') == 'true'
run = 40146403326
source = 'd199f0dc67ed929ad7c5a3fe8edb855ef50f1f67'
artifact = 12580498901
size = 146190324
digest = 'sha256:51d6ea82c9ccc4f9ca0f7fc960826d986c924b544cdc303ed7f66848adfaceda'
case = os.environ.get('FAILURE_CASE') or 'original'
assert case in ('original', 'viewport')
if case == 'viewport':
    run = 40154163799
    source = '094d475e2d8860c30ffcc2fb903d5aa9747706e9'
    artifact = 12584082874
    size = 146820764
    digest = 'sha256:bac698dcac07a4917e36412ada410213ef93a1ac2701d56f5a072b534019fd60'
api = 'https://api.github.com/repos/NoGod3524/EXReader'
headers = {'Authorization': 'Bearer ' + os.environ['GH_TOKEN'], 'Accept': 'application/vnd.github+json', 'User-Agent': 'EXReader-pan-diagnosis'}

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
found = [name for name in names if name.endswith('android-fixed-pan/ui/first-instrumentation.txt')]
assert len(found) == 1
assert archive.getinfo(found[0]).file_size < 1024**2
print(json.dumps({'diagnostic_only': True, 'accepted': False, 'source': source, 'run': run, 'artifact': artifact, 'digest': digest, 'path': found[0]}), flush=True)
print(archive.read(found[0]).decode('utf-8', errors='replace'), flush=True)
print(json.dumps({'retained_pan_files': [name for name in names if 'android-fixed-pan/ui/' in name]}), flush=True)
reports = [name for name in names if name.endswith('android-fixed-pan/ui/first-report.json')]
if reports:
    assert len(reports) == 1 and archive.getinfo(reports[0]).file_size < 8 * 1024**2
    report = json.loads(archive.read(reports[0]))
    assert report['source_sha'] == source and report['run_id'] == str(run) and report['attempt'] == '1'
    def selected(tree):
        result = []
        if tree.get('id', '').endswith('/selection_status'):
            result.append(tree.get('text'))
        for child in tree.get('children', []):
            result.extend(selected(child))
        return result
    print(json.dumps({'diagnostic_only': True, 'accepted': False, 'checks': report['checks'],
                      'failure': report.get('failure'), 'observations': [
                          {'name': item['name'], 'selected': selected(item['tree']), 'frame': item.get('frame')}
                          for item in report['observations']]}, ensure_ascii=False), flush=True)
if os.environ.get('PREPARE_REPLAY') == 'true':
    assert case == 'original'
    folder = Path('build/android-fixed-pan-replay')
    folder.mkdir(parents=True, exist_ok=True)
    for suffix, output in [('examples/android/app/build/outputs/apk/debug/app-debug.apk', 'host.apk'),
                           ('build/android-fixed-pan/test-apks/fixed-pan-ui.apk', 'probe.apk')]:
        found = [name for name in names if name.endswith(suffix)]
        assert len(found) == 1 and archive.getinfo(found[0]).file_size < 100 * 1024**2
        (folder / output).write_bytes(archive.read(found[0]))
    originals = [name for name in names if '/android-fixed-pan/fixtures/' in name and not name.endswith('/')]
    assert len(originals) == 8
    (folder / 'fixtures').mkdir(exist_ok=True)
    for name in originals:
        assert archive.getinfo(name).file_size < 32 * 1024**2
        (folder / 'fixtures' / PurePosixPath(name).name).write_bytes(archive.read(name))
