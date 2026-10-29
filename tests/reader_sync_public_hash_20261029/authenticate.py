"""Independent original-upload and semantic replay for the new union only."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile
import package_contract as C
from test_contract import evidence_mutations,isolation_mutations,archive_pair_mutations
sys.path.insert(0,str(C.ROOT/'tools'))
from check_parallel_integration import fetch,pages,download_artifact_zip

ORIGINAL='f25ce471ce057c3181eb81853e6912350a1b5fed'
ORIGINAL_TREE='303060019705b60728bb45467c1c6f93c13a6c0f'
ORIGINAL_RUN=40833911771
PINS={
    'android':dict(id=12879963967,name='sync-public-hash-android-40833911771-1',size_in_bytes=69520521,
        digest='sha256:9fa61b42bd9976c77bbee6129abfde9c0a64b8e7a2a2bfe67d3d8786680bbb77',job=123314193573,
        root='/home/runner/work/EXReader/EXReader',files=3635,
        steps={'Build exact installed SDK and package':'success','Run reactivecircus/android-emulator-runner@v2':'failure',
            'Capture APK, installed archives and actual compiler dependency graph':'failure'}),
    'iphone':dict(id=12881237625,name='sync-public-hash-iphone-40833911771-1',size_in_bytes=34276768,
        digest='sha256:fb4aa0e29a22f4a50df1f321721f3a262ba47f4acac375850f871371e321c8e3',job=123314193565,
        root='/Users/runner/work/EXReader/EXReader',files=3642,
        steps={'Original F06 SDK342 profile and actual relocated entries, PURE remains OFF':'success',
            'Public C/C++ and unchanged selector/C06 assertions on actual native targets':'success',
            'Capture installed archives, make dependency files, native maps and entries':'failure'})}
PAIR={
    'built':dict(path='build/f06/iphonesimulator-build/product-build/reading-state/libreader_reading_state_codec.a',bytes=33608,
        sha256='3f9e7d9158334a73360bbc480d6a14bf069404d5fc7bb4bde2fefb187d654f62'),
    'installed':dict(path='build/f06/iphonesimulator-build/product/lib/libreader_reading_state_codec.a',bytes=33608,
        sha256='0263850f19ce0ad5b1312a1403e58253b839e6ca04e5b989dc6bdc2d6e6c5ee2')}
CACHE='examples/android/app/.cxx/Debug/4qm105d1/x86_64/CMakeCache.txt'
CACHE_SHA='cd6add24b3f3a3666afe3c613a0e5164a39cbf3f0b72109f00d32ec19c6cc82f'

def unique_json(raw):
    def pairs(rows):
        result={}
        for key,value in rows:C.require(key not in result,'duplicate JSON key');result[key]=value
        return result
    return json.loads(raw,object_pairs_hook=pairs)

def original_git(path):
    C.checked_relative(path)
    return subprocess.check_output(['git','show',ORIGINAL+':'+path],cwd=C.ROOT)

def historical_projection():
    C.require(subprocess.check_output(['git','rev-parse',ORIGINAL+'^{tree}'],cwd=C.ROOT,text=True).strip()==ORIGINAL_TREE,
        'original tree identity differs')
    lock=unique_json(original_git('tests/reader_sync_public_hash_20261029/source_lock.json'))
    C.require(lock['base_sha']==C.BASE and len(lock['expected_delta'])==28 and
        'public_validation_override' not in lock,'historical source lock differs')
    paths=set(lock['adopted'])|set(lock['public_packet'])|set(lock['owner'])|set(lock['added'])
    C.require(len(paths)==53,'historical source53 differs')
    hashes={p:hashlib.sha256(original_git(p)).hexdigest() for p in sorted(paths)}
    C.require(hashes[C.PUBLIC_OVERRIDE]==C.PUBLIC_ORIGINAL_SHA,'original comparator Git bytes differ')
    folder=C.ROOT/'build/sync-retained-frozen'
    folder.mkdir(parents=True,exist_ok=False);(folder/'run.py').write_bytes(original_git(C.PUBLIC_OVERRIDE))
    old=C.load('build/sync-retained-frozen/run.py','union_original_public_refusal')
    return hashes,old

def replay_actual_cache(archive,names,inventory,root):
    caches=sorted(n for n,i in names.items() if not i.is_dir() and n.startswith('examples/android/app/.cxx/') and n.endswith('/CMakeCache.txt'))
    C.require(caches==[CACHE] and names[CACHE].file_size==22349 and inventory['files'][CACHE]['symlink_target'] is None,
        'exact original Android cache inventory differs')
    raw=archive.read(CACHE);C.require(hashlib.sha256(raw).hexdigest()==CACHE_SHA,'original cache bytes differ')
    text=raw.decode('utf-8');home=root+'/examples/android/app/src/main/cpp';build=root+'/'+str(Path(CACHE).parent)
    C.require('ANDROID_ABI:STRING=x86_64' not in text and text.splitlines()[17]=='ANDROID_ABI:UNINITIALIZED=x86_64',
        'original literal selector failure changed')
    selected=C.android_cache_identity(text,home,build)
    C.require(selected['ANDROID_ABI']==dict(type='UNINITIALIZED',value='x86_64'),'observed ABI cache type differs')
    controls={}
    mutations={
        'duplicate':text+'\nANDROID_ABI:UNINITIALIZED=x86_64\n',
        'conflict':text+'\nANDROID_ABI:STRING=arm64-v8a\n',
        'missing':text.replace('ANDROID_ABI:UNINITIALIZED=x86_64','REMOVED_ABI:UNINITIALIZED=x86_64'),
        'wrong-type':text.replace('ANDROID_ABI:UNINITIALIZED=x86_64','ANDROID_ABI:BOOL=x86_64'),
        'abi':text.replace('ANDROID_ABI:UNINITIALIZED=x86_64','ANDROID_ABI:UNINITIALIZED=arm64-v8a'),
        'home':text.replace('CMAKE_HOME_DIRECTORY:INTERNAL='+home,'CMAKE_HOME_DIRECTORY:INTERNAL='+home+'/../cpp'),
        'build':text.replace('CMAKE_CACHEFILE_DIR:INTERNAL='+build,'CMAKE_CACHEFILE_DIR:INTERNAL='+build+'-foreign'),
        'platform':text.replace('ANDROID_PLATFORM:UNINITIALIZED=android-26','ANDROID_PLATFORM:UNINITIALIZED=android-25'),
        'stl':text.replace('ANDROID_STL:UNINITIALIZED=c++_static','ANDROID_STL:UNINITIALIZED=c++_shared'),
        'ndk':text.replace('/ndk/27.0.12077973/','/ndk/26.0.0/'),
        'sdk':text.replace('EXR_HOST_SDK_VERSION:STRING=3.42.0','EXR_HOST_SDK_VERSION:STRING=3.41.0'),
        'raw':text.replace('EXR_READER_SELECTOR_BYTES_CANDIDATE:BOOL=ON','EXR_READER_SELECTOR_BYTES_CANDIDATE:BOOL=OFF')}
    for name,changed in mutations.items():
        C.require(changed!=text,'actual cache control did not mutate intended row: '+name)
        try:C.android_cache_identity(changed,home,build)
        except ValueError as error:controls[name]=str(error)
        else:raise ValueError('actual cache control admitted: '+name)
    return dict(original_path=CACHE,original_bytes=len(raw),original_sha256=CACHE_SHA,original_literal_candidates=0,
        repaired_candidates=1,selected=selected,negative_controls=controls,actual_host_provider_claim=False,passed=True)

def replay_actual_pair(archive,names,inventory,old):
    pairs=[p for p in inventory['report'].get('built_installed_archive_comparison',[]) if p.get('owner')=='reading-state']
    C.require(len(pairs)==1,'exact original failed ReadingState pair missing');pair=pairs[0];values={}
    for role,pin in PAIR.items():
        name=pin['path']
        C.require(pair[role]==name and pair[role+'_bytes']==pin['bytes'] and pair[role+'_sha256']==pin['sha256'] and
            name in names and names[name].file_size==pin['bytes'] and inventory['files'][name]['symlink_target'] is None,
            'original ReadingState pair claim differs')
        raw=archive.read(name)
        C.require(len(raw)==pin['bytes'] and hashlib.sha256(raw).hexdigest()==pin['sha256'],'pinned pair bytes differ')
        values[role]=raw
    before,after=values['built'],values['installed'];refusals={}
    for role,raw in values.items():
        try:old.bsd_index_archive(raw)
        except AssertionError as error:refusals[role]=str(error)
        else:raise ValueError('historical parser unexpectedly admitted original')
    try:old.installed_archive_equivalence(before,after,'iphone')
    except AssertionError as error:refusals['pair']=str(error)
    else:raise ValueError('historical comparator unexpectedly admitted original')
    C.require(set(refusals.values())=={'noncanonical BSD name alignment/padding'},'historical refusal differs')
    row=C.union_archive_equivalence(before,after,'iphone');profile=row['union_criterion'];frames=profile['build_frames']
    C.require(profile['profiles']==['A'] and len(frames)==2 and frames[0]['name']=='__.SYMDEF SORTED' and
        frames[0]['header_offset']==8 and frames[0]['payload_offset']==88 and frames[0]['payload_bytes']==736 and
        frames[0]['payload_sha256']=='fa571aa825ca3925a74a9702a1ef40cee1d6263898109d2fec469a2cffdf66c4' and
        frames[1]['name']=='reading_state.cpp.o' and frames[1]['header_offset']==824 and
        frames[1]['name_bytes']==19 and frames[1]['nul_padding_bytes']==9 and frames[1]['extended_name_bytes']==28 and
        frames[1]['payload_offset']==912 and frames[1]['payload_bytes']==32696 and
        frames[1]['payload_sha256']=='e88e9fbc46eab2e607b1adbbb957b2fc0dde8a99d3b39bb1bbd269cdf120d459',
        'actual Apple-profile geometry differs from pinned observation')
    C.require(row['comparison']['differing_offsets']==pair['first_different_offsets']==[33] and
        pair['different_common_bytes']==1 and pair['length_difference']==0 and
        row['comparison']['build_timestamp']==1793258114 and row['comparison']['installed_timestamp']==1793258115,
        'actual first timestamp delta differs')
    controls=archive_pair_mutations(before,after)
    C.require(len(controls)==12 and all(x['rejected'] for x in controls.values()),'actual archive controls incomplete')
    return dict(original_pair=PAIR,historical_refusals=refusals,new_criterion=row,negative_controls=controls,
        original_run_accepted=False,passed=True)

def replay_retained_isolation(extracted,inventory,ident):
    root=Path(extracted).resolve();proof=root/C.PROOF_REL
    C.require(not (root/C.ISOLATION_REL).exists() and not (root/C.PARK_REL).exists(),
        'original unexpectedly contains successor isolation record')
    wanted={p[len(C.PROOF_REL)+1:]:{k:r[k] for k in ('bytes','sha256')} for p,r in inventory['files'].items()
        if p.startswith(C.PROOF_REL+'/')}
    C.require(wanted and all(inventory['files'][C.PROOF_REL+'/'+p]['symlink_target'] is None for p in wanted),
        'original proof bytes missing/aliased')
    strip=lambda records:{p:{k:r[k] for k in ('bytes','sha256')} for p,r in records.items()}
    C.require(strip(C.proof_inventory(proof)['files'])==wanted,'materialized original proof bytes differ')
    (root/C.PUBLIC_REL).mkdir(parents=True,exist_ok=True)
    live=C.live_cache_inventory(root,True)
    expected_live={p:{k:r[k] for k in ('bytes','sha256')} for p,r in inventory['files'].items() if
        (p.startswith('build/') or p.startswith('examples/android/app/.cxx/')) and p.endswith('/CMakeCache.txt') and
        not p.startswith((C.PROOF_REL+'/',C.PUBLIC_REL+'/'))}
    C.require(live==expected_live,'complete retained live cache projection differs')
    calls=[]
    def observe():
        C.require(not proof.exists() and (root/C.PARK_REL).is_dir(),'diagnostic proof not parked')
        C.require(C.live_cache_inventory(root,False)==live,'diagnostic callback live roots changed')
        calls.append('bounded-observation-no-build')
    success=C.isolated_capture(root,ident,observe)
    C.require(calls==['bounded-observation-no-build'] and success['isolation_passed'],'bounded isolation callback failed')
    C.require(strip(C.proof_inventory(proof)['files'])==wanted,'successful restore changed original content')
    def failure():
        observe();raise RuntimeError('intentional retained-only callback failure')
    try:C.isolated_capture(root,ident,failure)
    except ValueError as error:C.require('intentional retained-only callback failure' in str(error),'wrong restoration-control failure')
    else:raise ValueError('intentional callback failure admitted')
    failed=unique_json((root/C.ISOLATION_REL).read_bytes())
    C.require(failed['restored'] is True and failed['capture_succeeded'] is False and failed['isolation_passed'] is False and
        [e['phase'] for e in failed['errors']]==['capture'] and strip(C.proof_inventory(proof)['files'])==wanted and
        C.live_cache_inventory(root,True)==live,'failed callback did not restore exact retained content')
    for path,meta in inventory['files'].items():
        C.require(C.record(root/path)=={k:meta[k] for k in ('bytes','sha256')},'retained diagnostic changed original file: '+path)
    return dict(passed=True,retained_proof_file_count=len(wanted),retained_live_caches=len(live),
        success_record=success,failure_record=failed,
        original_producer_isolation_record_present=False,original_capture_accepted=False,
        metadata_origin='new diagnostic materialization only; original modes/empty directories not credited')

def original_retained_prerequisites():
    C.actions();source=C.guard();ident=C.identity();C.require(C.current_lane()=='retained','retained lane marker required')
    out=C.OUT/'retained-authentication';out.mkdir(parents=True,exist_ok=False)
    result=dict(ident,source=source,retained_prerequisites_passed=False,original_run_accepted=False,native_rebuilt=False,
        combined_named_boundaries=False,f07_accepted=False,installed_android_sync_runtime=False,physical_device=False,
        configured_retained_runner_minutes=45,conditional_full_runner_minutes=725,targets={},failures=[],stage='current_protocol')
    try:
        run=fetch(f'actions/runs/{ident["run_id"]}/attempts/{ident["attempt"]}')
        C.require(run['head_sha']==ident['source_sha'] and run['head_branch']==C.BRANCH and run['path']==C.WORKFLOW and
            run['run_attempt']==1 and run['event']=='push','current retained run identity differs')
        jobs=pages(f'actions/runs/{ident["run_id"]}/attempts/1/jobs','jobs')
        protocol=[j for j in jobs if j['name']=='protocol']
        C.require(len(protocol)==1 and protocol[0]['head_sha']==ident['source_sha'] and
            protocol[0]['status']=='completed' and protocol[0]['conclusion']=='success','retained protocol did not pass')
        other=[j for j in jobs if j['name'] not in ('protocol','authenticate')]
        C.require(4<=len(other)<=5 and all(j['name'].startswith('boundary-') and j['conclusion']=='skipped' for j in other),
            'retained workflow did not skip every native producer')
        result['protocol_job_id']=protocol[0]['id'];result['native_producers_skipped']=[j['id'] for j in other]
        expected,old=historical_projection()
        original=fetch(f'actions/runs/{ORIGINAL_RUN}/attempts/1')
        C.require(original['head_sha']==ORIGINAL and original['head_branch']==C.BRANCH and original['path']==C.WORKFLOW and
            original['workflow_id']==400305015 and original['event']=='push' and original['run_attempt']==1 and
            original['status']=='completed' and original['conclusion']=='failure','original failed run identity differs')
        original_jobs=pages(f'actions/runs/{ORIGINAL_RUN}/attempts/1/jobs','jobs')
        artifacts=pages(f'actions/runs/{ORIGINAL_RUN}/artifacts','artifacts')
        stamp=lambda value:datetime.fromisoformat(value.replace('Z','+00:00'))
        for target,pin in PINS.items():
            result['stage']=target+'-original-upload';item={};result['targets'][target]=item
            candidates=[j for j in original_jobs if j['id']==pin['job'] and j['name']=='boundary-'+target]
            C.require(len(candidates)==1,'unique original producer missing');job=candidates[0]
            C.require(job['head_sha']==ORIGINAL and job['status']=='completed' and job['conclusion']=='failure','original producer identity differs')
            for name,conclusion in pin['steps'].items():
                steps=[s for s in job['steps'] if s['name']==name]
                C.require(len(steps)==1 and steps[0]['conclusion']==conclusion,'original producer step differs: '+name)
            matches=[a for a in artifacts if a['id']==pin['id'] or a['name']==pin['name']]
            C.require(len(matches)==1,'ambiguous original upload');artifact=matches[0]
            C.require(all(artifact[k]==pin[k] for k in ('id','name','size_in_bytes','digest')) and artifact['expired'] is False and
                artifact['workflow_run']['id']==ORIGINAL_RUN and artifact['workflow_run']['head_sha']==ORIGINAL and
                artifact['workflow_run']['head_branch']==C.BRANCH and
                stamp(job['started_at'])<=stamp(artifact['created_at'])<=stamp(job['completed_at']) and
                stamp(artifact['expires_at'])>datetime.now(timezone.utc),'original upload metadata identity differs')
            upload=out/(target+'-original-upload.zip')
            with upload.open('w+b') as stream:download_artifact_zip(pin['id'],output=stream)
            C.require(upload.stat().st_size==pin['size_in_bytes'] and 'sha256:'+C.digest(upload)==pin['digest'],'original upload bytes differ')
            item.update(original_artifact={k:pin[k] for k in ('id','name','size_in_bytes','digest')},original_job_id=job['id'])
            with zipfile.ZipFile(upload) as archive:
                names=C.H.safe_members(archive)
                C.require(len(names)<=20000 and sum(i.file_size for i in names.values())<=2*1024**3 and
                    'inventory.json' in names and names['inventory.json'].file_size<=16*1024**2,'bounded original ZIP required')
                inventory=unique_json(archive.read('inventory.json'));oldident=dict(source_sha=ORIGINAL,run_id=str(ORIGINAL_RUN),attempt='1')
                C.require(all(inventory[k]==v for k,v in oldident.items()) and
                    {n for n,i in names.items() if not i.is_dir()}==set(inventory['files'])|{'inventory.json'},'original upload inventory differs')
                for path,meta in inventory['files'].items():
                    digest=hashlib.sha256();size=0
                    with archive.open(path) as stream:
                        for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block);size+=len(block)
                    C.require(size==meta['bytes'] and digest.hexdigest()==meta['sha256'],'original file hash differs: '+path)
                report=inventory['report']
                C.require(all(report[k]==v for k,v in oldident.items()) and report['target']==target and
                    report['capture_complete'] is False and report['named_boundary_accepted'] is False and report['f07_accepted'] is False,
                    'original failed capture relabeled')
                def small_json(path):
                    C.require(path in names and names[path].file_size<=2*1024**2,'original metadata missing/oversized')
                    return unique_json(archive.read(path))
                oldsource=small_json('build/sync-public-hash/source.json');build=small_json('build/sync-public-hash/build.json')
                C.require(oldsource['authorized_paths_sha256']==expected and all(oldsource[k]==v for k,v in oldident.items()) and
                    oldsource['source_scope_passed'] is True and oldsource['configured_runner_minutes']==725 and oldsource['f07_accepted'] is False,
                    'original source53 projection differs')
                C.require(all(build[k]==v for k,v in oldident.items()) and build['target']==target and build['source']==oldsource and
                    build['hash_prefix']==pin['root']+'/build/sync-public-hash/hash-stage','original workspace/build identity differs')
                C.require(len(inventory['files'])==pin['files'],'original retained file cardinality differs')
                item.update(original_files_verified=len(inventory['files']),original_source_paths_verified=len(expected))
                result['stage']=target+'-actual-repair-replay'
                item['repair']=replay_actual_cache(archive,names,inventory,pin['root']) if target=='android' else replay_actual_pair(archive,names,inventory,old)
                extracted=C.H.extract(archive,out/(target+'-materialized'))
            result['stage']=target+'-isolation-replay'
            item['isolation']=replay_retained_isolation(extracted,inventory,ident)
            C.require('sha256:'+C.digest(upload)==pin['digest'],'original ZIP changed during retained replay')
            shutil.rmtree(extracted)
        C.require(set(result['targets'])=={'android','iphone'} and all(t['repair']['passed'] and t['isolation']['passed'] for t in result['targets'].values()),
            'named retained prerequisites incomplete')
        result.update(retained_prerequisites_passed=True,stage='complete',
            scope='Pinned original cache/archive and diagnostic-only isolation; all new native/full-F07 acceptance remains false')
    except Exception as error:result['failures'].append(str(error));raise
    finally:
        C.save(C.OUT/'authenticated.json',result);print(json.dumps(result,sort_keys=True),flush=True)

DIAG_SOURCE='4c3efa0089de92e5e0c24e152b780fd78a4767ff'
DIAG_TREE='16cda7dde499a62918d50297b4f3e5820a164317'
DIAG_RUN=40849061712
DIAG_JOB=123363769500
DIAG_PATH='tests/reader_sync_public_hash_20261029/authenticate.py'
DIAG_ROOT='/home/runner/work/EXReader/EXReader'
DIAG_BUILD=DIAG_ROOT+'/examples/android/app/.cxx/Debug/4qm105d1/x86_64'
DIAG_ARTIFACT=dict(id=12887310165,name='sync-public-hash-android-40849061712-1',size_in_bytes=184029237,
    digest='sha256:1a387884f43f674a6cc90b3dcc064c2403d6e27d78470e818af80cc2d50d2d25')
DIAG_QUERY=['ninja','-C',DIAG_BUILD,'-t','query','exreader_product']
DIAG_PREFIX='build/public-boundary-v1/logs/'
DIAG_PROOF='build/sync-public-hash/proof/'
DIAG_LIMITS=dict(zip_entries=30000,zip_total_bytes=8*1024**3,zip_member_bytes=2*1024**3,
    inventory_bytes=16*1024**2,commands_bytes=16*1024**2,cache_bytes=2*1024**2,ninja_bytes=8*1024**2,
    stream_bytes=65536,stream_lines=256,line_bytes=4096,build_statements=32,statement_bytes=65536,json_bytes=1024**2)

def diag_git(path):
    C.checked_relative(path)
    return subprocess.check_output(['git','show',DIAG_SOURCE+':'+path],cwd=C.ROOT)

def diag_scope():
    C.require(subprocess.check_output(['git','rev-parse',DIAG_SOURCE+'^{tree}'],cwd=C.ROOT,text=True).strip()==DIAG_TREE,
        'diagnostic pinned original tree differs')
    subprocess.run(['git','merge-base','--is-ancestor',DIAG_SOURCE,'HEAD'],cwd=C.ROOT,check=True)
    delta=subprocess.check_output(['git','diff','--name-status',DIAG_SOURCE,'HEAD'],cwd=C.ROOT,text=True).splitlines()
    C.require(delta==['M\t'+DIAG_PATH],'diagnostic exact one-auth-file delta required')
    lock=unique_json(diag_git('tests/reader_sync_public_hash_20261029/source_lock.json'))
    paths=set(lock['adopted'])|set(lock['public_packet'])|set(lock['owner'])|set(lock['added'])
    C.require(len(paths)==53,'diagnostic original source53 cardinality differs')
    expected={p:hashlib.sha256(diag_git(p)).hexdigest() for p in sorted(paths)}
    C.require(expected[C.PUBLIC_OVERRIDE]==C.digest(C.ROOT/C.PUBLIC_OVERRIDE),
        'diagnostic parser bytes differ from original Git source')
    return expected

def diag_metadata(run,job,artifact):
    C.require(run['id']==DIAG_RUN and run['run_attempt']==1 and run['head_sha']==DIAG_SOURCE and
        run['head_branch']==C.BRANCH and run['path']==C.WORKFLOW and run['workflow_id']==400305015 and
        run['event']=='push' and run['status']=='completed' and run['conclusion']=='failure','diagnostic original run identity differs')
    C.require(job['id']==DIAG_JOB and job['run_id']==DIAG_RUN and job['head_sha']==DIAG_SOURCE and
        job['name']=='boundary-android' and job['status']=='completed' and job['conclusion']=='failure',
        'diagnostic original producer identity differs')
    for name,conclusion in PINS['android']['steps'].items():
        rows=[s for s in job['steps'] if s['name']==name]
        C.require(len(rows)==1 and rows[0]['conclusion']==conclusion,'diagnostic original step identity differs')
    stamp=lambda s:datetime.fromisoformat(s.replace('Z','+00:00'))
    C.require(all(artifact.get(k)==v for k,v in DIAG_ARTIFACT.items()) and artifact['expired'] is False and
        artifact['workflow_run']['id']==DIAG_RUN and artifact['workflow_run']['head_sha']==DIAG_SOURCE and
        artifact['workflow_run']['head_branch']==C.BRANCH and
        stamp(job['started_at'])<=stamp(artifact['created_at'])<=stamp(job['completed_at']) and
        stamp(artifact['expires_at'])>datetime.now(timezone.utc),'diagnostic original artifact identity differs')

def diag_zip_bounds(names):
    C.require(len(names)<=DIAG_LIMITS['zip_entries'] and
        all(0<=i.file_size<=DIAG_LIMITS['zip_member_bytes'] for i in names.values()) and
        sum(i.file_size for i in names.values())<=DIAG_LIMITS['zip_total_bytes'],'diagnostic ZIP resource bound')

def diag_stream(raw,label):
    C.require(len(raw)<=DIAG_LIMITS['stream_bytes'],'diagnostic stream byte bound: '+label)
    rows=raw.splitlines(keepends=True)
    C.require(len(rows)<=DIAG_LIMITS['stream_lines'] and all(len(r)<=DIAG_LIMITS['line_bytes'] for r in rows),
        'diagnostic stream line bound: '+label)
    text=raw.decode('utf-8',errors='strict')
    return dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),text=text,hex=raw.hex(),
        lines=[dict(number=i+1,bytes=len(r),hex=r.hex(),text=r.decode('utf-8',errors='strict')) for i,r in enumerate(rows)])

def diag_json(value):
    encoded=(json.dumps(value,sort_keys=True,ensure_ascii=True)+'\n').encode('utf-8')
    C.require(len(encoded)<=DIAG_LIMITS['json_bytes'],'diagnostic JSON output bound')
    return encoded

def diag_bound_command(commands,raw,argv=DIAG_QUERY,output='links/android-host-alias.log'):
    C.require(isinstance(commands,list) and len(commands)<=10000,'diagnostic command count bound')
    rows=[r for r in commands if r.get('output')==output]
    C.require(len(rows)==1,'diagnostic unique original command required')
    row=rows[0]
    C.require(set(row)=={'argv','cwd','output','output_record','returncode','expected_returncode','subjects'} and
        row['argv']==argv and row['cwd']==DIAG_ROOT and row['returncode']==row['expected_returncode']==0 and
        row['subjects']=={},'diagnostic exact original command binding')
    C.require(row['output_record']==dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()),
        'diagnostic original command output hash differs')
    return row

def diag_public_command(row,argv):
    C.require(set(row)=={'argv','cwd','exit_code'} and row['argv']==argv and row['cwd']==DIAG_ROOT and row['exit_code']==0,
        'diagnostic later exact command binding')
    return row

def diag_ninja_statements(raw,nodes):
    C.require(len(raw)<=DIAG_LIMITS['ninja_bytes'],'diagnostic Ninja file byte bound')
    text=raw.decode('utf-8',errors='strict');lines=text.splitlines(keepends=True);selected=[]
    for index,line in enumerate(lines):
        matched=[n for n in nodes if line.startswith('build '+n+':')]
        if not matched:continue
        C.require(len(matched)==1,'diagnostic Ninja target ambiguity')
        chunk=[line];position=index+1
        while position<len(lines) and (chunk[-1].rstrip('\r\n').endswith('$') or lines[position].startswith((' ','\t'))):
            chunk.append(lines[position]);position+=1
        joined=''.join(chunk).encode('utf-8')
        C.require(len(joined)<=DIAG_LIMITS['statement_bytes'],'diagnostic Ninja statement byte bound')
        selected.append(dict(node=matched[0],first_line=index+1,last_line=position,text=''.join(chunk),
            bytes=len(joined),sha256=hashlib.sha256(joined).hexdigest()))
        C.require(len(selected)<=DIAG_LIMITS['build_statements'],'diagnostic Ninja statement count bound')
    C.require(len(selected)==len(nodes) and {r['node'] for r in selected}==set(nodes),
        'diagnostic exact retained Ninja target statements missing/duplicate')
    return dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),selected=selected,
        scope='literal retained statements only; not an executed or substitute Ninja graph')

def diag_controls(run,job,artifact):
    # In-memory refusal controls run only in this Actions entrypoint.
    clone=lambda value:json.loads(json.dumps(value));results={}
    def reject(name,call):
        try:call()
        except (ValueError,AssertionError) as error:results[name]=dict(rejected=True,error=str(error))
        else:raise ValueError('diagnostic control unexpectedly admitted: '+name)
    for field in ('source','job','artifact'):
        a,b,c=clone(run),clone(job),clone(artifact)
        if field=='source':a['head_sha']='0'*40
        elif field=='job':b['id']=0
        else:c['digest']='sha256:'+'0'*64
        reject('metadata-'+field,lambda a=a,b=b,c=c:diag_metadata(a,b,c))
    raw=b'exreader_product:\n  input: phony\n    /original/libexreader_product.so\n  outputs:\n'
    row=dict(argv=DIAG_QUERY,cwd=DIAG_ROOT,output='links/android-host-alias.log',returncode=0,expected_returncode=0,
        subjects={},output_record=dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()))
    diag_bound_command([row],raw);diag_stream(raw,'valid-control')
    for field in ('argv','cwd','hash','duplicate'):
        rows=[clone(row)]
        if field=='argv':rows[0]['argv'][-1]='foreign_node'
        elif field=='cwd':rows[0]['cwd']='/foreign'
        elif field=='hash':rows[0]['output_record']['sha256']='0'*64
        else:rows.append(clone(row))
        reject('command-'+field,lambda rows=rows:diag_bound_command(rows,raw))
    reject('stream-byte-limit',lambda:diag_stream(b'x'*(DIAG_LIMITS['stream_bytes']+1),'control'))
    reject('stream-line-limit',lambda:diag_stream(b'x\n'*(DIAG_LIMITS['stream_lines']+1),'control'))
    reject('stream-line-byte-limit',lambda:diag_stream(b'x'*(DIAG_LIMITS['line_bytes']+1),'control'))
    reject('truncated-command-output',lambda:diag_bound_command([row],raw[:-1]))
    class Entry:
        def __init__(self,size):self.file_size=size
    reject('zip-member-limit',lambda:diag_zip_bounds({'x':Entry(DIAG_LIMITS['zip_member_bytes']+1)}))
    reject('zip-total-limit',lambda:diag_zip_bounds({str(i):Entry(DIAG_LIMITS['zip_member_bytes']) for i in range(5)}))
    reject('zip-entry-limit',lambda:diag_zip_bounds({str(i):Entry(0) for i in range(DIAG_LIMITS['zip_entries']+1)}))
    reject('json-output-limit',lambda:diag_json({'text':'x'*DIAG_LIMITS['json_bytes']}))
    ninja=b'build alias: phony /image\n\nbuild /image: CXX_SHARED_LIBRARY_LINKER obj.o\n'
    diag_ninja_statements(ninja,['alias','/image'])
    reject('ninja-missing-target',lambda:diag_ninja_statements(ninja,['foreign']))
    reject('ninja-duplicate-target',lambda:diag_ninja_statements(ninja+ninja,['alias','/image']))
    return results

def retained():
    """One pinned4c query observation; never native or prerequisite admission."""
    C.actions();source=C.guard();ident=C.identity()
    C.require(C.current_lane()=='retained','diagnostic requires existing retained-only marker')
    result=dict(ident,source=source,diagnostic_complete=False,retained_prerequisites_passed=False,native_rebuilt=False,
        original_run_accepted=False,combined_named_boundaries=False,installed_android_sync_runtime=False,f07_accepted=False,
        configured_runner_minutes=45,limits=DIAG_LIMITS,stage='source_scope',failures=[],observations={})
    out=C.OUT/'host-query-diagnostic';out.mkdir(parents=True,exist_ok=False)
    try:
        expected=diag_scope();result['stage']='current_protocol'
        current=fetch(f'actions/runs/{ident["run_id"]}/attempts/1')
        C.require(current['id']==int(ident['run_id']) and current['workflow_id']==400305015 and
            current['head_sha']==ident['source_sha'] and current['head_branch']==C.BRANCH and current['path']==C.WORKFLOW and
            current['run_attempt']==1 and current['event']=='push','diagnostic current run identity differs')
        current_jobs=pages(f'actions/runs/{ident["run_id"]}/attempts/1/jobs','jobs')
        protocol=[j for j in current_jobs if j['name']=='protocol']
        C.require(len(protocol)==1 and protocol[0]['head_sha']==ident['source_sha'] and protocol[0]['conclusion']=='success',
            'diagnostic protocol did not pass')
        others=[j for j in current_jobs if j['name'] not in ('protocol','authenticate')]
        C.require(4<=len(others)<=5 and all(j['name'].startswith('boundary-') and j['conclusion']=='skipped' for j in others),
            'diagnostic native jobs not all skipped')
        result['protocol_job_id']=protocol[0]['id'];result['stage']='original_provider_identity'
        run=fetch(f'actions/runs/{DIAG_RUN}/attempts/1');jobs=pages(f'actions/runs/{DIAG_RUN}/attempts/1/jobs','jobs')
        matched=[j for j in jobs if j['id']==DIAG_JOB];C.require(len(matched)==1,'diagnostic original job missing');job=matched[0]
        artifacts=pages(f'actions/runs/{DIAG_RUN}/artifacts','artifacts')
        matched=[a for a in artifacts if a['id']==DIAG_ARTIFACT['id'] or a['name']==DIAG_ARTIFACT['name']]
        C.require(len(matched)==1,'diagnostic original artifact ambiguous');artifact=matched[0]
        diag_metadata(run,job,artifact);result['original_artifact']=DIAG_ARTIFACT;result['original_job_id']=DIAG_JOB
        result['controls']=diag_controls(run,job,artifact);result['stage']='original_upload'
        upload=out/'original-android.zip'
        with upload.open('w+b') as stream:download_artifact_zip(DIAG_ARTIFACT['id'],output=stream)
        C.require(upload.stat().st_size==DIAG_ARTIFACT['size_in_bytes'] and 'sha256:'+C.digest(upload)==DIAG_ARTIFACT['digest'],
            'diagnostic original upload bytes differ')
        with zipfile.ZipFile(upload) as archive:
            names=C.H.safe_members(archive);diag_zip_bounds(names)
            def read(path,limit):
                if path in inventory['files']:
                    result['observations'].setdefault('selected_files',{})[path]=inventory['files'][path]
                C.require(path in names and not names[path].is_dir() and names[path].file_size<=limit,
                    'diagnostic selected file missing/oversized: '+path)
                C.require(inventory['files'][path]['symlink_target'] is None,'diagnostic selected original file was aliased: '+path)
                return archive.read(path)
            C.require('inventory.json' in names and names['inventory.json'].file_size<=DIAG_LIMITS['inventory_bytes'],
                'diagnostic outer inventory missing/oversized')
            inventory=unique_json(archive.read('inventory.json'));oldident=dict(source_sha=DIAG_SOURCE,run_id=str(DIAG_RUN),attempt='1')
            C.require(all(inventory[k]==v for k,v in oldident.items()) and
                {n for n,i in names.items() if not i.is_dir()}==set(inventory['files'])|{'inventory.json'},'diagnostic complete original inventory differs')
            result['stage']='all_original_files'
            for path,meta in inventory['files'].items():
                digest=hashlib.sha256();size=0
                with archive.open(path) as stream:
                    for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block);size+=len(block)
                C.require(size==meta['bytes'] and digest.hexdigest()==meta['sha256'],'diagnostic retained bytes differ: '+path)
            result['all_original_files_verified']=len(inventory['files']);result['stage']='original_source53'
            oldsource=unique_json(read('build/sync-public-hash/source.json',DIAG_LIMITS['inventory_bytes']))
            C.require(all(oldsource[k]==v for k,v in oldident.items()) and oldsource['authorized_paths_sha256']==expected and
                oldsource['source_scope_passed'] is True and oldsource['lane']=='native' and oldsource['configured_runner_minutes']==725 and
                oldsource['f07_accepted'] is False,'diagnostic original source53 differs')
            build=unique_json(read('build/sync-public-hash/build.json',DIAG_LIMITS['inventory_bytes']))
            C.require(all(build[k]==v for k,v in oldident.items()) and build['source']==oldsource and build['target']=='android' and
                build['hash_prefix']==DIAG_ROOT+'/build/sync-public-hash/hash-stage','diagnostic original build/workspace differs')
            report=inventory['report']
            C.require(all(report[k]==v for k,v in oldident.items()) and report['target']=='android' and report['source']==oldsource and
                report['capture_complete'] is True and report['named_boundary_accepted'] is True and report['f07_accepted'] is False and
                DIAG_PROOF+'manifest.json' not in names,'diagnostic public/union failure boundary differs')
            result['original_source_paths_verified']=len(expected);result['public_capture_complete_union_manifest_absent']=True
            result['stage']='bound_query_streams'
            commands=unique_json(read(DIAG_PROOF+'commands.json',DIAG_LIMITS['commands_bytes']))
            early=read(DIAG_PROOF+'links/android-host-alias.log',DIAG_LIMITS['stream_bytes'])
            result['observations']['earlier']=dict(command=diag_bound_command(commands,early),stream=diag_stream(early,'earlier-merged'),
                origin='raw merged subprocess stdout/stderr bytes; original decoding was strict UTF-8')
            later={}
            for key,suffix in (('stdout','stdout.txt'),('stderr','stderr.txt')):
                raw=read(DIAG_PREFIX+'android-product-alias.'+suffix,DIAG_LIMITS['stream_bytes'])
                later[key]=diag_stream(raw,'later-'+key)
            later['command']=diag_public_command(unique_json(read(DIAG_PREFIX+'android-product-alias.command.json',65536)),DIAG_QUERY)
            later['origin']='producer text-mode decoded/re-encoded files, not original process raw-byte streams'
            result['observations']['later']=later
            try:C.P.ninja_explicit_inputs(early.decode('utf-8'),'exreader_product','phony')
            except AssertionError as error:result['earlier_refusal']=str(error)
            else:raise ValueError('diagnostic original earlier refusal not reproduced')
            C.require(result['earlier_refusal']=='exact Ninja node/rule binding','diagnostic earlier refusal changed')
            inputs,outputs=C.P.ninja_explicit_inputs(later['stdout']['text'],'exreader_product','phony')
            C.require(len(inputs)==1 and inputs[0].startswith(DIAG_ROOT+'/examples/android/app/build/intermediates/cxx/') and
                inputs[0].endswith('/obj/x86_64/libexreader_product.so'),'diagnostic later exact image input differs')
            C.checked_relative(inputs[0][len(DIAG_ROOT)+1:]);image=inputs[0]
            link={key:diag_stream(read(DIAG_PREFIX+'android-product-link-input.'+suffix,DIAG_LIMITS['stream_bytes']),'link-'+key)
                for key,suffix in (('stdout','stdout.txt'),('stderr','stderr.txt'))}
            link['command']=diag_public_command(unique_json(read(DIAG_PREFIX+'android-product-link-input.command.json',65536)),
                ['ninja','-C',DIAG_BUILD,'-t','query',image])
            link_inputs,link_outputs=C.P.ninja_explicit_inputs(link['stdout']['text'],image,'CXX_SHARED_LIBRARY_LINKER')
            result['observations']['later_link']=link
            result['later_strict_replay']=dict(alias_inputs=inputs,alias_outputs=outputs,link_inputs=link_inputs,link_outputs=link_outputs)
            result['stream_comparisons']=dict(early_equals_later_stdout=early==later['stdout']['text'].encode('utf-8'),
                early_equals_later_stdout_then_stderr=early==(later['stdout']['text']+later['stderr']['text']).encode('utf-8'),
                early_equals_later_stderr_then_stdout=early==(later['stderr']['text']+later['stdout']['text']).encode('utf-8'),
                interleaving_or_cause_inferred=False)
            result['stage']='retained_cache_and_ninja'
            cache_path=DIAG_BUILD[len(DIAG_ROOT)+1:]+'/CMakeCache.txt'
            cache=read(cache_path,DIAG_LIMITS['cache_bytes'])
            result['cache']=dict(path=cache_path,bytes=len(cache),sha256=hashlib.sha256(cache).hexdigest(),
                identity=C.android_cache_identity(cache.decode('utf-8'),DIAG_ROOT+'/examples/android/app/src/main/cpp',DIAG_BUILD))
            ninja_path=DIAG_BUILD[len(DIAG_ROOT)+1:]+'/build.ninja'
            result['ninja']=dict(path=ninja_path,**diag_ninja_statements(read(ninja_path,DIAG_LIMITS['ninja_bytes']),['exreader_product',image]))
        C.require('sha256:'+C.digest(upload)==DIAG_ARTIFACT['digest'],'diagnostic original ZIP changed')
        result.update(diagnostic_complete=True,stage='complete',scope='Pinned earlier/later query observations only; no parser repair or native eligibility')
    except Exception as error:result['failures'].append(str(error)[:4096]);raise
    finally:
        encoded=(json.dumps(result,sort_keys=True,ensure_ascii=True)+'\n').encode('utf-8')
        if len(encoded)>DIAG_LIMITS['json_bytes']:
            bounded=dict(ident,diagnostic_complete=False,retained_prerequisites_passed=False,native_rebuilt=False,
                original_run_accepted=False,combined_named_boundaries=False,installed_android_sync_runtime=False,f07_accepted=False,
                stage='json_output_bound',failures=['diagnostic output exceeded1MiB'],
                attempted_json_bytes=len(encoded),attempted_json_sha256=hashlib.sha256(encoded).hexdigest(),
                original_artifact=result.get('original_artifact'),prior_stage=result.get('stage'),prior_failures=result['failures'])
            encoded=diag_json(bounded);(C.OUT/'authenticated.json').write_bytes(encoded);print(encoded.decode('utf-8'),end='',flush=True)
            raise ValueError('diagnostic JSON output bound')
        encoded=diag_json(result);(C.OUT/'authenticated.json').write_bytes(encoded);print(encoded.decode('utf-8'),end='',flush=True)

def main():
    C.actions();source=C.guard();C.require(C.current_lane()=='native','normal authentication requires native lane')
    ident=C.identity();out=C.OUT/'authentication'
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
                comparison=C.P.replay_archive_comparisons(z.read,measured,target,archive_comparator=C.union_archive_equivalence)
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
            isolation=C.validate_capture_isolation(extracted,inventory,ident)
            isolation_controls=isolation_mutations(extracted,inventory,ident)
            checked=C.validate(proof,source)
            C.require(checked['target']==target,'new proof target differs')
            controls=evidence_mutations(proof,source)
            C.require(controls==json.loads((extracted/'build/sync-public-hash/mutation-controls.json').read_text()),'independent coherent mutation replay differs')
            result['targets'][target]=dict(checked,public_archive_comparisons=comparison,mutations=controls,
                capture_isolation=isolation,capture_isolation_mutations=isolation_controls,
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
