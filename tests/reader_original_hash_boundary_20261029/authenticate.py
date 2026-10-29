"""Independently authenticate each same-run original upload, then replay its contract."""
from datetime import datetime, timezone
import hashlib
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

def inspect_prior_archive():
    """Pinned failed-original forensic replay; never turns its failure into admission."""
    C.actions_only();C.guard();out=C.ROOT/'build/hash-archive-diagnostic';out.mkdir(parents=True)
    prior_sha='3597b549340450929c693c31fd3d2f7bf254bbf6';prior_run=40813101185
    pin=dict(id=12871351856,name='original-hash-failed-macos-40813101185-1',size_in_bytes=15151587,
        digest='sha256:ff875ece2f5d27128a83798f0309f237a72daeb5997ab5118fe8f0794fe03b16')
    run=fetch(f'actions/runs/{prior_run}/attempts/1')
    C.require(run['head_sha']==prior_sha and run['head_branch']==C.BRANCH and run['path']==C.WORKFLOW and
        run['run_attempt']==1 and run['status']=='completed' and run['conclusion']=='failure','original failed run identity differs')
    jobs=pages(f'actions/runs/{prior_run}/attempts/1/jobs','jobs')
    producer=[j for j in jobs if j['name']=='produce (macos)']
    C.require(len(producer)==1 and producer[0]['id']==123247837566 and producer[0]['head_sha']==prior_sha and
        producer[0]['status']=='completed' and producer[0]['conclusion']=='failure','original macOS failure identity differs')
    artifact=fetch('actions/artifacts/'+str(pin['id']))
    C.require(all(artifact[k]==v for k,v in pin.items()) and not artifact['expired'] and
        artifact['workflow_run']['id']==prior_run and artifact['workflow_run']['head_sha']==prior_sha,'pinned failed upload metadata differs')
    original=out/'original-upload.zip'
    with original.open('w+b') as stream:download_artifact_zip(pin['id'],output=stream)
    C.require(original.stat().st_size==pin['size_in_bytes'] and 'sha256:'+C.digest(original)==pin['digest'],'original failed upload bytes differ')
    with zipfile.ZipFile(original) as z:folder=C.extract(z,out/'original')
    source=json.loads((folder/'source.json').read_text())
    C.require(source['source_sha']==prior_sha and source['run_id']==str(prior_run) and source['attempt']=='1' and
        source['base_sha']==C.BASE and source['source_scope_passed'] is True,'retained original source identity differs')
    C.require(all(source['files'][p]==C.record(C.ROOT/p) for p in C.OWNER_PATHS),'owner source changed since failed original')
    native=json.loads((folder/'native.json').read_text());dependency=json.loads((folder/'dependency.json').read_text())
    def raw_records(raw):
        C.archive_members(raw)  # strict complete archive grammar/bounds first
        records=[];offset=8
        while offset<len(raw):
            header=raw[offset:offset+60];size=int(header[48:58]);start=offset+60;end=start+size
            records.append(dict(offset=offset,header_hex=header.hex(),name_field=header[:16].decode('ascii').rstrip(),
                mtime=header[16:28].decode('ascii').strip(),uid=header[28:34].decode('ascii').strip(),
                gid=header[34:40].decode('ascii').strip(),mode=header[40:48].decode('ascii').strip(),bytes=size,
                payload_sha256=hashlib.sha256(raw[start:end]).hexdigest(),padding_hex=raw[end:end+size%2].hex()))
            offset=end+size%2
        return records
    report=dict(C.identity(),diagnostic_only=True,original_artifact=pin,original_source_sha=prior_sha,
        original_run_id=prior_run,original_attempt=1,owner_source_unchanged=True,
        original_failed=True,accepted=False,f07_accepted=False,full_six_accepted=False,archives={})
    paths={'hash':('trees/hash-build/libopds_sha256_stream.a','prefix/hash/lib/libopds_sha256_stream.a'),
        'importer':('trees/catalog/libreader_original_import.a','prefix/product/lib/libreader_original_import.a')}
    for owner,(built,installed) in paths.items():
        C.require(dependency[owner]['build_archive']==built and native[owner]['archive']==installed,'retained archive role/path differs')
        before=(folder/built).read_bytes();after=(folder/installed).read_bytes()
        bm=C.archive_members(before);am=C.archive_members(after)
        br=raw_records(before);ar=raw_records(after)
        count=0;preview=[]
        for i in range(max(len(before),len(after))):
            if before[i:i+1]!=after[i:i+1]:
                count+=1
                if len(preview)<64:preview.append(i)
        report['archives'][owner]=dict(build_path=built,installed_path=installed,
            build=C.record(folder/built),installed=C.record(folder/installed),exact_archive_equal=before==after,
            object_payloads_equal=bm==am,build_records=br,installed_records=ar,
            build_members=[dict(name=n,bytes=len(p),sha256=hashlib.sha256(p).hexdigest()) for n,p in bm],
            installed_members=[dict(name=n,bytes=len(p),sha256=hashlib.sha256(p).hexdigest()) for n,p in am],
            differing_byte_count=count,first_64_differing_offsets=preview,
            difference_preview_truncated=count>64)
    C.save(out/'diagnostic.json',report)
    print(json.dumps(report,sort_keys=True),flush=True)

if __name__=='__main__':
    if sys.argv[1:]==['--archive-diagnostic']:inspect_prior_archive()
    else:
        C.require(not sys.argv[1:],'unsupported authentication mode');main()
