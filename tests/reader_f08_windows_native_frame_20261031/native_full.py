"""Native-local entry over all original 78 product starts (66 after a documented TXT rejection).

The CUA controller handles every real picker request printed on stdout, then
atomically writes its completion JSON. This file never changes display settings,
sets Actions variables, or uses a local source checkout as the producer identity.
"""
import argparse,contextlib,ctypes as C,hashlib,json,os,runpy,shutil,subprocess,sys,threading,time,traceback,zipfile
from ctypes import wintypes as W
from pathlib import Path,PurePosixPath
from local_probe import need,sha,save,module

class DisplayMode(C.Structure):
 _fields_=[('device',W.WCHAR*32),('spec',W.WORD),('driver',W.WORD),('size',W.WORD),('extra',W.WORD),('fields',W.DWORD),
  ('x',W.LONG),('y',W.LONG),('orientation',W.DWORD),('fixed',W.DWORD),('color',W.SHORT),('duplex',W.SHORT),
  ('resolution',W.SHORT),('tt',W.SHORT),('collate',W.SHORT),('form',W.WCHAR*32),('dpi',W.WORD),('bits',W.DWORD),
  ('width',W.DWORD),('height',W.DWORD),('flags',W.DWORD),('frequency',W.DWORD),('icm',W.DWORD),('intent',W.DWORD),
  ('media',W.DWORD),('dither',W.DWORD),('reserved1',W.DWORD),('reserved2',W.DWORD),('panx',W.DWORD),('pany',W.DWORD)]

def validate_picker_marker(request,marker,pid,now):
 need(marker.get('pid')==pid and marker.get('request')==request['request'] and
  marker.get('computer_use_returned') is True and marker.get('post_action_refresh_returned') is True and
  type(marker.get('qpc')) is int and request['qpc']<=marker['qpc']<=now,'real CUA completion and post-action refresh barrier')

def unpack(a,out):
 data=Path(a.zip).read_bytes();meta=json.loads(Path(a.metadata).read_text(encoding='utf-8-sig'))
 need(len(data)==meta['size_in_bytes'] and 'sha256:'+hashlib.sha256(data).hexdigest()==meta['digest'],'build ZIP identity')
 need(meta['workflow_run']['head_sha']==a.expected_source and not meta['expired'],'producer source')
 raw=out/'product';raw.mkdir()
 with zipfile.ZipFile(a.zip) as z:
  names=[n for n in z.namelist() if not n.endswith('/')];need(len(names)==len(set(n.casefold() for n in names)),'unique ZIP inventory')
  for n in names:
   v=PurePosixPath(n);need(not v.is_absolute() and '..' not in v.parts and '\\' not in n and ':' not in n,'safe ZIP member')
   dest=raw/n;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(z.read(n))
 m=json.loads((raw/'manifest.json').read_text());ident=json.loads((raw/'build-identity.json').read_text())
 need(m['source_sha']==ident['source_sha']==a.expected_source and str(m['run_id'])==str(meta['workflow_run']['id']),'manifest origin')
 need(set(names)==set(m['files'])|{'manifest.json'},'complete build inventory')
 for n,v in m['files'].items():need(sha(raw/n)==v['sha256'] and (raw/n).stat().st_size==v['bytes'],'build payload '+n)
 need(sha(raw/'program/EXReader.exe')==ident['program_sha256'] and sha(raw/'seed.exe')==ident['seed_sha256'],'executed binaries')
 for n,v in ident['unchanged_helpers'].items():need(sha(Path(a.helper_root)/n)==v,'original helper '+n)
 need(sha(a.observer)==a.observer_sha256 and Path(a.observer).stat().st_size==a.observer_bytes,'observer identity')
 controls=subprocess.run([a.observer,'--check-limits'],capture_output=True,timeout=10)
 (out/'observer-limit-controls.log').write_bytes(controls.stdout+controls.stderr);need(controls.returncode==0 and json.loads(controls.stdout).get('passed') is True,'bounded full observer protocol')
 need((raw/'native-source/seed_shelf.c').is_file(),'authenticated producer seed source bytes')
 need(sha(__file__)==sha(raw/'native-source/native_full.py') and sha(sys.modules['local_probe'].__file__)==sha(raw/'native-source/local_probe.py'),'executed native harness source bytes')
 need(json.loads((raw/'native-frame-build.json').read_text())['instrumented'] is True,'native review producer')
 return raw,meta,ident

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--zip',required=True);ap.add_argument('--metadata',required=True);ap.add_argument('--expected-source',required=True)
 ap.add_argument('--helper-root',required=True);ap.add_argument('--output',required=True);ap.add_argument('--observer',required=True)
 ap.add_argument('--observer-source',required=True);ap.add_argument('--observer-sha256',required=True);ap.add_argument('--observer-bytes',required=True,type=int)
 a=ap.parse_args();collection_started=time.monotonic();need(os.name=='nt' and os.environ.get('COMPUTERNAME','').upper()=='LAP25002','named native Windows host')
 need(os.environ.get('GITHUB_ACTIONS')!='true','native execution must not impersonate Actions')
 out=Path(a.output).resolve();base=(Path(os.environ['USERPROFILE'])/'.codex/f08-device-runs').resolve()
 need(out.is_relative_to(base) and not out.exists(),'fresh bounded native output');out.mkdir(parents=True)
 raw,meta,ident=unpack(a,out);helper=Path(a.helper_root)
 sys.path.insert(0,str(helper/'tests/reader_perf_windows'));import perf_windows as P
 need(sha(P.__file__)==ident['unchanged_helpers']['tests/reader_perf_windows/perf_windows.py'],'loaded original sampler')
 user=P.U;kernel=P.K
 kernel.QueryPerformanceCounter.argtypes=[C.POINTER(C.c_longlong)];kernel.QueryPerformanceCounter.restype=W.BOOL
 kernel.QueryPerformanceFrequency.argtypes=[C.POINTER(C.c_longlong)];kernel.QueryPerformanceFrequency.restype=W.BOOL
 user.EnumDisplaySettingsW.argtypes=[W.LPCWSTR,W.DWORD,C.POINTER(DisplayMode)];user.EnumDisplaySettingsW.restype=W.BOOL
 user.GetPropW.argtypes=[W.HWND,W.LPCWSTR];user.GetPropW.restype=W.HANDLE
 user.GetWindowThreadProcessId.argtypes=[W.HWND,C.POINTER(W.DWORD)];user.GetWindowThreadProcessId.restype=W.DWORD
 user.GetClassNameW.argtypes=[W.HWND,W.LPWSTR,C.c_int];user.GetClassNameW.restype=C.c_int
 user.GetDlgCtrlID.argtypes=[W.HWND];user.GetDlgCtrlID.restype=C.c_int
 user.IsWindowVisible.argtypes=[W.HWND];user.IsWindowVisible.restype=W.BOOL
 user.IsWindowEnabled.argtypes=[W.HWND];user.IsWindowEnabled.restype=W.BOOL
 user.PostMessageW.argtypes=[W.HWND,W.UINT,W.WPARAM,W.LPARAM];user.PostMessageW.restype=W.BOOL
 def qpc():
  v=C.c_longlong();need(kernel.QueryPerformanceCounter(C.byref(v)),'QPC');return v.value
 freq=C.c_longlong();need(kernel.QueryPerformanceFrequency(C.byref(freq)),'QPC frequency')
 def display():
  d=DisplayMode(size=C.sizeof(DisplayMode));need(user.EnumDisplaySettingsW(None,0xffffffff,C.byref(d)),'read current display');return [d.width,d.height,d.frequency]
 before=display();deadline=collection_started+5400;stage_deadline=deadline;done=threading.Event();expired=threading.Event()
 report={'execution':'local-native','source_sha':a.expected_source,'run_id':out.name,'attempt':'local-native','producer':meta,
  'harness_sha256':sha(__file__),'actions_environment_value':os.environ.get('GITHUB_ACTIONS'),'observer_source_sha':a.observer_source,'observer_sha256':a.observer_sha256,'display_before':before,
  'planned':{'maximum_product_starts':78,'txt':3,'diagnostic_bisect_launches':1,'main_per_cohort':12,'main_cohorts':['cold_shelf','warm_shelf','reading','import','import_epub'],'interaction_per_cohort':5,'interaction_cohorts':['warm_shelf','reading'],'preparation_launches':4},
  'steps':[],'captures':[],'problems':[],'f08_accepted':False,'all_ui_frame_census_complete':False,'observer_attach_policy':'after original shelf/restore TTI; before first explicit open; all native trace rows kept from launch','picker_policy':'real dialog close releases original body; real CUA post-action refresh must return before product close/next launch'}
 save(out/'native-origin.json',report)
 active={};current_stage='initial';suppressed=0
 def check():
  if (out/'STOP').exists():raise InterruptedError('controller stopped native full collection')
  if expired.is_set() or time.monotonic()>=min(stage_deadline,deadline):raise TimeoutError('original stage / 90-minute full collection cap')
 def watchdog():
  if not done.wait(max(0,deadline-time.monotonic())):
   expired.set()
   for host in list(active.values()):
    if getattr(host,'window',None):user.PostMessageW(host.window,0x10,0,0)
 threading.Thread(target=watchdog,daemon=True).start()
 # Original cleanup paths are moved into this run instead of deleting failure evidence.
 old_rmtree=shutil.rmtree
 def retain_tree(path,*args,**kwargs):
  target=Path(path).resolve();need(target.is_relative_to(out) and target!=out,'bounded original cleanup path')
  if target.exists():
   retained=out/'retained-cleanup';retained.mkdir(exist_ok=True);dest=retained/('%05d-'%len(list(retained.iterdir()))+target.name)
   need(dest.resolve().is_relative_to(out),'bounded retained path');target.rename(dest)
 shutil.rmtree=retain_tree
 original_run=subprocess.run
 def bounded_run(args,*v,**kw):
  check();remaining=max(.01,min(stage_deadline,deadline)-time.monotonic());requested=kw.get('timeout');kw['timeout']=remaining if requested is None else min(requested,remaining)
  return original_run(args,*v,**kw)
 subprocess.run=bounded_run
 # Replace only the original source-byte request; no local git process is run.
 class ProducerProcesses:
  def __getattr__(self,name):return getattr(subprocess,name)
  def check_output(self,args,*v,**kw):
   if list(args)==['git','show','HEAD:tests/windows_host/seed_shelf.c']:return (raw/'native-source/seed_shelf.c').read_bytes()
   need(not args or str(args[0])!='git','no local source Git access');return subprocess.check_output(args,*v,**kw)
  def run(self,args,*v,**kw):
   check();need(not args or str(args[0])!='git','no local source Git access');return subprocess.run(args,*v,**kw)
 P.subprocess=ProducerProcesses()
 original_environment=P.environment
 def environment(*v,**kw):
  d=original_environment(*v,**kw);d.update(source_sha=a.expected_source,run_id=out.name,attempt='local-native',execution='local-native')
  d['producer']={k:meta[k] for k in ('id','digest','workflow_run')};d['native_display']=before
  d['source_access']='CI-manifest-authenticated seed_shelf.c bytes; no local Git or Actions impersonation';return d
 P.environment=environment
 original_init,original_find,original_send,original_close,original_poll,original_click=P.Host.__init__,P.Host.find_window,P.Host.send,P.Host.close,P.Host.poll,P.Host.click
 original_enabled,original_wait=P.Host.enabled,P.Host.wait_enabled
 original_window,original_first,original_resume=P.op_window,P.op_first_screen,P.op_resume
 replay=module('native_full_replay',raw/'native-source/replay.py')
 def emit(host,event):
  event.setdefault('qpc',qpc());event.setdefault('pid',host.process.pid)
  with (host._native_folder/'driver.jsonl').open('a',encoding='utf-8') as stream:stream.write(json.dumps(event)+'\n')
 def init(host,*v,**kw):
  check();index=len(report['captures']);folder=out/('capture-%03d'%index);folder.mkdir();entry={'index':index,'folder':folder.name,'stage':current_stage,'complete':False}
  host._native_folder=folder;host._native_entry=entry;host._native_observer=None;host._native_stream=None;host._native_bridges=[];host.window=None
  host._native_profile=Path(v[2] if len(v)>2 else kw['data'])
  report['captures'].append(entry)
  previous=os.environ.get('EXREADER_F08_TRACE');os.environ['EXREADER_F08_TRACE']=str(folder/'product-native-trace.json')
  try:original_init(host,*v,**kw)
  except BaseException as error:
   entry['constructor_error']=repr(error)
   if hasattr(host,'process'):active[host.process.pid]=host
   raise
  finally:
   if previous is None:os.environ.pop('EXREADER_F08_TRACE',None)
   else:os.environ['EXREADER_F08_TRACE']=previous
  active[host.process.pid]=host
  entry.update(pid=host.process.pid,frequency=freq.value,program_sha256=sha(host.exe),log=str(host.log_path),profile=str(host.data),expected_reader=Path(host.log_path).stem.startswith('reading-'),resume_launch=Path(host.log_path).stem.startswith('reading-') and Path(host.log_path).stem!='reading-00')
  emit(host,{'kind':'process','frequency':freq.value,'exe_sha256':entry['program_sha256'],'log':entry['log']})
 def find(host):
  found=original_find(host)
  if found:
   entry=host._native_entry;entry['hwnd']=int(found);child=user.GetDlgItem(found,123);pid=W.DWORD();user.GetWindowThreadProcessId(child,C.byref(pid));name=C.create_unicode_buffer(128);user.GetClassNameW(child,name,128)
   entry['reader_locator']={'hwnd':int(child or 0),'pid':pid.value,'class':name.value,'valid':bool(child and pid.value==host.process.pid and name.value=='EXReaderPage')}
  return found
 def observe(host):
  if host._native_observer is not None:return
  find(host)
  entry=host._native_entry;need(host.window,'owned native root window');folder=host._native_folder
  entry['observer_limit_ms']=max(1,min(5400000,int((min(stage_deadline,deadline)-time.monotonic())*1000)))
  host._native_stream=(folder/'native.jsonl').open('wb');obs=subprocess.Popen([a.observer,str(int(host.window)),str(host.process.pid),str(folder/'stop'),str(folder/'images'),str(entry['observer_limit_ms'])],stdout=host._native_stream,stderr=subprocess.STDOUT)
  host._native_observer=obs;entry['observer_pid']=obs.pid;until=time.monotonic()+10
  while '"kind":"ready"' not in (folder/'native.jsonl').read_text():
   check();need(obs.poll() is None and time.monotonic()<until,'owned-window capture readiness');time.sleep(.01)
  entry['observer_ready_qpc']=qpc()
 def poll(host,probe,timeout,interval=.004):
  def bounded():check();return probe()
  return original_poll(host,bounded,min(timeout,max(.01,min(stage_deadline,deadline)-time.monotonic())),interval)
 def enabled(host,*v,**kw):check();return original_enabled(host,*v,**kw)
 def wait_enabled(host,name,timeout=60):
  check();return original_wait(host,name,min(timeout,max(.01,min(stage_deadline,deadline)-time.monotonic())))
 def send(host,hwnd,message,wparam=0,lparam=0,timeout=2000):
  check()
  if message not in (0xF5,0x20A,0x186,0x197,0x111,0xC):return original_send(host,hwnd,message,wparam,lparam,timeout)
  event={'kind':'input','hwnd':int(hwnd),'control':user.GetDlgCtrlID(hwnd),'message':message,'wparam':int(wparam),'start_qpc':qpc()}
  event['enabled_at_attempt']=bool(user.IsWindowEnabled(hwnd))
  try:return original_send(host,hwnd,message,wparam,lparam,timeout)
  except BaseException as error:event['error']=repr(error);raise
  finally:event['end_qpc']=qpc();emit(host,event)
 def dialog(host):
  found=[]
  @P.ENUM
  def visit(window,unused):
   pid=W.DWORD();user.GetWindowThreadProcessId(window,C.byref(pid));name=C.create_unicode_buffer(80);user.GetClassNameW(window,name,80)
   if pid.value==host.process.pid and window!=host.window and user.IsWindowVisible(window) and name.value=='#32770' and user.GetDlgItem(window,1):found.append(window)
   return True
  user.EnumWindows(visit,0);return found[-1] if found else None
 def click(host,name,timeout=2000):
  if name=='open':host._native_entry['expected_reader']=True
  if name!='import':return original_click(host,name,timeout)
  path=Path(host.text(host.control('path'))).resolve();need(path.is_file(),'fixed real picker input');host.wait_enabled('import',60);need(not dialog(host),'no pre-existing picker')
  number=len(host._native_bridges);complete=host._native_folder/('picker-%02d-complete.json'%number)
  request={'kind':'picker_request','pid':host.process.pid,'request':number,'path':str(path),'sha256':sha(path),'bytes':path.stat().st_size,'complete_file':str(complete),'qpc':qpc()}
  host._native_bridges.append(request);emit(host,request);print('F08_NATIVE_FULL_PICKER '+json.dumps(request),flush=True)
  need(user.PostMessageW(host.control('import'),0xF5,0,0),'post real import button');shown=host.poll(lambda:(dialog(host),) if dialog(host) else None,30)[0]
  emit(host,{'kind':'picker_dialog','request':number,'hwnd':int(shown)})
  host.poll(lambda:(True,) if not dialog(host) else None,60)
  # Return at the real dialog-close boundary; the original body observes busy
  # work itself. A fast preparation import may already be done, never faked busy.
  emit(host,{'kind':'picker_closed','request':number,'import_enabled':host.import_enabled(),'product_job_state':int(user.GetPropW(host.window,'EXReaderF08JobState') or 0)})
 def close(host,*v,**kw):
  if getattr(host,'_native_closed',False):return host._native_close_result
  entry=host._native_entry;folder=host._native_folder;host._native_close_result=None;original_closed=False
  try:
   for req in host._native_bridges:
    file=Path(req['complete_file']);host.poll(lambda:(True,) if file.exists() else None,60)
    marker=json.loads(file.read_text(encoding='utf-8'));validate_picker_marker(req,marker,host.process.pid,qpc())
    emit(host,{'kind':'picker_cua_complete','request':req['request'],'marker':marker})
   if host._native_observer is not None:
    (folder/'stop').write_text('original case finished; stop observer before closing product\n');entry['observer_exit']=host._native_observer.wait(timeout=30)
   host._native_close_result=original_close(host,*v,**kw);original_closed=True;entry['process_exit']=host.process.poll();entry['peak']=host._native_close_result
   if host._native_profile.is_dir():
    snapshot=folder/'profile-after-close';shutil.copytree(host._native_profile,snapshot);entry['profile_snapshot']=snapshot.relative_to(out).as_posix()
   trace=folder/'product-native-trace.json'
   need(trace.is_file(),'native trace exists for every completed process')
   document=json.loads(trace.read_text());need(document['pid']==host.process.pid and document['frequency']==freq.value,'native trace process clock')
   value=replay.replay(document);save(folder/'native-analysis.json',value);entry['native_analysis']=value
   entry['complete']=entry['process_exit']==0 and entry.get('observer_exit')==0
   return host._native_close_result
  except BaseException as error:entry['error']=repr(error);raise
  finally:
   obs=host._native_observer
   if obs is not None:
    if obs.poll() is None:
     (folder/'stop').write_text('failure cleanup\n')
     try:obs.wait(timeout=30)
     except subprocess.TimeoutExpired:obs.kill();obs.wait(timeout=10);entry['observer_killed']=True
    entry['observer_exit']=obs.poll()
   if host._native_stream is not None:host._native_stream.close()
   if hasattr(host,'process'):
    if not original_closed and hasattr(host,'sampler'):
     host._native_close_result=original_close(host,*v,**kw);entry['peak']=host._native_close_result
    elif host.process.poll() is None:
     if host.window:user.PostMessageW(host.window,0x10,0,0)
     try:host.process.wait(timeout=20)
     except subprocess.TimeoutExpired:host.process.kill();host.process.wait(timeout=10);entry['product_killed']=True
    entry['process_exit']=host.process.poll();emit(host,{'kind':'close','exit':entry['process_exit']});active.pop(host.process.pid,None)
   if hasattr(host,'log') and not host.log.closed:host.log.close()
   host._native_closed=True
 def window(host,*v,**kw):
  result=original_window(host,*v,**kw)
  if not suppressed and not host._native_entry['resume_launch']:observe(host)
  return result
 def first(host,*v,**kw):
  nonlocal suppressed
  suppressed+=1
  try:result=original_first(host,*v,**kw)
  finally:suppressed-=1
  observe(host);return result
 def resume(host,*v,**kw):
  host._native_entry['expected_reader']=True;result=original_resume(host,*v,**kw);observe(host);return result
 P.Host.__init__,P.Host.find_window,P.Host.send,P.Host.close,P.Host.poll,P.Host.click=init,find,send,close,poll,click
 P.Host.enabled,P.Host.wait_enabled=enabled,wait_enabled
 P.op_window,P.op_first_screen,P.op_resume=window,first,resume
 base_page=P.op_shelf_next_page
 def scroll_origin(host,*v,**kw):
  result=base_page(host,*v,**kw);lines=W.UINT();user.SystemParametersInfoW.argtypes=[W.UINT,W.UINT,W.LPVOID,W.UINT];user.SystemParametersInfoW.restype=W.BOOL
  need(user.SystemParametersInfoW(0x68,0,C.byref(lines),0) and 0<lines.value<100,'read native wheel profile');required=12*lines.value;until=time.monotonic()+15
  while host.lb_top()<required:check();need(time.monotonic()<until,'original scroll preparation bound');host.wheel(4);time.sleep(.02)
  emit(host,{'kind':'scroll_origin_preparation','required_top':required,'observed_top':host.lb_top(),'preparation_only':True});return result
 common=['--package',str(raw/'program'),'--seed',str(raw/'seed.exe')]
 scripts=helper/'tests';argv_before=list(sys.argv)
 def stage(name,cap,script,args,call=None):
  nonlocal current_stage,stage_deadline
  current_stage=name;stage_deadline=min(deadline,time.monotonic()+cap);entry={'name':name,'started_qpc':qpc(),'script':str(script),'script_sha256':sha(script)};report['steps'].append(entry)
  sys.argv=[str(script),*args]
  class Tee:
   def __init__(self,log,parent):self.log,self.parent=log,parent
   def write(self,value):self.log.write(value);self.log.flush();return self.parent.write(value)
   def flush(self):self.log.flush();self.parent.flush()
  try:
   check()
   with (out/(name+'.log')).open('w',encoding='utf-8') as log,contextlib.redirect_stdout(Tee(log,sys.stdout)),contextlib.redirect_stderr(Tee(log,sys.stderr)):
    if call is not None:code=call()
    else:
     try:runpy.run_path(str(script),run_name='__main__');code=0
     except SystemExit as error:code=error.code or 0
   entry['exit']=code
   if code:report['problems'].append(name+': original exit '+str(code))
  except BaseException as error:entry.update(exit=1,error=repr(error),traceback=traceback.format_exc());report['problems'].append(name+': '+repr(error))
  finally:entry['ended_qpc']=qpc();save(out/'native-progress.json',report);sys.argv=argv_before
 try:
  stage('txt-diagnosis',1800,scripts/'reader_perf_windows/diagnose_txt_import.py',[*common,'--output',str(out/'txt'),'--runs','3'])
  stage('original-main',3600,scripts/'reader_perf_windows/perf_windows.py',[*common,'--output',str(out/'observations'),'--work',str(out/'main-work'),'--cohorts','cold_shelf,warm_shelf,reading,import,import_epub','--launches-per-cohort','12','--txt-diagnostic',str(out/'txt/diagnosis.json')],P.main)
  P.op_shelf_next_page=scroll_origin
  stage('original-interactions',1800,scripts/'reader_product_performance_handoff/sample_windows_interactions.py',[*common,'--output',str(out/'interactions'),'--work',str(out/'interaction-work'),'--cohorts','warm_shelf,reading','--launches-per-cohort','5'])
 finally:
  for host in list(active.values()):
   try:close(host)
   except BaseException as error:report['problems'].append('final cleanup: '+repr(error))
  done.set();shutil.rmtree=old_rmtree;subprocess.run=original_run
  try:after=display()
  except BaseException as error:after=None;report['problems'].append('display observation: '+repr(error))
  report.update(observed_product_starts=len(report['captures']),display_after=after,collection_cap_expired=expired.is_set(),controller_stop_requested=(out/'STOP').exists(),collection_complete=all(s.get('exit')==0 for s in report['steps']) and len(report['steps'])==3 and all(e['complete'] for e in report['captures']))
  report['display_unchanged']=report['display_after']==before;save(out/'result.json',report)
  # Nested original manifests are retained, too; exclude only this root manifest.
  files={p.relative_to(out).as_posix():{'sha256':sha(p),'bytes':p.stat().st_size} for p in out.rglob('*') if p.is_file() and p!=out/'manifest.json'}
  save(out/'manifest.json',{'execution':'local-native','source_sha':a.expected_source,'files':files,'f08_accepted':False})
 print('F08_NATIVE_FULL_OUTPUT',str(out),flush=True);return 0 if report['collection_complete'] and report['display_unchanged'] else 1
if __name__=='__main__':raise SystemExit(main())
