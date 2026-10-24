"""Actions-only read of one retained UI artifact; grants no acceptance."""
import hashlib
import io
import json
import os
from pathlib import PurePosixPath
import re
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile

assert os.environ.get('GITHUB_ACTIONS') == 'true'
run = 40090470041
source = 'ed9ff5ffc3608971bb19020f1ec07496a79d9710'
artifact = 12559220856
size = 107771689
digest = 'sha256:5d1c1e3487b1dbcf5903bef102c7a721b5edd05ad977f0ff92b693c7bb794bf6'
api = 'https://api.github.com/repos/NoGod3524/EXReader'
headers = {'Authorization': 'Bearer ' + os.environ['GH_TOKEN'], 'Accept': 'application/vnd.github+json', 'User-Agent': 'EXReader-host-ui-inspect'}

def read_json(path):
    with urllib.request.urlopen(urllib.request.Request(api + path, headers=headers), timeout=60) as response:
        return json.load(response)

identity = read_json('/actions/runs/' + str(run))
metadata = read_json('/actions/artifacts/' + str(artifact))
assert identity['head_sha'] == source and identity['conclusion'] == 'success' and identity['run_attempt'] == 1
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
def retained(suffix):
    found = [name for name in names if name.endswith(suffix)]
    assert len(found) == 1
    return archive.read(found[0])

phases=[]
for phase in ('first', 'secure-reopen', 'session-reopen', 'semantics'):
    report = json.loads(retained('/ui/' + phase + '-report.json'))
    assert report['source_sha'] == source and report['run_id'] == str(run) and report['attempt'] == '1'
    assert report['passed'] is True
    phases.append({'phase':phase,'pid':report['pid'],'checks':report['checks'],'count':report['count']})
ui=json.loads(retained('/ui/result.json'))
assert ui['accepted'] and ui['checks']==16 and len({phase['pid'] for phase in phases})==4
runtimes=[]
with tempfile.TemporaryDirectory(prefix='reader-native-inspect-') as directory:
    for label,suffix in [('installed-engine','/sdk-stage/lib/libexreader.so'),('installed-jni','/sdk-stage/lib/libexreader_jni.so')]+[(variant+'-'+kind,'/native/'+variant+'-runtime-'+name) for variant in ('debug','release') for kind,name in [('engine','libexreader.so'),('jni','libexreader_jni.so')]]:
        data=retained(suffix);assert data.startswith(b'\x7fELF')
        path=os.path.join(directory,label+'.so')
        with open(path,'wb') as output:output.write(data)
        dynamic=subprocess.check_output(['readelf','-d',path],text=True)
        runtimes.append({'name':label,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'needed':re.findall(r'\(NEEDED\).*\[([^\]]+)\]',dynamic)})
cache_paths=[name for name in names if name.endswith('/sdk/CMakeCache.txt')]
print(json.dumps({'diagnostic_only':True,'accepted':False,'producer_source':source,'producer_run':run,
                  'artifact_id':artifact,'artifact_bytes':size,'artifact_digest':digest,'phases':phases,
                  'checks':ui['checks'],'boundaries':ui['boundaries'],'captures':ui['captures'],'storage_scans':len(ui['storage_scan']),
                  'runtime_materials':runtimes,'actual_cmake_cache':None if not cache_paths else cache_paths,
                  'actual_cmake_options_measured':False,'declared_build_options':{'EXR_ENABLE_AUDIO':'ON (explicit workflow option)','EXR_ENABLE_AAC':'OFF (explicit workflow option)','EXR_ENABLE_MP3':'ON (source default)'},
                  'desktop_reading_profile':False},ensure_ascii=False),flush=True)
