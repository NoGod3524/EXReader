"""Mac26 native reader capability over the original reader bodies; never F08 acceptance."""
import argparse,hashlib,importlib.util,json,math,os,pathlib,plistlib,shutil,signal,subprocess,time,traceback
import xml.etree.ElementTree as ET
ROOT=pathlib.Path(__file__).resolve().parents[2]
HERE=pathlib.Path(__file__).resolve().parent
PROFILE=json.loads((HERE/"profile.json").read_text())
BASE=PROFILE["source_base"]
ALLOWED={".github/workflows/dot-f08-apple-reader26-20261031.yml","tests/reader_f08_apple_reader26_20261031/run.py","tests/reader_f08_apple_reader26_20261031/helpers.py","tests/reader_f08_apple_reader26_20261031/profile.json"}
spec=importlib.util.spec_from_file_location("reader26_original_helpers",HERE/"helpers.py")
cap=importlib.util.module_from_spec(spec);spec.loader.exec_module(cap)
need,save,sha,command,identity=cap.need,cap.save,cap.sha,cap.command,cap.identity
cap.PROFILE=PROFILE;cap.BASE=PROFILE["input_source_sha"]
OUT=ROOT/"build/f08-apple-reader26"
def guard():
 need(os.environ.get("GITHUB_ACTIONS")=="true","Actions only")
 need(os.environ.get("GITHUB_REPOSITORY")=="NoGod3524/EXReader","repository")
 need(command(["git","rev-parse","HEAD"],text=True).strip()==identity()["source_sha"],"real diagnostic HEAD")
 need(not command(["git","status","--porcelain","--untracked-files=no"],text=True).strip(),"tracked diagnostic source changed")
 command(["git","merge-base","--is-ancestor",BASE,"HEAD"])
 need(set(command(["git","diff","--no-renames","--name-only",BASE,"HEAD"],text=True).splitlines())==ALLOWED,"exact reader diagnostic additions only")

def swift_function(text,name):
 start=text.index("    "+name)
 brace=text.index("{",start);depth=1;end=brace+1
 while depth:
  need(end<len(text),"Swift function boundary")
  depth+=(text[end]=="{")-(text[end]=="}");end+=1
 return text[start:end]
def reader_body_hashes(text):
 return {name:hashlib.sha256(swift_function(text,name).encode()).hexdigest() for name in
  ("func test11FrozenOriginalFontAndLocateMetrics()","func test12LongReaderPageFontAndLocateDiagnostic()","private func nativeMetrics()")}
def driver_text():
 original=(ROOT/"tests/apple_host/shelf/ui/ShelfUITests.swift").read_text()
 insertion=(ROOT/"tests/reader_f08_apple_20261031/Metrics.swift").read_text()
 inside,marker,standalone=insertion.partition("// F08_STANDALONE_CLASSES");need(marker,"original metrics boundary")
 at=original.rfind("}");need(at>0,"original class boundary")
 needle='        app.launchArguments = ["-EXRShelfSeed", "-EXRFreshState", "1", "-EXRUITestFixtures", "1"]\n        app.launch()'
 need(standalone.count(needle)==1,"reader setup only")
 standalone=standalone.replace(needle,needle+'\n#if os(macOS)\n        XCTAssertTrue(f08PrepareReaderWindow(self, app), "Actual reader window preparation failed")\n#endif')
 candidate='import CryptoKit\nimport Darwin\nimport CoreGraphics\n'+original[:at]+inside+original[at:]+standalone+RUNTIME+PREP
 need(reader_body_hashes(candidate)==reader_body_hashes(insertion),"original reader bodies and nativeMetrics changed")
 return candidate

RUNTIME=r'''
private func f08RuntimeBindingData(_ app: XCUIApplication, _ reason: String) -> [String: Any] {
    var value: [String: Any] = ["kind": "runtime-binding", "reason": reason,
        "uptime_s": ProcessInfo.processInfo.systemUptime, "declared_launch_arguments": app.launchArguments,
        "allowlisted_declared_launch_environment_subset": app.launchEnvironment.filter { ["ApplePersistenceIgnoreState", "NSQuitAlwaysKeepsWindows", "AppleLanguages", "AppleLocale"].contains($0.key) }]
#if os(macOS)
    let applications = NSRunningApplication.runningApplications(withBundleIdentifier: "org.exreader.host")
    value["provider"] = "NSWorkspace NSRunningApplication; executable bytes read during reader setup outside every measurement"
    value["applications"] = applications.map { application -> [String: Any] in
        var item: [String: Any] = ["pid": application.processIdentifier, "active": application.isActive,
            "terminated": application.isTerminated, "finished_launching": application.isFinishedLaunching,
            "bundle_url": application.bundleURL?.path ?? "", "executable_url": application.executableURL?.path ?? ""]
        if let executable = application.executableURL, let data = try? Data(contentsOf: executable) {
            item["executable_sha256"] = SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
        }
        if let bundle = application.bundleURL,
           let data = try? Data(contentsOf: bundle.appendingPathComponent("Contents/Info.plist")),
           let plist = try? PropertyListSerialization.propertyList(from: data, format: nil),
           let info = plist as? [String: Any] {
            item["program_source_sha"] = info["EXRSourceSHA"] ?? ""
        }
        return item
    }
#else
    value["provider"] = "declared guest arguments; native shelf phases retain guest PID; sealed program and xctestrun retain the executable target; no NSWorkspace in Simulator guest"
#endif
    return value
}'''
PREP=r'''
#if os(macOS)
private func f08PrepareReaderWindow(_ test: XCTestCase, _ app: XCUIApplication) -> Bool {
    var events: [[String: Any]] = []
    func record(_ phase: String) {
        let pids = Set(NSRunningApplication.runningApplications(withBundleIdentifier: "org.exreader.host").map(\.processIdentifier))
        let windows = (CGWindowListCopyWindowInfo([.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID) as? [[String: Any]] ?? [])
            .filter { row in (row[kCGWindowOwnerPID as String] as? NSNumber).map { pids.contains($0.int32Value) } == true }
            .map { row -> [String: Any] in ["owner_pid": row[kCGWindowOwnerPID as String] ?? -1,
                "layer": row[kCGWindowLayer as String] ?? -1, "bounds": row[kCGWindowBounds as String] ?? [:]] }
        func restoreSubset(_ values: [String: Any]) -> [String: Any] {
            values.filter { ["NSQuitAlwaysKeepsWindows", "ApplePersistenceIgnoreState"].contains($0.key) || $0.key.hasPrefix("NSWindow Frame") }
        }
        events.append(["phase": phase, "uptime_s": ProcessInfo.processInfo.systemUptime,
            "runtime": f08RuntimeBindingData(app, phase), "native_owned_windows": windows,
            "ax_window_count": app.windows.count,
            "search_exists": app.descendants(matching: .any).matching(identifier: "library.search").firstMatch.exists,
            "product_persistent_restore_subset": restoreSubset(UserDefaults.standard.persistentDomain(forName: "org.exreader.host") ?? [:]),
            "global_persistent_restore_subset": restoreSubset(UserDefaults.standard.persistentDomain(forName: UserDefaults.globalDomain) ?? [:])])
    }
    defer {
        let value: [String: Any] = ["kind": "reader-window-preparation", "test": test.name, "events": events,
            "meaning": "Reader setup only, before nativeMetrics and measure. Not launch09, TTI, or a stable/public restore-key contract."]
        if let data = try? JSONSerialization.data(withJSONObject: value, options: [.sortedKeys]) {
            let attachment = XCTAttachment(string: String(decoding: data, as: UTF8.self))
            attachment.name = "f08-reader-window-preparation"; attachment.lifetime = .keepAlways; test.add(attachment)
        }
    }
    record("after-original-launch")
    if app.windows.count == 0 {
        let file = app.menuBars.menuBarItems["File"]
        guard file.exists && file.isEnabled else { record("file-menu-unavailable"); return false }
        file.click()
        let item = app.menuBars.menuItems["New Window"].firstMatch
        record("before-standard-new-window-command")
        guard item.exists && item.isEnabled else { record("new-window-command-unavailable"); return false }
        item.click()
        record("after-standard-new-window-command")
    }
    let exists = app.windows.firstMatch.waitForExistence(timeout: 30)
    record(exists ? "window-prepared" : "window-missing")
    return exists
}
#endif
'''

def files_under(root):
 result={}
 for p in sorted(root.rglob("*")):
  if p.is_file():
   cap.remaining();result[p.relative_to(root).as_posix()]={"sha256":sha(p),"bytes":p.stat().st_size}
 return result

def verify_sdk_records(installed,sdk_record,kind):
 target=kind.removesuffix("-sdk")
 expected={"source_sha":cap.BASE,"run_id":str(PROFILE["producer_run"]),"attempt":str(PROFILE["producer_attempt"])}
 need(all(str(installed.get(k))==v and str(sdk_record.get(k))==v for k,v in expected.items()),"actual SDK source/run/attempt")
 need(installed.get("sdk_content_candidate")==cap.BASE and installed.get("target")==target and installed.get("sdk_version")=="3.42.0","actual SDK content/target/version")
 need(sdk_record.get("platform")==target and sdk_record.get("sdk_version")=="3.42.0" and sdk_record.get("abi")==1,"native SDK platform/version/ABI")
 need(sdk_record.get("job")==PROFILE["producer_sdk_job"],"retain actual SDK producer job; never relabel")

def prepare_inputs(folder,metadata_folder):
 result={}
 producer=cap.api('actions/runs/'+str(cap.PROFILE['producer_run']))
 need(producer['head_sha']==cap.BASE and producer['run_attempt']==cap.PROFILE['producer_attempt'] and producer['path']==PROFILE['producer_workflow'],'actual 9a input producer')
 for row in cap.PROFILE['inputs']:
  cap.remaining()
  if row['kind'] not in ('macos','macos-sdk','iphonesimulator-sdk'):continue
  meta=cap.api('actions/artifacts/'+str(row['id']))
  need(not meta['expired'] and meta['workflow_run']['head_sha']==cap.BASE and meta['workflow_run']['id']==cap.PROFILE['producer_run'],'input artifact producer')
  data=cap.archive_bytes(meta);digest=hashlib.sha256(data).hexdigest()
  need(len(data)==meta['size_in_bytes']==row['bytes'] and digest==row['sha256'] and meta['digest']=='sha256:'+digest,'input ZIP identity')
  z,manifest=cap.validate_zip(data)
  need(manifest['source_sha']==cap.BASE and manifest['run_id']==str(cap.PROFILE['producer_run']) and manifest['attempt']==str(cap.PROFILE['producer_attempt']) and manifest['kind']==row['kind'],'input manifest identity')
  resource_input=row['kind']=='macos'
  dest=folder/('resources' if resource_input else row['kind']);dest.mkdir(parents=True)
  prefix='program/EXReaderHost.app/Contents/Resources/'
  expected={}
  for name,item in manifest['files'].items():
   if resource_input:
    if not name.startswith(prefix):continue
    relative=name.removeprefix(prefix)
   else:
    if not (name.startswith(('sdk/','raw-products/')) or name.endswith('.json')):continue
    relative=name
   need(not any(part.endswith('.app') for part in pathlib.PurePosixPath(relative).parts),'input extraction must not create app bundles')
   p=dest/relative;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(z.read(name));expected[relative]=item
  need(files_under(dest)==expected,'extracted input bytes')
  if not resource_input:
   installed=json.loads((dest/'sdk342-installed-identity.json').read_text());sdk_record=json.loads((dest/'sdk-identity.json').read_text())
   verify_sdk_records(installed,sdk_record,row['kind'])
  else:
   need(len(expected)==15,'only original Resources inventory')
  result['resources' if resource_input else row['kind']]={'root':dest,'manifest':manifest}
  save(metadata_folder/(row['kind']+'.json'),{'metadata':meta,'zip_sha256':digest,'zip_bytes':len(data),'original_manifest':manifest,'extraction_prefix':prefix if resource_input else 'sdk/raw-products/identity JSON only','extracted_files':expected})
 need(not list(folder.rglob('*.app')),'extra same-bundle-ID input apps forbidden')
 return result

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

def verify_program(app,platform,expected=None):
 files=files_under(app)
 if expected is not None:need(files==expected,'executed program changed')
 info=plistlib.loads((app/('Contents/Info.plist' if platform=='macos' else 'Info.plist')).read_bytes())
 need(info.get('EXRSourceSHA')==identity()['source_sha'] and info.get('EXRSDKVersion')=='3.42.0' and info.get('EXRPageThemeEnabled') is True and info.get('CFBundleIdentifier')=='org.exreader.host','new full-feature program source and SDK')
 return files

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

def observations(folder):
 rows=[]
 manifest=folder/'attachments/manifest.json'
 if not manifest.exists():return rows
 for case in json.loads(manifest.read_text()):
  for att in case.get('attachments',[]):
   label=att.get('suggestedHumanReadableName','')
   if not any(tag in label for tag in ('f08-launch-observations','f08-reader-observations','f08-runtime-binding','f08-reader-window-preparation','f08-native-metric-configuration')):continue
   rows.append(json.loads((folder/'attachments'/att['exportedFileName']).read_text()))
 return rows

def runtime_row_identity(row,expected_sha,expected_source):
 issues=[];pids=[]
 applications=row.get('applications')
 if not expected_sha or not expected_source:issues.append(('missing','expected program identity unavailable'))
 if not isinstance(applications,list) or not applications:
  applications=[];issues.append(('missing','applications row is empty or absent'))
 for application in applications:
  if not isinstance(application,dict):
   issues.append(('missing','application identity is not an object'));continue
  pid=application.get('pid')
  if not isinstance(pid,int) or isinstance(pid,bool) or pid<=0:issues.append(('missing','application PID unavailable'))
  else:pids.append(pid)
  for key,expected in (('executable_sha256',expected_sha),('program_source_sha',expected_source)):
   actual=application.get(key)
   if not isinstance(actual,str) or not actual:issues.append(('missing',key+' unavailable'))
   elif expected and actual!=expected:issues.append(('mismatch',key+' differs from expected program'))
 return {'issues':issues,'runtime_pids':sorted(set(pids)),'application_count':len(applications)}

def binding_status(issues):
 return 'mismatch' if any(s=='mismatch' for s,_ in issues) else ('missing' if issues else 'matched')

def expected_cases(platform):
 need(platform=="macos","Mac only")
 return PROFILE["macos_cases"]


def native(platform):
 started=time.monotonic();deadline=started+PROFILE['native_collector_soft_limit_s'];hard_deadline=started+PROFILE['native_main_maximum_budget_s'];cap.DEADLINE=deadline
 guard();need(platform=='macos','Mac only');folder=OUT/platform/'evidence';folder.mkdir(parents=True)
 cap.EVIDENCE=folder
 report={**identity(),'platform':platform,'diagnostic_only':True,'f08_accepted':False,'collection_complete':False,'commands':[],'problems':[]}
 device=None
 def run(args,role,timeout=180,required=True,separate_streams=False):
  args=list(map(str,args));timeout=min(timeout,max(0.05,deadline-time.monotonic()))
  need(time.monotonic()<hard_deadline,'native overall deadline exhausted before '+role)
  timeout=min(timeout,hard_deadline-time.monotonic())
  print('READER26_PHASE',platform,role,flush=True)
  log=folder/(role+('.stdout.json' if separate_streams else '.log'))
  error_log=folder/(role+'.stderr.log');timed=False;signals=[];wait_error=None;started=time.monotonic()
  env=os.environ.copy();removed=[];xcodebuild=pathlib.Path(args[0]).name=='xcodebuild'
  inspect_group=separate_streams or xcodebuild
  if xcodebuild:
   for name in ('GH_TOKEN','GITHUB_TOKEN','ACTIONS_RUNTIME_TOKEN','ACTIONS_ID_TOKEN_REQUEST_TOKEN'):
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
   'stdout_file':log.name,'stderr_file':error_log.name if separate_streams else 'combined in stdout_file',
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
   print('\n'.join(log.read_text(errors='replace').splitlines()[-35:]),flush=True)
   if separate_streams:print('\n'.join(error_log.read_text(errors='replace').splitlines()[-35:]),flush=True)
   if required:raise RuntimeError(role+' failed; raw streams and known process state retained')
   return False
  return True
 try:
  save(folder/'profile.json',PROFILE)
  run(['xcodebuild','-version'],'xcode-version',120)
  xcode=(folder/'xcode-version.log').read_text();os_version=command(['sw_vers'],text=True)
  need(xcode.splitlines()[0]==PROFILE['environment']['xcode_version_line'] and int(command(['sw_vers','-productVersion'],text=True).split('.')[0])==26 and os.environ.get('DEVELOPER_DIR')==PROFILE['environment']['developer_dir'],'declared Mac26/Xcode26.2 environment')
  save(folder/'environment.json',{'xcode':xcode,'os':os_version,'developer_dir':os.environ.get('DEVELOPER_DIR'),'runner_image':os.environ.get('ImageVersion'),'arch':command(['uname','-m'],text=True)})
  run(['system_profiler','SPDisplaysDataType','-json'],'display-before',30)
  installed=prepare_inputs(OUT/platform/'input',folder/'inputs')
  resources=installed['resources']['root']
  seed=json.loads((resources/'shelf-seed.json').read_text());need(seed['books']==2202 and len(set(seed['source_keys']))==2202,'frozen actual2202')
  shutil.copyfile(resources/'shelf-seed.json',folder/'shelf-seed.json')
  extract_metrics,load_results=cap.load_native_tools()
  tests=OUT/platform/'driver/shelf/ui';tests.mkdir(parents=True)
  driver=tests/'ShelfUITests.swift';driver.write_text(driver_text());shutil.copyfile(driver,folder/'ShelfUITests.swift')
  save(folder/'driver.json',{'candidate_sha256':sha(driver),'original_reader_bodies':reader_body_hashes(driver.read_text()),'original_metrics_file_unchanged':True,'measurement_closures_unchanged':True,'window_preparation_only_in_reader_setup':True})
  project=OUT/platform/'project';run(['ruby','tests/reader_team24_apple/make_project.rb',project,resources,tests,'wave3'],'project',45)
  run(['ruby','-rxcodeproj','-e','p=Xcodeproj::Project.open(ARGV[0]);p.targets.each{|t|next unless t.product_type=="com.apple.product-type.application";t.build_configurations.each{|c|c.build_settings["SWIFT_ACTIVE_COMPILATION_CONDITIONS"]+=" EXR_APPLE_F08_REVIEW"}};p.save',project/'EXReaderHost.xcodeproj'],'observer-flags',30)
  config=json.loads(command(['ruby','-rxcodeproj','-rjson','-e','p=Xcodeproj::Project.open(ARGV[0]);v={};p.targets.each{|t|next unless t.product_type=="com.apple.product-type.application";t.build_configurations.each{|c|v[t.name+"/"+c.name]=c.build_settings["SWIFT_ACTIVE_COMPILATION_CONDITIONS"]}};puts JSON.generate(v)',project/'EXReaderHost.xcodeproj'],text=True))
  required={'EXR_APPLE_F08_REVIEW','EXR_APPLE_SHELF_REVIEW','EXR_APPLE_HOST_REVIEW','EXR_APPLE_RAW3','EXR_APPLE_WAVE3','EXR_APPLE_PAGE_THEME'}
  need(len(config)==4 and all(required<=set(v.split()) for v in config.values()),'full feature flags');save(folder/'project-configuration.json',config)
  for path in (project/'EXReaderHost.xcodeproj/xcshareddata/xcschemes').glob('*.xcscheme'):
   tree=ET.parse(path)
   for tag in ('TestAction','LaunchAction'):
    action=tree.getroot().find(tag);need(action is not None,'scheme action')
    action.attrib.update({'buildConfiguration':'Release','selectedDebuggerIdentifier':'','selectedLauncherIdentifier':'Xcode.IDEFoundation.Launcher.PosixSpawn','codeCoverageEnabled':'NO','disableMainThreadChecker':'YES','enableAddressSanitizer':'NO','enableThreadSanitizer':'NO','enableUBSanitizer':'NO'})
   tree.write(path,encoding='utf-8',xml_declaration=True);dest=folder/'schemes'/path.name;dest.parent.mkdir(exist_ok=True);shutil.copyfile(path,dest)
  target='macos';destination='platform=macOS';scheme='EXReaderHost-macOS';test_target='EXReaderHostUITests-macOS';suffix='Release';signing='YES'
  sdk=installed[target+'-sdk']['root'];derived=OUT/platform/'derived'
  build=['-project',project/'EXReaderHost.xcodeproj','-scheme',scheme,'-destination',destination,'-derivedDataPath',derived,'-configuration','Release','EXR_SDK_DIR='+str(sdk/'sdk'),'EXR_PRODUCTS_DIR='+str(sdk/'raw-products'),'CODE_SIGNING_ALLOWED='+signing,'SWIFT_OPTIMIZATION_LEVEL=-O','GCC_OPTIMIZATION_LEVEL=s','ONLY_ACTIVE_ARCH=YES']
  common=[*build,'-enableCodeCoverage','NO','-enableAddressSanitizer','NO','-enableThreadSanitizer','NO','-enableUndefinedBehaviorSanitizer','NO','-parallel-testing-enabled','NO','-test-timeouts-enabled','YES','-default-test-execution-time-allowance','240','-maximum-test-execution-time-allowance','240']
  run(['xcodebuild','-showBuildSettings','-json',*build],'show-build-settings',120,separate_streams=True)
  settings=json.loads((folder/'show-build-settings.stdout.json').read_text());save(folder/'build-settings.json',settings)
  product_settings=[x['buildSettings'] for x in settings if x.get('target')==scheme];need(len(product_settings)==1 and product_settings[0]['SWIFT_OPTIMIZATION_LEVEL']=='-O' and product_settings[0]['CONFIGURATION']=='Release','Release O')
  run(['xcodebuild','build-for-testing',*common],'build',300)
  runs=sorted((derived/'Build/Products').glob('*.xctestrun'));need(runs,'actual xctestrun missing')
  (folder/'xctestrun').mkdir()
  for path in runs:
   raw=path.read_bytes()
   for name in ('GH_TOKEN','GITHUB_TOKEN','ACTIONS_RUNTIME_TOKEN','ACTIONS_ID_TOKEN_REQUEST_TOKEN'):
    credential=os.environ.get(name);need(not credential or credential.encode() not in raw,'credential found in raw xctestrun; refuse to seal')
   shutil.copyfile(path,folder/'xctestrun'/path.name)
  app=derived/'Build/Products'/suffix/'EXReaderHost.app';expected=verify_program(app,platform)
  save(folder/'program-identity.json',{'runtime_probe_not_product_completion':True,'program_source_sha':identity()['source_sha'],'program_sha256':sha(cap.binary(app,platform)),'program_files':expected,'sdk_input_source_sha':cap.BASE,'destination':destination,'built_executable_url':str(cap.binary(app,platform).resolve())})
  shutil.copytree(app,folder/'program/EXReaderHost.app')
  bundle=folder/'reader.xcresult'
  run(['xcodebuild','test-without-building',*common,'-resultBundlePath',bundle,*['-only-testing:'+test_target+'/'+c for c in expected_cases(platform)]],'native',600,required=False)
  verify_program(app,platform,expected)
  if bundle.exists():
   objects,performance=extract_metrics(bundle,with_cases=True);save(folder/'xcresult-objects.json',objects);save(folder/'performance-cases.json',performance)
   statuses=load_results(bundle);save(folder/'test-cases.json',statuses)
   need_names={x.rsplit('/',1)[-1]+'()' for x in expected_cases(platform)}
   if {x['name'] for x in statuses}!=need_names or any(x['result']!='Passed' for x in statuses):report['problems'].append('requested native case set/status incomplete')
   run(['xcrun','xcresulttool','export','attachments','--path',bundle,'--output-path',folder/'attachments'],'attachments',60,required=False)
   obs=observations(folder);save(folder/'observations.json',obs)
   report['collection_complete']=not report['problems']
  else:report['problems'].append('reader xcresult bundle missing')
 except BaseException as e:
  report['problems'].append(repr(e));report['traceback']=traceback.format_exc()
 finally:
  try:run(['system_profiler','SPDisplaysDataType','-json'],'display-after',30,required=False)
  except BaseException as e:report['problems'].append('display-after '+repr(e))
  report['collection_complete']=not report['problems']
  report['main_elapsed_s']=time.monotonic()-started;report['total_deadline_budget_s']=PROFILE['native_collector_soft_limit_s'];cap.DEADLINE=None
  save(folder/'result.json',report);print('READER26_RESULT',json.dumps(report),flush=True)
 need(report['collection_complete'],'diagnosis incomplete; all observations retained')

def seal(platform):
 guard();folder=OUT/platform/'evidence';folder.mkdir(parents=True,exist_ok=True)
 result_path=folder/'result.json';result=json.loads(result_path.read_text()) if result_path.is_file() else None
 commands=result.get('commands',[]) if result else []
 unsafe=[c for c in commands if (pathlib.Path(c.get('argv',[''])[0]).name=='xcodebuild' or 'owned_group_observation_complete' in c) and c.get('owned_group_terminal_verified') is not True]
 if result is None or unsafe:
  save(OUT/platform/'control/UNSEALED.json',{**identity(),'kind':'unsealed-controller-receipt','diagnostic_only':True,'f08_accepted':False,
   'native_archive_sealed':False,'reason':'owned writer terminal state unverified' if unsafe else 'native terminal report missing',
   'collection_problems':result.get('problems',[]) if result else ['native terminal report missing'],
   'owned_group_records':[c for c in commands if 'owned_group_observation_complete' in c],'unverified_owned_group_records':unsafe})
  raise ValueError('owned writer terminal state unverified or terminal report missing; UNSEALED control only, refuse to seal or upload native directory')
 need(all(result.get(k)==v for k,v in identity().items()),'terminal report source differs')
 files=files_under(folder);files.pop('f08-manifest.json',None)
 save(folder/'f08-manifest.json',{**identity(),'kind':platform,'diagnostic_only':True,'f08_accepted':False,'files':files})


def short_metric(m):
 def value(v):return v.get("_value") if isinstance(v,dict) else v
 def number(v):
  raw=value(v)
  try:n=float(raw)
  except (ValueError,TypeError,OverflowError):return str(raw)
  return n if math.isfinite(n) else str(raw)
 return {"identifier":value(m.get("identifier")),"name":value(m.get("displayName")),"unit":value(m.get("unitOfMeasurement")),
  "values":[number(v) for v in m.get("measurements",{}).get("_values",[])]}
def metric_configurations(folder):
 rows=[]
 path=folder/'attachments/manifest.json'
 if not path.exists():return rows
 for case in json.loads(path.read_text()):
  for att in case.get('attachments',[]):
   if 'f08-native-metric-configuration' in att.get('suggestedHumanReadableName',''):
    rows.append({"case":case["testIdentifier"],"configuration":json.loads((folder/'attachments'/att['exportedFileName']).read_text())})
 return rows
def native_coverage(performance,configurations):
 rows=[]
 def finite(v):return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v)
 for expected in PROFILE["macos_cases"]:
  matches=[c for c in performance if c.get("identifier")==expected+"()"]
  case=matches[0] if len(matches)==1 else {"identifier":expected+"()","status":"missing"}
  metrics=[short_metric(m) for m in case.get("performance_metrics",[])]
  hitch=[m for m in metrics if "Hitch Time Ratio" in (m["name"] or "")]
  frames=[m for m in metrics if "Frame Count" in (m["name"] or "")]
  success=case.get("status")=="Success"
  positive=len(frames)==1 and frames[0]["unit"]=="frames" and len(frames[0]["values"])==5 and all(finite(x) and x>0 for x in frames[0]["values"])
  units=len(hitch)==1 and hitch[0]["unit"]=="ms per s"
  hitch_values=units and len(hitch[0]["values"])==5 and all(finite(x) and x>=0 for x in hitch[0]["values"])
  configured=any(r["case"]==case.get("identifier") and "XCTHitchMetric" in r["configuration"].get("configured_native_metric_types",[]) for r in configurations)
  rows.append({"case":case.get("identifier"),"status":case.get("status"),"metrics":metrics,"XCTHitchMetric_configured":configured,"native_positive_frames":positive,
   "native_hitch_unit_verified":units,"native_hitch_values_valid":hitch_values,"hitch_time_ratio_budget_ms_per_s":10,
   "hitch_budget_passed":bool(success and len(matches)==1 and configured and positive and hitch_values and all(x<=10 for x in hitch[0]["values"])),
   "missing":[name for name,ok in [("one successful native performance case",len(matches)==1 and success),("XCTHitchMetric actual configuration",configured),("five finite positive native frame values",positive),("native hitch ratio with verified units",units),("five finite nonnegative native hitch values",hitch_values)] if not ok]})
 return rows
def reader_runtime_bindings(obs,program):
 rows=[]
 for expected in PROFILE["macos_cases"]:
  found=[o for o in obs if o.get("kind")=="reader-window-preparation" and expected.rsplit("/",1)[-1] in o.get("test","")]
  if len(found)!=1:
   rows.append({"test":expected,"status":"missing","issues":[["missing","one actual reader Window preparation attachment required"]]});continue
  record=found[0]
  final=[e for e in record.get("events",[]) if e.get("phase")=="window-prepared"]
  if len(final)!=1:
   rows.append({"test":record.get("test"),"status":"missing","issues":[["missing","exact successful pre-measurement Window event absent"]]});continue
  event=final[0];runtime=event.get("runtime",{});row=runtime_row_identity(runtime,program.get("program_sha256"),identity()["source_sha"])
  if row["application_count"]!=1:row["issues"].append(("missing","runtime application identity is ambiguous"))
  for application in runtime.get("applications",[]):
   if not application.get("executable_url"):row["issues"].append(("missing","runtime executableURL absent"))
   elif application["executable_url"]!=program.get("built_executable_url"):row["issues"].append(("mismatch","runtime executableURL differs from exact built product"))
  if event.get("ax_window_count",0)<1:row["issues"].append(("missing","prepared app has no AX Window"))
  primary=[w for w in event.get("native_owned_windows",[]) if w.get("layer")==0 and w.get("owner_pid") in row["runtime_pids"] and w.get("bounds",{}).get("Width",0)>0 and w.get("bounds",{}).get("Height",0)>0]
  if not primary:row["issues"].append(("missing","no recorded positive-sized owned layer0 Window; menu layers do not qualify"))
  row.update({"test":record.get("test"),"status":binding_status(row["issues"]),"scope":"reader setup only; not launch09 or TTI"})
  rows.append(row)
 return rows
def audit():
 cap.DEADLINE=time.monotonic()+900
 out=ROOT/'build/f08-apple-reader26-audit';out.mkdir(parents=True,exist_ok=True)
 report={"authenticated":False,"diagnostic_only":True,"f08_accepted":False,"verified_stages":[],"missing":[],"errors":[],
  "native_coverage":native_coverage([],[]),"input_producer":{"source_sha":cap.BASE,"run_id":PROFILE["producer_run"],"attempt":PROFILE["producer_attempt"],"actual_sdk_job":PROFILE["producer_sdk_job"]}}
 try:
  report.update(identity());guard();report["verified_stages"].append("real diagnostic HEAD guard")
  prepare_inputs(out/'producer-inputs',out/'producer-input-metadata');report["verified_stages"].append("original producer inputs")
  producer=cap.api('actions/runs/'+identity()['run_id'])
  need(producer['head_sha']==identity()['source_sha'] and producer['run_attempt']==int(identity()['attempt']),'diagnostic producer source/attempt')
  report["verified_stages"].append("diagnostic producer source/attempt")
  name='f08-apple-reader26-macos-'+identity()['run_id']+'-'+identity()['attempt']
  metas=cap.api('actions/runs/'+identity()['run_id']+'/artifacts?per_page=100')['artifacts']
  candidates=[m for m in metas if m['name']==name and not m['expired']]
  if not candidates:
   report["missing"].append("diagnostic native archive")
   controls=[m for m in metas if m['name']=='f08-apple-reader26-unsealed-control-'+identity()['run_id']+'-'+identity()['attempt'] and not m['expired']]
   if len(controls)==1:
    control=controls[0];report["unsealed_control_artifact_id"]=control["id"]
    need(control['workflow_run']['head_sha']==identity()['source_sha'] and control['workflow_run']['id']==int(identity()['run_id']),'unsealed control producer')
    data=cap.archive_bytes(control);digest=hashlib.sha256(data).hexdigest()
    report.update({"unsealed_control_archive_sha256":digest,"unsealed_control_archive_bytes":len(data)})
    need(len(data)==control['size_in_bytes'] and control['digest']=='sha256:'+digest,'unsealed control ZIP identity')
    with cap.zipfile.ZipFile(cap.io.BytesIO(data)) as control_zip:
     need(control_zip.namelist()==['UNSEALED.json'] and control_zip.getinfo('UNSEALED.json').file_size<1024**2,'exact bounded unsealed control receipt')
     receipt=json.loads(control_zip.read('UNSEALED.json'))
    need(all(receipt.get(k)==v for k,v in identity().items()) and receipt.get('kind')=='unsealed-controller-receipt' and receipt.get('native_archive_sealed') is False and receipt.get('f08_accepted') is False,'unsealed controller receipt identity')
    report["unsealed_controller_receipt"]=receipt;report["verified_stages"].append("separate UNSEALED controller receipt")
   else:report["missing"].append("unique UNSEALED controller receipt")
  need(len(candidates)==1,'unique diagnostic archive')
  meta=candidates[0];report["artifact_id"]=meta["id"]
  need(meta['workflow_run']['head_sha']==identity()['source_sha'] and meta['workflow_run']['id']==int(identity()['run_id']),'diagnostic archive producer')
  report["verified_stages"].append("diagnostic archive producer")
  data=cap.archive_bytes(meta);digest=hashlib.sha256(data).hexdigest()
  report.update({"archive_sha256":digest,"archive_bytes":len(data)})
  need(len(data)==meta['size_in_bytes'] and meta['digest']=='sha256:'+digest,'diagnostic ZIP identity')
  report["verified_stages"].append("diagnostic ZIP outer identity")
  z,m=cap.validate_zip(data);report["verified_stages"].append("safe complete ZIP inventory and all payload hashes")
  need(all(m.get(k)==v for k,v in identity().items()) and m['kind']=='macos' and m['diagnostic_only'] is True and m['f08_accepted'] is False,'diagnostic manifest')
  report["verified_stages"].append("diagnostic manifest identity")
  folder=out/'raw';folder.mkdir()
  for n in m['files']:
   cap.remaining();p=folder/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(z.read(n))
  if not (folder/'result.json').is_file():report["missing"].append("native terminal result")
  result=json.loads((folder/'result.json').read_text())
  report.update({"collection_complete":result.get("collection_complete"),"problems":result.get("problems",[]),
   "main_elapsed_s":result.get("main_elapsed_s"),"main_budget_s":PROFILE["native_main_maximum_budget_s"]})
  need(all(result.get(k)==v for k,v in identity().items()),'diagnostic result source')
  need(all(c.get('owned_group_terminal_verified') is True for c in result.get('commands',[]) if pathlib.Path(c.get('argv',[''])[0]).name=='xcodebuild' or 'owned_group_observation_complete' in c),'sealed native archive has unverified owned writer terminal state')
  report["verified_stages"].append("native terminal result source and owned writer terminal states")
  program=None
  if (folder/'program-identity.json').exists():
   verify_configuration(folder,'macos');report["verified_stages"].append("original Release flags and schemes")
   program=json.loads((folder/'program-identity.json').read_text())
   expected=verify_program(folder/'program/EXReaderHost.app','macos')
   need(expected==program['program_files'] and sha(cap.binary(folder/'program/EXReaderHost.app','macos'))==program['program_sha256'],'complete diagnostic program bytes')
   need(program["sdk_input_source_sha"]==cap.BASE and program["program_source_sha"]==identity()["source_sha"],'separate real app and SDK producer sources')
   report["program_source_sha"]=program["program_source_sha"];report["program_sha256"]=program["program_sha256"]
   report["verified_stages"].append("complete actual diagnostic program and separate SDK source")
   need((folder/'ShelfUITests.swift').read_text()==driver_text(),'exact driver and unchanged reader bodies')
   need((folder/'profile.json').read_text()==json.dumps(PROFILE,indent=2,allow_nan=False)+'\n','declared profile')
   runs=list((folder/'xctestrun').glob('*.xctestrun'))
   if not runs:report["missing"].append("actual xctestrun")
   need(runs,'actual xctestrun missing')
   report["xctestrun"]=[{"name":p.name,"sha256":sha(p),"bytes":p.stat().st_size} for p in runs]
   report["verified_stages"].append("exact original bodies, declared profile and actual xctestrun")
  else:
   report["missing"].append("diagnostic program identity")
   need(not result["collection_complete"],'complete diagnostic lacks program')
  bundle=folder/'reader.xcresult'
  if bundle.exists():
   extract_metrics,load_results=cap.load_native_tools();_,performance=extract_metrics(bundle,with_cases=True);cases=load_results(bundle)
   report.update({"native_test_cases":cases,"native_performance_cases":performance})
   need(performance==json.loads((folder/'performance-cases.json').read_text()) and cases==json.loads((folder/'test-cases.json').read_text()),'independent native metrics and cases')
   report["verified_stages"].append("independent native metrics and cases")
   obs=observations(folder);report["observations"]=obs
   need(obs==json.loads((folder/'observations.json').read_text()),'actual native attachments')
   configs=metric_configurations(folder)
   report.update({"actual_metric_configurations":configs,"native_coverage":native_coverage(performance,configs)})
   if program:report["runtime_bindings"]=reader_runtime_bindings(obs,program)
   report["verified_stages"].append("actual native attachments and coverage assessment")
   if result["collection_complete"]:
    names={c.split("/")[-1] for c in PROFILE["macos_cases"]}
    need({c["name"] for c in cases}=={n+"()" for n in names} and all(c["result"]=="Passed" for c in cases),'complete original reader case set')
    sample_rows=[o for o in obs if "F08ReaderUITests" in o.get("test","") and "samples" in o]
    report["reader_observation_groups"]=[{"test":o.get("test"),"sample_count":len(o.get("samples",[]))} for o in sample_rows]
    need(len(sample_rows)==2 and all(len(o["samples"])==6 for o in sample_rows) and all(any(n in o["test"] for o in sample_rows) for n in names),'every original reader warmup and five measured observations')
    for record in sample_rows:
     for sample in record["samples"]:
      for value in sample.values():
       if isinstance(value,dict) and "source_sha" in value:need(value["source_sha"]==identity()["source_sha"],"raw reader snapshot source differs from real diagnostic program")
    bindings=report.get("runtime_bindings",[])
    report["runtime_identity_complete"]=len(bindings)==2 and all(r["status"]=="matched" for r in bindings) and all(any(n in r["test"] for r in bindings) for n in names)
  else:
   report["missing"].append("reader xcresult bundle")
   need(not result["collection_complete"],'complete result lacks reader xcresult')
  need(not result["collection_complete"] or report.get("runtime_identity_complete") is True,'complete reader result lacks matched setup executable identity; assessments retained')
  need(result.get("main_elapsed_s",0)<=PROFILE["native_main_maximum_budget_s"],'native main budget exceeded; raw retained')
  report["verified_stages"].append("complete-result identity and native main budget")
  report["authenticated"]=True
 except BaseException as e:
  report["errors"].append(repr(e));report["traceback"]=traceback.format_exc()
  if isinstance(e,FileNotFoundError):report["missing"].append(str(e.filename))
  raise
 finally:
  cap.DEADLINE=None;save(out/'report.json',report)
  print('READER26_AUDIT',json.dumps(report),flush=True)


if __name__=="__main__":
 parser=argparse.ArgumentParser();parser.add_argument("mode",choices=("guard","native","seal","audit"));parser.add_argument("--platform",choices=("macos",),default="macos");args=parser.parse_args()
 if args.mode=="guard":guard()
 elif args.mode=="native":native(args.platform)
 elif args.mode=="seal":seal(args.platform)
 else:audit()
