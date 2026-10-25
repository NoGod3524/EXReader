"""Two real process stages; successful complete cycles alone increment counts."""
import argparse,importlib,json,os,platform as platform_module,subprocess,sys,threading,time,traceback
from pathlib import Path
import psutil
from contract import ACTIONS,FORMATS,ROUNDS,SDK,digest,write,validate
assert os.environ.get('GITHUB_ACTIONS')=='true'
p=argparse.ArgumentParser();p.add_argument('platform',choices=('windows','gtk'));args=p.parse_args()
out=Path('evidence').resolve();identity=json.loads((out/'build-identity.json').read_text())
paths=dict(txt=out/'fixtures/Reading.txt',epub=out/'fixtures/D14 EPUB.epub',pdf=out/'fixtures/Fixed.pdf',cbz=out/'fixtures/Comic.cbz')
originals={p.relative_to(out).as_posix():digest(p) for p in (out/'fixtures').rglob('*') if p.is_file()}
report=dict(identity,accepted=False,plan=dict(stages=2,rounds=ROUNDS,formats=list(FORMATS),actions=list(ACTIONS),ceiling_seconds=2700),actions=[],stages=[],resources=[],failures=[],sampler_errors=[],completed_cycles=0,duration_seconds=0,performance_accepted=False,physical_device_accepted=False,screenreader_accepted=False,leak_free_claim=False,originals=originals,environment=dict(os=platform_module.platform(),cpu=platform_module.processor(),logical_cpus=os.cpu_count()),allowed_writes='native imported originals and implicit progress saves only; no annotations or setting commits')
started=time.monotonic();stop=threading.Event();driver=None;process=None;current_stage=None

def save():
    report['duration_seconds']=time.monotonic()-started;write(out/'report.json',report)
def sample(stage,pid):
    proc=psutil.Process(pid)
    while not stop.is_set():
        try:
            with proc.oneshot():
                cpu=proc.cpu_times();row=dict(stage=stage,pid=pid,create_time=proc.create_time(),monotonic_seconds=time.monotonic()-started,unix_seconds=time.time(),rss_bytes=proc.memory_info().rss,cpu_user_seconds=cpu.user,cpu_system_seconds=cpu.system,threads=proc.num_threads(),children=[dict(pid=c.pid,create_time=c.create_time(),name=c.name()) for c in proc.children(recursive=True)])
                if args.platform=='windows':
                    import ctypes as C
                    from ctypes import wintypes as W
                    k=C.WinDLL('kernel32',use_last_error=True);u=C.WinDLL('user32',use_last_error=True)
                    k.OpenProcess.argtypes=[W.DWORD,W.BOOL,W.DWORD];k.OpenProcess.restype=W.HANDLE;k.CloseHandle.argtypes=[W.HANDLE]
                    u.GetGuiResources.argtypes=[W.HANDLE,W.DWORD];u.GetGuiResources.restype=W.DWORD
                    h=k.OpenProcess(0x1000,False,pid);assert h
                    try:row.update(handles=proc.num_handles(),gdi=u.GetGuiResources(h,0))
                    finally:k.CloseHandle(h)
                else:row['fds']=proc.num_fds()
            report['resources'].append(row)
        except psutil.NoSuchProcess:return
        except Exception:report['sampler_errors'].append(traceback.format_exc());return
        stop.wait(.5)

def action(identifier,fn,after_state=True):
    assert time.monotonic()-started<2640,'bounded lifecycle deadline'
    row=dict(id=identifier,stage=current_stage['stage'] if current_stage else None,pid=process.pid if process else None,status='attempted',started_seconds=time.monotonic()-started,after=None)
    report['actions'].append(row);save()
    try:
        value=fn();row.update(status='completed',finished_seconds=time.monotonic()-started,after=driver.state() if after_state else value)
        print(json.dumps(row),flush=True);save()
    except BaseException:
        row.update(status='failed',error=traceback.format_exc(),finished_seconds=time.monotonic()-started);save();raise

try:
    module=importlib.import_module(args.platform);driver=module.Driver(out,out/identity['program'],out/'Reader.otf')
    for stage in (1,2):
        process=driver.launch(stage);proc=psutil.Process(process.pid)
        current_stage=dict(stage=stage,pid=process.pid,create_time=proc.create_time(),exe=proc.exe(),program_sha256=digest(proc.exe()),exit_code=None,completed_cycles=0)
        assert current_stage['program_sha256']==identity['program_sha256']
        report['stages'].append(current_stage);stop.clear();sampler=threading.Thread(target=sample,args=(stage,process.pid),daemon=True);sampler.start()
        if stage==2:action('2/no_replay',driver.no_replay,False)
        for round_ in range(ROUNDS):
            for kind in FORMATS:
                base=f'{stage}/{round_}/{kind}'
                for name in ACTIONS:
                    if name=='open':fn=lambda path=paths[kind],initial=stage==1 and round_==0:driver.open(path,initial)
                    elif name in ('search','directory','records','settings'):fn=lambda name=name:driver.modal(name)
                    else:fn=getattr(driver,name)
                    action(base+'/'+name,fn)
                current_stage['completed_cycles']+=1;report['completed_cycles']+=1
                write(out/f'stage-{stage}-round-{round_}-{kind}.json',driver.snapshot(f'stage-{stage}-round-{round_}-{kind}'));save()
        if stage==1:action('1/close_processing',lambda:driver.close_processing(out/'fixtures/Processing.txt'),False)
        else:action('2/final_close',driver.close,False)
        stop.set();sampler.join(timeout=5);current_stage['exit_code']=process.poll();save()
    def unchanged():
        actual={p.relative_to(out).as_posix():digest(p) for p in (out/'fixtures').rglob('*') if p.is_file()};assert actual==originals;return actual
    action('originals_unchanged',unchanged,False)
    validate(report,identity);report['accepted']=True
except BaseException:
    report['failures'].append(traceback.format_exc());print(report['failures'][-1],flush=True)
    if driver:
        try:write(out/'failure-snapshot.json',driver.snapshot('failure'))
        except BaseException:report['snapshot_error']=traceback.format_exc()
finally:
    stop.set()
    if process and process.poll() is None:
        try:driver.close()
        except BaseException:
            report['cleanup_error']=traceback.format_exc();process.kill();process.wait(timeout=10)
    if current_stage and process:current_stage['exit_code']=process.poll()
    save()
    # All product/log writers are stopped before sealing exact raw file inventory.
    write(out/'bundle.json',{p.relative_to(out).as_posix():dict(bytes=p.stat().st_size,sha256=digest(p)) for p in out.rglob('*') if p.is_file() and p.name!='bundle.json'})
    print('D14_RESULT '+json.dumps(report),flush=True)
assert report['accepted'],'D14 lifecycle incomplete; retained every failure and uncompleted scope'
