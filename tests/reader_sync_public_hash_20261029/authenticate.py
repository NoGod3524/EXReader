"""Independent original-upload and semantic replay for the new union only."""
from datetime import datetime, timezone
import hashlib
import json
import os
import sys
import zipfile
import package_contract as C
from test_contract import evidence_mutations
sys.path.insert(0,str(C.ROOT/'tools'))
from check_parallel_integration import fetch,pages,download_artifact_zip

def main():
    C.actions();source=C.guard();ident=C.identity();out=C.OUT/'authentication'
    out.mkdir(parents=True,exist_ok=False)
    result=dict(ident,combined_named_boundaries=False,original_uploads_verified=False,
        sync_public_link_boundary=False,original_behavior_checks=False,f07_accepted=False,
        full_product_accepted=False,physical_device=False,installed_android_sync_runtime=False,
        targets={},failures=[])
    try:
        run=fetch(f'actions/runs/{ident["run_id"]}/attempts/{ident["attempt"]}')
        C.require(run['head_sha']==ident['source_sha'] and run['head_branch']==C.BRANCH and
            run['path']==C.WORKFLOW and run['run_attempt']==int(ident['attempt']),'immutable run identity differs')
        jobs=pages(f'actions/runs/{ident["run_id"]}/attempts/{ident["attempt"]}/jobs','jobs')
        producers={}
        for name in ('protocol',*('boundary-'+t for t in C.TARGETS)):
            rows=[j for j in jobs if j['name']==name]
            C.require(len(rows)==1 and rows[0]['head_sha']==ident['source_sha'] and
                rows[0]['status']=='completed' and rows[0]['conclusion']=='success','required job failed/missing: '+name)
            producers[name]=rows[0]
        artifacts=pages(f'actions/runs/{ident["run_id"]}/artifacts','artifacts')
        wires=[];covered=[]
        for target in C.TARGETS:
            name=f'sync-public-hash-{target}-{ident["run_id"]}-{ident["attempt"]}'
            matches=[a for a in artifacts if a['name']==name]
            C.require(len(matches)==1,'ambiguous/missing original upload: '+name);a=matches[0]
            C.require(not a['expired'] and a['workflow_run']['head_sha']==ident['source_sha'] and
                a['workflow_run']['id']==int(ident['run_id']),'artifact source/run differs')
            def timestamp(text):return datetime.fromisoformat(text.replace('Z','+00:00'))
            job=producers['boundary-'+target]
            C.require(timestamp(job['started_at'])<=timestamp(a['created_at'])<=timestamp(job['completed_at']) and
                timestamp(a['expires_at'])>datetime.now(timezone.utc),'artifact producer-time/expiry differs')
            original=out/(target+'-upload.zip')
            with original.open('w+b') as stream:download_artifact_zip(a['id'],output=stream)
            C.require(original.stat().st_size==a['size_in_bytes'] and 'sha256:'+C.digest(original)==a['digest'],'original upload bytes differ')
            with zipfile.ZipFile(original) as z:
                names=C.H.safe_members(z);inventory=json.loads(z.read('inventory.json'))
                C.require(all(inventory[k]==v for k,v in ident.items()),'original inventory identity differs')
                C.require({n for n,i in names.items() if not i.is_dir()}==set(inventory['files'])|{'inventory.json'},'complete upload inventory differs')
                for path,meta in inventory['files'].items():
                    with z.open(path) as stream:
                        digest=hashlib.sha256();size=0
                        for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block);size+=len(block)
                    C.require(size==meta['bytes'] and digest.hexdigest()==meta['sha256'],'retained file bytes differ: '+path)
                measured=inventory['report']
                C.require(measured['source']==source and measured['target']==target and measured['capture_complete'] is True and
                    measured['named_boundary_accepted'] is True,'public native/source gate incomplete')
                C.require(measured['f07_accepted'] is False and measured['final_whole_image_f07_audit'] is False,'public scope inflated')
                comparison=C.P.replay_archive_comparisons(z.read,measured,target)
                entries={'iphone','ipad'} if target=='iphone' else {target}
                C.require({e['target'] for e in measured['native']['entries']}==entries,'native entry inventory differs')
                for entry in entries:C.P.verify_delivered_entry(z,entry,measured['packages'][entry])
                for entry in measured['native']['entries']:
                    C.require(all(entry[k]==v for k,v in ident.items()) and entry['passed'] is True and
                        set(entry['retained_wires'])==C.P.EXPECTED_WIRES,'original native wire checks failed')
                    for path,sha in entry['retained_wires'].items():
                        C.require(hashlib.sha256(z.read('build/public-boundary-v1/native-data/'+entry['target']+'-retained/'+path)).hexdigest()==sha,
                            'actual retained wire bytes differ')
                    covered.append(entry['target']);wires.append(entry['retained_wires'])
                extracted=C.H.extract(z,out/(target+'-evidence'))
            proof=extracted/'build/sync-public-hash/proof'
            checked=C.validate(proof,source)
            C.require(checked['target']==target,'new proof target differs')
            controls=evidence_mutations(proof,source)
            C.require(controls==json.loads((extracted/'build/sync-public-hash/mutation-controls.json').read_text()),'independent coherent mutation replay differs')
            result['targets'][target]=dict(checked,public_archive_comparisons=comparison,mutations=controls,
                producer_job_id=job['id'],artifact={k:a[k] for k in ('id','name','size_in_bytes','digest','expires_at')})
            # Keep the immutable original upload; only disposable extracted copy
            # consumes space temporarily. No invocation of artifact binaries.
            import shutil
            shutil.rmtree(extracted)
        C.require(sorted(covered)==sorted(C.ENTRIES) and all(w==wires[0] for w in wires),'six-entry coverage/wire parity differs')
        result.update(combined_named_boundaries=True,original_uploads_verified=True,sync_public_link_boundary=True,
            original_behavior_checks=True,entries=covered,cross_six_retained_wires_equal=True,
            original_behavior_suite_scope=['unchanged public codec/retained plus selector/C06 raw and legacy probes on six entries',
                'unchanged SDK342/F06 delivered entry checks and Linux navigation/folder backend and GUI suites',
                'desktop catalog/original-import fixtures; stream vectors/import faults; new Android digest adapter controls'],
            original_sync_network_suites_run=False,
            original_source_guards_excluded=source['original_source_guards_excluded'],configured_runner_minutes=725,
            limitations=['Android adapter source runtime is not installed Sync/WebDAV hash-path runtime',
                'iPhone/iPad are simulator entries, not physical iOS-device proof',
                'all-module/all-image private imports and original external provider identities remain separate F07 gates'])
    except Exception as error:
        result['failures'].append(str(error));raise
    finally:
        C.save(C.OUT/'authenticated.json',result);print(json.dumps(result,sort_keys=True),flush=True)

if __name__=='__main__':main()
