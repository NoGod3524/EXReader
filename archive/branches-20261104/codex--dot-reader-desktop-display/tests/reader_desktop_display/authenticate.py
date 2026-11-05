#!/usr/bin/env python3
"""Actions-only authenticated ZIP/raw/binary verifier and executable mutations."""
import copy
import datetime as dt
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from report import strict_json, validate_raw

NAMES = {'linux':'native (linux)', 'windows':'native (windows)'}

def require(ok, why):
    if not ok: raise ValueError(why)
def utc(s): return dt.datetime.fromisoformat(s.replace('Z','+00:00'))
def validate(meta, payload, platform, source, run, attempt, job, module_tree, now=None):
    now=now or dt.datetime.now(dt.timezone.utc)
    require(job['name']==NAMES[platform] and job['status']=='completed' and job['conclusion']=='success','job not completed/success')
    require(job['head_sha']==source and job['run_id']==run and job['run_attempt']==attempt,'wrong job source/run/attempt')
    require(meta['name']==f'd07-{platform}-{run}-{attempt}','wrong unique artifact name/attempt')
    require(isinstance(meta['id'],int) and meta['id']>0,'invalid artifact id')
    require(not meta['expired'] and utc(meta['expires_at'])>now,'expired artifact')
    require(meta['workflow_run']['id']==run and meta['workflow_run']['head_sha']==source,'artifact workflow binding')
    require(utc(job['started_at'])<=utc(meta['created_at'])<=utc(job['completed_at']),'artifact outside actual job')
    require(meta['size_in_bytes']==len(payload) and len(payload)>0,'ZIP byte size mismatch')
    require(meta.get('digest')=='sha256:'+hashlib.sha256(payload).hexdigest(),'API digest mismatch')
    with zipfile.ZipFile(io.BytesIO(payload)) as z:
        infos=z.infolist(); names=[i.filename for i in infos]
        require(len(names)==len(set(names)),'duplicate ZIP member')
        require(names.count('report.json')==1 and len(names)<=256,'missing report or member limit')
        require(sum(i.file_size for i in infos)<=128*1024*1024,'uncompressed limit')
        for i in infos:
            p=PurePosixPath(i.filename)
            require(not p.is_absolute() and '..' not in p.parts and '\\' not in i.filename and p.as_posix()==i.filename and not i.is_dir() and ((i.external_attr>>16)&0o170000)!=0o120000,'unsafe member')
        data={n:z.read(n) for n in names}
    r=strict_json(data['report.json'].decode())
    require(r['schema']==1 and r['source_sha']==source and r['run_id']==run and r['run_attempt']==attempt and r['platform']==platform,'wrong report source/run/attempt/platform')
    require(r['module_tree']==module_tree and r['job_name']==NAMES[platform],'original module/job mismatch')
    require(set(r['files'])==set(data)-{'report.json'},'unbound/missing raw or binary member')
    for n,identity in r['files'].items():
        require(identity=={'size':len(data[n]),'sha256':hashlib.sha256(data[n]).hexdigest()},'binary/raw identity mismatch '+n)
    suffix='.exe' if platform=='windows' else ''
    required=['bin/display_probe'+suffix,'bin/consumer_c'+suffix,'bin/consumer_cpp'+suffix,'lib/exr_desktop_display.lib' if platform=='windows' else 'lib/libexr_desktop_display.a']
    require(r['actual_binaries']==required and all(data.get(n) for n in required),'actual binary set missing/changed')
    # The original installed module source stamp must occur in every linked binary.
    require(all(source.encode() in data[n] for n in required),'original module source stamp missing from actual binary')
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        for n,b in data.items():
            if n.startswith('raw/'):
                p=root/n; p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(b)
        actual=validate_raw(root,platform,source)
    require(r['cases']==actual,'summary substituted for original raw results')
    return r

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs): return None

def request(url, binary=False):
    headers={'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28','Authorization':'Bearer '+os.environ['GITHUB_TOKEN']}
    req=urllib.request.Request(url,headers=headers)
    try:
        with urllib.request.build_opener(NoRedirect).open(req,timeout=60) as r: b=r.read()
    except urllib.error.HTTPError as e:
        if not binary or e.code not in (301,302,303,307,308): raise
        # Signed artifact URL receives NO GitHub authorization header.
        with urllib.request.urlopen(e.headers['Location'],timeout=120) as r: b=r.read()
    return b if binary else strict_json(b.decode())

def select_original(jobs, artifacts, platform, run, attempt):
    ids=[a['id'] for a in artifacts]
    require(len(ids)==len(set(ids)), 'duplicate artifact IDs')
    selected=[j for j in jobs if j['name']==NAMES[platform]]
    require(len(selected)==1, 'missing/duplicate native job')
    selected_art=[a for a in artifacts if a['name']==f'd07-{platform}-{run}-{attempt}']
    require(len(selected_art)==1, 'missing/duplicate unique artifact')
    return selected[0], selected_art[0]

def collection_mutations(jobs, artifacts, run, attempt):
    passed=[]
    _, original=select_original(jobs,artifacts,'linux',run,attempt)
    for name, js, ars in [
        ('duplicate_artifact_id',jobs,artifacts+[copy.deepcopy(original)]),
        ('duplicate_artifact_name',jobs,artifacts+[dict(original,id=max(a['id'] for a in artifacts)+1)]),
        ('missing_native_artifact',jobs,[a for a in artifacts if a['id']!=original['id']]),
        ('duplicate_upstream_job',jobs+[next(j for j in jobs if j['name']==NAMES['linux'])],artifacts),
        ('missing_upstream_job',[j for j in jobs if j['name']!=NAMES['linux']],artifacts),
    ]:
        try: select_original(js,ars,'linux',run,attempt)
        except ValueError: passed.append(name); continue
        raise ValueError('negative collection verifier accepted '+name)
    return passed

def mutations(meta,payload,platform,source,run,attempt,job,tree):
    passed=[]
    def reject(name,m=meta,b=payload,j=job):
        try: validate(m,b,platform,source,run,attempt,j,tree)
        except (ValueError,KeyError,zipfile.BadZipFile,UnicodeError): passed.append(name); return
        raise ValueError('negative verifier accepted '+name)
    m=copy.deepcopy(meta); m['digest']='sha256:'+'0'*64; reject('bad_api_digest',m)
    m=copy.deepcopy(meta); m['size_in_bytes']+=1; reject('bad_zip_size',m)
    m=copy.deepcopy(meta); m['expired']=True; reject('expired_artifact',m)
    m=copy.deepcopy(meta); m['name']+='-wrong'; reject('wrong_attempt_name',m)
    m=copy.deepcopy(meta); m['workflow_run']['head_sha']='0'*40; reject('wrong_artifact_source',m)
    j=copy.deepcopy(job); j['conclusion']='failure'; reject('failed_job',j=j)
    j=copy.deepcopy(job); j['status']='in_progress'; reject('unfinished_job',j=j)
    j=copy.deepcopy(job); j['run_attempt']+=1; reject('wrong_job_attempt',j=j)
    with zipfile.ZipFile(io.BytesIO(payload)) as z: original={n:z.read(n) for n in z.namelist()}
    def altered(name, fn, duplicate=False):
        data=copy.deepcopy(original); fn(data); buf=io.BytesIO()
        with zipfile.ZipFile(buf,'w',zipfile.ZIP_DEFLATED) as z:
            for n,b in data.items(): z.writestr(n,b)
            if duplicate: z.writestr('report.json',data['report.json'])
        b=buf.getvalue(); m=copy.deepcopy(meta); m['size_in_bytes']=len(b); m['digest']='sha256:'+hashlib.sha256(b).hexdigest(); reject(name,m,b)
    altered('duplicate_zip_report',lambda d:None,True)
    altered('missing_report',lambda d:d.pop('report.json'))
    altered('duplicate_json_key',lambda d:d.__setitem__('report.json',d['report.json'][:-2]+b',"schema":1}\n'))
    def edit_report(d, fn):
        r=json.loads(d['report.json']); fn(r); d['report.json']=json.dumps(r).encode()
    altered('wrong_report_sha',lambda d:edit_report(d,lambda r:r.__setitem__('source_sha','0'*40)))
    altered('wrong_original_module',lambda d:edit_report(d,lambda r:r.__setitem__('module_tree','0'*40)))
    altered('changed_actual_binary',lambda d:d.__setitem__('bin/display_probe'+('.exe' if platform=='windows' else ''),b'replaced'))
    altered('missing_raw_member',lambda d:d.pop('raw/native.jsonl'))
    altered('summary_not_original',lambda d:edit_report(d,lambda r:r['cases'].pop(next(iter(r['cases'])))))
    def raw_mutation(d, mode):
        n='raw/native.jsonl'; records=[json.loads(x) for x in d[n].splitlines()]
        if mode=='missing': records.pop()
        elif mode=='duplicate': records.append(records[0])
        elif mode=='fail': records[0]['result']='FAIL'
        elif mode=='module': records[0]['module']='0'*40
        elif mode=='unavailable': records[0]['result']='UNAVAILABLE'; records[0]['detail']='mock success cannot grant real capability'
        d[n]=''.join(json.dumps(x)+'\n' for x in records).encode()
        def reb(r): r['files'][n]={'size':len(d[n]),'sha256':hashlib.sha256(d[n]).hexdigest()}
        edit_report(d,reb)
    for mode in ['missing','duplicate','fail','module','unavailable']:
        altered('raw_'+mode,lambda d,m=mode:raw_mutation(d,m))
    return passed

def main():
    require(os.environ.get('GITHUB_ACTIONS')=='true','Actions only')
    repo=os.environ['GITHUB_REPOSITORY']; source=os.environ['GITHUB_SHA']; run=int(os.environ['GITHUB_RUN_ID']); attempt=int(os.environ['GITHUB_RUN_ATTEMPT'])
    base=f'https://api.github.com/repos/{repo}/actions'
    run_info=request(f'{base}/runs/{run}')
    require(run_info['head_sha']==source and run_info['run_attempt']==attempt and run_info['path']=='.github/workflows/reader-desktop-display.yml','actual workflow mismatch')
    jobs=request(f'{base}/runs/{run}/attempts/{attempt}/jobs?per_page=100')['jobs']
    artifacts=request(f'{base}/runs/{run}/artifacts?per_page=100')['artifacts']
    require(len(jobs)<100 and len(artifacts)<100,'unhandled pagination')
    tree=subprocess.check_output(['git','rev-parse',source+':extras/desktop-reader-display'],text=True).strip()
    out={'source_sha':source,'run_id':run,'run_attempt':attempt,'module_tree':tree,'artifacts':[],'negative_cases':{'collections':collection_mutations(jobs,artifacts,run,attempt)}}
    for platform in NAMES:
        job,m=select_original(jobs,artifacts,platform,run,attempt)
        b=request(f'{base}/artifacts/{m["id"]}/zip',True)
        r=validate(m,b,platform,source,run,attempt,job,tree)
        out['negative_cases'][platform]=mutations(m,b,platform,source,run,attempt,job,tree)
        out['artifacts'].append({'platform':platform,'job_id':job['id'],'id':m['id'],'name':m['name'],'size_in_bytes':len(b),'sha256':hashlib.sha256(b).hexdigest(),'expires_at':m['expires_at'],'actual_binaries':{n:r['files'][n] for n in r['actual_binaries']},'results':{v:sum(c['result']==v for c in r['cases'].values()) for v in ['PASS','UNAVAILABLE']},'capabilities':r['capabilities']})
    Path('authenticated.json').write_text(json.dumps(out,indent=2)+'\n'); print(json.dumps(out,indent=2))
if __name__=='__main__': main()
