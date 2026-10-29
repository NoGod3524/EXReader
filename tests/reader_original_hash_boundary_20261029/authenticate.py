"""Independently authenticate each same-run original upload, then replay its contract."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import zipfile
import package_contract as C
sys.path.insert(0,str(C.ROOT/'tools'))
from check_parallel_integration import fetch,pages,download_artifact_zip


def main():
    C.actions_only();source=C.guard();ident=C.identity();out=C.ROOT/'build/hash-authentication';out.mkdir(parents=True)
    result=dict(ident,accepted=False,f07_accepted=False,full_six_accepted=False,targets={},failures=[])
    try:
        C.require(os.environ['PROTOCOL_RESULT']=='success' and os.environ['PRODUCERS_RESULT']=='success','upstream job failed')
        run=fetch(f'actions/runs/{ident["run_id"]}/attempts/{ident["attempt"]}')
        C.require(run['head_sha']==ident['source_sha'] and run['head_branch']==C.BRANCH and run['path']==C.WORKFLOW and
            run['run_attempt']==int(ident['attempt']),'run identity differs')
        jobs=pages(f'actions/runs/{ident["run_id"]}/attempts/{ident["attempt"]}/jobs','jobs')
        for name in ('protocol',*('produce ('+t+')' for t in C.TARGETS)):
            rows=[j for j in jobs if j['name']==name]
            C.require(len(rows)==1 and rows[0]['head_sha']==ident['source_sha'] and rows[0]['conclusion']=='success','producer job missing/failed: '+name)
        artifacts=pages(f'actions/runs/{ident["run_id"]}/artifacts','artifacts')
        for target in C.TARGETS:
            name=f'original-hash-{target}-{ident["run_id"]}-{ident["attempt"]}'
            matches=[a for a in artifacts if a['name']==name];C.require(len(matches)==1,'missing/duplicate upload: '+name);a=matches[0]
            C.require(not a['expired'] and a['workflow_run']['id']==int(ident['run_id']) and a['workflow_run']['head_sha']==ident['source_sha'] and
                datetime.fromisoformat(a['expires_at'].replace('Z','+00:00'))>datetime.now(timezone.utc),'artifact identity/expiry')
            path=out/(target+'-upload.zip')
            with path.open('w+b') as f:download_artifact_zip(a['id'],output=f)
            C.require(path.stat().st_size==a['size_in_bytes'] and 'sha256:'+C.digest(path)==a['digest'],'original upload byte identity')
            with zipfile.ZipFile(path) as z:
                C.require(set(C.safe_members(z))=={'manifest.json','envelope.json','result.json','evidence.zip'},'unexpected transport membership')
                dest=C.extract(z,out/(target+'-upload'))
            envelope=json.loads((dest/'envelope.json').read_text());manifest=json.loads((dest/'manifest.json').read_text())
            C.require(all(envelope[k]==v for k,v in ident.items()) and envelope['target']==target,'envelope identity')
            C.require(C.record(dest/'evidence.zip')==envelope['archive'] and C.record(dest/'manifest.json')==envelope['manifest'],'nested byte identity')
            with zipfile.ZipFile(dest/'evidence.zip') as z:folder=C.extract(z,out/(target+'-evidence'))
            checked=C.validate(folder,manifest)
            from test_contract import evidence_mutations
            C.require(evidence_mutations(folder,manifest)==json.loads((folder/'mutation-controls.json').read_text()),
                'independent actual-evidence mutation replay differs')
            C.require(checked['target']==target and json.loads((dest/'result.json').read_text())==dict(ident,**checked),'producer/replay mismatch')
            result['targets'][target]=dict(checked,artifact=dict(id=a['id'],name=a['name'],size_in_bytes=a['size_in_bytes'],digest=a['digest'],expires_at=a['expires_at']))
        result.update(accepted=True,scope='public streaming hash boundary; desktop behavior, all six target links; no mobile runtime or full F07')
        C.save(out/'github.json',dict(run=run,jobs=jobs,source=source))
    except Exception as error:result['failures'].append(str(error))
    finally:C.save(out/'authentication.json',result)
    print(json.dumps(result,sort_keys=True),flush=True)
    C.require(result['accepted'],'same-source boundary authentication failed')

if __name__=='__main__':main()
