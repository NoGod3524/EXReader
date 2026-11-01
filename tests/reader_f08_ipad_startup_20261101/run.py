"""Fixed iPad13 startup phase diagnostic. No product/test-body changes or F08 acceptance."""
import argparse,ctypes,errno,gzip,hashlib,importlib.util,json,math,os,pathlib,plistlib,re,shutil,signal,subprocess,sys,threading,time,traceback
ROOT=pathlib.Path(__file__).resolve().parents[2];HERE=pathlib.Path(__file__).resolve().parent
BASE="68702016fe7a877dfc6ee1f0006644b5efc1cab6";PRODUCER="943938213560d329177b9afbdb2fc0953fbfc4ac";PRODUCER_RUN=41273725066
ALLOWED={"tests/reader_f08_ipad_startup_20261101/run.py",".github/workflows/dot-f08-ipad-startup-20261101.yml"}
spec=importlib.util.spec_from_file_location("ipad13_verified_io",ROOT/"tests/reader_f08_mac_reader_animation_20261101/run.py");IO=importlib.util.module_from_spec(spec);spec.loader.exec_module(IO)
need,save,sha,identity,command=IO.need,IO.save,IO.sha,IO.identity,IO.command
OUT=ROOT/"build/f08-ipad13-startup";CASE="F08LaunchUITests/test13NativeResponsiveLaunchWithoutExtendedTaskControl"
RUNTIME="com.apple.CoreSimulator.SimRuntime.iOS-26-2";DEVICE="iPad mini (A17 Pro)"
INPUTS={"iphonesimulator-sdk":(13070610751,22510401,"95adaf903a76cfdd815a10db7ba4e29a08fee25972fb6227e60c4330cf10851c"),"ipad":(13072685569,90484947,"a09a3ecad9ea7641e71d73183ebfe8f1a487555cca85488859ee5aeabdb33112")}
RESOURCES={"Bounded.epub","BoundedLong.epub","Broken.epub","Large.epub","OFL.txt","Reader.otf","Repeated.epub","Sample.epub","Sample.pdf","ShelfSeed-library.sqlite","ShelfSeed-reader-catalog.db","Unicode.epub","manifest.json","reader-catalog-v1.sql","shelf-seed.json"}
PHASES=("accounts-init-begin","accounts-directory-resolved","accounts-metadata-begin","accounts-init-end","app-scene-body-enter","account-root-body-enter","startup-main-enqueue")

def guard():
 need(os.environ.get("GITHUB_ACTIONS")=="true" and os.environ.get("GITHUB_REPOSITORY")=="NoGod3524/EXReader","real Actions repository")
 need(sys.version_info[:2]==(3,13),"CPython3.13")
 need(os.environ.get("F08_APPLE_DIAGNOSTIC")=="false" and os.environ.get("EXR_APPLE_RAW3")=="OFF","normal lane environment")
 need(command(["git","rev-parse","HEAD"],text=True).strip()==identity()["source_sha"] and not command(["git","status","--porcelain","--untracked-files=no"],text=True).strip(),"real clean source")
 command(["git","merge-base","--is-ancestor",BASE,"HEAD"])
 need(set(command(["git","diff","--no-renames","--name-only",BASE,"HEAD"],text=True).splitlines())==ALLOWED,"two fixed diagnostic additions only")
 return {**identity(),"base":BASE,"files":{p:sha(ROOT/p) for p in sorted(ALLOWED)}}

def generated_sources():
 result={};blocks=[]
 def mark(name,indent=8,builder=False,count=False):
  line=" "*indent+("let _ = " if builder else "")+'HostF08Review.phase("'+name+'"'+(", count: profiles.count" if count else "")+")\n"
  block="#if EXR_APPLE_F08_REVIEW\n"+line+"#endif\n";blocks.append(block);return block
 def replace(text,old,new):need(text.count(old)==1,"exact phase insertion boundary");return text.replace(old,new,1)
 path=ROOT/"examples/apple/HostAccount.swift";old=path.read_text();text=replace(old,'    init(folder: URL? = nil) {\n','    init(folder: URL? = nil) {\n'+mark(PHASES[0]))
 needle='            .appendingPathComponent("EXReader", isDirectory: true)\n';text=replace(text,needle,needle+mark(PHASES[1]))
 needle='        if exr_credentials_open("org.exreader.host.webdav", &credentials) != EXR_CRED_OK { credentials = nil }\n';text=replace(text,needle,needle+mark(PHASES[2]))
 needle='            message = "账号记录无法读取；原文件已保留，请先恢复该文件"\n        }\n';text=replace(text,needle,needle+mark(PHASES[3],count=True));result[path.name]=text
 path=ROOT/"examples/apple/ReaderApp.swift";old=path.read_text();needle='    var body: some Scene {\n';result[path.name]=replace(old,needle,needle+mark(PHASES[4],builder=True))
 path=ROOT/"examples/apple/HostAccountViews.swift";old=path.read_text();needle='    var body: some View {\n        VStack(spacing: 0) {\n';result[path.name]=replace(old,needle,'    var body: some View {\n'+mark(PHASES[5],builder=True)+'        VStack(spacing: 0) {\n')
 path=ROOT/"examples/apple/HostModel.swift";old=path.read_text();needle='                DispatchQueue.main.async {\n#if EXR_APPLE_F08_REVIEW\n                    HostF08Review.phase("startup-main-publish", count: rows.count)';result[path.name]=replace(old,needle,mark(PHASES[6],indent=16)+needle)
 clock='            "mach_uptime_ns": DispatchTime.now().uptimeNanoseconds,\n';needle='        var value: [String: Any] = ["phase": name, "uptime_s": ProcessInfo.processInfo.systemUptime,\n';result["HostModel.swift"]=replace(result["HostModel.swift"],needle,needle+clock);blocks.append(clock)
 for name,text in result.items():
  stripped=text
  for block in blocks:stripped=stripped.replace(block,"")
  need(stripped==(ROOT/"examples/apple"/name).read_text(),"only seven phase calls and one Mach-clock field")
 need(sum(text.count('HostF08Review.phase("'+name+'"') for text in result.values() for name in PHASES)==7,"exact seven phase points")
 return result

def driver_text():
 original=(ROOT/"tests/apple_host/shelf/ui/ShelfUITests.swift").read_text();metrics=(ROOT/"tests/reader_f08_apple_20261031/Metrics.swift").read_text();inside,marker,standalone=metrics.partition("// F08_STANDALONE_CLASSES");need(marker,"original metrics boundary");at=original.rfind("}")
 text=original[:at]+inside+original[at:]+standalone
 for name in ("func test13NativeResponsiveLaunchWithoutExtendedTaskControl()","private func launchMetric("):
  need(IO.protocol.swift_function(text,name)==IO.protocol.swift_function(metrics,name),"original13/launchMetric byte-exact")
 return text

def inputs(folder,receipts):
 run=IO.api("actions/runs/"+str(PRODUCER_RUN));need(run['head_sha']==PRODUCER and run['run_attempt']==1 and run['repository']['full_name']=='NoGod3524/EXReader',"original943 input run")
 result={}
 for kind,(aid,size,digest) in INPUTS.items():
  meta=IO.api("actions/artifacts/"+str(aid));w=meta['workflow_run'];need(not meta['expired'] and w['id']==PRODUCER_RUN and w['head_sha']==PRODUCER and w['repository_id']==run['repository']['id'] and w['head_repository_id']==run['head_repository']['id'],"external original artifact identity")
  data=IO.archive_bytes(meta);need(len(data)==size==meta['size_in_bytes'] and hashlib.sha256(data).hexdigest()==digest and meta['digest']=='sha256:'+digest,"pinned original ZIP bytes")
  z,m=IO.validate_zip(data);need(m['source_sha']==PRODUCER and m['run_id']==str(PRODUCER_RUN) and m['attempt']=='1' and m['kind']==kind,"original input manifest")
  dest=folder/("resources" if kind=='ipad' else "sdk");dest.mkdir(parents=True);expected={};prefix='program/EXReaderHost.app/'
  for name,item in m['files'].items():
   if kind=='ipad':
    if not name.startswith(prefix) or name.removeprefix(prefix) not in RESOURCES:continue
    relative=name.removeprefix(prefix)
   else:
    if not(name.startswith(('sdk/','raw-products/')) or name.endswith('.json')):continue
    relative=name
   IO.remaining();path=dest/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(z.read(name));expected[relative]=item
  need(IO.files_under(dest)==expected and not list(dest.rglob('*.app')),"exact inputs without old App")
  if kind=='ipad':
   need(set(expected)==RESOURCES,"original15 resource whitelist");seed=json.loads((dest/'shelf-seed.json').read_text());need(seed['source_sha']==PRODUCER and str(seed['run_id'])==str(PRODUCER_RUN) and str(seed['attempt'])=='1' and seed['books']==len(set(seed['source_keys']))==2202,"unmodified943 real2202 seed")
  else:IO.verify_sdk_records(dest,kind)
  save(receipts/(kind+'.json'),{'repository_full_name':'NoGod3524/EXReader','artifact':meta,'run':run,'manifest':m,'extracted_files':expected,'zip_bytes':size,'zip_sha256':digest});result[kind]=dest
 return result

def program(app):
 info=plistlib.loads((app/'Info.plist').read_bytes());need(info.get('EXRSourceSHA')==identity()['source_sha'] and info.get('EXRSDKVersion')=='3.42.0' and info.get('EXRPageThemeEnabled') is True and info.get('CFBundleIdentifier')=='org.exreader.host' and info.get('DTSDKName')=='iphonesimulator18.5',"actual new diagnostic App/source/SDK")
 return {'program_source_sha':identity()['source_sha'],'sdk_source_sha':PRODUCER,'resource_source_sha':PRODUCER,'program_sha256':sha(app/'EXReaderHost'),'program_files':IO.files_under(app),'info':info}

def device_state(device):
 data=json.loads(command(['xcrun','simctl','list','devices','--json']));matches=[v for rows in data['devices'].values() for v in rows if v['udid']==device];need(len(matches)==1,"owned Simulator UUID");return matches[0]

def observed_process_group(group,deadline):
 attempts=[]
 for limit in (5,10):
  current=IO.process_group_snapshot(group,timeout=min(limit,IO.remaining(deadline)));attempts.append(current)
  if current.get('probe_returncode')==0 or not current.get('probe_error','').startswith('TimeoutExpired('):break
 return {**current,'probe_attempts':attempts}

def sample_completion(path,target,post_identity=None):
 text=path.read_text();process=re.findall(r'^Process:[ \t]*(.+)$',text,re.M);paths=re.findall(r'^Path:[ \t]*(.+)$',text,re.M);need(text.strip() and len(process)==len(paths)==1,'unique sample Process/Path header')
 match=re.fullmatch(r'EXReaderHost[ \t]+\[([0-9]+)\]',process[0].strip());need(match is not None and int(match.group(1))==target['pid'] and paths[0].strip()==target['executable_path'],'sample header PID/path differs from verified target')
 value={'process':process[0].strip(),'pid':int(match.group(1)),'executable_path':paths[0].strip(),'report_sha256':sha(path)}
 if post_identity is not None:
  try:
   actual=post_identity();need(actual=={k:target[k] for k in ('pid','uid','ruid','start_s','start_us','name','executable_path')},'warmup PID birth/UID/path changed after sample');value.update(post_target_state='live-verified',post_identity=actual)
  except OSError as error:
   if error.errno!=errno.ESRCH:raise
   value.update(post_target_state='exited-esrch',post_errno=errno.ESRCH)
 return value

def warmup_sample(folder,device,expected,run,stop,ready,state,deadline):
 # Metadata only: no name-based sample -wait and no all-process tracing.
 class ProcBSDInfo(ctypes.Structure):
  _fields_=[(n,ctypes.c_uint32) for n in ('flags','status','xstatus','pid','ppid','uid','gid','ruid','rgid','svuid','svgid','reserved')]+[('comm',ctypes.c_char*16),('name',ctypes.c_char*32)]+[(n,ctypes.c_uint32) for n in ('nfiles','pgid','jobc','tdev','tpgid')]+[('nice',ctypes.c_int32),('start_s',ctypes.c_uint64),('start_us',ctypes.c_uint64)]
 try:
  need(ctypes.sizeof(ProcBSDInfo)==136 and os.getuid()==os.geteuid(),'libproc ABI and same UID');lib=ctypes.CDLL('/usr/lib/libproc.dylib',use_errno=True)
  lib.proc_listpids.argtypes=[ctypes.c_uint32,ctypes.c_uint32,ctypes.c_void_p,ctypes.c_int];lib.proc_listpids.restype=ctypes.c_int
  lib.proc_pidinfo.argtypes=[ctypes.c_int,ctypes.c_int,ctypes.c_uint64,ctypes.c_void_p,ctypes.c_int];lib.proc_pidinfo.restype=ctypes.c_int
  lib.proc_pidpath.argtypes=[ctypes.c_int,ctypes.c_void_p,ctypes.c_uint32];lib.proc_pidpath.restype=ctypes.c_int
  owned=(pathlib.Path.home()/'Library/Developer/CoreSimulator/Devices'/device/'data/Containers/Bundle/Application').resolve();uid=os.getuid()
  def bsd(pid):
   value=ProcBSDInfo();ctypes.set_errno(0);n=lib.proc_pidinfo(pid,3,0,ctypes.byref(value),ctypes.sizeof(value))
   if n!=ctypes.sizeof(value):raise OSError(ctypes.get_errno() or errno.EIO,'PROC_PIDTBSDINFO unavailable',pid)
   return {'pid':value.pid,'uid':value.uid,'ruid':value.ruid,'start_s':value.start_s,'start_us':value.start_us,'name':bytes(value.name or value.comm).decode(errors='replace')}
  def path_for(pid):
   buf=ctypes.create_string_buffer(4096);ctypes.set_errno(0);n=lib.proc_pidpath(pid,buf,len(buf))
   if n<=0:raise OSError(ctypes.get_errno() or errno.EIO,'proc_pidpath unavailable',pid)
   need(n<len(buf),'proc_pidpath truncated');return pathlib.Path(buf.value.decode()).resolve(strict=True)
  def candidates():
   size=lib.proc_listpids(4,uid,None,0);need(size>0,'same-UID PID inventory');buf=(ctypes.c_int*(size//4+64))();n=lib.proc_listpids(4,uid,buf,ctypes.sizeof(buf));need(0<n<ctypes.sizeof(buf) and n%4==0,'bounded same-UID PID inventory');found=[]
   for pid in sorted(set(buf[:n//4])-{0}):
    try:record=bsd(pid)
    except OSError as error:
     if error.errno!=errno.ESRCH:raise
     continue
    if record['name']!='EXReaderHost':continue
    actual=path_for(pid)
    if actual.is_relative_to(owned):found.append((record,actual))
   return found
  need(not candidates(),'owned App already exists before original case13');ready.set()
  while not stop.is_set() and time.monotonic()<deadline:
   found=candidates()
   if not found:stop.wait(0.02);continue
   need(len(found)==1,'ambiguous first owned App PID');record,exe=found[0];state['candidate']={**record,'executable_path':str(exe),'observed_uptime_ns':time.monotonic_ns()}
   need(record['uid']==record['ruid']==uid and record['start_s']>0 and exe.name=='EXReaderHost' and exe.parent.name=='EXReaderHost.app','owned warmup identity')
   info=plistlib.loads((exe.parent/'Info.plist').read_bytes());digest=sha(exe);need(info.get('CFBundleIdentifier')=='org.exreader.host' and info.get('EXRSourceSHA')==expected['program_source_sha'] and digest==expected['program_sha256'],'actual warmup source/executable')
   need(bsd(record['pid'])==record and path_for(record['pid'])==exe,'warmup PID changed before sample');state['target']={**state['candidate'],'source_sha':info['EXRSourceSHA'],'executable_sha256':digest,'info_plist_sha256':sha(exe.parent/'Info.plist'),'verified_uptime_ns':time.monotonic_ns()};state['attempted']=True
   ok=run(['/usr/bin/sample',record['pid'],1,10,'-mayDie','-file',folder/'warmup.sample.txt'],'warmup-sample',120,required=False)
   need(ok,'sample rejected or failed; no retry')
   def post_identity():
    after=bsd(record['pid']);need(after==record,'warmup PID birth/UID changed after sample');return {**after,'executable_path':str(path_for(record['pid']))}
   state['sample_completion']=sample_completion(folder/'warmup.sample.txt',state['target'],post_identity);state['status']='captured';state.pop('reason',None);return
  state['reason']='no owned warmup PID before monitor stopped or deadline'
 except BaseException as error:state.update(status='missing',reason=repr(error))
 finally:
  state['finished_uptime_ns']=time.monotonic_ns();ready.set();save(folder/'warmup-sample.json',state)

def sample_binding(folder,samples,commands):
 value={'status':'missing','scope':'missing','whole_window_within_preAccounts':False,'counts_are_cpu_ms':False}
 try:
  state=json.loads((folder/'warmup-sample.json').read_text());value['observation']=state;clock=state['clock_info'];need(type(clock['implementation']) is str and 'mach_absolute_time' in clock['implementation'] and clock['monotonic'] is True and clock['adjustable'] is False,'controller Mach-clock domain')
  need(state['status']=='captured' and state['attempted'] is True,state.get('reason','sample missing'));target=state['target'];expected=json.loads((folder/'program.json').read_text());need(target['source_sha']==expected['program_source_sha'] and target['executable_sha256']==expected['program_sha256'],'sample actual source/executable binding');phases=samples[0]['shelf']['f08_launch_phases'];need({p['pid'] for p in phases}=={target['pid']},'sample PID is not original warmup PID')
  first=[p for p in phases if p['phase']=='app-init'];last=[p for p in phases if p['phase']=='accounts-init-begin'];need(len(first)==len(last)==1,'unique warmup gap boundaries');a=first[0]['mach_uptime_ns'];b=last[0]['mach_uptime_ns'];need(type(a) is int and type(b) is int and 0<a<b,'warmup Mach-clock fields')
  matched=[c for c in commands if c['role']=='warmup-sample'];need(len(matched)==1,'exactly one PID sample attempt');c=matched[0];need(c['argv'][:6]==['/usr/bin/sample',str(target['pid']),'1','10','-mayDie','-file'] and len(c['argv'])==7 and pathlib.PurePosixPath(c['argv'][-1]).name=='warmup.sample.txt','single fixed PID sample command')
  lo=c['popen_before_uptime_ns'];reaped=c['reaped_after_uptime_ns'];hi=c['owned_outputs_closed_after_uptime_ns'];need(all(type(v) is int for v in [lo,reaped,hi,target['verified_uptime_ns']]) and 0<target['verified_uptime_ns']<=lo<=reaped<=hi and c['returncode']==0 and c['owned_group_terminal_verified'] is True,'sample controller bounds and terminal state')
  completed=state['sample_completion'];header=sample_completion(folder/'warmup.sample.txt',target);need(all(completed.get(k)==v for k,v in header.items()),'independent sample header/report binding')
  if completed.get('post_target_state')=='live-verified':need(completed.get('post_identity')=={k:target[k] for k in ('pid','uid','ruid','start_s','start_us','name','executable_path')},'sample post-live identity')
  else:need(completed.get('post_target_state')=='exited-esrch' and type(completed.get('post_errno')) is int and completed['post_errno']==errno.ESRCH,'sample post-target exit must be ESRCH')
  inside=a<=lo<=hi<=b;value.update(status='captured',scope='preAccounts callgraph' if inside else 'warmup startup callgraph',whole_window_within_preAccounts=inside,controller_popen_before_uptime_ns=lo,controller_reaped_after_uptime_ns=reaped,controller_owned_outputs_closed_after_uptime_ns=hi,warmup_app_init_mach_uptime_ns=a,warmup_accounts_init_mach_uptime_ns=b,original_report_sha256=sha(folder/'warmup.sample.txt'))
 except (KeyError,ValueError,OSError) as error:value['reason']=str(error)
 return value

def replay(folder,commands):
 extract,statuses=IO.load_native_tools();objects,metrics=extract(folder/'launch.xcresult',with_cases=True);cases=statuses(folder/'launch.xcresult');need(len(cases)==1 and cases[0]['name']==CASE.rsplit('/',1)[-1]+'()' and cases[0]['result']=='Passed',"only original13 Passed")
 need(len(metrics)==1 and metrics[0]['identifier']==CASE+'()' and metrics[0]['status']=='Success',"one original13 metric case")
 native=[m for m in metrics[0]['performance_metrics'] if m.get('identifier',{}).get('_value')=='com.apple.dt.XCTMetric_ApplicationLaunch-ApplicationFirstFramePresentationResponsive.duration'];need(len(native)==1 and native[0]['unitOfMeasurement']['_value']=='s',"native responsive metric/units")
 values=[float(v['_value']) for v in native[0]['measurements']['_values']];need(len(values)==5 and all(math.isfinite(v) and v>0 for v in values),"all five native measurements")
 base=folder/'attachments';manifest=json.loads((base/'manifest.json').read_text());need(len(manifest)==1 and manifest[0]['testIdentifier']==CASE+'()',"single-case attachments")
 found=[a for a in manifest[0]['attachments'] if a.get('suggestedHumanReadableName','').startswith('f08-launch-observations_')];need(len(found)==1,"one raw original phase attachment");raw=json.loads(IO.attachment_path(folder,found[0]['exportedFileName']).read_text());samples=raw['samples'];need(len(samples)==6,"warmup plus five raw samples")
 for s in samples:
  phases=s['shelf']['f08_launch_phases'];need(phases and len({p['pid'] for p in phases})==1 and all(any(p['phase']==name for p in phases) for name in PHASES),'complete raw7 phase points');need(s['native_extended_task_requested'] is False and s['native_extended_task_enabled'] is False,"unchanged no-extended control")
 return {'cases':cases,'performance':metrics,'raw_observation':raw,'native_seconds':values,'tti_budget_ms':2000,'native_tti_budget_passed':all(v*1000<=2000 for v in values),'diagnostic_only':True,'f08_accepted':False,'warmup_sample':sample_binding(folder,samples,commands)}

def native():
 start=time.monotonic();soft=start+900;hard=start+1050;IO.DEADLINE=soft;control=OUT/'control';folder=OUT/'evidence';folder.mkdir(parents=True);budget={**identity(),'started_uptime_s':start,'soft_deadline_uptime_s':soft,'hard_deadline_uptime_s':hard};need(not (control/'budget.json').exists(),"do not restart native");save(control/'budget.json',budget)
 report={**identity(),'commands':[],'problems':[],'unsafe_writers':[],'diagnostic_only':True,'f08_accepted':False,'collection_complete':False};device=None;app=None;monitor=None;monitor_joined=False;stop=threading.Event();ready=threading.Event();sample_state={'status':'missing','attempted':False,'reason':'monitor not started','duration_s':1,'interval_ms':10,'counts_are_cpu_ms':False}
 def run(args,role,limit=120,cleanup=False,required=True):
  timeout=min(limit,IO.remaining(hard if cleanup else soft));args=list(map(str,args));record={'role':role,'argv':args,'started_uptime_s':time.monotonic(),'signals_sent':[],'owned_group_terminal_verified':False};report['commands'].append(record);env={k:v for k,v in os.environ.items() if k not in IO.CREDENTIAL_NAMES};proc=None;error=None
  print('IPAD13_PHASE',role,flush=True)
  record.update(stdout_file=role+'.log',stderr_file=role+'.stderr.log')
  with (folder/(role+'.log')).open('wb') as log,(folder/(role+'.stderr.log')).open('wb') as errors:
   try:
    record['popen_before_uptime_ns']=time.monotonic_ns();proc=subprocess.Popen(args,cwd=ROOT,stdout=log,stderr=errors,env=env,start_new_session=True);record.update(pid=proc.pid,owned_process_group=proc.pid);proc.wait(timeout=timeout);record['reaped_after_uptime_ns']=time.monotonic_ns()
   except BaseException as e:error=repr(e)
   if proc is not None:
    def snap():return observed_process_group(proc.pid,hard)
    before=snap();record['owned_group_before_cleanup']=before
    for sig,grace in ((signal.SIGINT,20),(signal.SIGTERM,10),(signal.SIGKILL,5)):
     if proc.poll() is not None and before.get('probe_returncode')==0 and not IO.group_has_live_members(before):break
     try:os.killpg(proc.pid,sig);record['signals_sent'].append({'signal':int(sig),'uptime_s':time.monotonic()})
     except ProcessLookupError:pass
     try:proc.wait(timeout=min(grace,IO.remaining(hard)))
     except subprocess.TimeoutExpired:pass
     before=snap()
    if proc.poll() is not None and 'reaped_after_uptime_ns' not in record:record['reaped_after_uptime_ns']=time.monotonic_ns()
    known_terminal=proc.poll() is not None and before.get('probe_returncode')==0 and not IO.group_has_live_members(before);after=before if known_terminal else snap();record.update(returncode=proc.poll(),owned_group_after_cleanup=after,terminal_observation_reused=known_terminal,owned_group_terminal_verified=after.get('probe_returncode')==0 and not IO.group_has_live_members(after) and proc.poll() is not None)
    if not record['owned_group_terminal_verified']:report['unsafe_writers'].append(role)
  record.update(error=error,finished_uptime_s=time.monotonic(),owned_outputs_closed_after_uptime_ns=time.monotonic_ns())
  if error or proc is None or proc.returncode or record.get('owned_group_terminal_verified') is not True:
   report['problems'].append(role+': '+(error or str(record.get('returncode'))))
   if required or report['unsafe_writers']:raise RuntimeError(role+' failed; original log retained')
   return False
  return True
 def join_monitor():
  nonlocal monitor_joined
  if monitor is None or monitor_joined:return
  monitor_joined=True;stop.set();monitor.join(timeout=max(0,min(240,hard-time.monotonic())));report['sample_monitor_terminal_verified']=not monitor.is_alive()
  if monitor.is_alive():report['unsafe_writers'].append('warmup-monitor');raise RuntimeError('warmup monitor terminal state unknown')
 try:
  save(folder/'source.json',guard());save(folder/'budget.json',budget);run(['xcodebuild','-version'],'xcode')
  need((folder/'xcode.log').read_text().splitlines()[0]=='Xcode 16.4' and os.environ.get('DEVELOPER_DIR')=='/Applications/Xcode_16.4.app/Contents/Developer' and command(['sw_vers','-productVersion'],text=True).startswith('15.'),"fixed Mac15/Xcode16.4")
  prepared=inputs(OUT/'input',folder/'inputs');resources=prepared['ipad'];sdk=prepared['iphonesimulator-sdk'];generated=OUT/'generated';generated.mkdir();sources=generated_sources()
  for name,text in sources.items():(generated/name).write_text(text)
  tests=OUT/'driver/shelf/ui';tests.mkdir(parents=True);(tests/'ShelfUITests.swift').write_text(driver_text())
  shutil.copytree(generated,folder/'generated');shutil.copyfile(tests/'ShelfUITests.swift',folder/'ShelfUITests.swift')
  for p in sorted(ALLOWED):target=folder/'source'/p;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/p,target)
  try:command(['ruby','-rxcodeproj','-e','puts Xcodeproj::VERSION'],timeout=30)
  except subprocess.CalledProcessError:run(['gem','install','xcodeproj','--no-document'],'xcodeproj-dependency',120)
  run(['ruby','-rxcodeproj','-e','puts Xcodeproj::VERSION'],'xcodeproj-check',30)
  project=OUT/'project';run(['ruby','tests/reader_team24_apple/make_project.rb',project,resources,tests,'wave3'],'project',45)
  patch='p=Xcodeproj::Project.open(ARGV[0]);p.targets.each{|t|next unless t.product_type=="com.apple.product-type.application";t.build_configurations.each{|c|c.build_settings["SWIFT_ACTIVE_COMPILATION_CONDITIONS"]+=" EXR_APPLE_F08_REVIEW"}};t=p.targets.find{|x|x.name=="EXReaderHost-iOS"};ARGV.drop(2).each{|name|old=File.expand_path(File.join(ARGV[1],"examples/apple",name));files=t.source_build_phase.files.select{|f|f.file_ref && File.expand_path(f.file_ref.path.to_s,File.dirname(ARGV[0]))==old};raise "one original source" unless files.length==1;files.first.remove_from_project;ref=p.new_file(Pathname.new(File.expand_path(File.join(ARGV[1],"build/f08-ipad13-startup/generated",name))).relative_path_from(Pathname.new(File.dirname(File.expand_path(ARGV[0])))).to_s);t.add_file_references([ref])};p.save'
  run(['ruby','-rxcodeproj','-rpathname','-e',patch,project/'EXReaderHost.xcodeproj',ROOT,*sources],'phase-source-references',30)
  config=json.loads(command(['ruby','-rxcodeproj','-rjson','-e','p=Xcodeproj::Project.open(ARGV[0]);v={};p.targets.each{|t|next unless t.product_type=="com.apple.product-type.application";t.build_configurations.each{|c|v[t.name+"/"+c.name]=c.build_settings["SWIFT_ACTIVE_COMPILATION_CONDITIONS"]}};puts JSON.generate(v)',project/'EXReaderHost.xcodeproj'],text=True));save(folder/'project-configuration.json',config)
  required={'EXR_APPLE_PAGE_THEME','EXR_APPLE_HOST_REVIEW','EXR_APPLE_SHELF_REVIEW','EXR_APPLE_RAW3','EXR_APPLE_WAVE3','EXR_APPLE_F08_REVIEW'};need(len(config)==4 and all(required<=set(v.split()) for v in config.values()),"all six normal flags")
  for p in (project/'EXReaderHost.xcodeproj/xcshareddata/xcschemes').glob('*.xcscheme'):
   tree=IO.ET.parse(p)
   for tag in ['TestAction','LaunchAction']:tree.getroot().find(tag).attrib.update(buildConfiguration='Release',selectedDebuggerIdentifier='',selectedLauncherIdentifier='Xcode.IDEFoundation.Launcher.PosixSpawn',codeCoverageEnabled='NO',disableMainThreadChecker='YES',enableAddressSanitizer='NO',enableThreadSanitizer='NO',enableUBSanitizer='NO')
   tree.write(p,encoding='utf-8',xml_declaration=True);target=folder/'schemes'/p.name;target.parent.mkdir(exist_ok=True);shutil.copyfile(p,target)
  devices=json.loads(command(['xcrun','simctl','list','devices','available','--json']));matches=[v for v in devices['devices'].get(RUNTIME,[]) if v.get('isAvailable') and v['name']==DEVICE];need(len(matches)==1,"exact original iPad/runtime available");device=matches[0]['udid'];save(folder/'destination.json',{'runtime':RUNTIME,'device':matches[0]})
  if matches[0]['state']!='Shutdown':run(['xcrun','simctl','shutdown',device],'initial-shutdown',30)
  run(['xcrun','simctl','erase',device],'erase',60);run(['xcrun','simctl','boot',device],'boot',30);run(['xcrun','simctl','bootstatus',device,'-b'],'boot-ready',180)
  derived=OUT/'derived';common=['-project',project/'EXReaderHost.xcodeproj','-scheme','EXReaderHost-iOS','-destination','platform=iOS Simulator,id='+device,'-derivedDataPath',derived,'-configuration','Release','EXR_SDK_DIR='+str(sdk/'sdk'),'EXR_PRODUCTS_DIR='+str(sdk/'raw-products'),'CODE_SIGNING_ALLOWED=NO','SWIFT_OPTIMIZATION_LEVEL=-O','GCC_OPTIMIZATION_LEVEL=s','ONLY_ACTIVE_ARCH=YES','-enableCodeCoverage','NO','-enableAddressSanitizer','NO','-enableThreadSanitizer','NO','-enableUndefinedBehaviorSanitizer','NO','-parallel-testing-enabled','NO','-test-timeouts-enabled','YES','-default-test-execution-time-allowance','240','-maximum-test-execution-time-allowance','240']
  run(['xcodebuild','-showBuildSettings','-json',*common[:common.index('-enableCodeCoverage')]],'show-build-settings',120);settings=json.loads((folder/'show-build-settings.log').read_text());save(folder/'build-settings.json',settings);run(['xcodebuild','build-for-testing',*common],'build',300)
  app=derived/'Build/Products/Release-iphonesimulator/EXReaderHost.app';before=program(app);expected_resources=IO.files_under(resources);need(all(before['program_files'].get(n)==expected_resources[n] for n in RESOURCES),'built App has original15 resource bytes');save(folder/'program.json',before)
  for man in [pathlib.Path('/usr/share/man/man1/sample.1'),pathlib.Path('/usr/share/man/man1/sample.1.gz')]:
   if man.is_file():
    try:(folder/('sample-man'+man.suffix)).write_bytes(man.read_bytes());(folder/'sample-man.txt').write_bytes(gzip.decompress(man.read_bytes()) if man.suffix=='.gz' else man.read_bytes())
    except OSError as error:sample_state['man_read_error']=repr(error)
    break
  sample_state.update(started_uptime_ns=time.monotonic_ns(),clock_info=vars(time.get_clock_info('monotonic')));monitor=threading.Thread(target=warmup_sample,args=(folder,device,before,run,stop,ready,sample_state,min(soft,time.monotonic()+360)),name='owned-warmup-sample',daemon=True);monitor.start()
  if not ready.wait(timeout=min(5,IO.remaining())):stop.set();sample_state['reason']='monitor initialization timeout'
  try:run(['xcodebuild','test-without-building',*common,'-resultBundlePath',folder/'launch.xcresult','-only-testing:EXReaderHostUITests-iOS/'+CASE],'case13',360,required=False)
  finally:join_monitor()
  run(['xcrun','xcresulttool','export','attachments','--path',folder/'launch.xcresult','--output-path',folder/'attachments'],'attachments',60,required=False)
  if run(['xcrun','simctl','get_app_container',device,'org.exreader.host','app'],'installed-app',30,required=False):
   paths=[line for line in (folder/'installed-app.log').read_text().splitlines() if line.startswith('/') and line.endswith('.app')];need(len(paths)==1,'one installed App path');installed=pathlib.Path(paths[0]);need(installed.resolve().is_relative_to((pathlib.Path.home()/'Library/Developer/CoreSimulator/Devices'/device).resolve()),'owned installed App path');bound=program(installed);need(bound['program_sha256']==before['program_sha256'] and all(bound['program_files'].get(n)==expected_resources[n] for n in RESOURCES),"actual installed executable and original15 resource bytes");save(folder/'installed-program.json',bound)
  value=replay(folder,report['commands']);save(folder/'replay.json',value)
  if value['warmup_sample']['status']!='captured':report['problems'].append('warmup sample missing: '+value['warmup_sample'].get('reason','unknown'))
 except BaseException as e:report['problems'].append(repr(e));report['traceback']=traceback.format_exc()
 finally:
  IO.DEADLINE=hard
  try:join_monitor()
  except BaseException as error:report['problems'].append(repr(error))
  if device and report.get('sample_monitor_terminal_verified') is not False:
   try:
    if device_state(device)['state']!='Shutdown':run(['xcrun','simctl','shutdown',device],'final-shutdown',60,cleanup=True)
    state=device_state(device);need(state['state']=='Shutdown',"owned Simulator stopped");report['simulator_cleanup']={'verified':True,'device':state}
   except BaseException as e:report['simulator_cleanup']={'verified':False,'error':repr(e)};report['problems'].append('Simulator cleanup '+repr(e))
  if app and app.exists() and report.get('sample_monitor_terminal_verified') is not False:
   try:
    after=program(app);need(after==json.loads((folder/'program.json').read_text()),"program unchanged");shutil.copytree(app,folder/'program/EXReaderHost.app')
   except BaseException as e:report['problems'].append('program final archive '+repr(e))
  report.update(collection_complete=not report['problems'],native_elapsed_s=time.monotonic()-start);save(folder/'result.json',report)
 need(report['collection_complete'],"single-case diagnostic incomplete; raw retained")

def seal():
 folder=OUT/'evidence';control=OUT/'control';result=None
 try:
  b=IO.validated_budget(json.loads((control/'budget.json').read_text()),identity(),time.monotonic());IO.DEADLINE=b['hard_deadline_uptime_s'];guard();result=json.loads((folder/'result.json').read_text());need(not result['unsafe_writers'] and all(c.get('owned_group_terminal_verified') is True for c in result['commands']),"all owned writers terminal")
  if (folder/'destination.json').exists():need(result.get('simulator_cleanup',{}).get('verified') is True,"owned Simulator terminal")
  files=IO.files_under(folder);files.pop('f08-manifest.json',None)
  save(folder/'f08-manifest.json',{**identity(),'kind':'ipad13-startup','diagnostic_only':True,'f08_accepted':False,'files':files,'sealing_elapsed_s':time.monotonic()-b['started_uptime_s'],'hard_budget_s':1050});IO.remaining()
 except BaseException as e:
  (folder/'f08-manifest.json').unlink(missing_ok=True);save(control/'UNSEALED.json',{**identity(),'native_archive_sealed':False,'diagnostic_only':True,'f08_accepted':False,'error':repr(e),'result':result});raise

def audit():
 started=time.monotonic();hard=started+1050;IO.DEADLINE=started+900;out=ROOT/'build/f08-ipad13-startup-audit';out.mkdir(parents=True);report={**identity(),'archive_authenticated':False,'diagnostic_only':True,'f08_accepted':False,'errors':[]}
 try:
  admitted=guard();run=IO.api('actions/runs/'+identity()['run_id']);need(run['head_sha']==identity()['source_sha'] and run['run_attempt']==int(identity()['attempt']),"actual diagnostic source/attempt")
  metas=IO.api('actions/runs/'+identity()['run_id']+'/artifacts?per_page=100')['artifacts'];name='f08-ipad13-startup-'+identity()['run_id']+'-'+identity()['attempt'];found=[m for m in metas if m['name']==name and not m['expired']];need(len(found)==1,"one sealed diagnostic archive");meta=found[0];w=meta['workflow_run'];need(w['head_sha']==identity()['source_sha'] and w['id']==int(identity()['run_id']) and w['repository_id']==run['repository']['id'] and w['head_repository_id']==run['head_repository']['id'],'diagnostic artifact source/run/repository');raw=IO.archive_bytes(meta);need(len(raw)==meta['size_in_bytes'] and hashlib.sha256(raw).hexdigest()==meta['digest'].removeprefix('sha256:'),'diagnostic ZIP bytes');save(out/'receipt.json',{'repository_full_name':'NoGod3524/EXReader','artifact':meta,'run':run})
  z,m=IO.validate_zip(raw);need(all(m.get(k)==v for k,v in identity().items()) and m['kind']=='ipad13-startup' and 0<=m['sealing_elapsed_s']<=1050 and m['hard_budget_s']==1050,'sealed identity/deadline');folder=out/'raw';folder.mkdir()
  for name in m['files']:
   IO.remaining();path=folder/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(z.read(name))
  need(json.loads((folder/'source.json').read_text())==admitted,'exact diagnostic source');report['archive_authenticated']=True
  for path in ALLOWED:need((folder/'source'/path).read_bytes()==(ROOT/path).read_bytes(),'exact diagnostic source snapshot')
  fresh=inputs(out/'original-inputs',out/'original-receipts')
  for kind in INPUTS:
   old=json.loads((folder/'inputs'/(kind+'.json')).read_text());new=json.loads((out/'original-receipts'/(kind+'.json')).read_text());need(all(old[k]==new[k] for k in ['manifest','extracted_files','zip_bytes','zip_sha256']),'independent original input bytes')
  for name,text in generated_sources().items():need((folder/'generated'/name).read_text()==text,'exact seven-point generated copy')
  need((folder/'ShelfUITests.swift').read_text()==driver_text(),'unchanged original13/launchMetric');IO.verify_configuration(folder,'ipad');info=program(folder/'program/EXReaderHost.app');need(info==json.loads((folder/'program.json').read_text()),'exact program bytes/new source');resource_files=IO.files_under(fresh['ipad']);need(all(info['program_files'].get(n)==resource_files[n] for n in RESOURCES),'independent original15 program resources');need(json.loads((folder/'installed-program.json').read_text())['program_sha256']==info['program_sha256'],'installed source binding')
  result=json.loads((folder/'result.json').read_text());value=replay(folder,result['commands']);report['replay']=value;need(result['collection_complete'] and not result['problems'] and not result['unsafe_writers'] and result['simulator_cleanup']['verified'] and all(c['owned_group_terminal_verified'] for c in result['commands']),'all collection and owned cleanup states')
  need(value==json.loads((folder/'replay.json').read_text()),'independent actual native/phase replay');report.update(replay=value,diagnostic_complete=True)
 except BaseException as e:report['errors'].append(repr(e));report['traceback']=traceback.format_exc();raise
 finally:
  IO.DEADLINE=hard;report['audit_elapsed_s']=time.monotonic()-started;report['audit_soft_s']=900;report['audit_hard_s']=1050;save(out/'report.json',report);IO.remaining()

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['native','seal','audit']);mode=parser.parse_args().mode
 {'native':native,'seal':seal,'audit':audit}[mode]()
