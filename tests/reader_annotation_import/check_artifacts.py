# SPDX-License-Identifier: MIT
"""Strict producer identity and artifact verifier; downloads only in Actions."""
import copy
from datetime import datetime,timezone
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
from check_parallel_integration import fetch,pages,download_artifact_zip,require
from check_import import REQUIRED
PLATFORMS=[('Linux','ubuntu-22.04','linux'),('Windows','windows-2022','win32'),('macOS','macos-15','darwin')]
START='a826a65c9c66e43620eff61b49cb79f941a3c953'

def unique_pairs(pairs):
    out={}
    for key,value in pairs:
        require(key not in out,'duplicate JSON key '+key);out[key]=value
    return out

def parse_json(data):return json.loads(data,object_pairs_hook=unique_pairs)
def metadata(a,j,source,run,attempt,name,jobname):
    require(a['name']==name and isinstance(a['id'],int) and a['id']>0,'artifact identity')
    require(a['size_in_bytes']>0 and a['expired'] is False and datetime.fromisoformat(a['expires_at'].replace('Z','+00:00'))>datetime.now(timezone.utc),'empty/expired artifact')
    require(a['workflow_run']['id']==run and a['workflow_run']['head_sha']==source,'artifact source/run')
    require(j['name']==jobname and j['head_sha']==source and j['run_attempt']==attempt and j['status']=='completed' and j['conclusion']=='success','producer job incomplete/cross-source')

def report_check(r,source,run,attempt,platform):
    require(r['accepted'] is False and r['measured_capability_passed'] is True,'grant separation')
    require(r['source_sha']==source and r['run_id']==run and r['attempt']==attempt and r['platform']==platform,'report identity')
    require(set(r['checks'])==REQUIRED and len(r['checks'])==len(REQUIRED)==r['checks_count'] and set(r['required'])==REQUIRED,'required named cases')
    require(r['problems']==[] and len(r['gaps'])>=3 and r['host_ui_accepted'] is False and r['sdk_changed'] is False and r['schema_changed'] is False,'report claims')

def zip_members(data):
    archive=zipfile.ZipFile(io.BytesIO(data));names=archive.namelist()
    require(len(names)==len(set(names)) and all(not n.startswith('/') and '..' not in Path(n).parts for n in names),'duplicate/unsafe ZIP member')
    require(names.count('ai-evidence/result.json')==1,'unique required report')
    return archive

def rejects(fn,name,out):
    try:fn()
    except Exception:out.append(name);return
    raise AssertionError('verifier accepted negative '+name)

def main():
    require(os.environ.get('GITHUB_ACTIONS')=='true','Actions only')
    source=os.environ['GITHUB_SHA'];run=int(os.environ['GITHUB_RUN_ID']);attempt=int(os.environ['GITHUB_RUN_ATTEMPT']);out=Path(sys.argv[1]);out.mkdir(parents=True)
    result={'accepted':False,'evidence_verified':False,'source_sha':source,'run_id':run,'attempt':attempt,'artifacts':[],'jobs':[],'verifier_negative_checks':[],'problems':[],'gaps':['Head-only export cannot recreate omitted history','Advisory export metadata has no public lossless product write API','No host UI acceptance']}
    try:
        caller=fetch(f'actions/runs/{run}');require(caller['head_sha']==source and caller['run_attempt']==attempt and caller['path']=='.github/workflows/reader-annotation-import.yml','caller mismatch')
        jobs=pages(f'actions/runs/{run}/attempts/{attempt}/jobs','jobs');artifacts=pages(f'actions/runs/{run}/artifacts','artifacts')
        require(len({j['id'] for j in jobs})==len(jobs),'duplicate job IDs');require(len({a['id'] for a in artifacts})==len(artifacts) and len({a['name'] for a in artifacts})==len(artifacts),'duplicate artifact names/IDs')
        for label,runner,platform in PLATFORMS:
            name=f'reader-annotation-import-{label}-{run}-{attempt}';jobname=f'annotation import ({runner})'
            aa=[a for a in artifacts if a['name']==name];jj=[j for j in jobs if j['name']==jobname];require(len(aa)==len(jj)==1,'missing/duplicate required artifact/job');a,j=aa[0],jj[0]
            metadata(a,j,source,run,attempt,name,jobname)
            with tempfile.TemporaryFile() as stream:
                download_artifact_zip(a['id'],stream);stream.seek(0);data=stream.read()
            sha=hashlib.sha256(data).hexdigest();require(len(data)==a['size_in_bytes'] and 'sha256:'+sha==a.get('digest'),'ZIP size/API digest mismatch')
            with zip_members(data) as z:
                r=parse_json(z.read('ai-evidence/result.json'));report_check(r,source,run,attempt,platform)
                for p,tree in r['module_trees'].items():
                    require(subprocess.check_output(['git','rev-parse','HEAD:'+p],text=True).strip()==tree,'module tree not bound')
                    if p not in ['apps/reader/annotation-import','tests/reader_annotation_import']:
                        require(subprocess.check_output(['git','rev-parse',START+':'+p],text=True).strip()==tree,'original module changed')
                require(set(r['module_trees'])=={'apps/reader/annotation-export','apps/reader/revisions','apps/reader/reading-state','tests/reader_annotation_export','apps/reader/annotation-import','tests/reader_annotation_import'},'missing module binding')
                suffix='.exe' if platform=='win32' else ''
                require(set(r['binaries'])=={'annotation-import-probe'+suffix,'annotation-import-c'+suffix},'binary set')
                for b,identity in r['binaries'].items():
                    content=z.read('ai-consumer/'+b);require(len(content)==identity['bytes']>0 and hashlib.sha256(content).hexdigest()==identity['sha256'],'consumer binary mismatch')
                require(r['package_files'] and any(p.endswith(('.a','.lib')) for p in r['package_files']),'installed static package absent')
                for p,identity in r['package_files'].items():
                    content=z.read('ai-import-stage/'+p);require(len(content)==identity['bytes']>0 and hashlib.sha256(content).hexdigest()==identity['sha256'],'installed package mismatch')
                if label=='Linux':
                    negatives=result['verifier_negative_checks']
                    for key,value in [('source_sha','0'*40),('attempt',attempt+1),('accepted',True),('measured_capability_passed',False),('checks',r['checks'][:-1]),('checks',r['checks']+[r['checks'][0]])]:
                        bad=copy.deepcopy(r);bad[key]=value;rejects(lambda:report_check(bad,source,run,attempt,platform),'report_'+key+'_'+str(len(negatives)),negatives)
                    for key,value in [('expired',True),('size_in_bytes',0),('expires_at','2000-01-01T00:00:00Z')]:
                        bad=copy.deepcopy(a);bad[key]=value;rejects(lambda:metadata(bad,j,source,run,attempt,name,jobname),'artifact_'+key,negatives)
                    bad=copy.deepcopy(j);bad['status']='in_progress';rejects(lambda:metadata(a,bad,source,run,attempt,name,jobname),'producer_incomplete',negatives)
                    rejects(lambda:parse_json(b'{"x":1,"x":2}'),'duplicate_json_key',negatives)
                    buf=io.BytesIO()
                    with zipfile.ZipFile(buf,'w') as fake:fake.writestr('ai-evidence/result.json','{}');fake.writestr('ai-evidence/result.json','{}')
                    rejects(lambda:zip_members(buf.getvalue()),'duplicate_zip_report',negatives)
                    buf=io.BytesIO()
                    with zipfile.ZipFile(buf,'w') as fake:fake.writestr('unrelated','{}')
                    rejects(lambda:zip_members(buf.getvalue()),'missing_zip_report',negatives)
            result['artifacts'].append({**{k:a[k] for k in ['id','name','size_in_bytes','digest','expires_at']},'recomputed_zip_sha256':sha,'checks_count':r['checks_count'],'binaries':r['binaries'],'module_trees':r['module_trees']})
            result['jobs'].append({k:j[k] for k in ['id','name','head_sha','run_attempt','status','conclusion']})
        result['evidence_verified']=True
    except Exception as error:result['problems'].append(str(error))
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
    raise SystemExit(0 if result['evidence_verified'] else 1)
if __name__=='__main__':main()
