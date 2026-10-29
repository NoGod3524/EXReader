"""Independently authenticate each same-run original upload, then replay its contract."""
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import subprocess
import re
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
        report['archives'][owner]['first_bsd_index']=dict(build=C.bsd_index_record(before),installed=C.bsd_index_record(after))
        report['archives'][owner]['equivalence']=C.archive_equivalence(before,after,'macos')
    C.require(report['archives']['hash']['equivalence']['mode']=='exact' and
        report['archives']['importer']['equivalence']['mode']=='macos-first-bsd-index-timestamp' and
        report['archives']['importer']['equivalence']['normalization']['differing_offsets']==[33],
        'original measured archive difference changed')
    C.save(out/'diagnostic.json',report)
    print(json.dumps(report,sort_keys=True),flush=True)

def inspect_retained():
    """No native build: exact original failures plus explicitly partial green replay."""
    C.actions_only();C.guard();out=C.ROOT/'build/hash-retained-diagnostic';out.mkdir(parents=True)
    prior='1198abce384aabe78bc23450db0c38be487706e1';run_id=40816180401
    ident=dict(source_sha=prior,run_id=str(run_id),attempt='1')
    pins={
        'windows':(123257727505,'failure',12872172780,20484861,'3c583f239db3ce44bf1c42a74a663e379a626e1ab3b72387545687ed45a4f438'),
        'android':(123257727506,'failure',12872796406,34983147,'b6e5147f78106c453e95acc8f210cc8579e35e82a1f06044e8b80207c175e56d'),
        'ios-simulator':(123257727410,'failure',12873070476,15080497,'5091108aed26fa040c09306dd8d059f835eb8405fed8d9863c84ff55971a63e6'),
        'linux':(123257727441,'success',12872257369,15257989,'0af1380ab4c84ea1ef5acbc3105c566ac4c96d9ba4cf73fd794e8777fb469852'),
        'macos':(123257727355,'success',12872318239,14784426,'69f4d3e3c511ecdf1bf425d42bccb510ba6cd039ed48bea9000e6a2891d1378f'),
        'ios-device':(123257727411,'success',12872328343,14590280,'26869f8a1ffd1e35bf6bc6bea043406cb5a37776251ae29dbdc295073d21cfaf')}
    result=dict(C.identity(),original_identity=ident,diagnostic_only=True,accepted=False,f07_accepted=False,
        full_six_accepted=False,diagnostic_complete=False,failures=[],original_artifacts={},failed_producer_details={},
        independently_replayed_original_green={},scope='original-source partial replay; no current-source native acceptance')
    try:
        run=fetch(f'actions/runs/{run_id}/attempts/1')
        C.require(run['head_sha']==prior and run['head_branch']==C.BRANCH and run['path']==C.WORKFLOW and
            run['run_attempt']==1 and run['status']=='completed' and run['conclusion']=='failure','original full run identity differs')
        jobs=pages(f'actions/runs/{run_id}/attempts/1/jobs','jobs')
        protocol=[j for j in jobs if j['name']=='protocol']
        C.require(len(protocol)==1 and protocol[0]['id']==123257662840 and protocol[0]['head_sha']==prior and protocol[0]['conclusion']=='success','original protocol identity differs')
        subprocess.run(['git','merge-base','--is-ancestor',prior,'HEAD'],cwd=C.ROOT,check=True)
        paths=C.OWNER_PATHS+C.VALIDATION_PATHS
        changed=subprocess.check_output(['git','diff','--name-only',C.BASE,prior],cwd=C.ROOT,text=True).splitlines()
        C.require(set(changed)==set(paths),'historical source escaped sixteen-file scope')
        sources={p:subprocess.check_output(['git','show',prior+':'+p],cwd=C.ROOT) for p in paths}
        original_source=dict(ident,base_sha=C.BASE,source_scope_passed=True,
            files={p:dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest()) for p,b in sources.items()})
        C.require(all(original_source['files'][p]==C.record(C.ROOT/p) for p in C.OWNER_PATHS),'owner bytes changed since retained run')
        # Replay exact historical verifier/control bytes, not the new diagnostic's predicates.
        code=out/'historical-verifier';code.mkdir()
        for name in ('package_contract.py','test_contract.py'):
            (code/name).write_bytes(sources['tests/reader_original_hash_boundary_20261029/'+name])
        spec=importlib.util.spec_from_file_location('original_hash_contract',code/'package_contract.py')
        old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
        old.ROOT=C.ROOT;old.identity=lambda:dict(ident);old.guard=lambda:original_source
        saved=sys.modules['package_contract'];sys.modules['package_contract']=old
        try:
            spec=importlib.util.spec_from_file_location('original_hash_controls',code/'test_contract.py')
            controls=importlib.util.module_from_spec(spec);spec.loader.exec_module(controls)
        finally:sys.modules['package_contract']=saved
        result['historical_replay_verifier']={name:C.record(code/name) for name in ('package_contract.py','test_contract.py')}
        result['historical_identity_binding']='exact prior git source/16-path guard and original run identity; never relabeled current source'
        for target in ('linux','macos','ios-device','windows','android','ios-simulator'):
            job_id,conclusion,artifact_id,size,digest=pins[target]
            rows=[j for j in jobs if j['name']=='produce ('+target+')']
            C.require(len(rows)==1 and rows[0]['id']==job_id and rows[0]['head_sha']==prior and
                rows[0]['status']=='completed' and rows[0]['conclusion']==conclusion,'original producer identity differs: '+target)
            artifact=fetch('actions/artifacts/'+str(artifact_id))
            name=f'original-hash-{"failed-" if conclusion=="failure" else ""}{target}-{run_id}-1'
            pin=dict(id=artifact_id,name=name,size_in_bytes=size,digest='sha256:'+digest)
            C.require(all(artifact[k]==v for k,v in pin.items()) and not artifact['expired'] and
                artifact['workflow_run']['id']==run_id and artifact['workflow_run']['head_sha']==prior,'original upload metadata differs: '+target)
            original=out/(target+'-original.zip')
            with original.open('w+b') as stream:download_artifact_zip(artifact_id,output=stream)
            C.require(original.stat().st_size==size and C.digest(original)==digest,'original upload bytes differ: '+target)
            with zipfile.ZipFile(original) as z:
                if conclusion=='success':C.require(set(C.safe_members(z))=={'manifest.json','envelope.json','result.json','evidence.zip'},'unexpected successful transport membership')
                folder=C.extract(z,out/(target+'-original'))
            result['original_artifacts'][target]=pin
            if conclusion=='success':
                envelope=json.loads((folder/'envelope.json').read_text());manifest=json.loads((folder/'manifest.json').read_text())
                C.require(all(envelope[k]==v for k,v in ident.items()) and envelope['target']==target,'original envelope identity')
                C.require(C.record(folder/'evidence.zip')==envelope['archive'] and C.record(folder/'manifest.json')==envelope['manifest'],'original nested upload identity')
                with zipfile.ZipFile(folder/'evidence.zip') as z:evidence=C.extract(z,out/(target+'-evidence'))
                checked=old.validate(evidence,manifest)
                C.require(controls.evidence_mutations(evidence,manifest)==json.loads((evidence/'mutation-controls.json').read_text()),'original actual-evidence control replay differs')
                C.require(checked['target']==target and json.loads((folder/'result.json').read_text())==dict(ident,**checked),'original producer/replay mismatch')
                result['independently_replayed_original_green'][target]=checked
                continue
            C.require(json.loads((folder/'source.json').read_text())==original_source,'failed retained source identity differs')
            report=json.loads((folder/'report.json').read_text())
            C.require(all(report[k]==v for k,v in ident.items()) and report['target']==target,'failed retained target identity differs')
            native=json.loads((folder/'native.json').read_text());commands=json.loads((folder/'commands.json').read_text())
            def command_record(path):
                rows=[r for r in commands if r['output']==path]
                C.require(len(rows)==1 and rows[0]['output_record']==C.record(folder/path) and rows[0]['returncode']==0,'diagnostic output not bound to original command')
                return rows[0]
            if target=='windows':
                details=[]
                for owner,entry in native.items():
                    members=C.archive_members((folder/entry['archive']).read_bytes())
                    C.require([n for n,_ in members]==[m['name'] for m in entry['members']],'original COFF member set differs')
                    for (name,payload),member in zip(members,entry['members']):
                        C.require((folder/member['object']).read_bytes()==payload,'original COFF member bytes differ')
                        row=command_record(member['symbols'])
                        C.require(row['subjects']=={member['object']:C.record(folder/member['object'])} and len(row['argv'])==3 and
                            row['argv'][:2]==['dumpbin','/symbols'] and row['argv'][2].replace('\\','/').endswith('/evidence/'+member['object']),'original dumpbin invocation differs')
                        lines=(folder/member['symbols']).read_text().splitlines();weak=[i for i,l in enumerate(lines) if 'WeakExternal' in l]
                        if weak:
                            C.require(len(lines)<=100000 and len(weak)<=4096,'weak diagnostic resource bound')
                            groups=[]
                            for i in weak:
                                context=lines[max(0,i-1):i+3]
                                indices=re.findall(r'Default index\s+([0-9A-Fa-f]+)','\n'.join(context),re.I)
                                fallbacks=[line for line in lines if (label:=re.match(r'^\s*([0-9A-Fa-f]+)\s',line)) and
                                    any(int(label[1],16)==int(index,16) for index in indices)]
                                groups.append(dict(line=i+1,context=context,advertised_default_indices=indices,fallback_rows=fallbacks))
                            details.append(dict(owner=owner,member=name,archive=entry['archive'],object=C.record(folder/member['object']),
                                symbols=C.record(folder/member['symbols']),weak_groups=groups))
                C.require(details,'original weak COFF failure not reproduced in retained diagnostics')
                result['failed_producer_details'][target]=dict(weak_externals=details,admitted=False)
            elif target=='android':
                links=json.loads((folder/'links.json').read_text());details={}
                C.require(set(links)=={'installed','relocated','normal-first','hash-first','revision-first','hash-revision'},'Android link inventory differs')
                for name,link in links.items():
                    command_record(link['commands']);command,inputs,responses=C.link_closure(folder,link)
                    cache_path='trees/'+name+'-build/CMakeCache.txt';cache=(folder/cache_path).read_text()
                    try:C.android_binding(cache,command,name in ('installed','relocated'));failure=None
                    except ValueError as error:failure=str(error)
                    details[name]=dict(final_command=command,inputs=inputs,responses=responses,cache=C.record(folder/cache_path),
                        image=C.record(folder/link['image']),map=C.record(folder/link['map']),binding_failure=failure)
                C.require(any(d['binding_failure']=='unclassified Android linker escape' for d in details.values()),'original Android escape failure not reproduced')
                result['failed_producer_details'][target]=dict(links=details,admitted=False)
            else:
                dependency=json.loads((folder/'dependency.json').read_text());details={}
                for owner,(built,installed) in {'hash':('trees/hash-build/libopds_sha256_stream.a','prefix/hash/lib/libopds_sha256_stream.a'),
                        'importer':('trees/catalog/libreader_original_import.a','prefix/product/lib/libreader_original_import.a')}.items():
                    C.require(dependency[owner]['build_archive']==built and native[owner]['archive']==installed,'original simulator archive role differs')
                    before=(folder/built).read_bytes();after=(folder/installed).read_bytes();count=0;preview=[];outside=0
                    for i in range(max(len(before),len(after))):
                        if before[i:i+1]!=after[i:i+1]:
                            count+=1;outside+=not 24<=i<36
                            if len(preview)<64:preview.append(i)
                    details[owner]=dict(build=C.record(folder/built),installed=C.record(folder/installed),
                        build_index=C.bsd_index_record(before),installed_index=C.bsd_index_record(after),
                        exact_archive_equal=before==after,ordered_object_payloads_equal=C.archive_members(before)==C.archive_members(after),
                        differing_byte_count=count,first_64_differing_offsets=preview,preview_truncated=count>64,
                        differing_bytes_outside_first_timestamp=outside)
                C.require(any(not d['exact_archive_equal'] for d in details.values()),'original simulator archive failure not reproduced')
                result['failed_producer_details'][target]=dict(archives=details,admitted=False,
                    criterion='iOS-simulator still requires full archive byte equality; no macOS rule applied')
        C.require(set(result['failed_producer_details'])=={'windows','android','ios-simulator'} and
            set(result['independently_replayed_original_green'])=={'linux','macos','ios-device'},'partial diagnostic coverage incomplete')
        result['diagnostic_complete']=True
    except Exception as error:result['failures'].append(str(error))
    finally:C.save(out/'diagnostic.json',result)
    print(json.dumps(result,sort_keys=True),flush=True)
    C.require(result['diagnostic_complete'],'retained diagnostic/partial replay failed')

if __name__=='__main__':
    if sys.argv[1:]==['--archive-diagnostic']:inspect_prior_archive()
    elif sys.argv[1:]==['--retained-diagnostic']:inspect_retained()
    else:
        C.require(not sys.argv[1:],'unsupported authentication mode');main()
