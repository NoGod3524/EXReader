"""Read seven authenticated members from one failed GTK producer. No host execution."""
import hashlib,json,math,os,re,select,signal,stat,subprocess,sys,time,zipfile
from pathlib import Path,PurePosixPath
import driver
ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'build/f05-gtk-cleanup-inspect'
WORK=ROOT/'build/f05-gtk-cleanup-work'
PARENT='834aac8adea2f19b3ccda832608ffacc4049449f'
BRANCH='dot/f05-gtk-cleanup-inspect-20261103'
PRODUCER_BRANCH='dot/f05-gtk-native-recovery-20261103'
RUN=41629004820
JOB=125893568906
ART=13228252454
SIZE=35461520
DIGEST='64c29c211097d0e50f2fd7a73c44d4c9e7ee81f647d5eb766229c7da1f95fbd4'
PREFIX='repos/NoGod3524/EXReader/actions/'
NATIVE='build/f05-gtk-native/'
STAGE='build/f05-gtk/'
MEMBERS=['inventory.json',NATIVE+'coverage.json',NATIVE+'receipt.json',
         NATIVE+'receive-observations.json',STAGE+'native6.json',
         STAGE+'native6.stdout.log',STAGE+'observation-controls.json']
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
    need(git('show','-s','--format=%P','HEAD')==PARENT,'diagnostic parent')
    need(sorted(git('diff','--name-status',PARENT,'HEAD').splitlines())==sorted([
        'A\ttests/product/f05_gtk_native_recovery_20261103/inspect_cleanup.py',
        'M\t.github/workflows/gtk-sdk342-package.yml']),'diagnostic scope')
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
            cap=16*1024*1024 if name==NATIVE+'receive-observations.json' else 2*1024*1024
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
    need(inventory['complete'] is True and not inventory['missing'] and not inventory['errors'],'original collection incomplete')
    for name,entry in result['members'].items():
        if name=='inventory.json':continue
        canonical(name)
        need(inventory['files'].get(name)==entry,'original inventory fingerprint '+name)
    result['inventory_verified']=True
    coverage=read(NATIVE+'coverage.json');same(coverage['identity'],native_identity)
    receipt=read(NATIVE+'receipt.json');same(receipt['identity'],native_identity)
    trace=read(NATIVE+'receive-observations.json');same(trace['identity'],native_identity)
    runtime=read(STAGE+'native6.json');same(runtime,expected)
    controls=read(STAGE+'observation-controls.json');same(controls,expected)
    need(coverage['host']=='linux' and receipt['host']=='linux' and receipt['schema']==2,'native report type')
    need(coverage['F05_accepted'] is False and receipt['F05_accepted'] is False,'full acceptance must stay false')
    need(receipt['program_sha256']==coverage['program_sha256']==trace['program_sha256'],'program report identity')
    result['program_hash_cross_checked_not_rehashed']=coverage['program_sha256']
    result['cleanup_errors']=coverage['cleanup_errors'];need(isinstance(result['cleanup_errors'],list),'cleanup errors shape')
    for error in result['cleanup_errors']:
        need(isinstance(error,dict) and isinstance(error.get('action'),str) and isinstance(error.get('error'),str),'cleanup entry shape')
    result['original_errors']=coverage['errors']
    result['cases']=[{'name':x['name'],'outcome':x['outcome']} for x in coverage['cases']]
    result['receipt_cases']=[{'name':x['id'],'outcome':x['outcome']} for x in receipt['cases']]
    result['runtime']={k:runtime.get(k) for k in ('name','passed','returncode','error','cleanup_error','cleanup_incomplete','process_reaped','elapsed_seconds')}
    need(runtime['name']=='native6' and runtime['passed'] is False and runtime['returncode']!=0,'original failure preserved')
    need(result['members'][STAGE+'native6.stdout.log']['sha256']==runtime['stdout_sha256'],'original stdout binding')
    need(controls['count']==8 and controls['accepted'] is True
        and controls['synthetic_predicate_controls_only'] is True,'original control report flags')
    need([x['name'] for x in controls['checks']]==driver.OBS_CONTROLS
        and all(x['passed'] is True for x in controls['checks']),'original eight reported controls')
    result['predicate_controls']=controls['checks']
    result['predicate_controls_reexecuted']=False
    records=trace['records'];result['traces']=[]
    need(isinstance(records,list) and len(records)<=15,'original trace count')
    for row in records:
        status={'index':row.get('index'),'host':row.get('host'),'pid':row.get('pid'),
            'case_index':row.get('case_index'),'generation':row.get('generation'),
            'completed':row.get('completed'),'outcome':row.get('outcome'),
            'error':row.get('error'),'predicate_revalidated':False}
        try:driver.verify_receive_trace(row);status['predicate_revalidated']=True
        except Exception as error:status['validation_error']=clean(repr(error))[:2000]
        result['traces'].append(status)
    result['trace_shape_matches_original15']=(len(records)==15 and
        [r.get('host') for r in records]==driver.SYNC_HOSTS and
        [r.get('index') for r in records]==list(range(1,16)) and
        [r.get('case_index') for r in records]==[0,0,1,1,2,2,3,3,3,3,3,3,4,4,4])
    log=(WORK/'selected'/STAGE/'native6.stdout.log').read_text(errors='replace')
    (OUT/'original-native-stdout-tail.log').write_text(clean(log[-24000:]))
    result['diagnostic_complete']=True
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
        (OUT/'result.json').write_text(text+'\n')
        print(text,flush=True)
    return 0 if result['diagnostic_complete'] and not result['errors'] else 1
if __name__=='__main__':
    try:sys.exit(main())
    except Exception as error:
        print('F05 CLEANUP INSPECTION FAILED '+clean(repr(error))[:6000],flush=True)
        sys.exit(1)
