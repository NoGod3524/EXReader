"""Read five authenticated members from one failed GTK producer. No host execution."""
import hashlib,json,math,os,re,select,signal,stat,subprocess,sys,time,zipfile
from pathlib import Path,PurePosixPath
import driver
from case_alignment import align_cases
ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'build/f05-gtk-network-inspect'
WORK=ROOT/'build/f05-gtk-network-work'
PARENT='c4d67540a0e17a86bd42ad9323cd269ce8959326'
BRANCH='codex/f05-gtk-delete-details-20261103'
PRODUCER_BRANCH='dot/f05-gtk-native-recovery-20261103'
RUN=41642819421
JOB=125940466725
ART=13234044335
SIZE=34886675
DIGEST='4b9c81a902b5f95f77b54668f1269fb0acdcfbb4fb7c3dc5668fa6120cbc6eb8'
PREFIX='repos/NoGod3524/EXReader/actions/'
NATIVE='build/f05-gtk-native/'
STAGE='build/f05-gtk/'
MEMBERS=['inventory.json',NATIVE+'coverage.json',NATIVE+'receipt.json',
         NATIVE+'receive-observations.json',STAGE+'native6.json']
def need(v,s):
    if not v:raise AssertionError(s)
def clean(s):
    s=str(s);token=os.environ.get('GH_TOKEN','')
    if token:s=s.replace(token,'<redacted>')
    return re.sub(r'(?i)(authorization[=: ]+)(?:basic|bearer)\s+\S+',r'\1<redacted>',s)
def sanitize(value):
    if isinstance(value,str):return clean(value)
    if isinstance(value,list):return [sanitize(x) for x in value]
    if isinstance(value,dict):return {k:sanitize(v) for k,v in value.items()}
    return value
def finite(s):
    v=float(s);need(math.isfinite(v),'nonfinite number');return v
def pairs(items):
    v={}
    for k,x in items:
        need(k not in v,'duplicate JSON key');v[k]=x
    return v
def loads(b):return json.loads(b,object_pairs_hook=pairs,parse_float=finite,
    parse_constant=lambda s:(_ for _ in ()).throw(ValueError('nonfinite constant')))
def write(name,v):
    (OUT/name).write_text(json.dumps(v,indent=2,allow_nan=False)+'\n')
def api(path):
    p=subprocess.run(['gh','api',PREFIX+path],cwd=ROOT,capture_output=True,timeout=60)
    need(p.returncode==0,'GitHub read failed '+clean(p.stderr.decode(errors='replace'))[-2000:])
    return loads(p.stdout)
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def same(v,expected):
    need(isinstance(v,dict),'identity object absent')
    for k,x in expected.items():need(str(v.get(k))==str(x),'identity mismatch '+k)
def canonical(name,directory=False):
    need(isinstance(name,str) and name and len(name)<1024,'invalid member name')
    need(not any(c in name for c in ['\x00','\\',':']),'unsafe member name')
    p=PurePosixPath(name)
    need(not p.is_absolute() and '..' not in p.parts and str(p)!='.','unsafe member path')
    need(name==str(p) or (directory and name==str(p)+'/'),'noncanonical member path')
    return str(p)
def download(path):
    proc=subprocess.Popen(['gh','api',PREFIX+'artifacts/'+str(ART)+'/zip'],cwd=ROOT,
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
    streams={proc.stdout:'data',proc.stderr:'error'};count=0;errors=bytearray()
    end=time.monotonic()+180
    try:
        with path.open('wb') as out:
            while streams:
                need(time.monotonic()<end,'download deadline')
                ready,_,_=select.select(list(streams),[],[],min(3,max(0,end-time.monotonic())))
                for f in ready:
                    data=os.read(f.fileno(),1024*1024)
                    if not data:del streams[f];continue
                    if streams[f]=='data':
                        count+=len(data);need(count<=64*1024*1024,'download actual limit');out.write(data)
                    else:
                        errors.extend(data);need(len(errors)<=65536,'download stderr limit')
        need(proc.wait(timeout=10)==0,'artifact download failed '+clean(errors.decode(errors='replace'))[-2000:])
    finally:
        if proc.poll() is None:
            os.killpg(proc.pid,signal.SIGKILL);proc.wait(timeout=10)
        (OUT/'download.log').write_text(clean(errors.decode(errors='replace')))
    need(count==SIZE and sha(path)==DIGEST,'original archive identity mismatch')
def inspect(result):
    need(os.environ.get('GITHUB_ACTIONS')=='true' and os.environ.get('GITHUB_EVENT_NAME')=='workflow_dispatch','Actions manual only')
    need(os.environ.get('GITHUB_REF')=='refs/heads/'+BRANCH and os.environ.get('GITHUB_RUN_ATTEMPT')=='1','one diagnostic branch attempt')
    def git(*a):return subprocess.check_output(['git',*a],cwd=ROOT,text=True).strip()
    need(git('rev-parse','HEAD')==os.environ['GITHUB_SHA'],'current source mismatch')
    driver.admit()
    run=api('runs/'+str(RUN));job=api('jobs/'+str(JOB));art=api('artifacts/'+str(ART))
    write('original-run.json',run);write('original-job.json',job);write('original-artifact.json',art)
    same(run,{'id':RUN,'head_sha':PARENT,'head_branch':PRODUCER_BRANCH,'event':'workflow_dispatch',
        'run_attempt':1,'status':'completed','conclusion':'failure','path':'.github/workflows/gtk-sdk342-package.yml'})
    need(run['repository']['full_name']=='NoGod3524/EXReader','original repository')
    same(job,{'id':JOB,'run_id':RUN,'head_sha':PARENT,'head_branch':PRODUCER_BRANCH,
        'run_attempt':1,'status':'completed','conclusion':'failure','name':'F05 GTK native producer',
        'workflow_name':run['name']})
    same(art,{'id':ART,'name':'f05-gtk-native-'+str(RUN)+'-1','size_in_bytes':SIZE,'digest':'sha256:'+DIGEST})
    need(art['expired'] is False,'artifact expired')
    same(art['workflow_run'],{'id':RUN,'head_sha':PARENT,'head_branch':PRODUCER_BRANCH,
        'repository_id':run['repository']['id'],'head_repository_id':run['head_repository']['id']})
    result['producer_authenticated']=True
    archive=WORK/'original.zip';download(archive);result['archive_digest_verified']=True
    total=0;found={}
    with zipfile.ZipFile(archive) as z:
        infos=z.infolist();need(len(infos)<=4096,'archive member count')
        need(sum(i.file_size for i in infos)<=512*1024*1024,'archive declared total')
        names=set()
        for info in infos:
            name=canonical(info.orig_filename,info.is_dir())
            need(info.orig_filename==info.filename and name not in names,'alias or duplicate archive member')
            names.add(name)
            mode=info.external_attr>>16;kind=stat.S_IFMT(mode)
            need(kind in (0,stat.S_IFREG,stat.S_IFDIR),'nonregular archive member')
            need(not(kind==stat.S_IFDIR and not info.is_dir()) and not(kind==stat.S_IFREG and info.is_dir()),'archive type conflict')
            need(not(info.flag_bits&1) and info.compress_type in (zipfile.ZIP_STORED,zipfile.ZIP_DEFLATED),'encrypted/unknown compression')
            need(info.file_size<=128*1024*1024,'archive single declared limit')
            if name in MEMBERS:
                need(not info.is_dir() and kind in (0,stat.S_IFREG),'selected member not regular')
                found[name]=info
        result['missing']=[n for n in MEMBERS if n not in found]
        for name in MEMBERS:
            if name not in found:continue
            cap=16*1024*1024 if name==NATIVE+'receive-observations.json' else (4*1024*1024 if name==NATIVE+'coverage.json' else 2*1024*1024)
            info=found[name];need(info.file_size<=cap,'selected declared limit '+name)
            dest=WORK/'selected'/name;dest.parent.mkdir(parents=True,exist_ok=True)
            length=0;h=hashlib.sha256()
            with z.open(info) as inp,dest.open('wb') as out:
                while True:
                    b=inp.read(65536)
                    if not b:break
                    length+=len(b);total+=len(b)
                    need(length<=cap and total<=28*1024*1024,'selected actual limit')
                    h.update(b);out.write(b)
            need(length==info.file_size,'selected actual size')
            result['members'][name]={'bytes':length,'sha256':h.hexdigest()}
    need(not result['missing'],'selected evidence absent')
    def read(name):return loads((WORK/'selected'/name).read_bytes())
    expected={'source_sha':PARENT,'run_id':str(RUN),'attempt':'1'}
    native_identity={'source':PARENT,'run':str(RUN),'attempt':'1'}
    inventory=read('inventory.json');same(inventory,expected)
    need(inventory['complete'] is False,'expected original incomplete collection')
    need(isinstance(inventory['missing'],list) and len(inventory['missing'])<=32
        and all(isinstance(x,str) and len(x)<=1024 for x in inventory['missing']),'missing list budget')
    need(isinstance(inventory['errors'],list) and len(inventory['errors'])<=32
        and all(isinstance(x,str) and len(x)<=2000 for x in inventory['errors']),'collection error budget')
    result['original_collection']={'complete':inventory['complete'],'missing':inventory['missing'],'errors':inventory['errors']}
    for name,entry in result['members'].items():
        if name=='inventory.json':continue
        canonical(name)
        need(inventory['files'].get(name)==entry,'original inventory fingerprint '+name)
    result['inventory_verified']=True
    coverage=read(NATIVE+'coverage.json');same(coverage['identity'],native_identity)
    receipt=read(NATIVE+'receipt.json');same(receipt['identity'],native_identity)
    trace=read(NATIVE+'receive-observations.json');same(trace['identity'],native_identity)
    runtime=read(STAGE+'native6.json');same(runtime,expected)
    need(coverage['host']=='linux' and receipt['host']=='linux' and receipt['schema']==2,'native report type')
    need(coverage['F05_accepted'] is False and receipt['F05_accepted'] is False,'full acceptance must stay false')
    need(receipt['program_sha256']==coverage['program_sha256']==trace['program_sha256'],'program report identity')
    result['program_hash_cross_checked_not_rehashed']=coverage['program_sha256']
    result['validation_findings']=[]
    result['diagnostic_findings']=[]
    def inconsistent(message):
        result['validation_findings'].append(message)
    cleanup=coverage['cleanup_errors'];need(isinstance(cleanup,list) and len(cleanup)<=32,'cleanup error shape')
    result['cleanup_errors']=[]
    for error in cleanup:
        need(isinstance(error,dict) and isinstance(error.get('action'),str) and isinstance(error.get('error'),str),'cleanup entry shape')
        result['cleanup_errors'].append({'action':clean(error['action'])[:200],'error':clean(error['error'])[:2000]})
    errors=coverage['errors'];need(isinstance(errors,list) and len(errors)<=32,'original errors shape')
    result['original_errors']=[clean(str(x))[:2000] for x in errors]
    need(isinstance(coverage['cases'],list) and isinstance(receipt['cases'],list)
        and len(coverage['cases'])<=6 and len(receipt['cases'])<=6,'case report budget')
    for items,key in [(coverage['cases'],'name'),(receipt['cases'],'id')]:
        need(all(isinstance(x,dict) and isinstance(x.get(key),str) and len(x[key])<=100
            and isinstance(x.get('outcome'),str) and len(x['outcome'])<=80 for x in items),'case fields budget')
    result['cases']=[{'name':x['name'],'outcome':x['outcome']} for x in coverage['cases']]
    result['receipt_cases']=[{'name':x['id'],'outcome':x['outcome']} for x in receipt['cases']]
    try:
        result['case_alignment']=align_cases(coverage['cases'],receipt['cases'],receipt['claims'])
    except AssertionError as error:
        inconsistent('coverage/receipt '+str(error))
    result['receipt_error_crosscheck']={}
    for field in ['errors','cleanup_errors']:
        if field in receipt:
            matches=receipt[field]==coverage[field]
            result['receipt_error_crosscheck'][field]={'field_provided':True,'matches_coverage':matches}
            if not matches:inconsistent('coverage/receipt '+field+' mismatch')
        else:
            result['receipt_error_crosscheck'][field]={'field_provided':False,'crosscheck_performed':False}
    result['runtime']={k:runtime.get(k) for k in ('name','passed','returncode','error','cleanup_error','cleanup_incomplete','process_reaped','elapsed_seconds')}
    need(runtime['name']=='native6' and runtime['passed'] is False and type(runtime['returncode']) is int and runtime['returncode']!=0,'original failure preserved')
    result['predicate_controls_reexecuted']=False
    records=trace['records'];result['traces']=[]
    need(isinstance(records,list) and len(records)==5,'exact original trace count')
    need([r.get('index') for r in records]==[1,2,3,4,5]
        and [r.get('host') for r in records]==['first','second','first','second','first']
        and [r.get('case_index') for r in records]==[0,0,1,1,2],'original trace identity/order')
    pids=[r.get('pid') for r in records]
    need(all(type(pid) is int and pid>0 for pid in pids),'original PID types')
    result['pid_sequence']={'values':pids,'first_reused_for_trace3':pids[0]==pids[2],
        'second_reused_for_trace4':pids[1]==pids[3],'trace5_is_new_first_process':pids[4]!=pids[0]}
    if not(pids[0]==pids[2] and pids[1]==pids[3] and pids[4]!=pids[0]):
        inconsistent('original PID sequence mismatch')
    for row in records[:4]:
        status={'index':row['index'],'host':row['host'],'pid':row['pid'],
                'completed':row.get('completed'),'outcome':row.get('outcome'),'predicate_revalidated':False}
        try:driver.verify_receive_trace(row);status['predicate_revalidated']=True
        except Exception as error:
            status['validation_error']=clean(repr(error))[:2000]
            inconsistent('original completed trace '+str(row['index'])+' failed predicate validation')
        result['traces'].append(status)
    row=records[4]
    need(row.get('error')=='new network session deadline' and row.get('completed') is False
        and row.get('dispatch_count')==0 and row.get('dispatch_ok') is False and row.get('samples')==[],
        'fifth original failure boundary changed')
    need(type(row.get('pid')) is int and row['pid']>0,'fifth PID absent')
    before=driver.observation_snapshot(row['before_network'])
    idle={'visible':'1','owner_busy':'0','preparing':'0','closing':'0','session_present':'0'}
    result['before_network_idle']={key:before[key]==value for key,value in idle.items()}
    if not all(result['before_network_idle'].values()):
        inconsistent('before_network does not match original idle prerequisite')
    samples=row['network_samples'];need(isinstance(samples,list) and 1<=len(samples)<=2500,'network samples absent/over budget')
    conditions={'visible':'1','owner_busy':'0','preparing':'0','phase':'0','closing':'0',
                'session_present':'1','session_state':'4','session_status':'0',
                'receive_enabled':'1','cancel_requested':'0'}
    names=['new_generation',*conditions,'exact_network_notice']
    stats={name:{'true_samples':0,'false_samples':0,'transitions':0,
                 'last_true_elapsed':None,'first_false_elapsed':None,'last_false_elapsed':None} for name in names}
    old_flags=None;previous=-1;transitions=[];old_state=None;all_ready=0;generation_values=set()
    def safe_time(value):
        return type(value) in (int,float) and math.isfinite(value) and value>=0
    for sample in samples:
        need(isinstance(sample,dict) and type(sample.get('pid')) is int and sample.get('pid')==row['pid'],'sample host PID mismatch')
        elapsed=sample.get('elapsed');need(safe_time(elapsed) and elapsed>=previous,'network sample clock')
        previous=elapsed;state=driver.observation_snapshot(sample['state'])
        flags={'new_generation':int(state['session_generation'])>int(before['session_generation']),
               **{key:state[key]==value for key,value in conditions.items()},
               'exact_network_notice':state['notice']==driver.NETWORK_FINISHED}
        for name,ok in flags.items():
            item=stats[name];item['true_samples' if ok else 'false_samples']+=1
            if ok:item['last_true_elapsed']=elapsed
            else:
                if item['first_false_elapsed'] is None:item['first_false_elapsed']=elapsed
                item['last_false_elapsed']=elapsed
            if old_flags is not None and old_flags[name]!=ok:item['transitions']+=1
        if all(flags.values()):all_ready+=1
        if old_state!=state:
            changed=list(state) if old_state is None else [key for key in state if state[key]!=old_state[key]]
            if len(transitions)<64:
                transitions.append({'elapsed':elapsed,'changed_fields':changed,
                                    'state':state,'unmet':[name for name,ok in flags.items() if not ok]})
        old_flags=flags;old_state=state;generation_values.add(state['session_generation'])
    last=samples[-1]
    late=[sample['elapsed'] for sample in samples if sample['elapsed']>240]
    if late:
        result['diagnostic_findings'].append({'kind':'samples_completed_after_declared_deadline',
            'count':len(late),'first_elapsed':late[0],'last_elapsed':late[-1],
            'explanation':'The original guard checks before sampling; sample work may finish after the deadline.'})
    result['fifth_network']={'index':5,'host':row['host'],'pid':row['pid'],'case_index':row['case_index'],
        'before_network':before,'sample_count':len(samples),'sample_limit':2500,
        'first_elapsed':samples[0]['elapsed'],'last_elapsed':last['elapsed'],
        'declared_network_deadline_seconds':240,'deadline_observed_error':row['error'],
        'sample_limit_reached':len(samples)==2500,'recorded_generation_field':row.get('generation'),
        'generation_values':sorted(generation_values,key=int),
        'receive_dispatch_count':row['dispatch_count'],'receive_sample_count':0,
        'all_ready_sample_count':all_ready,'conditions':stats,'last_state':old_state,
        'last_unmet_conditions':[name for name,ok in old_flags.items() if not ok],
        'state_transitions_first64':transitions,
        'transitions_may_be_truncated':len(transitions)==64,
        'sampling_not_continuous_between_observations':True,
        'failure_is_preserved':True,'product_root_cause_inferred':False}
    result['fifth_network']['original_precondition_on_last_sample']={'passed':False}
    try:
        driver.receive_precondition(before,old_state)
        result['fifth_network']['original_precondition_on_last_sample']['passed']=True
    except Exception as error:
        result['fifth_network']['original_precondition_on_last_sample']['error']=clean(repr(error))[:2000]
    if all_ready:
        inconsistent('saved network samples contradict original readiness failure')
    result['evidence_consistent']=not result['validation_findings']
    result['diagnostic_complete']=result['evidence_consistent']
def main():
    OUT.mkdir(parents=True,exist_ok=False);WORK.mkdir(parents=True,exist_ok=False)
    result={'diagnostic_source':os.environ.get('GITHUB_SHA'),'diagnostic_run':os.environ.get('GITHUB_RUN_ID'),
        'original_source':PARENT,'original_run':RUN,'original_job':JOB,'original_artifact':ART,
        'original_producer_conclusion':'failure','full_F05_accepted':False,'native_accepted':False,
        'diagnostic_complete':False,'members':{},'missing':[],'errors':[]}
    try:inspect(result)
    except Exception as error:result['errors'].append(clean(repr(error))[:6000])
    finally:
        # Only the bounded sanitized report is uploaded, never the full archive,
        # profiles, original binaries, or credentials.
        text=json.dumps(sanitize(result),indent=2,allow_nan=False)
        raw=text.encode()
        if len(raw)>2*1024*1024:
            result={key:result.get(key) for key in ['diagnostic_source','diagnostic_run',
                'original_source','original_run','original_job','original_artifact',
                'original_producer_conclusion','producer_authenticated','archive_digest_verified',
                'inventory_verified','members']}
            result.update(diagnostic_complete=False,evidence_consistent=False,native_accepted=False,
                full_F05_accepted=False,errors=['diagnostic report exceeded 2 MiB'],
                omitted_fields=True,original_result_bytes=len(raw),
                original_result_sha256=hashlib.sha256(raw).hexdigest())
            text=json.dumps(sanitize(result),indent=2,allow_nan=False)
        (OUT/'result.json').write_text(text+'\n')
        print(text,flush=True)
    return 0 if result['diagnostic_complete'] and not result['errors'] else 1
if __name__=='__main__':
    try:sys.exit(main())
    except Exception as error:
        print('F05 NETWORK INSPECTION FAILED '+clean(repr(error))[:6000],flush=True)
        sys.exit(1)
