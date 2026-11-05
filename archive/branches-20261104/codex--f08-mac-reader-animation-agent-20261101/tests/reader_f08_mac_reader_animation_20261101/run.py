"""Bounded Mac15 reader animation diagnostic; original bodies and inputs remain separate."""
import argparse,hashlib,importlib.util,io,json,math,os,pathlib,plistlib,shutil,signal,stat,subprocess,sys,time,traceback,urllib.request,zipfile
import xml.etree.ElementTree as ET
ROOT=pathlib.Path(__file__).resolve().parents[2]
HERE=pathlib.Path(__file__).resolve().parent
PROFILE=json.loads((HERE/"profile.json").read_text())
BASE=PROFILE["source_base"]
PRODUCER=PROFILE["producer_source_sha"]
ALLOWED={".github/workflows/dot-f08-mac-reader-animation-20261101.yml",*["tests/reader_f08_mac_reader_animation_20261101/"+n for n in ("run.py","helpers.py","profile.json","Bridge.swift","ReaderAnimationTests.swift","test_protocol.py")]}
spec=importlib.util.spec_from_file_location("f08_reader_animation_helpers",HERE/"helpers.py")
protocol=importlib.util.module_from_spec(spec);spec.loader.exec_module(protocol)
OUT=ROOT/"build/f08-mac-reader-animation"
DEADLINE=None
CREDENTIAL_NAMES=("GH_TOKEN","GITHUB_TOKEN","ACTIONS_RUNTIME_TOKEN","ACTIONS_ID_TOKEN_REQUEST_TOKEN")
ORIGINAL_CASES=("F08ReaderUITests/test11FrozenOriginalFontAndLocateMetrics","F08ReaderUITests/test12LongReaderPageFontAndLocateDiagnostic")
def need(value,message):
 if not value:raise ValueError(message)
def remaining(deadline=None,clock=None):
 end=DEADLINE if deadline is None else deadline
 if end is None:return 120
 value=end-(time.monotonic() if clock is None else clock())
 if not math.isfinite(value) or value<=0:raise TimeoutError("reader diagnostic total deadline exhausted")
 return value
def command(args,**kw):
 kw["timeout"]=min(kw.get("timeout",120),remaining())
 return subprocess.check_output(list(map(str,args)),cwd=ROOT,**kw)
def sha(path):
 with pathlib.Path(path).open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def save(path,value):
 path=pathlib.Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 path.write_text(json.dumps(value,indent=2,allow_nan=False)+"\n")
def identity():return {"source_sha":os.environ["GITHUB_SHA"],"run_id":os.environ["GITHUB_RUN_ID"],"attempt":os.environ["GITHUB_RUN_ATTEMPT"]}
def api(path):return json.loads(command(["gh","api","repos/NoGod3524/EXReader/"+path]))
def archive_bytes(meta):return command(["gh","api","repos/NoGod3524/EXReader/actions/artifacts/"+str(meta["id"])+"/zip"])
def guard():
 need(os.environ.get("GITHUB_ACTIONS")=="true" and os.environ.get("GITHUB_REPOSITORY")=="NoGod3524/EXReader","real repository Actions only")
 need(command(["git","rev-parse","HEAD"],text=True).strip()==identity()["source_sha"],"real diagnostic HEAD")
 need(not command(["git","status","--porcelain","--untracked-files=no"],text=True).strip(),"tracked diagnostic source changed")
 command(["git","merge-base","--is-ancestor",BASE,"HEAD"])
 need(set(command(["git","diff","--no-renames","--name-only",BASE,"HEAD"],text=True).splitlines())==ALLOWED,"exact isolated diagnostic additions")
 need(os.environ.get("F08_APPLE_DIAGNOSTIC")=="false","normal full-feature configuration")
 need(sys.version_info[:2]==(3,13),"declared CPython3.13")
 return {**identity(),"base":BASE,"changed":sorted(ALLOWED),"source_files":{p:sha(ROOT/p) for p in sorted(ALLOWED)}}
def files_under(root):
 result={}
 for path in sorted(pathlib.Path(root).rglob("*")):
  if path.is_file():remaining();result[path.relative_to(root).as_posix()]={"sha256":sha(path),"bytes":path.stat().st_size}
 return result
def validate_zip(data):
 z=zipfile.ZipFile(io.BytesIO(data));infos=z.infolist()
 need(0<len(infos)<100000 and sum(i.file_size for i in infos)<4*1024**3,"archive bounds")
 seen=set()
 for i in infos:
  remaining();p=pathlib.PurePosixPath(i.filename);key=str(p).casefold()
  need(str(p)!="." and not p.is_absolute() and ".." not in p.parts and "\\" not in i.filename and ":" not in i.filename and key not in seen,"archive path")
  seen.add(key);need(not i.flag_bits&1 and stat.S_IFMT(i.external_attr>>16) in (0,stat.S_IFDIR,stat.S_IFREG),"archive entry kind")
 manifest=json.loads(z.read("f08-manifest.json"));need({i.filename for i in infos if not i.is_dir()}==set(manifest["files"])|{"f08-manifest.json"},"archive complete inventory")
 for name,item in manifest["files"].items():
  remaining();content=z.read(name);need(len(content)==item["bytes"] and hashlib.sha256(content).hexdigest()==item["sha256"],"archive file bytes "+name)
 return z,manifest
def verify_sdk_records(folder,kind):
 installed=json.loads((folder/"sdk342-installed-identity.json").read_text());record=json.loads((folder/"sdk-identity.json").read_text());target=kind.removesuffix("-sdk")
 expected={"source_sha":PRODUCER,"run_id":str(PROFILE["producer_run"]),"attempt":str(PROFILE["producer_attempt"])}
 need(all(str(installed.get(k))==v and str(record.get(k))==v for k,v in expected.items()),"actual SDK source/run/attempt")
 need(installed.get("sdk_content_candidate")==PRODUCER and installed.get("target")==target and installed.get("sdk_version")=="3.42.0","actual SDK content/target/version")
 need(record.get("platform")==target and record.get("sdk_version")=="3.42.0" and record.get("abi")==1 and record.get("job")==PROFILE["producer_sdk_job"],"actual SDK platform/version/ABI/job")
 for key,sub in (("sdk_files","sdk"),("raw_files","raw-products")):need(files_under(folder/sub)==installed[key],"SDK installed inventory "+sub)
def prepare_inputs(folder,metadata_folder):
 producer=api("actions/runs/"+str(PROFILE["producer_run"]))
 need(producer["head_sha"]==PRODUCER and producer["run_attempt"]==PROFILE["producer_attempt"] and producer["path"]==PROFILE["producer_workflow"] and producer["repository"]["full_name"]=="NoGod3524/EXReader","actual943 input producer")
 save(metadata_folder/"producer-run.json",producer);result={}
 for row in PROFILE["inputs"]:
  remaining();meta=api("actions/artifacts/"+str(row["id"]));w=meta["workflow_run"]
  need(not meta["expired"] and w["head_sha"]==PRODUCER and w["id"]==PROFILE["producer_run"] and w["repository_id"]==producer["repository"]["id"] and w["head_repository_id"]==producer["head_repository"]["id"],"external input artifact producer")
  data=archive_bytes(meta);digest=hashlib.sha256(data).hexdigest();need(len(data)==meta["size_in_bytes"]==row["bytes"] and digest==row["sha256"] and meta["digest"]=="sha256:"+digest,"input ZIP identity")
  z,manifest=validate_zip(data);need(manifest["source_sha"]==PRODUCER and manifest["run_id"]==str(PROFILE["producer_run"]) and manifest["attempt"]==str(PROFILE["producer_attempt"]) and manifest["kind"]==row["kind"],"input manifest identity")
  resources=row["kind"]=="macos";dest=folder/("resources" if resources else row["kind"]);dest.mkdir(parents=True);expected={};prefix="program/EXReaderHost.app/Contents/Resources/"
  for name,item in manifest["files"].items():
   if resources:
    if not name.startswith(prefix):continue
    relative=name.removeprefix(prefix)
   else:
    if not(name.startswith(("sdk/","raw-products/")) or name.endswith(".json")):continue
    relative=name
   need(not any(part.endswith(".app") for part in pathlib.PurePosixPath(relative).parts),"input must not materialize another same-ID app")
   remaining();path=dest/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(z.read(name));expected[relative]=item
  need(files_under(dest)==expected,"extracted original input bytes")
  if resources:need(len(expected)==15,"only original15 Resources")
  else:verify_sdk_records(dest,row["kind"])
  result["resources" if resources else row["kind"]]=dest
  save(metadata_folder/(row["kind"]+".json"),{"repository_full_name":"NoGod3524/EXReader","artifact":meta,"run":producer,"zip_sha256":digest,"zip_bytes":len(data),"original_manifest":manifest,"extracted_files":expected})
 need(set(result)=={"resources","macos-sdk","iphonesimulator-sdk"} and not list(folder.rglob("*.app")),"exact resource/twoSDK input roots; no extra apps")
 return result
def binary(app):return app/"Contents/MacOS/EXReaderHost"
def verify_program(app,expected=None):
 files=files_under(app)
 if expected is not None:need(files==expected,"executed program changed")
 info=plistlib.loads((app/"Contents/Info.plist").read_bytes())
 need(info.get("EXRSourceSHA")==identity()["source_sha"] and info.get("EXRSDKVersion")=="3.42.0" and info.get("EXRPageThemeEnabled") is True and info.get("CFBundleIdentifier")=="org.exreader.host","new full-feature program source and SDK")
 return files


def process_group_snapshot(group,timeout=5):
 result={'group':group,'members':[]}
 try:
  p=subprocess.run(['/bin/ps','-axo','pid=,ppid=,pgid=,stat=,comm='],capture_output=True,text=True,timeout=timeout)
  result['probe_returncode']=p.returncode;result['probe_stderr']=p.stderr[:1000]
  for line in p.stdout.splitlines():
   parts=line.strip().split(None,4)
   if len(parts)==5 and parts[2].isdigit() and int(parts[2])==group:
    result['members'].append({'pid':int(parts[0]),'ppid':int(parts[1]),'pgid':int(parts[2]),'state':parts[3],'executable_name':parts[4]})
 except BaseException as e:result['probe_error']=repr(e)
 return result

def group_has_live_members(snapshot):
 return any(not m['state'].startswith('Z') for m in snapshot['members'])

def verify_configuration(folder,platform):
 config=json.loads((folder/'project-configuration.json').read_text())
 required={'EXR_APPLE_F08_REVIEW','EXR_APPLE_SHELF_REVIEW','EXR_APPLE_HOST_REVIEW','EXR_APPLE_RAW3','EXR_APPLE_WAVE3','EXR_APPLE_PAGE_THEME'}
 need(len(config)==4 and all(required<=set(v.split()) for v in config.values()),'independent full feature flags')
 scheme='EXReaderHost-macOS' if platform=='macos' else 'EXReaderHost-iOS'
 settings=json.loads((folder/'build-settings.json').read_text());targets=[v['buildSettings'] for v in settings if v.get('target')==scheme]
 need(len(targets)==1 and targets[0]['CONFIGURATION']=='Release' and targets[0]['SWIFT_OPTIMIZATION_LEVEL']=='-O' and targets[0]['ONLY_ACTIVE_ARCH']=='YES','independent Release O configuration')
 schemes=list((folder/'schemes').glob('*.xcscheme'));need(len(schemes)==2,'independent two schemes')
 expected={'buildConfiguration':'Release','selectedDebuggerIdentifier':'','selectedLauncherIdentifier':'Xcode.IDEFoundation.Launcher.PosixSpawn','codeCoverageEnabled':'NO','disableMainThreadChecker':'YES','enableAddressSanitizer':'NO','enableThreadSanitizer':'NO','enableUBSanitizer':'NO'}
 for path in schemes:
  tree=ET.parse(path)
  for tag in ('TestAction','LaunchAction'):
   action=tree.getroot().find(tag);need(action is not None and all(action.get(k)==v for k,v in expected.items()),'independent native scheme settings')



def validated_budget(value,expected,now):
 need(all(value.get(k)==v for k,v in expected.items()),"budget source/run/attempt")
 fields=[value.get(k) for k in ("started_uptime_s","soft_deadline_uptime_s","hard_deadline_uptime_s")]
 need(all(type(x) in (int,float) and math.isfinite(x) and x>0 for x in fields),"budget monotonic values")
 started,soft,hard=fields
 need(soft==started+PROFILE["main_soft_deadline_s"] and hard==started+PROFILE["main_hard_deadline_s"] and type(now) in (int,float) and math.isfinite(now) and started<=now<hard,"original single monotonic budget; seal cannot reset")
 return value
def begin_budget():
 value={**identity(),"started_uptime_s":time.monotonic()}
 value.update(soft_deadline_uptime_s=value["started_uptime_s"]+PROFILE["main_soft_deadline_s"],hard_deadline_uptime_s=value["started_uptime_s"]+PROFILE["main_hard_deadline_s"])
 path=OUT/"macos/control/budget.json";need(not path.exists(),"native budget already exists; do not restart")
 save(path,value);return value
def expected_cases(platform="macos",group=None):
 need(platform=="macos","Mac only")
 selected=[v for v in PROFILE["numeric_groups"] if group is None or v["group"]==group]
 need(bool(selected),"declared numeric group")
 return [c for v in selected for c in v["selectors"]]
def original_body_hashes(text):
 names=("func test08F08ScrollMetrics()","func test14F08NativeShelfAnimationSignposts()","func test09NativeExtendedLaunchThroughShelfReady()","func test10NativeResponsiveLaunchAndShelfUpperBound()","func test13NativeResponsiveLaunchWithoutExtendedTaskControl()","func test11FrozenOriginalFontAndLocateMetrics()","func test12LongReaderPageFontAndLocateDiagnostic()","private func nativeMetrics()","private func launchMetric(")
 return {name:hashlib.sha256(protocol.swift_function(text,name).encode()).hexdigest() for name in names}
def load_native_tools():
 spec=importlib.util.spec_from_file_location("original_apple_measurements",ROOT/"tests/reader_f08_apple_20261031/run.py")
 module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);module.command=command
 sys.path.insert(0,str(ROOT/"tests/apple_host"));import collect_evidence
 def load_results(path):
  previous=collect_evidence.command
  try:
   collect_evidence.command=lambda *args:command(args,text=True).strip()
   return collect_evidence.load_results(path)
  finally:collect_evidence.command=previous
 return module.extract_metrics,load_results

def native(platform):
 global DEADLINE
 budget=begin_budget();started=budget['started_uptime_s'];deadline=budget['soft_deadline_uptime_s'];hard_deadline=budget['hard_deadline_uptime_s'];DEADLINE=deadline
 need(platform=='macos','Mac only');folder=OUT/platform/'evidence';folder.mkdir(parents=True)
 report={**identity(),'platform':platform,'diagnostic_only':True,'f08_accepted':False,'collection_complete':False,'commands':[],'problems':[]}
 app=None;expected=None;png_site=None;admitted=False
 def run(args,role,timeout=180,required=True,separate_streams=False,cleanup=False,group=None):
  log_group=group
  args=list(map(str,args));timeout=min(timeout,remaining(hard_deadline if cleanup else deadline))
  need(time.monotonic()<hard_deadline,'native overall deadline exhausted before '+role)
  timeout=min(timeout,hard_deadline-time.monotonic())
  print('READER_ANIMATION_PHASE',platform,role,log_group or 'controller',flush=True)
  logs=folder/log_group if log_group is not None else folder
  logs.mkdir(parents=True,exist_ok=True)
  log=logs/(role+('.stdout.json' if separate_streams else '.log'))
  error_log=logs/(role+'.stderr.log');timed=False;signals=[];wait_error=None;started=time.monotonic()
  env=os.environ.copy();removed=[];xcodebuild=pathlib.Path(args[0]).name=='xcodebuild'
  inspect_group=True
  if png_site is not None:env['PYTHONPATH']=str(png_site)
  for name in CREDENTIAL_NAMES:
   if name in env:removed.append(name);env.pop(name)
  def snapshot():
   remaining=hard_deadline-time.monotonic()
   if remaining<=0:return {'group':group,'members':[],'probe_error':'native overall deadline exhausted'}
   return process_group_snapshot(group,timeout=min(5,remaining))
  def observed(state):return state.get('probe_returncode')==0 and 'probe_error' not in state
  def wait_for_exit(grace):
   remaining=hard_deadline-time.monotonic()
   if remaining<=0:return False
   try:proc.wait(timeout=min(grace,remaining));return True
   except subprocess.TimeoutExpired:return False
  with log.open('wb') as f,error_log.open('wb') as e:
   proc=subprocess.Popen(args,cwd=ROOT,stdout=f,stderr=e if separate_streams else subprocess.STDOUT,start_new_session=True,env=env)
   group=proc.pid
   try:proc.wait(timeout=timeout)
   except subprocess.TimeoutExpired:
    timed=True
    for sig,grace in ((signal.SIGINT,20),(signal.SIGTERM,10),(signal.SIGKILL,5)):
     try:os.killpg(group,sig);signals.append({'signal':int(sig),'uptime_s':time.monotonic()})
     except ProcessLookupError:break
     if wait_for_exit(grace):break
    if proc.returncode is None:wait_for_exit(5)
   except BaseException as e:wait_error=repr(e)
   group_before=None;group_after=None
   if inspect_group:
    group_before=snapshot();state=group_before
    if not observed(state) or group_has_live_members(state):
     for sig,grace in ((signal.SIGTERM,2),(signal.SIGKILL,1)):
      try:os.killpg(group,sig);signals.append({'signal':int(sig),'uptime_s':time.monotonic(),'reason':'owned descendants after direct process exit'})
      except ProcessLookupError:break
      limit=min(hard_deadline,time.monotonic()+grace)
      while time.monotonic()<limit:
       state=snapshot()
       if not observed(state) or not group_has_live_members(state):break
       time.sleep(min(0.05,max(0,limit-time.monotonic())))
      if observed(state) and not group_has_live_members(state):break
    if proc.returncode is None:wait_for_exit(5)
    group_after=snapshot()
  record={'role':role,'argv':args,'returncode':proc.returncode,'timed_out':timed,'collector_limit_s':timeout,
   'pid':proc.pid,'owned_process_group':group,'direct_process_reaped':proc.poll() is not None,
   'started_uptime_s':started,'finished_uptime_s':time.monotonic(),'signals_sent':signals,
   'group':log_group,'stdout_file':log.relative_to(folder).as_posix(),'stderr_file':error_log.relative_to(folder).as_posix() if separate_streams else 'combined in stdout_file',
   'environment_credentials_removed_by_name':removed,'wait_error':wait_error}
  if inspect_group:
   record.update({'owned_group_before_cleanup':group_before,'owned_group_after_cleanup':group_after,
    'owned_group_observation_complete':all(observed(x) for x in (group_before,group_after)),
    'owned_group_terminal_verified':observed(group_after) and not group_has_live_members(group_after) and record['direct_process_reaped']})
  report['commands'].append(record)
  if inspect_group and (not record['owned_group_observation_complete'] or not record['owned_group_terminal_verified']):
   if not record['owned_group_observation_complete']:report['problems'].append(role+' owned process group terminal state unobserved')
   if group_has_live_members(group_after):report['problems'].append(role+' owned process group retains live members')
   if not record['direct_process_reaped']:report['problems'].append(role+' direct process not reaped')
   raise RuntimeError(role+' owned process group unobserved or still live after cleanup; stop before compilation, parsing or sealing')
  if wait_error:
   report['problems'].append(role+' wait failed '+wait_error)
   raise RuntimeError(role+' wait failed; group terminal observations retained')
  if timed or proc.returncode:
   report['problems'].append(role+(' collection timeout' if timed else ' exit '+str(proc.returncode)))
   if required:raise RuntimeError(role+' failed; raw streams and known process state retained')
   return False
  return True

 try:
  admission=guard();admitted=True
  save(folder/'profile.json',PROFILE);save(folder/'source-admission.json',admission);save(folder/'budget.json',budget)
  for source_path in sorted(ALLOWED):
   target=folder/'source'/source_path;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/source_path,target)
  png_site=prepare_png_tools(OUT/platform/'validation-tools',folder/'validation-tools')
  run([sys.executable,'-m','unittest','discover','-s',HERE,'-p','test_protocol.py','-v'],'protocol-controls',30)
  try:command(['ruby','-rxcodeproj','-e','puts Xcodeproj::VERSION'],text=True)
  except subprocess.CalledProcessError:run(['gem','install','xcodeproj','--no-document'],'xcodeproj-dependency',120)
  run(['xcodebuild','-version'],'xcode-version',120)
  xcode=(folder/'xcode-version.log').read_text();os_version=command(['sw_vers'],text=True)
  need(xcode.splitlines()[0]==PROFILE['environment']['xcode_version_line'] and int(command(['sw_vers','-productVersion'],text=True).split('.')[0])==15 and os.environ.get('DEVELOPER_DIR')==PROFILE['environment']['developer_dir'],'declared Mac15/Xcode16.4 environment')
  save(folder/'environment.json',{'xcode':xcode,'os':os_version,'developer_dir':os.environ.get('DEVELOPER_DIR'),'runner_image':os.environ.get('ImageVersion'),'arch':command(['uname','-m'],text=True),'python_executable':sys.executable,'python_version':sys.version})
  run(['system_profiler','SPDisplaysDataType','-json'],'display-before',30)
  installed=prepare_inputs(OUT/platform/'input',folder/'inputs');resources=installed['resources']
  seed=json.loads((resources/'shelf-seed.json').read_text());need(seed['books']==2202 and len(set(seed['source_keys']))==2202,'frozen actual2202');shutil.copyfile(resources/'shelf-seed.json',folder/'shelf-seed.json')
  fixed=PROFILE['numeric_scope_authorization']['sample'];sample=resources/'Sample.epub'
  need(sample.stat().st_size==fixed['bytes'] and sha(sample)==fixed['sha256'],'approved additional fixed Apple Sample bytes')
  extract_metrics,load_results=load_native_tools()
  tests=OUT/platform/'driver/shelf/ui';tests.mkdir(parents=True)
  expected_executable=OUT/platform/'derived/Build/Products/Release/EXReaderHost.app/Contents/MacOS/EXReaderHost'
  sources=protocol.driver_sources(identity()['source_sha'],str(expected_executable.resolve()))
  for name,text in sources.items():(tests/name).write_text(text);shutil.copyfile(tests/name,folder/name)
  original_metrics=(ROOT/'tests/reader_f08_apple_20261031/Metrics.swift').read_text()
  need(original_body_hashes(sources['ShelfUITests.swift'])==original_body_hashes(original_metrics),'original test11/test12/nativeMetrics bodies exact')
  generated_app=OUT/platform/'driver/ReaderApp.swift';generated_app.write_text(protocol.injected_reader_app((ROOT/'examples/apple/ReaderApp.swift').read_text()));shutil.copyfile(generated_app,folder/'ReaderApp.swift');shutil.copyfile(HERE/'Bridge.swift',folder/'Bridge.swift')
  save(folder/'driver.json',{'generated_files':{name:sha(tests/name) for name in sources},'original_reader_bodies':original_body_hashes(original_metrics),'original_shelf_source_sha256':sha(ROOT/'tests/apple_host/shelf/ui/ShelfUITests.swift'),'original_metrics_sha256':sha(ROOT/'tests/reader_f08_apple_20261031/Metrics.swift'),'original_reader_app_sha256':sha(ROOT/'examples/apple/ReaderApp.swift'),'generated_reader_app_sha256':sha(generated_app),'tracked_bridge_sha256':sha(HERE/'Bridge.swift'),'original_cases':list(ORIGINAL_CASES),'additional_cases':PROFILE['cases'],'action_only_cases':PROFILE['action_only_cases'],'numeric_groups':PROFILE['numeric_groups'],'original_seven_gate':'pending','f08_accepted':False})
  project=OUT/platform/'project';run(['ruby','tests/reader_team24_apple/make_project.rb',project,resources,tests,'wave3'],'project',45)
  patch=r'project=Xcodeproj::Project.open(ARGV[0]);project.targets.each{|target|next unless target.product_type=="com.apple.product-type.application";target.build_configurations.each{|c|c.build_settings["SWIFT_ACTIVE_COMPILATION_CONDITIONS"]+=" EXR_APPLE_F08_REVIEW"}};target=project.targets.find{|t|t.name=="EXReaderHost-macOS"};raise "Mac target" unless target;original=target.source_build_phase.files.select{|f|f.file_ref && File.expand_path(f.file_ref.path.to_s,File.dirname(ARGV[0]))==File.expand_path(ARGV[1])};raise "exact original App source" unless original.length==1;original.first.remove_from_project;[ARGV[2],ARGV[3]].each{|path|ref=project.main_group.new_file(File.expand_path(path));target.source_build_phase.add_file_reference(ref)};project.save'
  run(['ruby','-rxcodeproj','-e',patch,project/'EXReaderHost.xcodeproj',ROOT/'examples/apple/ReaderApp.swift',generated_app,HERE/'Bridge.swift'],'observer-flags',30)
  config=json.loads(command(['ruby','-rxcodeproj','-rjson','-e','p=Xcodeproj::Project.open(ARGV[0]);v={};p.targets.each{|t|next unless t.product_type=="com.apple.product-type.application";t.build_configurations.each{|c|v[t.name+"/"+c.name]=c.build_settings["SWIFT_ACTIVE_COMPILATION_CONDITIONS"]}};puts JSON.generate(v)',project/'EXReaderHost.xcodeproj'],text=True));required={'EXR_APPLE_F08_REVIEW','EXR_APPLE_SHELF_REVIEW','EXR_APPLE_HOST_REVIEW','EXR_APPLE_RAW3','EXR_APPLE_WAVE3','EXR_APPLE_PAGE_THEME'}
  need(len(config)==4 and all(required<=set(v.split()) for v in config.values()),'full feature flags');save(folder/'project-configuration.json',config)
  for path in (project/'EXReaderHost.xcodeproj/xcshareddata/xcschemes').glob('*.xcscheme'):
   tree=ET.parse(path)
   for tag in ('TestAction','LaunchAction'):
    action=tree.getroot().find(tag);need(action is not None,'scheme action');action.attrib.update({'buildConfiguration':'Release','selectedDebuggerIdentifier':'','selectedLauncherIdentifier':'Xcode.IDEFoundation.Launcher.PosixSpawn','codeCoverageEnabled':'NO','disableMainThreadChecker':'YES','enableAddressSanitizer':'NO','enableThreadSanitizer':'NO','enableUBSanitizer':'NO'})
   tree.write(path,encoding='utf-8',xml_declaration=True);dest=folder/'schemes'/path.name;dest.parent.mkdir(exist_ok=True);shutil.copyfile(path,dest)
  scheme='EXReaderHost-macOS';test_target='EXReaderHostUITests-macOS';sdk=installed['macos-sdk'];derived=OUT/platform/'derived'
  build=['-project',project/'EXReaderHost.xcodeproj','-scheme',scheme,'-destination','platform=macOS','-derivedDataPath',derived,'-configuration','Release','EXR_SDK_DIR='+str(sdk/'sdk'),'EXR_PRODUCTS_DIR='+str(sdk/'raw-products'),'CODE_SIGNING_ALLOWED=YES','SWIFT_OPTIMIZATION_LEVEL=-O','GCC_OPTIMIZATION_LEVEL=s','ONLY_ACTIVE_ARCH=YES']
  common=[*build,'-enableCodeCoverage','NO','-enableAddressSanitizer','NO','-enableThreadSanitizer','NO','-enableUndefinedBehaviorSanitizer','NO','-parallel-testing-enabled','NO','-test-timeouts-enabled','YES','-default-test-execution-time-allowance','240','-maximum-test-execution-time-allowance','240']
  run(['xcodebuild','-showBuildSettings','-json',*build],'show-build-settings',120,separate_streams=True);settings=json.loads((folder/'show-build-settings.stdout.json').read_text());save(folder/'build-settings.json',settings)
  product_settings=[x['buildSettings'] for x in settings if x.get('target')==scheme];need(len(product_settings)==1 and product_settings[0]['SWIFT_OPTIMIZATION_LEVEL']=='-O' and product_settings[0]['CONFIGURATION']=='Release','Release O')
  run(['xcodebuild','build-for-testing',*common],'build',300)
  runs=sorted((derived/'Build/Products').glob('*.xctestrun'));need(runs,'actual xctestrun missing');(folder/'xctestrun').mkdir()
  for path in runs:
   raw=path.read_bytes()
   for name in CREDENTIAL_NAMES:
    credential=os.environ.get(name);need(not credential or credential.encode() not in raw,'credential found in raw xctestrun; refuse to seal')
   shutil.copyfile(path,folder/'xctestrun'/path.name)
  app=derived/'Build/Products/Release/EXReaderHost.app';expected=verify_program(app)
  program={'runtime_probe_not_product_completion':True,'program_source_sha':identity()['source_sha'],'program_sha256':sha(binary(app)),'program_files':expected,'sdk_input_source_sha':PRODUCER,'resource_input_source_sha':PRODUCER,'input_run_id':str(PROFILE['producer_run']),'input_attempt':str(PROFILE['producer_attempt']),'destination':'platform=macOS','built_executable_url':str(binary(app).resolve())}
  save(folder/'program-identity.json',program)
  group_receipts=[];save(folder/'numeric-groups.json',group_receipts)
  for group in PROFILE['numeric_groups']:
   label=group['group'];directory=folder/label;directory.mkdir()
   verify_program(app,expected);before=sha(binary(app))
   receipt={**identity(),'group':label,'relative_path':label,'selectors':group['selectors'],'program_before_sha256':before}
   group_receipts.append(receipt);save(folder/'numeric-groups.json',group_receipts)
   bundle=directory/'native.xcresult'
   run(['xcodebuild','test-without-building',*common,'-resultBundlePath',bundle,*['-only-testing:'+test_target+'/'+c for c in group['selectors']]],'native',1200 if group['kind']=='shelf' else 600,required=False,group=label)
   receipt['owned_application_cleanup']=cleanup_program(binary(app),hard_deadline)
   receipt['program_after_sha256']=sha(binary(app));verify_program(app,expected);receipt['program_files_unchanged']=True
   save(folder/'numeric-groups.json',group_receipts)
   if not bundle.exists():
    report['problems'].append(label+' xcresult bundle missing');continue
   try:
    objects,performance=extract_metrics(bundle,with_cases=True);save(directory/'xcresult-objects.json',objects);save(directory/'performance-cases.json',performance)
    statuses=load_results(bundle);save(directory/'test-cases.json',statuses);need_names={x.rsplit('/',1)[-1]+'()' for x in group['selectors']}
    if {x['name'] for x in statuses}!=need_names or any(x['result']!='Passed' for x in statuses):report['problems'].append(label+' requested native case set/status incomplete')
    run(['xcrun','xcresulttool','export','attachments','--path',bundle,'--output-path',directory/'attachments'],'attachments',60,required=False,group=label)
    save(directory/'observations.json',observations(directory))
    if group['kind'] in ('capture','action_only'):
     assessment=protocol.assess(directory,performance,program,identity(),mode=group['kind']);save(directory/'assessment.json',assessment)
     if not assessment['complete']:report['problems'].append(label+' reader protocol or native capability missing')
     report.setdefault('final_sidecars',{})[label]=finalize_sidecars(directory,group['kind'])
     receipt['sidecars_finalized_after_owned_cleanup']=True;save(folder/'numeric-groups.json',group_receipts)
   except BaseException as error:
    report['problems'].append(label+' parsing '+repr(error));receipt['parsing_error']=repr(error);save(folder/'numeric-groups.json',group_receipts)
  assessment=protocol.assess_numeric(folder,program,identity());save(folder/'assessment.json',assessment)
  report['numeric_complete']=assessment['numeric_complete'];report['numeric_budgets_passed']=assessment['numeric_budgets_passed'];report['budget_failures']=assessment['budget_failures'];report['original_seven_gate']='pending'
  if not assessment['complete']:report['problems'].append('numeric groups or native data incomplete')

 except BaseException as error:report['problems'].append(repr(error));report['traceback']=traceback.format_exc()
 finally:
  DEADLINE=hard_deadline
  try:
   if app is not None:report['owned_application_cleanup']=cleanup_program(binary(app),hard_deadline)
  except BaseException as error:report['problems'].append('owned application cleanup '+repr(error));report['owned_application_cleanup']={'verified':False,'error':repr(error)}
  if app is not None and report.get('owned_application_cleanup',{}).get('verified') is True:
   try:
    remaining();actual=files_under(app);report['program_post_cleanup_unchanged']=expected is not None and actual==expected
    shutil.copytree(app,folder/'program/EXReaderHost.app');remaining()
    if not report['program_post_cleanup_unchanged']:report['problems'].append('actual program changed before final archive')
   except BaseException as error:report['problems'].append('postcleanup program archive '+repr(error))
   if set(report.get('final_sidecars',{}))!={'reader-capture','reader-action-only'}:report['problems'].append('per-group postcleanup sidecar inventory incomplete')
  if admitted:
   try:run(['system_profiler','SPDisplaysDataType','-json'],'display-after',30,required=False,cleanup=True)
   except BaseException as error:report['problems'].append('display-after '+repr(error))
  bridge_failures=[line for group in PROFILE['numeric_groups'] for path in [folder/group['group']/'native.log'] if path.exists() for line in path.read_text(errors='replace').splitlines() if 'F08_BRIDGE_FAIL' in line]
  report['bridge_failure_log_lines']=bridge_failures
  if bridge_failures:report['problems'].append('sticky app-main bridge failure in actual final native log')
  report['collection_complete']=not report['problems'];report['collector_elapsed_s']=time.monotonic()-started;report['soft_budget_s']=PROFILE['main_soft_deadline_s'];report['hard_budget_s']=PROFILE['main_hard_deadline_s'];save(folder/'result.json',report)
  print('READER_ANIMATION_RESULT',json.dumps({'collection_complete':report['collection_complete'],'problems':report['problems'],'collector_elapsed_s':report['collector_elapsed_s']}),flush=True)
 need(report['collection_complete'],'diagnosis incomplete; raw observations retained')



def owned_program_snapshot(executable,deadline):
 target=str(pathlib.Path(executable).resolve())
 raw=subprocess.check_output(['/bin/ps','-ww','-axo','pid=,uid=,stat=,comm='],text=True,timeout=min(5,remaining(deadline)))
 rows=[];unqualified_zombies=[]
 for line in raw.splitlines():
  parts=line.strip().split(None,3)
  if len(parts)==4 and parts[0].isdigit() and parts[3].strip('()')==pathlib.Path(target).name:
   if parts[2].startswith('Z'):unqualified_zombies.append({'pid':int(parts[0]),'uid':parts[1],'state':parts[2],'reported_executable':parts[3]})
   else:raise RuntimeError('live owned executable path unavailable; basename cannot prove terminal state')
  if len(parts)==4 and parts[0].isdigit() and parts[3]==target:
   need(parts[1].isdigit() and int(parts[1])==os.getuid(),'owned executable has different UID')
   rows.append({'pid':int(parts[0]),'uid':int(parts[1]),'state':parts[2],'executable_url':parts[3]})
 return {'observed':True,'executable_url':target,'members':rows,'unqualified_zombies':unqualified_zombies}
def cleanup_program(executable,deadline):
 initial=owned_program_snapshot(executable,deadline);signals=[]
 for sig,grace in ((signal.SIGTERM,3),(signal.SIGKILL,2)):
  current=owned_program_snapshot(executable,deadline);live=[v for v in current['members'] if not v['state'].startswith('Z')]
  if not live:break
  for item in live:
   # PID ownership is re-read immediately before each signal.
   if any(v['pid']==item['pid'] and not v['state'].startswith('Z') for v in owned_program_snapshot(executable,deadline)['members']):
    try:os.kill(item['pid'],sig);signals.append({'pid':item['pid'],'signal':int(sig),'uptime_s':time.monotonic()})
    except ProcessLookupError:pass
  stop=min(deadline,time.monotonic()+grace)
  while time.monotonic()<stop:
   if not any(not v['state'].startswith('Z') for v in owned_program_snapshot(executable,deadline)['members']):break
   time.sleep(min(.05,max(0,stop-time.monotonic())))
 final=owned_program_snapshot(executable,deadline);verified=not any(not v['state'].startswith('Z') for v in final['members'])
 need(verified,'owned product retains live PID after cleanup')
 return {'verified':True,'before':initial,'after':final,'signals':signals}
def attachment_path(folder,name):
 need(isinstance(name,str) and bool(name) and pathlib.Path(name).name==name,'attachment export path')
 base=folder/'attachments';path=base/name
 need(not path.is_symlink() and path.resolve().is_relative_to(base.resolve()),'attachment export path')
 return path

def observations(folder):
 rows=[];path=folder/'attachments/manifest.json'
 if not path.exists():return rows
 for case in json.loads(path.read_text()):
  for att in case.get('attachments',[]):
   if any(tag in att.get('suggestedHumanReadableName','') for tag in ('f08-launch-observations','shelf-observations','f08-reader-observations','f08-reader-window-preparation','f08-reader-animation-protocol','f08-reader-animation-app-log','f08-reader-animation-metric-configuration','f08-native-metric-configuration')):
    rows.append(json.loads(attachment_path(folder,att['exportedFileName']).read_text()))
 return rows
def assess(folder,performance,program,mode='capture'):return protocol.assess(folder,performance,program,identity(),mode=mode)



def attachment_records(folder,tag):
 records=[];base=folder/'attachments';manifest=base/'manifest.json'
 if not manifest.exists():return records
 for case in json.loads(manifest.read_text()):
  for attachment in case.get('attachments',[]):
   if tag not in attachment.get('suggestedHumanReadableName',''):continue
   path=attachment_path(folder,attachment['exportedFileName'])
   raw=path.read_bytes();records.append({'case':case['testIdentifier'],'path':path,'raw':raw,'value':json.loads(raw)})
 return records

def checked_sidecar_path(value,nonce,allowed_roots,uid):
 message='only declared same-UID nonce temporary sidecar'
 need(isinstance(value,dict) and isinstance(nonce,str) and len(nonce)==32 and all(c in '0123456789abcdef' for c in nonce) and type(uid) is int and uid>=0,message)
 raw_root=value.get('temporary_root');raw_path=value.get('app_log_path')
 need(isinstance(raw_root,str) and isinstance(raw_path,str) and bool(raw_root) and bool(raw_path),message)
 temporary=pathlib.Path(raw_root);path=pathlib.Path(raw_path)
 roots={pathlib.Path(root).resolve() for root in allowed_roots}
 need(temporary.is_absolute() and str(temporary)==raw_root and '..' not in temporary.parts and not temporary.is_symlink() and temporary==temporary.resolve() and temporary in roots,message)
 need(temporary.is_dir() and temporary.stat().st_uid==uid,message)
 expected=temporary/('F08ReaderAnimation-'+nonce)/'app-bridge.json'
 need(path.is_absolute() and str(path)==raw_path and '..' not in path.parts and path==expected and not path.parent.is_symlink() and not path.is_symlink(),message)
 directory_status=path.parent.lstat();file_status=path.lstat()
 need(stat.S_ISDIR(directory_status.st_mode) and directory_status.st_uid==uid and stat.S_IMODE(directory_status.st_mode)==0o700 and stat.S_ISREG(file_status.st_mode) and file_status.st_uid==uid,message)
 return path

def finalize_sidecars(folder,mode='capture'):
 records=attachment_records(folder,'f08-reader-animation-protocol');apps=attachment_records(folder,'f08-reader-animation-app-log')
 need(len(records)==len(apps)==2,'exact two final sidecar owners')
 result=[];seen=set();raw_root=command(['/usr/bin/getconf','DARWIN_USER_TEMP_DIR'],text=True).strip();temporary=pathlib.Path(raw_root).resolve()
 need(temporary.is_dir() and temporary.stat().st_uid==os.getuid(),'actual current-UID Darwin temporary root')
 runner_bundle='org.exreader.host.uitests.xctrunner'
 runner_temporary=(pathlib.Path.home()/'Library/Containers'/runner_bundle/'Data/tmp').resolve()
 allowed_roots={temporary,runner_temporary}
 save(folder/'temporary-root.json',{'provider':'independent getconf plus fixed original UITestRunner container','raw':raw_root,'canonical':str(temporary),'runner_bundle_identifier':runner_bundle,'runner_canonical':str(runner_temporary),'allowed_roots':sorted(str(root) for root in allowed_roots),'uid':os.getuid()})
 for record in records:
  value=record['value'];owner=value['identity'];case=str(owner['case_id']);nonce=owner['nonce']
  case_map=PROFILE['action_only_cases'] if mode=='action_only' else PROFILE['cases'];actual=record['case']
  need(case in case_map and actual==case_map[case]+'()' and value.get('actual_test_identifier')==actual and value.get('mode')==mode and case not in seen and len(nonce)==32 and all(c in '0123456789abcdef' for c in nonce),'unique actual testIdentifier/nonce/cohort sidecar owner');seen.add(case)
  path=checked_sidecar_path(value,nonce,allowed_roots,os.getuid())
  matches=[a for a in apps if a['case']==actual and a['value'].get('identity')==owner];need(len(matches)==1,'exact app-log attachment owner')
  remaining();raw=path.read_bytes();digest=hashlib.sha256(raw).hexdigest();target=folder/'final-sidecars'/(case+'-'+nonce+'.json');target.parent.mkdir(exist_ok=True);target.write_bytes(raw)
  item={'case_id':case,'actual_test_identifier':actual,'nonce':nonce,'mode':mode,'identity':owner,'owned_source_path':str(path),'relative_path':target.relative_to(folder).as_posix(),'sha256':digest,'bytes':len(raw),'ui_declared_sha256':value['app_log_sha256'],'attachment_sha256':hashlib.sha256(matches[0]['raw']).hexdigest(),'same_bytes':raw==matches[0]['raw'],'read_uptime_s':time.monotonic()}
  result.append(item);save(folder/'final-sidecars.json',result)
  need(item['same_bytes'] and digest==value['app_log_sha256'],'postcleanup sidecar changed after UI flush snapshot')
  need(json.loads(raw).get('errors')==[] and json.loads(raw).get('complete_log') is True,'final sidecar error/EOF')
 return result

def verify_final_sidecars(folder,result,mode='capture'):
 records=attachment_records(folder,'f08-reader-animation-protocol');apps=attachment_records(folder,'f08-reader-animation-app-log');items=result.get('final_sidecars')
 need(isinstance(items,list) and len(items)==len(records)==len(apps)==2,'complete postcleanup sidecar inventory')
 need(items==json.loads((folder/'final-sidecars.json').read_text()),'actual postcleanup sidecar receipt')
 need({v['case_id'] for v in items}==set(PROFILE['cases']),'exact final sidecar cases')
 for item in items:
  case=item['case_id'];nonce=item['nonce'];actual=item['actual_test_identifier'];case_map=PROFILE['action_only_cases'] if mode=='action_only' else PROFILE['cases'];need(actual==case_map[case]+'()' and item['mode']==mode and nonce==item['identity']['nonce'],'independent actual testIdentifier/nonce/cohort');path=folder/'final-sidecars'/(case+'-'+nonce+'.json');need(item['relative_path']==path.relative_to(folder).as_posix(),'exact archived sidecar path')
  raw=path.read_bytes();need(len(raw)==item['bytes'] and hashlib.sha256(raw).hexdigest()==item['sha256']==item['ui_declared_sha256']==item['attachment_sha256'] and item['same_bytes'] is True,'final sidecar bytes/digest receipt')
  ui=[r for r in records if r['case']==actual and r['value'].get('identity')==item['identity']];app=[r for r in apps if r['case']==actual and r['value'].get('identity')==item['identity']]
  need(len(ui)==len(app)==1 and raw==app[0]['raw'] and ui[0]['value']['app_log_sha256']==item['sha256'],'independent final/attachment/owner join')
  need(json.loads(raw).get('errors')==[] and json.loads(raw).get('complete_log') is True,'final closed sidecar error/EOF')
 return items

def seal(platform):
 global DEADLINE
 folder=OUT/platform/'evidence';control=OUT/platform/'control';result=None
 try:
  budget=validated_budget(json.loads((control/'budget.json').read_text()),identity(),time.monotonic());DEADLINE=budget['hard_deadline_uptime_s'];guard()
  result=json.loads((folder/'result.json').read_text());need(all(result.get(k)==v for k,v in identity().items()),'terminal report source/run')
  commands=result.get('commands',[]);unsafe=[c for c in commands if (pathlib.Path(c.get('argv',[''])[0]).name=='xcodebuild' or 'owned_group_observation_complete' in c) and c.get('owned_group_terminal_verified') is not True]
  need(not unsafe,'owned writer terminal state unverified')
  if any(c.get('role')=='native' for c in commands):need(result.get('owned_application_cleanup',{}).get('verified') is True,'owned application terminal state unverified')
  result['main_elapsed_s']=time.monotonic()-budget['started_uptime_s'];result['main_budget_s']=PROFILE['main_hard_deadline_s'];save(folder/'result.json',result)
  files=files_under(folder);files.pop('f08-manifest.json',None);remaining();need(time.monotonic()<budget['hard_deadline_uptime_s'],'sealing exceeds original hard deadline')
  save(folder/'f08-manifest.json',{**identity(),'kind':'macos','diagnostic_only':True,'f08_accepted':False,'files':files,'sealing_elapsed_s':time.monotonic()-budget['started_uptime_s'],'hard_budget_s':PROFILE['main_hard_deadline_s']})
  remaining()
 except BaseException as error:
  (folder/'f08-manifest.json').unlink(missing_ok=True)
  save(control/'UNSEALED.json',{**identity(),'kind':'unsealed-controller-receipt','diagnostic_only':True,'f08_accepted':False,'native_archive_sealed':False,'reason':repr(error),'collection_problems':result.get('problems',[]) if result else ['native terminal report unavailable'],'owned_group_records':[c for c in result.get('commands',[]) if 'owned_group_observation_complete' in c] if result else []})
  raise



def audit():
 global DEADLINE
 started=time.monotonic();DEADLINE=started+PROFILE['main_soft_deadline_s'];hard=started+PROFILE['main_hard_deadline_s'];out=ROOT/'build/f08-mac-reader-animation-audit';out.mkdir(parents=True,exist_ok=True)
 report={**identity(),'authenticated':False,'archive_authenticated':False,'program_authenticated':False,'diagnostic_complete':False,'diagnostic_only':True,'f08_accepted':False,'verified_stages':[],'errors':[],'missing':[],'input_producer':{'source_sha':PRODUCER,'run_id':PROFILE['producer_run'],'attempt':PROFILE['producer_attempt'],'actual_sdk_job':PROFILE['producer_sdk_job']}}
 try:
  admission=guard();report['verified_stages'].append('real diagnostic HEAD and exact isolated source additions')
  xcode=command(['xcodebuild','-version'],text=True);operating_system=command(['sw_vers','-productVersion'],text=True).strip()
  need(xcode.splitlines()[0]==PROFILE['environment']['xcode_version_line'] and int(operating_system.split('.')[0])==15 and os.environ.get('DEVELOPER_DIR')==PROFILE['environment']['developer_dir'],'independent actual Mac15/Xcode16.4 environment')
  save(out/'environment.json',{'xcode':xcode,'os':operating_system,'developer_dir':os.environ.get('DEVELOPER_DIR'),'python_executable':sys.executable,'python_version':sys.version})
  prepare_png_tools(out/'validation-tools',out/'validation-tools-receipt')
  prepare_inputs(out/'producer-inputs',out/'producer-input-metadata');report['verified_stages'].append('independent external943 producer receipts and complete input bytes')
  run=api('actions/runs/'+identity()['run_id']);need(run['head_sha']==identity()['source_sha'] and run['run_attempt']==int(identity()['attempt']) and run['repository']['full_name']=='NoGod3524/EXReader','diagnostic run source/repository/attempt')
  save(out/'run.json',run)
  jobs=api('actions/runs/'+identity()['run_id']+'/jobs?per_page=100')['jobs'];native_jobs=[j for j in jobs if j['name']=='native' and j['run_attempt']==int(identity()['attempt'])]
  need(len(native_jobs)==1 and native_jobs[0]['status']=='completed' and native_jobs[0]['head_sha']==identity()['source_sha'],'actual terminal native producer job');save(out/'native-job.json',native_jobs[0])
  metas=api('actions/runs/'+identity()['run_id']+'/artifacts?per_page=100')['artifacts'];name='f08-mac-reader-animation-macos-'+identity()['run_id']+'-'+identity()['attempt'];candidates=[m for m in metas if m['name']==name and not m['expired']]
  if len(candidates)!=1:
   controls=[m for m in metas if m['name']=='f08-mac-reader-animation-unsealed-control-'+identity()['run_id']+'-'+identity()['attempt'] and not m['expired']]
   if len(controls)==1:
    meta=controls[0];need(meta['workflow_run']['head_sha']==identity()['source_sha'] and meta['workflow_run']['id']==int(identity()['run_id']),'UNSEALED source/run');data=archive_bytes(meta);digest=hashlib.sha256(data).hexdigest();need(len(data)==meta['size_in_bytes'] and meta['digest']=='sha256:'+digest,'UNSEALED outer ZIP')
    with zipfile.ZipFile(io.BytesIO(data)) as control:
     need(control.namelist()==['UNSEALED.json'] and control.getinfo('UNSEALED.json').file_size<1024**2,'exact bounded UNSEALED receipt');receipt=json.loads(control.read('UNSEALED.json'))
    need(all(receipt.get(k)==v for k,v in identity().items()) and receipt.get('kind')=='unsealed-controller-receipt' and receipt.get('native_archive_sealed') is False,'UNSEALED controller source');report['unsealed_control']={'artifact':meta,'sha256':digest,'bytes':len(data),'receipt':receipt}
   report['missing'].append('unique sealed native diagnostic archive')
  need(len(candidates)==1,'unique sealed native diagnostic archive');meta=candidates[0];w=meta['workflow_run']
  need(w['head_sha']==identity()['source_sha'] and w['id']==int(identity()['run_id']) and w['repository_id']==run['repository']['id'] and w['head_repository_id']==run['head_repository']['id'],'external diagnostic artifact/run/source/repository')
  data=archive_bytes(meta);digest=hashlib.sha256(data).hexdigest();need(len(data)==meta['size_in_bytes'] and meta['digest']=='sha256:'+digest,'diagnostic ZIP outer bytes')
  report.update(artifact_id=meta['id'],artifact_sha256=digest,artifact_bytes=len(data));save(out/'artifact-receipt.json',{'repository_full_name':'NoGod3524/EXReader','artifact':meta,'run':run,'job':native_jobs[0]})
  z,manifest=validate_zip(data);need(all(manifest.get(k)==v for k,v in identity().items()) and manifest.get('kind')=='macos' and manifest.get('diagnostic_only') is True and manifest.get('f08_accepted') is False,'diagnostic manifest source/scope');report['verified_stages'].append('complete safe diagnostic inventory and every payload hash')
  need(manifest.get('hard_budget_s')==PROFILE['main_hard_deadline_s'] and 0<=manifest.get('sealing_elapsed_s',float('inf'))<=PROFILE['main_hard_deadline_s'],'producer seal within original hard budget')
  folder=out/'raw';folder.mkdir()
  for name in manifest['files']:
   remaining();path=folder/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(z.read(name))
  result=json.loads((folder/'result.json').read_text());need(all(result.get(k)==v for k,v in identity().items()) and result.get('diagnostic_only') is True and result.get('f08_accepted') is False,'native result identity/scope');report['producer_result']=result
  commands=result.get('commands',[]);need(all(c.get('owned_group_terminal_verified') is True for c in commands if pathlib.Path(c.get('argv',[''])[0]).name=='xcodebuild' or 'owned_group_observation_complete' in c),'all sealed owned writers terminal')
  if any(c.get('role')=='native' for c in commands):need(result.get('owned_application_cleanup',{}).get('verified') is True,'sealed owned product terminal')
  need(result.get('main_budget_s')==PROFILE['main_hard_deadline_s'] and 0<=result.get('main_elapsed_s',float('inf'))<=PROFILE['main_hard_deadline_s'],'producer entire main/cleanup budget');report['verified_stages'].append('native source, writer/application terminal state and original budget')
  need(json.loads((folder/'source-admission.json').read_text())==admission,'same-source admission')
  for path in sorted(ALLOWED):need((folder/'source'/path).read_bytes()==(ROOT/path).read_bytes(),'tracked source snapshot '+path)
  report['archive_authenticated']=True
  need(json.loads((folder/'profile.json').read_text())==PROFILE,'exact frozen diagnostic profile')
  for kind in ('macos','macos-sdk','iphonesimulator-sdk'):
   archived=json.loads((folder/'inputs'/(kind+'.json')).read_text());fresh=json.loads((out/'producer-input-metadata'/(kind+'.json')).read_text())
   need(all(archived[k]==fresh[k] for k in ('zip_sha256','zip_bytes','original_manifest','extracted_files')),'independent original input receipt '+kind)
  dependency=json.loads((folder/'validation-tools/dependency.json').read_text());catalog=json.loads((out/'validation-tools-receipt/pypi.json').read_text());native_wheel=folder/'validation-tools'/dependency['wheel_filename']
  published=[v for v in catalog['urls'] if v['filename']==dependency['wheel_filename']]
  need(dependency['name']=='Pillow' and dependency['version']=='12.0.0' and len(published)==1 and published[0]['digests']['sha256']==sha(native_wheel)==dependency['wheel_sha256'] and published[0]['size']==native_wheel.stat().st_size==dependency['wheel_bytes'],'independent official producer decoder bytes')
  verify_configuration(folder,'macos');program=json.loads((folder/'program-identity.json').read_text());files=verify_program(folder/'program/EXReaderHost.app')
  need(result.get('program_post_cleanup_unchanged') is True and files==program['program_files'] and sha(binary(folder/'program/EXReaderHost.app'))==program['program_sha256'] and program['program_source_sha']==identity()['source_sha'] and program['sdk_input_source_sha']==program['resource_input_source_sha']==PRODUCER and program['input_run_id']==str(PROFILE['producer_run']) and program['input_attempt']==str(PROFILE['producer_attempt']),'separate exact diagnostic program and943 SDK/resource identity');report['program_identity']=program;report['program_authenticated']=True
  expected_sources=protocol.driver_sources(identity()['source_sha'],program['built_executable_url'])
  for name,text in expected_sources.items():need((folder/name).read_text()==text,'exact generated driver '+name)
  need((folder/'ReaderApp.swift').read_text()==protocol.injected_reader_app((ROOT/'examples/apple/ReaderApp.swift').read_text()) and (folder/'Bridge.swift').read_bytes()==(HERE/'Bridge.swift').read_bytes(),'exact test-only App init and bridge')
  driver=json.loads((folder/'driver.json').read_text());need(driver['original_reader_bodies']==original_body_hashes((ROOT/'tests/reader_f08_apple_20261031/Metrics.swift').read_text()),'unchanged original reader bodies/nativeMetrics')
  runs=list((folder/'xctestrun').glob('*.xctestrun'));need(runs,'actual xctestrun missing');report['xctestrun']=[{'name':p.name,'sha256':sha(p),'bytes':p.stat().st_size} for p in runs]
  report['verified_stages'].append('all7 source snapshots, exact generated sources, full-feature Release program and actual xctestrun')
  extract_metrics,load_results=load_native_tools();all_cases=[];all_performance=[]
  for group in PROFILE['numeric_groups']:
   directory=folder/group['group'];bundle=directory/'native.xcresult'
   _,performance=extract_metrics(bundle,with_cases=True);cases=load_results(bundle)
   need(performance==json.loads((directory/'performance-cases.json').read_text()) and cases==json.loads((directory/'test-cases.json').read_text()),'independent actual native metrics/cases '+group['group'])
   need(observations(directory)==json.loads((directory/'observations.json').read_text()),'actual original/protocol attachments '+group['group'])
   if group['kind'] in ('capture','action_only'):
    assessment=assess(directory,performance,program,group['kind'])
    need(assessment==json.loads((directory/'assessment.json').read_text()),'independent reader protocol/PNG replay '+group['group'])
   all_cases.extend(cases);all_performance.extend(performance)
  report['native_cases']=all_cases;report['native_performance']=all_performance
  assessment=protocol.assess_numeric(folder,program,identity());report['assessment']=assessment
  need(assessment==json.loads((folder/'assessment.json').read_text()),'independent all-group numeric replay')
  report['final_sidecars']={group:verify_final_sidecars(folder/group,{'final_sidecars':result.get('final_sidecars',{}).get(group)},mode) for group,mode in (('reader-capture','capture'),('reader-action-only','action_only'))}
  names={v.rsplit('/',1)[-1]+'()' for v in expected_cases()};need(len(all_cases)==len(names) and {c['name'] for c in all_cases}==names and all(c['result']=='Passed' for c in all_cases),'all eleven actual numeric/capture/original-reader case results')
  bridge_failures=[line for group in PROFILE['numeric_groups'] for path in [folder/group['group']/'native.log'] for line in path.read_text(errors='replace').splitlines() if 'F08_BRIDGE_FAIL' in line]
  need(bridge_failures==result.get('bridge_failure_log_lines') and not bridge_failures,'independent sticky bridge log errors')
  need(result.get('collection_complete') is True and not result.get('problems') and assessment['complete'] is True,'complete numeric collection/protocol/native capability')
  report['numeric_complete']=assessment['numeric_complete'];report['numeric_budgets_passed']=assessment['numeric_budgets_passed'];report['budget_failures']=assessment['budget_failures'];report['original_seven_gate']='pending'

  report['verified_stages'].append('all original/additional cases, exact attachments, final sidecar bytes and independent capability replay');report['authenticated']=True;report['diagnostic_complete']=True
 except BaseException as error:
  report['errors'].append(repr(error));report['traceback']=traceback.format_exc();raise
 finally:
  DEADLINE=hard;report['audit_elapsed_s']=time.monotonic()-started;report['audit_hard_budget_s']=PROFILE['main_hard_deadline_s']
  if report['audit_elapsed_s']>PROFILE['main_hard_deadline_s']:report['authenticated']=False;report['diagnostic_complete']=False;report['errors'].append('audit hard deadline exceeded')
  save(out/'report.json',report);print('READER_ANIMATION_AUDIT',json.dumps({'authenticated':report['authenticated'],'errors':report['errors'],'missing':report['missing'],'audit_elapsed_s':report['audit_elapsed_s']}),flush=True)
  remaining()


def prepare_png_tools(folder,receipt_folder):
 folder.mkdir(parents=True);receipt_folder.mkdir(parents=True,exist_ok=True);site=folder/'site';site.mkdir()
 expected={'arm64':('pillow-12.0.0-cp313-cp313-macosx_11_0_arm64.whl','5193fde9a5f23c331ea26d0cf171fbf67e3f247585f50c08b3e205c7aeb4589b'),'x86_64':('pillow-12.0.0-cp313-cp313-macosx_10_13_x86_64.whl','c50f36a62a22d350c96e49ad02d0da41dbd17ddc2e29750dbdba4323f85eb4a5')}
 need(sys.version_info[:2]==(3,13) and os.uname().machine in expected,'predeclared CPython313 Mac wheel architecture');filename,pinned=expected[os.uname().machine]
 with urllib.request.urlopen('https://pypi.org/pypi/Pillow/12.0.0/json',timeout=min(60,remaining())) as response:metadata=json.load(response)
 matches=[f for f in metadata['urls'] if f['filename']==filename]
 need(metadata['info']['version']=='12.0.0' and len(matches)==1 and matches[0]['digests']['sha256']==pinned and matches[0]['url'].startswith('https://files.pythonhosted.org/'),'official release and predeclared wheel digest')
 save(receipt_folder/'pypi.json',metadata);wheel=receipt_folder/filename
 with urllib.request.urlopen(matches[0]['url'],timeout=min(60,remaining())) as response,wheel.open('xb') as output:
  while data:=response.read(1024*1024):remaining();output.write(data)
 need(sha(wheel)==pinned and wheel.stat().st_size==matches[0]['size'],'actual official decoder wheel bytes')
 with zipfile.ZipFile(wheel) as archive:
  seen=set()
  for info in archive.infolist():
   remaining();path=pathlib.PurePosixPath(info.filename);key=str(path).casefold()
   need(not path.is_absolute() and '..' not in path.parts and '\\' not in info.filename and ':' not in info.filename and key not in seen and not info.flag_bits&1 and stat.S_IFMT(info.external_attr>>16) in (0,stat.S_IFREG,stat.S_IFDIR),'owned decoder wheel path/kind');seen.add(key)
   if info.is_dir():continue
   target=site/path;target.parent.mkdir(parents=True,exist_ok=True)
   with archive.open(info) as source,target.open('xb') as output:
    while data:=source.read(1024*1024):remaining();output.write(data)
 sys.path.insert(0,str(site));import PIL
 need(PIL.__version__=='12.0.0' and pathlib.Path(PIL.__file__).resolve().is_relative_to(site.resolve()),'actual owned Pillow dependency')
 save(receipt_folder/'dependency.json',{'name':'Pillow','version':PIL.__version__,'python':sys.version,'wheel_filename':filename,'wheel_sha256':sha(wheel),'wheel_bytes':wheel.stat().st_size,'official_release':'https://pypi.org/project/pillow/12.0.0/','installed_into_owned_directory_only':True,'installation':'verified official wheel unpacked into private sys.path; no system installation'})
 return site

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('mode',choices=('guard','native','seal','audit'));parser.add_argument('--platform',choices=('macos',),default='macos');args=parser.parse_args()
 if args.mode=='guard':guard()
 elif args.mode=='native':native(args.platform)
 elif args.mode=='seal':seal(args.platform)
 else:audit()
