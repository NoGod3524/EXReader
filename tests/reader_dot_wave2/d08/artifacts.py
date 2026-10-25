"""Actions-only raw ZIP authentication, extraction and current-run strict summary."""
import datetime as dt
import hashlib
import json
import os
import re
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
def credential_scan(root, log_bytes):
    patterns=[rb"gh[pousr]_[A-Za-z0-9]{30,}", rb"github_pat_[A-Za-z0-9_]{30,}", rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", rb"https://[^\s\"]+[?&]sig=[^\s\"]+"]
    count=0
    for label,raw in [("native-job-log",log_bytes)]+[(str(p.relative_to(root)),p.read_bytes()) for p in root.rglob("*") if p.is_file()]:
        count+=1
        assert not any(re.search(pattern,raw) for pattern in patterns), "credential-shaped bytes found in "+label
        assert os.environ["GH_TOKEN"].encode() not in raw, "ephemeral token found in "+label
    return {"passed":True,"files_and_logs_scanned":count,"scope":"current native log and extracted current raw artifact; token and credential-pattern scan; no credential values logged"}

def summary():
    out=Path('build/d08-summary');out.mkdir(parents=True,exist_ok=True)
    result={'verified':False,'accepted':False,'problems':[]}
    try:
        run=int(os.environ['GITHUB_RUN_ID']);attempt=int(os.environ['GITHUB_RUN_ATTEMPT']);source=os.environ['GITHUB_SHA']
        current=api(f'actions/runs/{run}');assert current['head_sha']==source and current['run_attempt']==attempt
        jobs=api(f'actions/runs/{run}/attempts/{attempt}/jobs')['jobs']
        native=[j for j in jobs if j['name']=='d08-native'];assert len(native)==1
        proof=download(int(os.environ['ARTIFACT_ID']),out/'raw',run,source,os.environ['UPLOAD_DIGEST'].removeprefix('sha256:'))
        root=out/'raw'
        r=json.loads((root/'report.json').read_text(encoding='utf-8'));validate(r,source,run,attempt)
        for item in r['files']:
            p=root/item['path'];assert p.stat().st_size==item['bytes'] and sha(p)==item['sha256']
        indexed={i['path'] for i in r['files']}
        for c in r['configurations']:
            for name in c['screenshots']:
                assert 'observations/'+name in indexed and (root/'observations'/name).read_bytes()[:2]==b'BM'
        identity=json.loads((root/'build-identity.json').read_text());assert identity['target_sha']==TARGET and identity['sdk_source']==SDK
        assert r['program_sha256']==identity['program_sha256']==sha(root/'programs/EXReaderProduct.exe')
        assert native[0]['conclusion']=='success' and os.environ['NATIVE_RESULT']=='success'
        result.update(verified=True,artifact=proof,jobs=[{'id':j['id'],'name':j['name'],'conclusion':j['conclusion']} for j in jobs],report=r,credential_scan=credential_scan(root,api('actions/jobs/'+str(native[0]['id'])+'/logs',True)))
    except Exception:
        import traceback
        result['problems'].append(traceback.format_exc())
    (out/'validation.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False),flush=True)
    assert result['verified'],result['problems']
if __name__=='__main__':
    assert os.environ.get('GITHUB_ACTIONS')=='true'
    summary()
