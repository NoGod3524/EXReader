"""Authenticate two example producers; report Apple compilation separately."""
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import urllib.request
import urllib.parse
import zipfile
from run import ROOT,PHASES,admission,setup,sdk_objects,require

def read(p):return json.loads(p.read_bytes())
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def same(value,stamp):require(all(value.get(k)==v for k,v in stamp.items()),'source/run/attempt mismatch')
class Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        result=super().redirect_request(req,fp,code,msg,headers,newurl)
        if urllib.parse.urlsplit(newurl).netloc!='api.github.com':result.remove_header('Authorization')
        return result
def main():
    m=setup();stamp=admission();out=ROOT/'build/f03-sdk-audit';out.mkdir(parents=True,exist_ok=False)
    opener=urllib.request.build_opener(Redirect())
    def fetch(path):return opener.open(urllib.request.Request('https://api.github.com/repos/NoGod3524/EXReader'+path,
        headers={'Authorization':'Bearer '+os.environ['GITHUB_TOKEN'],'Accept':'application/vnd.github+json'}),timeout=180)
    prefix='/actions/runs/'+stamp['run_id']
    result={**stamp,'scope':'same SDK source; GTK and Windows examples receive organization data',
        'accepted':False,'six_host_acceptance':False,'catalog_state_changed':False,'problems':[]}
    try:
        with fetch(prefix+'/attempts/'+stamp['attempt']) as f:run=json.load(f)
        require(run['head_sha']==stamp['source_sha'],'API source differs')
        with fetch(prefix+'/attempts/'+stamp['attempt']+'/jobs?per_page=100') as f:jobs=json.load(f)['jobs']
        with fetch(prefix+'/artifacts?per_page=100') as f:artifacts=json.load(f)['artifacts']
        result['apple_build_only']={host:next((j['conclusion'] for j in jobs if j['name']=='apple-build ('+host+')'),'not-run')
                                    for host in ('macos','iphone','ipad')}
        result['producer_jobs']={h:next((j['conclusion'] for j in jobs if j['name']==h),'not-run') for h in ('gtk','windows')}
        provenance={}
        for host in ('gtk','windows'):
            job=[j for j in jobs if j['name']==host]
            require(len(job)==1 and job[0]['status']=='completed' and job[0]['conclusion']=='success','example producer failed: '+host)
            name='f03-sdk-'+host+'-'+stamp['run_id']+'-'+stamp['attempt']
            found=[a for a in artifacts if a['name']==name]
            require(len(found)==1 and not found[0]['expired'],'example artifact missing: '+host)
            a=found[0];require(a['workflow_run']['head_sha']==stamp['source_sha'] and str(a['workflow_run']['id'])==stamp['run_id'],'artifact source differs')
            archive=out/(host+'.zip')
            with fetch('/actions/artifacts/'+str(a['id'])+'/zip') as response,archive.open('wb') as stream:shutil.copyfileobj(response,stream)
            require(archive.stat().st_size==a['size_in_bytes'] and a['digest']=='sha256:'+sha(archive),'artifact bytes differ')
            with zipfile.ZipFile(archive) as z:
                members=z.infolist();require(len(members)==len({i.filename for i in members}),'duplicate archive member')
                require(sum(i.file_size for i in members)<2*1024**3,'archive expansion limit')
                for i in members:
                    p=Path(i.filename);require(not p.is_absolute() and '..' not in p.parts and ':' not in i.filename and '\\' not in i.filename and not stat.S_ISLNK(i.external_attr>>16),'unsafe archive member')
                z.extractall(out/host)
            provenance[host]={'job_id':job[0]['id'],'artifact_id':a['id'],'sha256':sha(archive),'bytes':a['size_in_bytes']}
        root=out/'gtk';identities=[]
        programs={'gtk':root/'package/EXReader-Linux/bin/exreader-linux',
                  'windows':out/'windows/windows-sdk342/package/EXReader/EXReader.exe'}
        for host in ('gtk','windows'):
            identity=read(out/host/('f03-sdk-'+host+'.json'));same(identity,stamp)
            require(identity['build_completed'] is True and identity['sdk_objects']==sdk_objects() and identity['sdk_version']=='3.42.0','SDK build identity differs')
            identities.append(identity)
        require(identities[0]['unfrozen_blob_ids']==identities[1]['unfrozen_blob_ids'],'builds used different current blobs')
        observations=[]
        for phase in PHASES:
            author=read(root/'f03-author'/phase/'projection.json');same(author,stamp)
            wire=read(root/'f03-author'/phase/'wire/state.json');same(wire,stamp)
            revisions={json.loads(base64.b64decode(e['body']))['id']:json.loads(base64.b64decode(e['body']))
                       for path,e in wire['entries'].items() if '/revisions/' in path}
            for host in ('gtk','windows'):
                folder=out/host/'f03-sdk-receipts'/host/phase
                receipt=read(folder/'projection.json');same(receipt,stamp)
                require(receipt['host']==host and receipt['sdk_version']=='3.42.0' and receipt['program_sha256']==sha(programs[host]),'example identity differs')
                require(receipt['native_sync_completed'] is True and receipt['restart_verified'] is True,'receive or restart missing')
                snapshot=receipt['snapshot']
                require(hashlib.sha256(m.canonical(snapshot)).hexdigest()==receipt['snapshot_sha256'],'snapshot digest differs')
                require(all(snapshot[t]==author['snapshot'][t] for t in m.TABLES),'organization projection diverges')
                bodies={r['id']:r['body'] for r in snapshot['revisions']}
                require(all(bodies.get(r['id'])==r['body'] and revisions.get(r['id'])==r['body'] for r in author['snapshot']['revisions']),'revision body differs')
                db=[p for p in (folder/'native-catalog').iterdir() if not p.name.endswith(('-wal','-shm'))]
                require(len(db)==1 and m.read_snapshot(db[0])==snapshot,'actual database differs')
                requests=read(folder/'wire/requests.json')
                require(requests and all(r['authenticated'] for r in requests) and any(r['method']=='GET' and '/revisions/' in r['path'] for r in requests),'real authenticated receive missing')
                observations.append({'host':host,'phase':phase,'snapshot_sha256':receipt['snapshot_sha256']})
        result.update(accepted=True,hosts=['gtk','windows'],sdk_objects=sdk_objects(),observations=observations,
            current_unfrozen_blobs=identities[0]['unfrozen_blob_ids'],artifacts=provenance)
    except Exception as error:result['problems'].append(type(error).__name__+': '+str(error))
    m.write_json(out/'result.json',result);print(json.dumps(result));raise SystemExit(0 if result['accepted'] else 1)
if __name__=='__main__':main()
