"""Actions-only same-source GTK retained/native acceptance. Partial is never full F05."""
import argparse, base64, select, hashlib, json, math, os, re, shutil, signal, stat, subprocess, sys, time, zipfile
from pathlib import Path, PurePosixPath
ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
OUT=ROOT/'build/f05-gtk'
EVID=ROOT/'build/f05-gtk-evidence'
IDENTITY={k:os.environ.get(e,'') for k,e in [('source_sha','GITHUB_SHA'),('run_id','GITHUB_RUN_ID'),('attempt','GITHUB_RUN_ATTEMPT')]}
def require(value,message):
    if not value: raise AssertionError(message)
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def pairs(items):
    result={}
    for k,v in items:
        require(k not in result,'duplicate JSON key '+k);result[k]=v
    return result
def finite(s):
    v=float(s);require(math.isfinite(v),'nonfinite JSON');return v
def loads(s): return json.loads(s,object_pairs_hook=pairs,parse_float=finite,parse_constant=lambda s:(_ for _ in ()).throw(ValueError(s)))
def read(p): return loads(Path(p).read_text())
def save(p,v):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(v,indent=2,allow_nan=False)+'\n')
def git(*args): return subprocess.check_output(['git',*args],cwd=ROOT,text=True).strip()
def contract(): return read(HERE/'contract.json')
def admit():
    c=contract()
    require(os.environ.get('GITHUB_ACTIONS')=='true','Actions only')
    require(IDENTITY['attempt']=='1','one attempt only')
    require(os.environ.get('GITHUB_EVENT_NAME')=='workflow_dispatch','manual only')
    require(os.environ.get('GITHUB_REF')=='refs/heads/'+c['branch'],'wrong branch')
    require(git('rev-parse','HEAD')==IDENTITY['source_sha'],'source mismatch')
    require(git('show','-s','--format=%P','HEAD')==c['parent'],'wrong sole parent')
    actual=git('diff','--name-status',c['parent'],'HEAD').splitlines()
    require(sorted(actual)==sorted(c['delta']),'unexpected source delta')
    for path,blob in c['frozen_blobs'].items():
        require(git('rev-parse','HEAD:'+path)==blob,'frozen source changed '+path)
    for path in ['src','include','cmake','CMakeLists.txt','bindings']:
        require(git('rev-parse','HEAD:'+path)==git('rev-parse',c['sdk_freeze']+':'+path),'SDK changed '+path)
    for name in ['gtk.py','fixture.py']:
        require(git('hash-object',str(HERE/name))==c['copied_blobs'][name],'native scenario changed '+name)
    for name, blob in c['r3_blobs'].items():
        require(git('hash-object',str(HERE/name))==blob,'R3 supporting source changed '+name)
    spec=c['retained_diagnostics']
    require(git('hash-object',str(HERE/'retained_diagnostics.py'))==spec['wrapper_blob'],'diagnostic wrapper changed')
    save(OUT/'observation-controls.json',observation_selftests())
    return c

# Receive observations are scoped to a newly created network session, not a
# fictional Receive counter. Only whitelisted account fields are archived.
NETWORK_FINISHED = "Sync finished. This does not mean those books are readable yet; choose Receive books to add them to your shelf"
RECEIVE_FINISHED = (
    "Sync finished. Open a book to add it to this device's reading library",
    "Sync finished. Some books have version conflicts; open the others to add them to this device",
)
OBS_NUMBERS = ('visible','owner_busy','preparing','phase','closing','session_present',
               'session_state','session_status','session_generation','closed_generation',
               'receive_enabled','projection_status','receive_seen','projected',
               'conflicted','waiting','cancel_requested')
OBS_FIELDS = (*OBS_NUMBERS, 'notice')
SYNC_HOSTS = ['first','second','first','second','first','second','first','second',
              'second','first','second','first','first','second','first']
OBS_CONTROLS = ['fast_same_seen','visible_transition','old_generation','old_receive_terminal',
                'network_only','generation_changed','no_dispatch_or_bad_fields','partial_and_wrong_notice']
def observation_snapshot(value):
    require(isinstance(value,dict),'account observation absent')
    result={}
    for key in OBS_NUMBERS:
        raw=value.get(key)
        require(isinstance(raw,str) and re.fullmatch(r'-?[0-9]{1,20}',raw) is not None,'invalid account field '+key)
        require(key in ('session_status','projection_status') or int(raw)>=0,'negative account counter '+key)
        result[key]=raw
    notice=value.get('notice')
    require(isinstance(notice,str) and len(notice)<=1024,'invalid account notice')
    result['notice']=notice
    for key in ('visible','owner_busy','preparing','closing','session_present','receive_enabled','cancel_requested'):
        require(result[key] in ('0','1'),'invalid boolean '+key)
    return result
def receive_precondition(before,ready):
    before=observation_snapshot(before);ready=observation_snapshot(ready)
    require(int(ready['session_generation'])>int(before['session_generation']),'not a new network session')
    require(all(ready[k]==v for k,v in {'visible':'1','owner_busy':'0','preparing':'0','phase':'0',
        'closing':'0','session_present':'1','session_state':'4','session_status':'0',
        'receive_enabled':'1','cancel_requested':'0'}.items()),'network not ready for Receive')
    require(ready['notice']==NETWORK_FINISHED,'not network-only finish')
    return int(ready['session_generation'])
def receive_observation(ready,current,dispatched):
    ready=observation_snapshot(ready);current=observation_snapshot(current)
    require(dispatched is True,'Receive not dispatched')
    require(current['session_generation']==ready['session_generation'],'network generation changed')
    require(current['visible']=='1' and current['closing']=='0' and current['session_present']=='1'
        and current['session_state']=='4' and current['session_status']=='0' and current['cancel_requested']=='0',
        'Receive host/session no longer active')
    idle=all(current[k]=='0' for k in ('phase','preparing','owner_busy'))
    if not idle:return None
    notice=current['notice']
    if notice==NETWORK_FINISHED:return None
    require(current['receive_enabled']=='1','Receive did not return to available')
    if notice in RECEIVE_FINISHED:
        require(current['projection_status']=='0','Receive completion has projection error')
        return 'received'
    match=re.fullmatch(r'Shelf organization: ([0-9]+) conflicting or incomplete versions; ([0-9]+) waiting for related items\. Sync or resolve them, then retry',notice)
    if match:
        require(int(match[1])+int(match[2])>0 and current['projection_status']!='0','invalid pending projection')
        return 'pending_projection'
    # The one in-progress text is not terminal even if observed with an older
    # idle snapshot. No generic Sync finished prefix or arbitrary error passes.
    if notice=='Adding received books to your shelf':return None
    raise AssertionError('unexpected Receive terminal notice: '+notice)
def verify_receive_trace(record):
    require(isinstance(record,dict) and record.get('completed') is True,'incomplete Receive trace')
    require(type(record.get('pid')) is int and record['pid']>0,'missing host PID')
    generation=receive_precondition(record['before_network'],record['ready'])
    require(record.get('generation')==generation,'trace generation binding')
    require(record.get('dispatch_count')==1 and record.get('dispatch_ok') is True,'not one successful key dispatch')
    dispatch=record.get('dispatch_elapsed')
    require(type(dispatch) in (int,float) and math.isfinite(dispatch) and 0<=dispatch<=300,'invalid dispatch time')
    samples=record.get('samples')
    require(isinstance(samples,list) and 1<=len(samples)<=1300,'Receive trace sample budget')
    network=record.get('network_samples')
    require(isinstance(network,list) and 1<=len(network)<=2500,'network trace sample budget')
    network_last=-1
    for item in network:
        elapsed=item.get('elapsed')
        require(type(elapsed) in (int,float) and math.isfinite(elapsed)
            and 0<=elapsed<240 and elapsed>=network_last,'network deadline/order')
        require(item.get('pid')==record['pid'],'network host changed')
        observation_snapshot(item['state']);network_last=elapsed
    require(network[-1]['state']==record['ready'] and network_last<=dispatch,'network ready binding')
    last=-1;outcome=None
    for index,item in enumerate(samples):
        elapsed=item.get('elapsed')
        require(type(elapsed) in (int,float) and math.isfinite(elapsed)
            and dispatch<=elapsed<dispatch+120 and elapsed>=last,'Receive deadline/order')
        require(item.get('pid')==record['pid'],'host process changed')
        require(outcome is None,'samples after terminal')
        outcome=receive_observation(record['ready'],item['state'],True)
        last=elapsed
    require(outcome is not None and outcome==record.get('outcome'),'terminal evidence absent')
    return outcome
def observation_selftests():
    base={key:'0' for key in OBS_NUMBERS}
    base.update(visible='1',session_generation='10',notice='Loading this library')
    ready=dict(base,session_generation='11',session_present='1',session_state='4',
               receive_enabled='1',receive_seen='1',notice=NETWORK_FINISHED)
    final=dict(ready,notice=RECEIVE_FINISHED[0])
    active=dict(ready,preparing='1',phase='2',owner_busy='1',receive_enabled='0',
                notice='Adding received books to your shelf')
    def trace(states,**changes):
        v={'pid':101,'before_network':base.copy(),'ready':ready.copy(),'generation':11,
           'dispatch_count':1,'dispatch_ok':True,'dispatch_elapsed':1.0,
           'network_samples':[{'elapsed':0.9,'pid':101,'state':ready.copy()}],
           'samples':[{'elapsed':1.1+i*.1,'pid':101,'state':x.copy()} for i,x in enumerate(states)],
           'outcome':'received','completed':True}
        v.update(changes);return v
    results=[]
    def passed(name,good=(),bad=()):
        for item in good:verify_receive_trace(item)
        for item in bad:
            try:verify_receive_trace(item)
            except (AssertionError,KeyError,TypeError,ValueError):pass
            else:raise AssertionError('negative observation control accepted '+name)
        results.append({'name':name,'passed':True,'positive_variants':len(good),'negative_variants':len(bad)})
    passed('fast_same_seen',[trace([final])])
    passed('visible_transition',[trace([active,final])])
    passed('old_generation',bad=[trace([final],before_network=dict(base,session_generation='11'))])
    passed('old_receive_terminal',bad=[trace([final],ready=dict(ready,notice=RECEIVE_FINISHED[0]))])
    passed('network_only',bad=[trace([ready])])
    passed('generation_changed',bad=[trace([dict(final,session_generation='12')])])
    missing=final.copy();missing.pop('receive_enabled')
    passed('no_dispatch_or_bad_fields',bad=[
        trace([final],dispatch_ok=False),trace([final],dispatch_count=0),
        trace([missing]),trace([dict(final,receive_seen='NaN')]),
        trace([final],samples=[{'elapsed':121.0,'pid':101,'state':final}])])
    pending=dict(final,projection_status='1',notice='Shelf organization: 1 conflicting or incomplete versions; 0 waiting for related items. Sync or resolve them, then retry')
    passed('partial_and_wrong_notice',[trace([pending],outcome='pending_projection')],[
        trace([pending]),trace([dict(final,notice='Sync finished. Fake')]),
        trace([dict(final,notice='Library update paused before the scan could finish. Select Retry to continue')]),
        trace([dict(final,notice='Shelf organization: incomplete')]),
        trace([dict(pending,projection_status='0')])])
    require([v['name'] for v in results]==OBS_CONTROLS,'observation control set')
    return dict(IDENTITY,checks=results,count=8,accepted=True,synthetic_predicate_controls_only=True)

def clean(text):
    text=str(text)
    token=os.environ.get('GH_TOKEN','')
    if token:text=text.replace(token,'<redacted>')
    return re.sub(r'(?i)(authorization[=: ]+)(?:basic|bearer)\s+\S+',r'\1<redacted>',text)
def safe_member(root,name,allowed=None):
    require(isinstance(name,str) and name and '\x00' not in name and '\\' not in name and ':' not in name,'unsafe reference')
    p=PurePosixPath(name)
    require(not p.is_absolute() and '..' not in p.parts and str(p)==name and name!='.','noncanonical reference')
    if allowed is not None:require(name in allowed,'unlisted reference '+name)
    file=Path(root).joinpath(*p.parts)
    require(not any(x.is_symlink() for x in [file,*list(file.parents)[:len(p.parts)-1]]),'symlink reference')
    return file
def cache(path):
    values={}
    for line in Path(path).read_text().splitlines():
        if line.startswith(('#','//')) or ':' not in line or '=' not in line:continue
        key,rest=line.split(':',1);_,value=rest.split('=',1)
        require(key not in values,'duplicate cache key '+key);values[key]=value
    return values
def provider_proof():
    c=admit();build=read(ROOT/'build/gtk-sdk342/build.json');check_identity(build,IDENTITY)
    records={}
    for path,digest in build['installed_sha256'].items():
        file=safe_member(ROOT,path)
        require(file.is_file() and not file.is_symlink() and sha(file)==digest,'installed original provider changed '+path)
        records[path]=digest
    hashes=ROOT/'build/f05-original-hash'
    require(hashes.resolve()==hashes and hashes.is_dir(),'noncanonical hash prefix')
    hc=cache(ROOT/'build/f05-original-hash-build/CMakeCache.txt')
    require(hc.get('EXREADER_OPDS_HASH_ONLY')=='ON' and hc.get('CMAKE_INSTALL_PREFIX')==str(hashes),'hash build identity')
    hash_files={}
    for file in sorted(hashes.rglob('*')):
        require(not file.is_symlink(),'hash prefix symlink')
        if file.is_file():hash_files[str(file.relative_to(ROOT))]=sha(file)
    require(hash_files and any('EXReaderOPDSHashConfig.cmake' in x for x in hash_files),'hash owner config absent')
    providers={}
    sdk=ROOT/'build/reading-library/stage';legacy=ROOT/'build/gtk-raw-wave3/legacy-stage'
    for label,spec in c['consumers'].items():
        folder=ROOT/'build/f05-consumers'/label
        values=cache(folder/'CMakeCache.txt')
        require(values.get('CMAKE_HOME_DIRECTORY')==str(ROOT/spec['source']),'consumer source '+label)
        require(values.get('CMAKE_PREFIX_PATH')==str(legacy)+';'+str(sdk),'consumer prefix '+label)
        require(values.get('EXR_SDK_VERSION')=='3.42.0' and values.get('EXR_SDK')==str(sdk),'consumer SDK '+label)
        location=Path(values.get(spec['package']+'_DIR',''))
        parent=sdk if label=='inspect' else legacy
        require(location.is_absolute() and location.resolve()==location and location.is_relative_to(parent),'consumer provider '+label)
        configs={}
        for file in sorted(location.glob('*.cmake')):
            relative=str(file.relative_to(ROOT))
            require(relative in records and sha(file)==records[relative],'unbound provider config')
            configs[relative]=sha(file)
        require(configs,'provider config missing')
        binary=folder/spec['target'];require(binary.is_file(),'consumer target absent '+label)
        providers[label]={'source':spec['source'],'target':spec['target'],'package':spec['package'],
                         'directory':str(location.relative_to(ROOT)),'configs':configs,'binary_sha256':sha(binary),
                         'cache_sha256':sha(folder/'CMakeCache.txt')}
    result=dict(IDENTITY,installed_sha256=records,hash_owner_files=hash_files,consumers=providers,
                hash_cache_sha256=sha(ROOT/'build/f05-original-hash-build/CMakeCache.txt'),passed=True)
    save(OUT/'providers.json',result)
    return result

def verify_import_diagnostics(path):
    c=contract();spec=c['retained_diagnostics']
    require(path.is_file() and not path.is_symlink() and path.stat().st_size<=2*1024*1024,'diagnostic report absent/oversize')
    report=read(path);check_identity(report,IDENTITY)
    require(report.get('schema')==1 and report.get('complete') is True and not report.get('errors'),'diagnostic incomplete')
    require(report.get('original_finished') is True and report.get('original_exception') is None,'original retained main did not finish')
    require(report.get('accepted') is False,'diagnostic must not grant original acceptance')
    require(report.get('timing_perturbation_possible') is True and report.get('extra_queries_only_after_failure') is True,'diagnostic scope')
    require(report.get('report_limit_bytes')==2*1024*1024 and report.get('call_limit')==1024
        and report.get('event_limit_per_call')==512 and report.get('failure_query_total_seconds')==5,'diagnostic limits')
    require(set(report['original_sources'])==set(spec['source_blobs']),'diagnostic source set')
    for source,blob in spec['source_blobs'].items():
        item=report['original_sources'][source]
        require(item['blob']==blob and git('rev-parse','HEAD:'+source)==blob
            and item['sha256']==sha(ROOT/source),'diagnostic original source identity')
    calls=report.get('calls')
    require(isinstance(calls,list) and 52<=len(calls)<=1024,'original dialog call coverage')
    def number(value):
        return type(value) in (int,float) and math.isfinite(value) and value>=0
    def win(value):
        return isinstance(value,str) and re.fullmatch(r'[0-9]{1,20}',value) is not None and int(value)>0
    for index,call in enumerate(calls,1):
        require(type(call['ordinal']) is int and call['ordinal']==index and call.get('outcome')=='returned'
            and call.get('truncated') is False,'original dialog failed/truncated')
        require(type(call['host_pid']) is int and 0<call['host_pid']<2**63,'host process identity')
        require(win(call.get('host_window')) and win(call.get('selected_window')),'original window identity')
        fixture=call.get('fixture');require(isinstance(fixture,dict),'fixture observation missing')
        kind=fixture.get('kind')
        if kind=='fixture':
            value=fixture.get('relative')
            require(set(fixture)=={'kind','relative'} and isinstance(value,str) and len(value)<=240
                and re.fullmatch(r'[A-Za-z0-9_./ -]+',value) is not None,'fixture relative name')
            parts=PurePosixPath(value)
            require(parts.parts and not parts.is_absolute() and parts.as_posix()==value and all(p not in ('..','.','profile','home','run') for p in parts.parts),'unsafe fixture relative name')
        else:
            require(set(fixture)=={'kind'} and kind in ('cancel','outside_fixture','unmapped_fixture','excluded_fixture','non_ascii_fixture'),'fixture category')
        begin=call['started_monotonic'];end=call['finished_monotonic']
        require(number(begin) and number(end) and end>=begin,'dialog clock order')
        events=call['events'];require(isinstance(events,list) and 3<=len(events)<=512,'dialog event budget')
        previous=begin;sync=[];states=[];searches=[]
        for entry in events:
            require(isinstance(entry,dict) and number(entry.get('monotonic'))
                and previous<=entry['monotonic']<=end,'event clock order')
            previous=entry['monotonic'];kind=entry.get('kind')
            if kind=='original_state_read':
                require(set(entry)=={'kind','monotonic','state'} and isinstance(entry['state'],dict)
                    and set(entry['state']).issubset({'sequence','book','error','busy','visible'}),'state observation shape')
                require(all(type(v) is int and -(2**63)<=v<2**63 for v in entry['state'].values()),'state integer fields')
                states.append(entry)
            elif kind=='original_sync_search_return':
                require(set(entry)=={'kind','monotonic','window_ids'} and isinstance(entry['window_ids'],list)
                    and 1<=len(entry['window_ids'])<=64 and all(win(v) for v in entry['window_ids']),'original sync search IDs')
                sync.append(entry)
            elif kind=='original_visible_search_return':
                require(set(entry)=={'kind','monotonic','returncode','stdout_discarded','stderr_discarded'}
                    and type(entry['returncode']) is int and -(2**31)<=entry['returncode']<2**31
                    and entry['stdout_discarded'] is True and entry['stderr_discarded'] is True,'original visible search record')
                searches.append(entry)
            else:
                require(False,'unexpected successful dialog event kind')
        require(len(sync)==1 and call['selected_window']==sync[0]['window_ids'][-1],'missing/ambiguous original selected window')
        require(states and type(states[0]['state'].get('sequence')) is int
            and states[0]['monotonic']<=sync[0]['monotonic'],'missing original entry sequence')
        require(searches and searches[-1]['returncode']==1,'original dialog close result missing')
    return {'complete':True,'calls':len(calls),'sha256':sha(path),'original_main_finished':True,'original_acceptance_not_replaced':True}

def execute(name):
    c=admit();require(name in c['stages'],'unknown stage')
    script=c['stages'][name];OUT.mkdir(parents=True,exist_ok=True)
    proof=dict(IDENTITY,name=name,script_sha256=hashlib.sha256(script.encode()).hexdigest(),passed=False)
    stdout=stderr='';process=None;start=time.monotonic()
    try:
        require(not (OUT/'stopped.json').exists(),'prior failed stage; not_executed')
        if name in ('retained48','native6'):
            expected=read(OUT/'providers.json')
            actual=provider_proof();require(actual==expected,'installed provider changed before runtime')
            proof['inputs']={}
            for path in c['runtime_inputs']:
                file=ROOT/path
                require(file.is_file() and not file.is_symlink(),'runtime input absent '+path)
                proof['inputs'][path]={'sha256':sha(file),'bytes':file.stat().st_size}
        process=subprocess.Popen(['bash','-euo','pipefail','-c',script],cwd=ROOT,stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE,text=True,encoding='utf-8',errors='replace',start_new_session=True)
        stdout,stderr=process.communicate(timeout=c['timeouts'][name])
        proof['returncode']=process.returncode;proof['passed']=process.returncode==0
        if name=='retained48' and proof['passed']:
            proof['diagnostic']=verify_import_diagnostics(OUT/'import-dialog-diagnostics.json')
    except BaseException as error:
        proof['error']=clean(repr(error))[:6000]
        proof['not_executed']=process is None
        if process is not None:
            try:os.killpg(process.pid,signal.SIGTERM)
            except ProcessLookupError:pass
            try:stdout,stderr=process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                try:os.killpg(process.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                try:stdout,stderr=process.communicate(timeout=5)
                except subprocess.TimeoutExpired:proof['cleanup_incomplete']=True
            proof['returncode']=process.poll()
        proof['passed']=False
    finally:
        if process is not None:
            try:
                try:os.killpg(process.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                process.wait(timeout=5)
                proof['process_reaped']=True
            except Exception as error:
                proof['cleanup_error']=clean(repr(error));proof['cleanup_incomplete']=True;proof['passed']=False
        proof['elapsed_seconds']=time.monotonic()-start
        if 'inputs' in proof:
            try:
                proof['inputs_unchanged']=all((ROOT/path).is_file() and sha(ROOT/path)==v['sha256'] and (ROOT/path).stat().st_size==v['bytes'] for path,v in proof['inputs'].items())
                proof['passed']=proof['passed'] and proof['inputs_unchanged']
            except Exception as error:
                proof['inputs_unchanged']=False;proof['inputs_error']=clean(repr(error));proof['passed']=False
            try:
                expected=read(OUT/'providers.json');actual=provider_proof()
                require(actual==expected,'provider changed after runtime')
                proof['providers_unchanged']=True
            except Exception as error:proof['providers_error']=clean(repr(error));proof['passed']=False
        for kind,body in [('stdout',stdout),('stderr',stderr)]:
            path=OUT/(name+'.'+kind+'.log');path.write_text(clean(body))
            proof[kind+'_sha256']=sha(path)
            print(name+' '+kind+':\n'+clean(body)[-12000:],flush=True)
        save(OUT/(name+'.json'),proof)
        if not proof['passed']:
            if not (OUT/'stopped.json').exists():save(OUT/'stopped.json',proof)
    require(proof['passed'],'stage failed '+name+'; '+proof.get('error','see original logs'))
def check_identity(v,expected):
    for k,val in expected.items():require(str(v.get(k))==str(val),'identity mismatch '+k)
def collect():
    c=admit();EVID.mkdir(parents=True,exist_ok=False)
    result=dict(IDENTITY,complete=False,files={},missing=[],excluded=[],errors=[],bytes_copied=0,full_F05_accepted=False)
    count=0
    def allowed(relative):
        parts=PurePosixPath(relative).parts
        if any(x in ('profile','certificates','home','run','sync-work') for x in parts):return False
        if relative.endswith(('.key','.pem','.p12','.sqlite','.sqlite3','.db')) or Path(relative).name.startswith('core'):return False
        return True
    def copy(source):
        nonlocal count
        relative=str(source.relative_to(ROOT))
        if not allowed(relative):
            if len(result['excluded'])<500:result['excluded'].append(relative)
            return
        require(source.is_file() and not source.is_symlink(),'nonregular evidence '+relative)
        size=source.stat().st_size
        require(size<=128*1024*1024 and count<4096,'evidence member budget')
        require(result['bytes_copied']+size<=512*1024*1024,'evidence total declared budget')
        dest=safe_member(EVID,relative);dest.parent.mkdir(parents=True,exist_ok=True)
        digest=hashlib.sha256();actual=0
        with source.open('rb') as inp,dest.open('wb') as out:
            while True:
                chunk=inp.read(1024*1024)
                if not chunk:break
                actual+=len(chunk);result['bytes_copied']+=len(chunk)
                require(actual<=128*1024*1024 and result['bytes_copied']<=512*1024*1024,'actual evidence budget')
                digest.update(chunk);out.write(chunk)
        require(actual==size,'evidence changed during copy')
        result['files'][relative]={'bytes':actual,'sha256':digest.hexdigest()};count+=1
    try:
        candidates=set()
        for relative in c['evidence_files']:
            file=safe_member(ROOT,relative)
            if not file.is_file():result['missing'].append(relative)
            else:candidates.add(file)
        for pattern in c['evidence_patterns']:
            matched=[p for p in ROOT.glob(pattern) if p.is_file()]
            if not matched and pattern not in c['optional_patterns']:result['missing'].append(pattern)
            candidates.update(matched)
        # Inventory names of excluded profile/credential outputs, never their bytes.
        for directory in ['build/f05-gtk-native','build/f05-gtk-retained']:
            folder=ROOT/directory
            if folder.exists():
                for p in folder.rglob('*'):
                    if p.is_file() and p not in candidates and len(result['excluded'])<500:
                        result['excluded'].append(str(p.relative_to(ROOT)))
        for file in sorted(candidates):copy(file)
        result['complete']=not result['missing']
    except Exception as error:
        result['errors'].append(clean(repr(error))[:6000])
    finally:
        save(EVID/'inventory.json',result)
        print(json.dumps({k:result[k] for k in ['complete','missing','errors','bytes_copied']},allow_nan=False),flush=True)
    require(result['complete'] and not result['errors'],'evidence incomplete; inventory retained')
def api(path):
    return loads(subprocess.check_output(['gh','api',path],text=True))
def failed_job_excerpt(job,audit):
    process=subprocess.Popen(['gh','api','--allow-escape-sequences','repos/NoGod3524/EXReader/actions/jobs/'+str(job['id'])+'/logs'],
                             stdout=subprocess.PIPE,stderr=subprocess.STDOUT,start_new_session=True)
    deadline=time.monotonic()+30;tail=bytearray();count=0
    try:
        while time.monotonic()<deadline and count<16*1024*1024:
            ready,_,_=select.select([process.stdout],[],[],min(3,max(0,deadline-time.monotonic())))
            if not ready:continue
            block=os.read(process.stdout.fileno(),65536)
            if not block:break
            count+=len(block);tail.extend(block)
            if len(tail)>65536:del tail[:-65536]
    finally:
        if process.poll() is None:os.killpg(process.pid,signal.SIGKILL)
        process.wait(timeout=10)
        (audit/'producer-failure-excerpt.log').write_text(clean(tail.decode('utf-8','replace')))
        save(audit/'producer-failure-excerpt.json',{'bytes_observed':count,'tail_bytes':len(tail),'bounded_excerpt':True})
def audit_inner(audit,state):
    c=admit();run=IDENTITY['run_id'];repo='NoGod3524/EXReader'
    prefix='repos/'+repo+'/actions'
    info=api(prefix+'/runs/'+run);save(audit/'run.json',info);state['run_received']=True
    require(info['head_sha']==IDENTITY['source_sha'] and str(info['run_attempt'])=='1','run source/attempt')
    require(info['head_branch']==c['branch'] and info['event']=='workflow_dispatch','run branch/event')
    require(info['repository']['full_name']==repo,'wrong repository')
    require(info['path']=='.github/workflows/gtk-sdk342-package.yml','wrong workflow')
    jobpage=api(prefix+'/runs/'+run+'/attempts/1/jobs?per_page=100');save(audit/'jobs.json',jobpage)
    require(jobpage['total_count']<=100,'job pagination exceeds bounded list')
    jobs=jobpage['jobs']
    found=[j for j in jobs if j['name']=='F05 GTK native producer']
    require(len(found)==1,'producer job not unique')
    if found[0]['status']=='completed' and found[0]['conclusion']!='success':failed_job_excerpt(found[0],audit)
    require(found[0]['status']=='completed' and found[0]['conclusion']=='success','producer not successful; original job/step metadata and available log excerpt retained')
    job=found[0];require(str(job['run_id'])==run and str(job['run_attempt'])=='1' and job['head_sha']==IDENTITY['source_sha'],'producer job identity')
    require(job['head_branch']==c['branch'] and job['workflow_name']==info['name'],'producer workflow/branch')
    artpage=api(prefix+'/runs/'+run+'/artifacts?per_page=100');save(audit/'artifacts.json',artpage)
    require(artpage['total_count']<=100,'artifact pagination exceeds bound')
    arts=artpage['artifacts']
    arts=[a for a in arts if a['name']=='f05-gtk-native-'+run+'-1']
    require(len(arts)==1 and not arts[0]['expired'],'artifact identity/expiry')
    art=arts[0]
    require(art['workflow_run']['head_sha']==IDENTITY['source_sha'] and str(art['workflow_run']['id'])==run,'artifact source/run')
    require(art['workflow_run']['head_branch']==c['branch'] and art['workflow_run']['repository_id']==info['repository']['id'] and art['workflow_run']['head_repository_id']==info['head_repository']['id'],'artifact branch/repository')
    require(0<art['size_in_bytes']<=512*1024*1024,'artifact compressed budget')
    digest=art.get('digest','')
    require(re.fullmatch('sha256:[0-9a-f]{64}',digest) is not None,'artifact digest missing')
    archive=audit/'original.zip'
    download=subprocess.Popen(['gh','api',prefix+'/artifacts/'+str(art['id'])+'/zip'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
    downloaded=0;deadline=time.monotonic()+180;errors=bytearray()
    streams={download.stdout:'out',download.stderr:'err'}
    try:
        with archive.open('wb') as out:
            while streams:
                remaining=deadline-time.monotonic();require(remaining>0,'download timeout')
                ready,_,_=select.select(list(streams),[],[],min(remaining,5))
                for stream in ready:
                    block=os.read(stream.fileno(),1024*1024)
                    if not block:del streams[stream];continue
                    if stream is download.stdout:
                        downloaded+=len(block);require(downloaded<=512*1024*1024,'download actual budget');out.write(block)
                    else:
                        errors.extend(block);require(len(errors)<=65536,'download error budget')
        require(download.wait(timeout=10)==0,'artifact download failed '+clean(errors.decode('utf-8','replace'))[-2000:])
    finally:
        if download.poll() is None:
            os.killpg(download.pid,signal.SIGKILL);download.wait(timeout=10)
        (audit/'download.log').write_text(clean(errors.decode('utf-8','replace')))
    require(archive.stat().st_size==art['size_in_bytes'] and sha(archive)==digest[7:],'archive bytes/digest')
    extracted=audit/'evidence';extracted.mkdir()
    total=0;seen=set()
    with zipfile.ZipFile(archive) as z:
        items=z.infolist()
        require(len(items)<=4096 and sum(i.file_size for i in items)<=512*1024*1024,'archive declared total/count')
        for item in items:
            require(not(item.flag_bits&1) and item.compress_type in (zipfile.ZIP_STORED,zipfile.ZIP_DEFLATED),'encrypted/unknown compression')
            require(item.file_size<=128*1024*1024,'declared member budget')
            name=item.orig_filename
            require(name==item.filename and '\x00' not in name and '\\' not in name and ':' not in name,'unsafe archive name')
            p=PurePosixPath(name)
            require(not p.is_absolute() and '..' not in p.parts and str(p)!='.' and (name==str(p) or (item.is_dir() and name==str(p)+'/')),'noncanonical member')
            require(str(p) not in seen,'duplicate member');seen.add(str(p))
            mode=item.external_attr>>16;kind=stat.S_IFMT(mode)
            require(kind in (0,stat.S_IFREG,stat.S_IFDIR),'nonregular archive member')
            require(not(kind==stat.S_IFREG and item.is_dir()) and not(kind==stat.S_IFDIR and not item.is_dir()),'type conflict')
            # All entries are validated before extracting any content.
        for item in items:
            p=PurePosixPath(item.orig_filename.rstrip('/'))
            dest=extracted.joinpath(*p.parts)
            if item.is_dir():dest.mkdir(parents=True,exist_ok=True);continue
            require(item.file_size<=128*1024*1024,'member budget')
            dest.parent.mkdir(parents=True,exist_ok=True);count=0
            with z.open(item) as inp,dest.open('wb') as out:
                while True:
                    block=inp.read(1024*1024)
                    if not block:break
                    count+=len(block);total+=len(block)
                    require(count<=128*1024*1024 and total<=512*1024*1024,'actual inflated budget')
                    out.write(block)
            require(count==item.file_size,'inflated length')
    inv=read(extracted/'inventory.json');check_identity(inv,IDENTITY)
    actual={str(p.relative_to(extracted)) for p in extracted.rglob('*') if p.is_file()}
    require(actual==set(inv['files'])|{'inventory.json'},'inventory exact member set')
    for name,entry in inv['files'].items():
        p=safe_member(extracted,name,actual)
        require(p.stat().st_size==entry['bytes'] and sha(p)==entry['sha256'],'member fingerprint '+name)
    require(inv['complete'] is True and not inv['errors'],'collection failed')
    require(not inv['missing'],'required outputs missing '+repr(inv['missing']))
    for name,script in c['stages'].items():
        proof=read(extracted/'build/f05-gtk'/ (name+'.json'));check_identity(proof,IDENTITY)
        require(proof['name']==name and proof['passed'] is True and proof['returncode']==0,'stage evidence '+name)
        require(proof['script_sha256']==hashlib.sha256(script.encode()).hexdigest(),'stage script '+name)
        if name in ('retained48','native6'):
            require(proof['inputs_unchanged'] is True and proof['providers_unchanged'] is True and set(proof['inputs'])==set(c['runtime_inputs']),'runtime input set')
            for path,item in proof['inputs'].items():
                require(sha(safe_member(extracted,path,inv['files']))==item['sha256'] and safe_member(extracted,path,inv['files']).stat().st_size==item['bytes'],'actual runtime input '+path)
        for kind in ['stdout','stderr']:
            require(sha(extracted/'build/f05-gtk'/(name+'.'+kind+'.log'))==proof[kind+'_sha256'],'original stage log '+name)
    diagnostic=verify_import_diagnostics(extracted/'build/f05-gtk/import-dialog-diagnostics.json')
    retained_proof=read(extracted/'build/f05-gtk/retained48.json')
    require(retained_proof.get('diagnostic')==diagnostic,'producer/audit diagnostic proof mismatch')
    build=read(extracted/'build/gtk-sdk342/build.json');check_identity(build,IDENTITY)
    require(build['passed'] is True and build['sdk_version']=='3.42.0','canonical build')
    raw=read(extracted/'build/gtk-raw-wave3/result.json')
    require(raw['source']==IDENTITY['source_sha'] and raw['accepted'] is True,'raw original acceptance')
    require(raw['raw_install']['accepted'] is True and raw['legacy_install']['accepted'] is True
        and raw['raw_host']['accepted'] is True and raw['raw_backend']['accepted'] is True and raw['legacy_host']['configured_and_linked'] is True,'raw/legacy gates')
    providers=read(extracted/'build/f05-gtk/providers.json');check_identity(providers,IDENTITY)
    require(providers['passed'] is True and providers['installed_sha256']==build['installed_sha256'],'original installed provider inventory')
    require(set(providers['consumers'])==set(c['consumers']),'four exact consumers')
    for label,spec in c['consumers'].items():
        folder='build/f05-consumers/'+label
        values=cache(safe_member(extracted,folder+'/CMakeCache.txt',inv['files']))
        require(values.get('CMAKE_HOME_DIRECTORY')==str(ROOT/spec['source']),'audited consumer source')
        require(values.get('CMAKE_PREFIX_PATH')==str(ROOT/'build/gtk-raw-wave3/legacy-stage')+';'+str(ROOT/'build/reading-library/stage'),'audited consumer family')
        require(values.get('EXR_SDK_VERSION')=='3.42.0' and values.get('EXR_SDK')==str(ROOT/'build/reading-library/stage'),'audited consumer SDK')
        provider=providers['consumers'][label]
        require(provider['source']==spec['source'] and provider['target']==spec['target'] and provider['package']==spec['package'],'provider type')
        location=Path(values.get(spec['package']+'_DIR',''))
        expected=ROOT/('build/reading-library/stage' if label=='inspect' else 'build/gtk-raw-wave3/legacy-stage')
        require(location.is_absolute() and '..' not in location.parts and location.is_relative_to(expected),'package family binding')
        require(str(location.relative_to(ROOT))==provider['directory'],'package directory identity')
        require(sha(safe_member(extracted,folder+'/'+spec['target'],inv['files']))==provider['binary_sha256'],'consumer binary identity')
        require(sha(safe_member(extracted,folder+'/CMakeCache.txt',inv['files']))==provider['cache_sha256'],'consumer cache identity')
        require(provider['configs'],'provider config inventory')
        for path,digest in provider['configs'].items():
            require(path in build['installed_sha256'] and build['installed_sha256'][path]==digest,'original package inventory')
            require(sha(safe_member(extracted,path,inv['files']))==digest,'original package bytes')
    require(providers['hash_owner_files'],'hash owner inventory absent')
    for path,digest in providers['hash_owner_files'].items():
        require(path.startswith('build/f05-original-hash/'),'hash owner prefix')
        require(sha(safe_member(extracted,path,inv['files']))==digest,'hash owner original bytes')
    hcpath=safe_member(extracted,'build/f05-original-hash-build/CMakeCache.txt',inv['files'])
    require(sha(hcpath)==providers['hash_cache_sha256'],'hash owner cache digest')
    hc=cache(hcpath)
    require(hc.get('EXREADER_OPDS_HASH_ONLY')=='ON' and hc.get('CMAKE_INSTALL_PREFIX')==str(ROOT/'build/f05-original-hash'),'canonical hash owner cache')
    host=extracted/c['payload']/'bin/exreader-linux'
    require(sha(host)==build['program_sha256'],'canonical payload/program')
    retained=read(extracted/'build/f05-gtk-retained/result.json');check_identity(retained,IDENTITY)
    require(retained['accepted'] is True and retained['count']==48 and len(retained['checks'])==48
        and retained['checks']==c['retained_checks'],'original exact48')
    require(retained['credential_leak_hits']==0 and retained['local_originals']==52 and retained['native_https'] is True and retained['remote_sdk_import_accepted'] is True and retained['remote_projection_accepted'] is True and retained['complete_product'] is False,'retained safety flags')
    require(retained['program_sha256']==sha(host),'retained host mismatch')
    received=retained['received']
    require(received['checks']==c['receive_checks'] and received['mislocated']==0 and received['originals_read_back']==4,'receive original25')
    native=extracted/'build/f05-gtk-native'
    coverage=read(native/'coverage.json')
    expected_native={'source':IDENTITY['source_sha'],'run':run,'attempt':'1'}
    check_identity(coverage['identity'],expected_native)
    require(coverage['host']=='linux' and not coverage['errors'] and not coverage['cleanup_errors'],'native errors')
    require(coverage.get('dry_run') is False and coverage.get('configuration_mode')=='ready','formal native execution required')
    timings=coverage.get('cleanup_timings')
    require(isinstance(timings,list),'cleanup timings absent')
    native_timings=[row for row in timings if row.get('action','').startswith('native-close-')]
    require([row.get('action') for row in native_timings]==['native-close-0','native-close-1','native-close-2']
        and all(type(row.get('seconds')) in (int,float) and 0<=row['seconds']<=20 for row in native_timings),
        'native cleanup exceeded 20 seconds')
    require(coverage['program_sha256']==sha(host),'native program mismatch')
    controls=read(extracted/'build/f05-gtk/observation-controls.json')
    require(controls==observation_selftests(),'original observation controls mismatch')
    trace=read(native/'receive-observations.json');check_identity(trace['identity'],expected_native)
    require(trace['program_sha256']==sha(host) and trace['full_F05_accepted'] is False,'Receive trace identity')
    records=trace['records']
    require(len(records)==15 and [r['host'] for r in records]==SYNC_HOSTS,'original15 sync calls')
    require([r['index'] for r in records]==list(range(1,16)),'Receive invocation order')
    require([r['case_index'] for r in records]==[0,0,1,1,2,2,3,3,3,3,3,3,4,4,4],'Receive case mapping')
    for row in records:verify_receive_trace(row)
    require(records[0]['pid']==records[2]['pid'] and records[4]['pid']!=records[0]['pid'],'restarted first host identity')
    for host_name,start,end in [('second',0,15),('first',0,4),('first',4,15)]:
        segment=[r for r in records[start:end] if r['host']==host_name]
        require(len({r['pid'] for r in segment})==1,'unexpected host replacement')
        require(all(a['generation']<b['generation'] for a,b in zip(segment,segment[1:])),'network generation did not advance')
    save(audit/'receive-observation-accepted.json',dict(IDENTITY,predicate_controls=8,
        actual_sync_invocations=15,pending_projection=[r['index'] for r in records if r['outcome']=='pending_projection'],
        full_F05_accepted=False,delete_detail_accepted=False))
    cases=coverage['cases']
    require([x['name'] for x in cases]==c['native_cases'],'six exact native cases')
    require([x['outcome'] for x in cases]==['passed','passed','passed','partial','passed','passed'],'partial must remain partial')
    receipt=read(native/'receipt.json');check_identity(receipt['identity'],expected_native)
    from case_alignment import align_cases
    require(all(row['executed'] for row in align_cases(cases,receipt['cases'],receipt['claims'])),
        'native case not executed')
    require(receipt['schema']==2 and receipt['host']=='linux' and receipt['sdk_freeze']==c['sdk_freeze'],'receipt schema')
    require(receipt['F05_accepted'] is False and receipt['artifact_authenticated_by_producer'] is False,'receipt claims')
    require(receipt['program_sha256']==sha(host)==sha(native/'program.bin'),'receipt actual binary')
    require(receipt['claims']=={claim:[{'case_id':case,'role':role}] for claim,case,role in c['claim_roles']},'exact native role mapping')
    normalized=receipt['cases']
    require([x['id'] for x in normalized]==c['native_cases'],'receipt native case mapping')
    for x,original in zip(normalized,cases):
        require(x['outcome']==original['outcome'] and x['actual_host_actions'] is True
            and x['receiver_database_injection'] is False and x['original_identity_preserved'] is True
            and x['revision_bytes_preserved'] is True,'native claim mismatch')
        for member in x['source_evidence']:
            require(member in receipt['evidence_members'] and safe_member(native,member,{p[len('build/f05-gtk-native/'):] for p in inv['files'] if p.startswith('build/f05-gtk-native/')}).is_file(),'case evidence absent')
    for member in receipt['evidence_members']:
        require(safe_member(native,member,{p[len('build/f05-gtk-native/'):] for p in inv['files'] if p.startswith('build/f05-gtk-native/')}).is_file() and not member.endswith('.key'),'evidence file absent')
    by={x['id']:x for x in normalized}
    cancel=by['cancel_sync_retry'];require(cancel['remote_boundary'] and cancel['native_cancel_observed'] and cancel['explicit_retry_passed'] and cancel['cancel_layer']=='transport','cancel proof')
    recovery=by['kill_commit_ack_replay']
    require(recovery['terminated_pid']!=recovery['reopened_pid'] and recovery['actual_process_termination']
        and recovery['durable_recovery_passed'] and recovery['recovery_boundary']=='committed-PUT-before-ACK','real recovery boundary')
    deletion=by['delete_put_tombstone_preserved']
    require(deletion['delete_conflict_displayed'] is False and deletion['explicit_user_restore'] is False
        and deletion['tombstone_preserved'] and deletion['stale_peer_did_not_resurrect'],'deletion partial semantics')
    proof=deletion['old_put_after_tombstone']
    require(proof['put']['operation']=='put' and proof['delete']['operation']=='delete'
        and proof['put']['parents']==proof['delete']['parents']==proof['common_parent'],'native parents/operation')
    require(proof['delete_commit']['index']<proof['put_commit']['index'] and proof['restore_revision_created'] is False,'old put ordering')
    require(set(deletion['competing_heads'])==set(deletion['final_heads']) and len(set(deletion['final_heads']))==2,'deletion heads')
    concurrent=by['concurrent_heads_preserved']
    require(concurrent['conflict_displayed'] and len(set(concurrent['final_heads']))==2
        and set(concurrent['final_heads'])==set(concurrent['competing_heads']),'concurrent heads')
    require(by['restart_offline_read']['reopened_host_readable'] and by['restart_offline_read']['network_requests']==0,'offline local endpoint proof')
    checkpoint=None
    for name in ['peer-baseline','peer-delete','peer-delete-put']:
        cp=read(native/name/'manifest.json');check_identity(cp,expected_native)
        require(cp['sdk']==c['sdk_freeze'],'checkpoint SDK')
        for path,item in cp['files'].items():
            body=safe_member(native/name,item['file'],{p[len('build/f05-gtk-native/'+name+'/'):] for p in inv['files'] if p.startswith('build/f05-gtk-native/'+name+'/')})
            require(body.is_file() and body.stat().st_size==item['bytes'] and sha(body)==item['sha256'],'wire bytes')
            require(any(k['path']==path and k['sha256']==item['sha256'] and k['authenticated_native_put'] for k in cp['commits']),'native authenticated commit')
        checkpoint=cp
    for role in ['put','delete']:
        match=[x for x in checkpoint['files'].values() if x['sha256']==proof[role+'_commit']['sha256']]
        require(len(match)==1,'typed native wire uniqueness')
        wire=read(safe_member(native/'peer-delete-put',match[0]['file'],{p[len('build/f05-gtk-native/peer-delete-put/'):] for p in inv['files'] if p.startswith('build/f05-gtk-native/peer-delete-put/')}))
        require(wire==proof[role],'actual wire vs typed native claim')
    require(sha(native/'offline-sdk-original.bin')==cases[-1]['original_sha256'],'offline bytes')
    save(audit/'accepted.json',dict(IDENTITY,artifact=art,producer_job=found[0],retained48_accepted=True,
        native_cases=6,native_passed=5,native_partial=1,delete_detail_accepted=False,
        artifact_authenticated=True,full_F05_accepted=False))
    print('F05 GTK original48 and five native recovery cases accepted; delete-put preservation partial; UI/fullF05 false',flush=True)
def authenticate():
    audit=ROOT/'build/f05-gtk-audit';audit.mkdir(parents=True,exist_ok=False)
    state=dict(IDENTITY,accepted=False,full_F05_accepted=False,delete_detail_accepted=False,errors=[])
    try:
        audit_inner(audit,state);state['accepted']=True
    except Exception as error:
        state['errors'].append(clean(repr(error))[:6000])
        raise
    finally:
        state['available_reports']=[]
        root=audit/'evidence'
        if root.is_dir():
            for path in sorted(root.rglob('*.json')):
                if len(state['available_reports'])>=300:break
                if path.is_file():state['available_reports'].append(str(path.relative_to(root)))
        save(audit/'audit-result.json',state)
        print(json.dumps(state,allow_nan=False),flush=True)
def main():
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['admit','exec','collect','audit','providers']);parser.add_argument('stage',nargs='?')
    args=parser.parse_args()
    if args.mode=='admit':admit();print('F05 GTK exact-source admission passed',flush=True)
    elif args.mode=='exec':execute(args.stage)
    elif args.mode=='collect':collect()
    elif args.mode=='providers':provider_proof()
    else:authenticate()
if __name__=='__main__':
    try:main()
    except Exception as e:
        print('F05 GTK FAILURE '+clean(repr(e))[:6000],flush=True)
        sys.exit(1)
