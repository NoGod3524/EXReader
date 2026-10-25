"""Actions-only raw ZIP authentication, extraction and current-run strict summary."""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import sys
import urllib.request
import urllib.parse
import zipfile
from contract import *
REPO = 'NoGod3524/EXReader'
class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        redirected=super().redirect_request(req,fp,code,msg,headers,newurl)
        if urllib.parse.urlsplit(req.full_url).netloc != urllib.parse.urlsplit(newurl).netloc:
            redirected.remove_header("Authorization")
        return redirected
OPENER=urllib.request.build_opener(SafeRedirect())
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def api(route, raw=False):
    req=urllib.request.Request('https://api.github.com/repos/'+REPO+'/'+route, headers={'Authorization':'Bearer '+os.environ['GH_TOKEN'], 'Accept':'application/vnd.github+json'})
    with OPENER.open(req,timeout=180) as response: value=response.read()
    return value if raw else json.loads(value)
def download(identifier, destination, expected_run, expected_sha, expected_digest=None, expected_size=None):
    meta=api('actions/artifacts/'+str(identifier))
    assert not meta['expired'] and dt.datetime.fromisoformat(meta['expires_at'].replace('Z','+00:00'))>dt.datetime.now(dt.timezone.utc)
    assert meta['workflow_run']['id']==expected_run and meta['workflow_run']['head_sha']==expected_sha
    raw=api('actions/artifacts/'+str(identifier)+'/zip', True)
    digest=hashlib.sha256(raw).hexdigest()
    assert len(raw)==meta['size_in_bytes'] and 'sha256:'+digest==meta['digest']
    if expected_digest: assert digest==expected_digest
    if expected_size: assert len(raw)==expected_size
    destination.mkdir(parents=True,exist_ok=True)
    archive=destination.parent/(destination.name+'.zip');archive.write_bytes(raw)
    with zipfile.ZipFile(archive) as z:
        names=z.namelist();assert len(names)==len(set(names))
        for name in names:
            assert not Path(name).is_absolute() and '..' not in Path(name).parts and '\\' not in name
        z.extractall(destination)
    return dict(id=identifier,name=meta['name'],bytes=len(raw),sha256=digest,expires_at=meta['expires_at'],workflow_run=meta['workflow_run'])
def producer():
    root=Path('build/d02-producer')
    run=api('actions/runs/'+str(RUN));assert run['head_sha']==PRODUCER and run['run_attempt']==1 and run['conclusion']=='success'
    job=api('actions/jobs/'+str(JOB));assert job['run_id']==RUN and job['conclusion']=='success'
    proof=download(ARTIFACT,root,RUN,PRODUCER,DIGEST,SIZE)
    identity=json.loads((root/'windows-341-identity.json').read_text())
    assert identity['source_sha']==PRODUCER and str(identity['run_id'])==str(RUN) and str(identity['attempt'])=='1'
    assert identity['sdk_source']==SDK and identity['sdk_version']=='3.41.0' and identity['sdk_abi']==1
    for item in identity['files'].values():
        p=root/item['path'];assert p.stat().st_size==item['bytes'] and sha(p)==item['sha256']
    assert sha(root/'compact-host/EXReaderProduct.exe')==ON_PROGRAM
    assert 'EXR_READER_WINDOWS_COMPACT:BOOL=ON' in (root/'compact-host/CMakeCache.txt').read_text()
    assert 'EXR_READER_WINDOWS_COMPACT:BOOL=OFF' in (root/'ws-host/CMakeCache.txt').read_text()
    out=Path('build/d02-evidence');out.mkdir(parents=True,exist_ok=True)
    proof.update(producer_job=JOB,producer_attempt=1,sdk_identity=identity,compact_program_sha256=ON_PROGRAM)
    (out/'producer-authentication.json').write_text(json.dumps(proof,indent=2))
    print(json.dumps(proof),flush=True)
def summary():
    out=Path('build/d02-summary');out.mkdir(parents=True,exist_ok=True)
    result={'verified':False,'accepted':False,'problems':[]}
    try:
        assert os.environ['NATIVE_RESULT']=='success'
        run=int(os.environ['GITHUB_RUN_ID']);attempt=int(os.environ['GITHUB_RUN_ATTEMPT']);source=os.environ['GITHUB_SHA']
        jobs=api(f'actions/runs/{run}/attempts/{attempt}/jobs')['jobs']
        native=[j for j in jobs if j['name']=='native-windows-audit'];assert len(native)==1 and native[0]['conclusion']=='success'
        proof=download(int(os.environ['ARTIFACT_ID']),out/'raw',run,source,os.environ['UPLOAD_DIGEST'].removeprefix('sha256:'))
        root=out/'raw'
        auth=json.loads((root/'producer-authentication.json').read_text());assert auth['id']==ARTIFACT and auth['sha256']==DIGEST
        reports=[]
        for mode in ('OFF','ON'):
            folder=root/mode;r=json.loads((folder/'report.json').read_text());validate(r,source,run,attempt,mode)
            for item in r['files']:
                p=folder/item['path'];assert p.stat().st_size==item['bytes'] and sha(p)==item['sha256']
            assert set(r['screenshots']) <= {i['path'] for i in r['files']}
            for p in r['screenshots']: assert (folder/p).read_bytes()[:2]==b'BM'
            reports.append(r)
        result.update(verified=True,harness_sha=source,run_id=run,attempt=attempt,upstream_job=native[0]['id'],artifact=proof,reports=reports)
    except Exception:
        import traceback
        result['problems'].append(traceback.format_exc())
    (out/'validation.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False),flush=True)
    assert result['verified'], result['problems']
if __name__=='__main__':
    assert os.environ.get('GITHUB_ACTIONS')=='true'
    {'producer':producer,'summary':summary}[sys.argv[1]]()
