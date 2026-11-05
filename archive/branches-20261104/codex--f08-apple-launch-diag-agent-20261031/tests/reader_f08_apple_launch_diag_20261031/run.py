"""Bounded diagnosis of the unchanged native launch endpoint, with independent byte/event audit."""
import argparse, hashlib, importlib.util, json, os, pathlib, plistlib, shutil, signal, subprocess, time, traceback
import xml.etree.ElementTree as ET
ROOT=pathlib.Path(__file__).resolve().parents[2]
HERE=pathlib.Path(__file__).resolve().parent
PROFILE=json.loads((HERE/'profile.json').read_text())
BASE=PROFILE['source_base']
ALLOWED={'examples/apple/HostModel.swift','.github/workflows/dot-f08-apple-launch-diag-20261031.yml',
 'tests/reader_f08_apple_launch_diag_20261031/profile.json','tests/reader_f08_apple_launch_diag_20261031/run.py'}
spec=importlib.util.spec_from_file_location('original_capability_helpers',ROOT/'tests/reader_f08_apple_cap26_20261031/run.py')
cap=importlib.util.module_from_spec(spec);spec.loader.exec_module(cap)
need,save,sha,command,identity=cap.need,cap.save,cap.sha,cap.command,cap.identity
OUT=ROOT/'build/f08-apple-launch-diag'
def guard():
 need(os.environ.get('GITHUB_ACTIONS')=='true','Actions only')
 need(command(['git','rev-parse','HEAD'],text=True).strip()==identity()['source_sha'],'head identity')
 command(['git','merge-base','--is-ancestor',BASE,'HEAD'])
 need(set(command(['git','diff','--name-only',BASE,'HEAD'],text=True).splitlines())==ALLOWED,'minimal launch observation source scope')
RUNTIME=r'''
private func f08RuntimeBindingData(_ app: XCUIApplication, _ reason: String) -> [String: Any] {
    var value: [String: Any] = ["kind": "runtime-binding", "reason": reason,
        "uptime_s": ProcessInfo.processInfo.systemUptime, "declared_launch_arguments": app.launchArguments,
        "declared_launch_environment": app.launchEnvironment.filter { ["ApplePersistenceIgnoreState", "NSQuitAlwaysKeepsWindows", "AppleLanguages", "AppleLocale"].contains($0.key) }]
#if os(macOS)
    let applications = NSRunningApplication.runningApplications(withBundleIdentifier: "org.exreader.host")
    value["provider"] = "NSWorkspace NSRunningApplication; executable bytes read after measurement stop or on an already failed launch"
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
        let process = Process(), output = Pipe(), errors = Pipe()
        process.executableURL = URL(fileURLWithPath: "/bin/ps")
        process.arguments = ["-ww", "-p", String(application.processIdentifier), "-o", "command="]
        process.standardOutput = output; process.standardError = errors
        do {
            try process.run()
            let deadline = Date().addingTimeInterval(2)
            while process.isRunning && Date() < deadline { RunLoop.current.run(until: Date().addingTimeInterval(0.01)) }
            let timedOut = process.isRunning
            if process.isRunning { process.terminate() }
            if process.isRunning { kill(process.processIdentifier, SIGKILL) }
            process.waitUntilExit()
            let words = String(decoding: output.fileHandleForReading.readDataToEndOfFile(), as: UTF8.self)
                .split(whereSeparator: { $0.isWhitespace }).map(String.init)
            let flags: Set<String> = ["-EXRShelfSeed", "-EXRFreshState", "-EXRF08Launch", "-EXRF08PhaseOnly",
                "-EXRUITestFixtures", "-NSQuitAlwaysKeepsWindows", "-ApplePersistenceIgnoreState",
                "-NSDocumentRevisionsDebugMode", "-AppleLanguages", "-AppleLocale"]
            var allowed: [String] = []
            for (index, word) in words.enumerated() where flags.contains(word) {
                allowed.append(word)
                if index + 1 < words.count {
                    let next = words[index + 1]
                    let publicValues = ["0", "1", "YES", "NO", "true", "false"]
                    if publicValues.contains(next) || (["-AppleLanguages", "-AppleLocale"].contains(word) && next.count < 128 &&
                        next.unicodeScalars.allSatisfy({ CharacterSet(charactersIn: "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-(),\"").contains($0) })) { allowed.append(next) }
                }
            }
            item["allowed_actual_argv"] = allowed
            item["argv_probe_returncode"] = process.terminationStatus; item["argv_probe_timed_out"] = timedOut
        } catch { item["argv_probe_error"] = String(describing: error) }
        return item
    }
#else
    value["provider"] = "declared guest arguments; native shelf phases retain guest PID; sealed program and xctestrun retain the executable target; no NSWorkspace in Simulator guest"
#endif
    return value
}
private func f08AttachRuntimeBinding(_ test: XCTestCase, _ app: XCUIApplication, _ reason: String,
    nativeShelf: [String: Any]? = nil, launchRequestUptime: Double? = nil) {
    var value = f08RuntimeBindingData(app, reason)
    value["test_name"] = test.name
    if let nativeShelf {
        let phases = nativeShelf["f08_launch_phases"] as? [[String: Any]] ?? []
        value["sample_native_phase_pids"] = Array(Set(phases.compactMap { ($0["pid"] as? NSNumber)?.intValue })).sorted()
    }
    if let launchRequestUptime { value["sample_launch_request_uptime_s"] = launchRequestUptime }
    guard let data = try? JSONSerialization.data(withJSONObject: value, options: [.sortedKeys]) else { return }
    let attachment = XCTAttachment(string: String(decoding: data, as: UTF8.self))
    attachment.name = "f08-runtime-binding"; attachment.lifetime = .keepAlways; test.add(attachment)
}
#if os(macOS)
final class F08WindowSceneControlUITests: XCTestCase {
    func test01ExplicitFileNewWindowCapability() throws {
        continueAfterFailure = true
        let app = XCUIApplication()
        app.launchArguments = ["-EXRShelfSeed", "-EXRFreshState", "1", "-EXRF08Launch"]
        var events: [[String: Any]] = []
        func record(_ phase: String) {
            let pids = Set(NSRunningApplication.runningApplications(withBundleIdentifier: "org.exreader.host").map(\.processIdentifier))
            let windows = (CGWindowListCopyWindowInfo([.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID) as? [[String: Any]] ?? [])
                .filter { row in (row[kCGWindowOwnerPID as String] as? NSNumber).map { pids.contains($0.int32Value) } == true }
                .map { row -> [String: Any] in ["owner_pid": row[kCGWindowOwnerPID as String] ?? -1,
                    "layer": row[kCGWindowLayer as String] ?? -1, "bounds": row[kCGWindowBounds as String] ?? [:],
                    "window_number": row[kCGWindowNumber as String] ?? -1] }
            func restoreKeys(_ values: [String: Any]) -> [String: Any] {
                values.filter { ["NSQuitAlwaysKeepsWindows", "ApplePersistenceIgnoreState"].contains($0.key) || $0.key.hasPrefix("NSWindow Frame") }
            }
            let productPreferences = restoreKeys(UserDefaults.standard.persistentDomain(forName: "org.exreader.host") ?? [:])
            let globalPreferences = restoreKeys(UserDefaults.standard.persistentDomain(forName: UserDefaults.globalDomain) ?? [:])
            events.append(["phase": phase, "uptime_s": ProcessInfo.processInfo.systemUptime,
                "runtime": f08RuntimeBindingData(app, phase), "native_owned_windows": windows,
                "ax_window_count": app.windows.count, "product_persistent_restore_preferences": productPreferences,
                "global_persistent_restore_preferences": globalPreferences,
                "search_exists": app.descendants(matching: .any).matching(identifier: "library.search").firstMatch.exists])
        }
        defer {
            record("final")
            let value: [String: Any] = ["kind": "window-scene-control", "events": events,
                "meaning": "Actual standard File > New Window capability only. All times remain separate from launch09 and TTI."]
            if let data = try? JSONSerialization.data(withJSONObject: value, options: [.sortedKeys]) {
                let attachment = XCTAttachment(string: String(decoding: data, as: UTF8.self))
                attachment.name = "f08-window-scene-control"; attachment.lifetime = .keepAlways; add(attachment)
            }
            app.terminate()
        }
        app.launch()
        record("launched-before-any-menu-action")
        if !app.windows.firstMatch.exists {
            let file = app.menuBars.menuBarItems["File"], newWindow = app.menuItems["New Window"]
            XCTAssertTrue(file.exists && file.isEnabled)
            file.click()
            XCTAssertTrue(newWindow.exists && newWindow.isEnabled)
            record("before-explicit-new-window")
            newWindow.click()
            XCTAssertTrue(app.windows.firstMatch.waitForExistence(timeout: 10))
            record("after-explicit-new-window")
        } else { record("window-already-present-no-menu-action") }
        let search = app.descendants(matching: .any).matching(identifier: "library.search").firstMatch
        XCTAssertTrue(search.waitForExistence(timeout: 20))
        if search.exists { XCTAssertTrue(search.isEnabled && search.isHittable) }
    }
}
#endif
'''
def driver_text():
 original=(ROOT/'tests/apple_host/shelf/ui/ShelfUITests.swift').read_text()
 insertion=(ROOT/'tests/reader_f08_apple_20261031/Metrics.swift').read_text()
 inside,marker,standalone=insertion.partition('// F08_STANDALONE_CLASSES');need(marker,'original class split')
 at=original.rfind('}');need(at>0,'original class end')
 needle='            stopMeasuring()\n            let phases = value["f08_launch_phases"]'
 need(standalone.count(needle)==1,'post-stop runtime binding boundary')
 standalone=standalone.replace(needle,'            stopMeasuring()\n            f08AttachRuntimeBinding(self, app, "after-measurement-stop", nativeShelf: value, launchRequestUptime: requestUptime)\n            let phases = value["f08_launch_phases"]')
 needle='        XCTFail("Native shelf launch task did not finish:'
 need(standalone.count(needle)==1,'failed-launch runtime binding boundary')
 standalone=standalone.replace(needle,'        f08AttachRuntimeBinding(self, app, "already-failed-native-ready-timeout")\n'+needle)
 return 'import CryptoKit\nimport Darwin\nimport CoreGraphics\n'+original[:at]+inside+original[at:]+standalone+cap.FONT+RUNTIME
def files_under(folder):
 return {p.relative_to(folder).as_posix():{'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(folder.rglob('*')) if p.is_file()}
def prepare_inputs(folder,metadata_folder):
 result={}
 producer=cap.api('actions/runs/'+str(cap.PROFILE['producer_run']))
 need(producer['head_sha']==cap.BASE and producer['run_attempt']==cap.PROFILE['producer_attempt'],'original input producer')
 for row in cap.PROFILE['inputs']:
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
  result['resources' if resource_input else row['kind']]={'root':dest,'manifest':manifest}
  save(metadata_folder/(row['kind']+'.json'),{'metadata':meta,'zip_sha256':digest,'zip_bytes':len(data),'original_manifest':manifest,'extraction_prefix':prefix if resource_input else 'sdk/raw-products/identity JSON only','extracted_files':expected})
 need(not list(folder.rglob('*.app')),'extra same-bundle-ID input apps forbidden')
 return result
def process_group_snapshot(group):
 result={'group':group,'members':[]}
 try:
  p=subprocess.run(['/bin/ps','-axo','pid=,ppid=,pgid=,stat=,comm='],capture_output=True,text=True,timeout=5)
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
   if not any(tag in label for tag in ('f08-launch-observations','f08-reader-observations','f08-runtime-binding','f08-window-scene-control')):continue
   rows.append(json.loads((folder/'attachments'/att['exportedFileName']).read_text()))
 return rows
def launch_events(sample):
 phases=sample.get('shelf',{}).get('f08_launch_phases',[])
 predicate=[p for p in phases if p.get('phase') in ('native-ready-predicate-observed','native-ready-observer-fired') and p.get('full_native_ready_predicate') is True]
 confirmed=next((p for p in phases if p.get('phase')=='native-layout-ready'),None)
 report={'first_observed_true_native_predicate_uptime_s':predicate[0]['uptime_s'] if predicate else None,
  'confirmed_uptime_s':confirmed['uptime_s'] if confirmed else None,
  'launch_request_uptime_s':sample.get('launch_request_uptime_s'),
  'confirmed_request_upper_bound_ms':sample.get('native_layout_ready_from_launch_request_upper_bound_ms'),
  'meaning':'Observed native-layout predicate and confirmation; no earlier user-input TTI or native/physical completion is inferred.'}
 if predicate and sample.get('launch_request_uptime_s') is not None:report['first_observed_native_predicate_request_upper_bound_ms']=(predicate[0]['uptime_s']-sample['launch_request_uptime_s'])*1000
 if not confirmed:return report
 arm_id=confirmed.get('observer_arm_id');revision=confirmed.get('signature_revision')
 arm=next((p for p in phases if p.get('phase')=='native-ready-observer-armed' and p.get('observer_arm_id')==arm_id),None)
 fired=next((p for p in phases if p.get('phase')=='native-ready-observer-fired' and p.get('observer_arm_id')==arm_id and p.get('full_native_ready_predicate') is True),None)
 origin=next((p for p in phases if p.get('phase')=='native-ready-predicate-observed' and p.get('signature_revision')==revision and p.get('signature_changed') is True),None)
 report.update({'confirmed_observer_arm_id':arm_id,'confirmed_signature_revision':revision,
  'final_confirmed_signature_first_observed_uptime_s':origin['uptime_s'] if origin else None,
  'confirmed_arm':arm,'confirmed_timer_fired':fired,
  'signature_changes':[p for p in phases if p.get('phase')=='native-ready-predicate-observed' and p.get('signature_changed') is True],
  'predicate_observations':[p for p in phases if p.get('phase')=='native-ready-predicate-observed']})
 if origin:report['final_observed_signature_to_confirm_ms']=(confirmed['uptime_s']-origin['uptime_s'])*1000
 if origin and sample.get('launch_request_uptime_s') is not None:report['final_confirmed_signature_origin_request_upper_bound_ms']=(origin['uptime_s']-sample['launch_request_uptime_s'])*1000
 if arm and fired:report['dispatch_due_to_fire_lateness_ms']=(fired['fired_dispatch_uptime_ns']-arm['due_dispatch_uptime_ns'])/1e6
 return report
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
def native_sample_pids(sample):
 shelf=sample.get('shelf');phases=shelf.get('f08_launch_phases',[]) if isinstance(shelf,dict) else []
 if not isinstance(phases,list) or not phases or any(not isinstance(p,dict) or not isinstance(p.get('pid'),int) or isinstance(p.get('pid'),bool) or p['pid']<=0 for p in phases):return []
 return sorted({p['pid'] for p in phases})
def runtime_binding_report(launch_observations,control_observations,expected_sha,expected_source):
 samples=[{'test_name':o['test'],'sample_index':index,'sample':sample}
  for o in launch_observations if 'F08LaunchUITests' in o.get('test','')
  for index,sample in enumerate(o.get('samples',[]))]
 rows=[o for o in launch_observations if o.get('kind')=='runtime-binding']
 assessments=[];sample_rows={i:[] for i in range(len(samples))}
 for index,row in enumerate(rows):
  item=runtime_row_identity(row,expected_sha,expected_source)
  item.update({'row_index':index,'reason':row.get('reason'),'test_name':row.get('test_name'),
   'sample_launch_request_uptime_s':row.get('sample_launch_request_uptime_s')})
  if row.get('reason')=='after-measurement-stop':
   item['scope']='measurement-after-stop'
   request=row.get('sample_launch_request_uptime_s')
   matches=[i for i,s in enumerate(samples) if isinstance(request,(int,float)) and not isinstance(request,bool)
    and s['test_name']==row.get('test_name') and s['sample'].get('launch_request_uptime_s')==request]
   if not matches:item['issues'].append(('missing','no native sample with the same test and launch request'))
   elif len(matches)!=1:item['issues'].append(('mismatch','test and launch request identify multiple native samples'))
   else:
    sample_index=matches[0];sample=samples[sample_index];sample_rows[sample_index].append(index)
    pids=native_sample_pids(sample['sample'])
    item.update({'native_sample_record':sample_index,'sample_index':sample['sample_index'],'native_phase_pids':pids})
    if len(pids)!=1:item['issues'].append(('missing','native sample does not identify one process'))
    captured=row.get('sample_native_phase_pids')
    if not isinstance(captured,list) or not captured or any(not isinstance(pid,int) or isinstance(pid,bool) or pid<=0 for pid in captured):item['issues'].append(('missing','runtime row lacks captured native phase PID'))
    elif len(pids)==1 and captured!=pids:item['issues'].append(('mismatch','captured phase PID does not match the native sample'))
    if len(pids)==1 and item['runtime_pids'] and item['runtime_pids']!=pids:item['issues'].append(('mismatch','NSWorkspace PID does not match the native sample'))
  else:
   item['scope']='failed-launch-identity-only'
   item['measurement_sample_binding']='missing; this row cannot satisfy a measured sample'
  item['status']=binding_status(item['issues']);assessments.append(item)
 sample_assessments=[]
 for index,entry in enumerate(samples):
  indices=sample_rows[index];issues=[]
  if not indices:issues.append(('missing','native sample has no after-stop runtime row'))
  elif len(indices)!=1:issues.append(('mismatch','native sample has multiple after-stop runtime rows'))
  else:issues.extend(assessments[indices[0]]['issues'])
  sample_assessments.append({'native_sample_record':index,'test_name':entry['test_name'],'sample_index':entry['sample_index'],
   'launch_request_uptime_s':entry['sample'].get('launch_request_uptime_s'),'runtime_row_indices':indices,
   'status':binding_status(issues),'issues':issues})
 controls=[]
 for observation in control_observations:
  if observation.get('kind')=='runtime-binding':controls.append(observation)
  if observation.get('kind')=='window-scene-control':
   controls.extend(e['runtime'] for e in observation.get('events',[]) if isinstance(e.get('runtime'),dict))
 control_assessments=[]
 for index,row in enumerate(controls):
  item=runtime_row_identity(row,expected_sha,expected_source)
  item.update({'row_index':index,'scope':'control-identity-only','status':binding_status(item['issues'])})
  control_assessments.append(item)
 required=[a for a in assessments if a['scope']=='measurement-after-stop']
 expected_count=PROFILE['measured_iterations']+(1 if PROFILE['default_warmup_retained'] else 0)
 issues=[issue for row in required+sample_assessments for issue in row['issues']]
 if len(samples)!=expected_count or len(required)!=expected_count:issues.append(('missing','required measured/warmup sample or after-stop runtime row count incomplete'))
 return {'runtime_bindings':rows,'runtime_binding_rows':assessments,'runtime_measurement_samples':sample_assessments,
  'runtime_expected_sample_count':expected_count,'control_runtime_bindings':controls,'control_runtime_binding_rows':control_assessments,
  'runtime_program_binding':binding_status(issues),'runtime_measurement_binding_issues':issues}
def expected_cases(platform):
 return [PROFILE['launch_case']]
def native(platform):
 guard();folder=OUT/platform/'evidence';folder.mkdir(parents=True)
 cap.EVIDENCE=folder
 report={**identity(),'platform':platform,'diagnostic_only':True,'f08_accepted':False,'collection_complete':False,'commands':[],'problems':[]}
 deadline=time.monotonic()+PROFILE['native_collector_soft_limit_s'];device=None
 def run(args,role,timeout=180,required=True,separate_streams=False):
  args=list(map(str,args));timeout=min(timeout,max(1,deadline-time.monotonic()))
  print('LAUNCH_DIAG_PHASE',platform,role,flush=True)
  log=folder/(role+('.stdout.json' if separate_streams else '.log'))
  error_log=folder/(role+'.stderr.log');timed=False;signals=[];started=time.monotonic()
  env=os.environ.copy()
  removed=[]
  if args[0]=='xcodebuild':
   for name in ('GH_TOKEN','GITHUB_TOKEN','ACTIONS_RUNTIME_TOKEN','ACTIONS_ID_TOKEN_REQUEST_TOKEN'):
    if name in env:removed.append(name);env.pop(name)
  with log.open('wb') as f,error_log.open('wb') as e:
   proc=subprocess.Popen(args,cwd=ROOT,stdout=f,stderr=e if separate_streams else subprocess.STDOUT,start_new_session=True,env=env)
   group=proc.pid
   try:proc.wait(timeout=timeout)
   except subprocess.TimeoutExpired:
    timed=True
    for sig,grace in ((signal.SIGINT,20),(signal.SIGTERM,10),(signal.SIGKILL,5)):
     try:os.killpg(group,sig);signals.append({'signal':int(sig),'uptime_s':time.monotonic()})
     except ProcessLookupError:break
     try:proc.wait(timeout=grace)
     except subprocess.TimeoutExpired:continue
     break
    if proc.returncode is None:proc.wait(timeout=5)
   group_before=None;group_after=None
   if separate_streams:
    group_before=process_group_snapshot(group)
    if group_has_live_members(group_before):
     for sig,grace in ((signal.SIGTERM,2),(signal.SIGKILL,1)):
      try:os.killpg(group,sig);signals.append({'signal':int(sig),'uptime_s':time.monotonic(),'reason':'owned settings descendants after direct process exit'})
      except ProcessLookupError:break
      limit=time.monotonic()+grace
      while time.monotonic()<limit and group_has_live_members(process_group_snapshot(group)):time.sleep(0.05)
      if not group_has_live_members(process_group_snapshot(group)):break
    group_after=process_group_snapshot(group)
  record={'role':role,'argv':args,'returncode':proc.returncode,'timed_out':timed,'collector_limit_s':timeout,
   'pid':proc.pid,'owned_process_group':group,'direct_process_reaped':proc.poll() is not None,
   'started_uptime_s':started,'finished_uptime_s':time.monotonic(),'signals_sent':signals,
   'stdout_file':log.name,'stderr_file':error_log.name if separate_streams else 'combined in stdout_file',
   'environment_credentials_removed_by_name':removed}
  if separate_streams:
   observed=all(x.get('probe_returncode')==0 and 'probe_error' not in x for x in (group_before,group_after))
   record.update({'owned_group_before_cleanup':group_before,'owned_group_after_cleanup':group_after,'owned_group_observation_complete':observed})
  report['commands'].append(record)
  if separate_streams and not record['owned_group_observation_complete']:
   report['problems'].append(role+' owned process group terminal state unobserved')
   if required:raise RuntimeError(role+' process-group observation missing; raw streams and direct process state retained')
  if separate_streams and group_has_live_members(group_after):
   report['problems'].append(role+' owned process group retains live members')
   if required:raise RuntimeError(role+' owned process group still live after cleanup; stop before compilation or sampling')
   return False
  if timed or proc.returncode:
   report['problems'].append(role+(' collection timeout' if timed else ' exit '+str(proc.returncode)))
   print('\n'.join(log.read_text(errors='replace').splitlines()[-35:]),flush=True)
   if separate_streams:print('\n'.join(error_log.read_text(errors='replace').splitlines()[-35:]),flush=True)
   if required:raise RuntimeError(role+' failed; raw streams and known process state retained')
   return False
  return True
 try:
  save(folder/'profile.json',PROFILE)
  xcode=command(['xcodebuild','-version'],text=True);os_version=command(['sw_vers'],text=True)
  need(xcode==PROFILE['environment']['default_xcode'] and int(command(['sw_vers','-productVersion'],text=True).split('.')[0])==15,'original default toolchain/host')
  save(folder/'environment.json',{'xcode':xcode,'os':os_version,'developer_dir':os.environ.get('DEVELOPER_DIR'),'runner_image':os.environ.get('ImageVersion'),'arch':command(['uname','-m'],text=True)})
  run(['system_profiler','SPDisplaysDataType','-json'],'display-before',30)
  installed=prepare_inputs(OUT/platform/'input',folder/'inputs')
  resources=installed['resources']['root']
  seed=json.loads((resources/'shelf-seed.json').read_text());need(seed['books']==2202 and len(set(seed['source_keys']))==2202,'frozen actual2202')
  shutil.copyfile(resources/'shelf-seed.json',folder/'shelf-seed.json')
  extract_metrics,load_results=cap.load_native_tools()
  tests=OUT/platform/'driver/shelf/ui';tests.mkdir(parents=True)
  driver=tests/'ShelfUITests.swift';driver.write_text(driver_text());shutil.copyfile(driver,folder/'ShelfUITests.swift')
  save(folder/'driver.json',{'candidate_sha256':sha(driver),'original_bodies_unchanged':True,'original_metrics_file_unchanged':True,'measurement_region_and_native_endpoint_unchanged':True,'generated_helper_runtime_probe_after_stop_and_on_failure':True,'font_body_sha256':hashlib.sha256(cap.FONT.encode()).hexdigest()})
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
  if platform=='macos':
   target='macos';destination='platform=macOS';scheme='EXReaderHost-macOS';test_target='EXReaderHostUITests-macOS';suffix='Release';signing='YES'
  else:
   target='iphonesimulator';choices=json.loads(command(['xcrun','simctl','list','devices','available','--json']));save(folder/'device-inventory.json',choices)
   prefix='iPhone' if platform=='iphone' else 'iPad'
   runtime,name,device=max((rt,d['name'],d['udid']) for rt,items in choices['devices'].items() for d in items if d.get('isAvailable') and d['name'].startswith(prefix))
   need(runtime==PROFILE['environment']['expected_runtime'] and name==PROFILE['environment']['expected_'+platform],'original matching simulator cohort')
   (folder/'destination.txt').write_text('\n'.join((runtime,name,device))+'\n')
   subprocess.run(['xcrun','simctl','shutdown',device],capture_output=True,timeout=30)
   destination='platform=iOS Simulator,id='+device;scheme='EXReaderHost-iOS';test_target='EXReaderHostUITests-iOS';suffix='Release-iphonesimulator';signing='NO'
  sdk=installed[target+'-sdk']['root'];derived=OUT/platform/'derived'
  build=['-project',project/'EXReaderHost.xcodeproj','-scheme',scheme,'-destination',destination,'-derivedDataPath',derived,'-configuration','Release','EXR_SDK_DIR='+str(sdk/'sdk'),'EXR_PRODUCTS_DIR='+str(sdk/'raw-products'),'CODE_SIGNING_ALLOWED='+signing,'SWIFT_OPTIMIZATION_LEVEL=-O','GCC_OPTIMIZATION_LEVEL=s','ONLY_ACTIVE_ARCH=YES']
  common=[*build,'-enableCodeCoverage','NO','-enableAddressSanitizer','NO','-enableThreadSanitizer','NO','-enableUndefinedBehaviorSanitizer','NO','-parallel-testing-enabled','NO','-test-timeouts-enabled','YES','-default-test-execution-time-allowance','240','-maximum-test-execution-time-allowance','240']
  run(['xcodebuild','-showBuildSettings','-json',*build],'show-build-settings',120,separate_streams=True)
  settings=json.loads((folder/'show-build-settings.stdout.json').read_text());save(folder/'build-settings.json',settings)
  product_settings=[x['buildSettings'] for x in settings if x.get('target')==scheme];need(len(product_settings)==1 and product_settings[0]['SWIFT_OPTIMIZATION_LEVEL']=='-O' and product_settings[0]['CONFIGURATION']=='Release','Release O')
  if device:
   run(['xcrun','simctl','erase',device],'erase',45);run(['xcrun','simctl','boot',device],'boot',30);run(['xcrun','simctl','bootstatus',device,'-b'],'boot-ready',180)
  run(['xcodebuild','build-for-testing',*common],'build',300)
  runs=sorted((derived/'Build/Products').glob('*.xctestrun'));need(runs,'actual xctestrun missing')
  (folder/'xctestrun').mkdir()
  for path in runs:
   raw=path.read_bytes()
   for name in ('GH_TOKEN','GITHUB_TOKEN','ACTIONS_RUNTIME_TOKEN','ACTIONS_ID_TOKEN_REQUEST_TOKEN'):
    credential=os.environ.get(name);need(not credential or credential.encode() not in raw,'credential found in raw xctestrun; refuse to seal')
   shutil.copyfile(path,folder/'xctestrun'/path.name)
  app=derived/'Build/Products'/suffix/'EXReaderHost.app';expected=verify_program(app,platform)
  save(folder/'program-identity.json',{'runtime_probe_not_product_completion':True,'program_source_sha':identity()['source_sha'],'program_sha256':sha(cap.binary(app,platform)),'program_files':expected,'sdk_input_source_sha':cap.BASE,'destination':destination})
  shutil.copytree(app,folder/'program/EXReaderHost.app')
  bundle=folder/'launch.xcresult'
  run(['xcodebuild','test-without-building',*common,'-resultBundlePath',bundle,*['-only-testing:'+test_target+'/'+c for c in expected_cases(platform)]],'native',600,required=False)
  verify_program(app,platform,expected)
  if bundle.exists():
   objects,performance=extract_metrics(bundle,with_cases=True);save(folder/'xcresult-objects.json',objects);save(folder/'performance-cases.json',performance)
   statuses=load_results(bundle);save(folder/'test-cases.json',statuses)
   need_names={x.rsplit('/',1)[-1]+'()' for x in expected_cases(platform)}
   if {x['name'] for x in statuses}!=need_names or any(x['result']!='Passed' for x in statuses):report['problems'].append('requested native case set/status incomplete')
   run(['xcrun','xcresulttool','export','attachments','--path',bundle,'--output-path',folder/'attachments'],'attachments',60,required=False)
   obs=observations(folder);save(folder/'observations.json',obs)
   save(folder/'launch-events.json',[{'test':o['test'],'samples':[launch_events(s) for s in o['samples']]} for o in obs if 'Launch' in o.get('test','')])
  if platform=='macos':
   if time.monotonic()<deadline-45:
    control=folder/'window-control';control.mkdir()
    control_bundle=control/'scene.xcresult'
    run(['xcodebuild','test-without-building',*common,'-resultBundlePath',control_bundle,
     '-only-testing:'+test_target+'/F08WindowSceneControlUITests/test01ExplicitFileNewWindowCapability'],'window-scene-control',180,required=False)
    verify_program(app,platform,expected)
    if control_bundle.exists():
     control_objects,control_performance=extract_metrics(control_bundle,with_cases=True)
     save(control/'xcresult-objects.json',control_objects);save(control/'performance-cases.json',control_performance)
     save(control/'test-cases.json',load_results(control_bundle))
     run(['xcrun','xcresulttool','export','attachments','--path',control_bundle,'--output-path',control/'attachments'],'window-control-attachments',60,required=False)
     save(control/'observations.json',observations(control))
   else:report['problems'].append('separate window capability not run: collector deadline')
  report['collection_complete']=not report['problems']
 except BaseException as e:
  report['problems'].append(repr(e));report['traceback']=traceback.format_exc()
 finally:
  if device:
   try:run(['xcrun','simctl','shutdown',device],'shutdown',30,required=False)
   except BaseException as e:report['problems'].append('shutdown '+repr(e))
  try:run(['system_profiler','SPDisplaysDataType','-json'],'display-after',30,required=False)
  except BaseException as e:report['problems'].append('display-after '+repr(e))
  report['collection_complete']=not report['problems']
  save(folder/'result.json',report);print('LAUNCH_DIAG_RESULT',json.dumps(report),flush=True)
 need(report['collection_complete'],'diagnosis incomplete; all observations retained')
def seal(platform):
 guard();folder=OUT/platform/'evidence';folder.mkdir(parents=True,exist_ok=True)
 files=files_under(folder);files.pop('f08-manifest.json',None)
 save(folder/'f08-manifest.json',{**identity(),'kind':platform,'diagnostic_only':True,'f08_accepted':False,'files':files})
def audit():
 guard();out=ROOT/'build/f08-apple-launch-diag-audit';out.mkdir(parents=True,exist_ok=True);cap.EVIDENCE=out
 prepare_inputs(out/'original-inputs',out/'original-input-metadata')
 report={**identity(),'authenticated':False,'diagnostic_only':True,'f08_accepted':False,'targets':{}}
 runtime_binding_violations=[]
 producer=cap.api('actions/runs/'+identity()['run_id']);need(producer['head_sha']==identity()['source_sha'],'native producer head')
 metas=cap.api('actions/runs/'+identity()['run_id']+'/artifacts')['artifacts'];extract_metrics,load_results=cap.load_native_tools()
 for platform in PROFILE['targets']:
  name='f08-apple-launch-diag-'+platform+'-'+identity()['run_id']+'-'+identity()['attempt']
  candidates=[x for x in metas if x['name']==name and not x['expired']];need(len(candidates)==1,'native archive '+platform);meta=candidates[0]
  need(meta['workflow_run']['head_sha']==identity()['source_sha'] and meta['workflow_run']['id']==int(identity()['run_id']),'artifact source/run')
  data=cap.archive_bytes(meta);digest=hashlib.sha256(data).hexdigest();need(len(data)==meta['size_in_bytes'] and meta['digest']=='sha256:'+digest,'native ZIP identity')
  z,m=cap.validate_zip(data);need(all(m.get(k)==v for k,v in identity().items()) and m['kind']==platform,'native manifest identity')
  folder=out/platform;folder.mkdir()
  for n in m['files']:
   p=folder/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(z.read(n))
  result=json.loads((folder/'result.json').read_text());need(all(result.get(k)==v for k,v in identity().items()),'native result identity')
  target={'artifact_id':meta['id'],'archive_sha256':digest,'archive_bytes':len(data),'collection_complete':result['collection_complete'],'problems':result['problems']}
  if (folder/'program-identity.json').exists():
   verify_configuration(folder,platform)
   program=json.loads((folder/'program-identity.json').read_text());expected=verify_program(folder/'program/EXReaderHost.app',platform)
   need(expected==program['program_files'] and sha(cap.binary(folder/'program/EXReaderHost.app',platform))==program['program_sha256'],'new complete program')
   need((folder/'ShelfUITests.swift').read_text()==driver_text(),'actual driver bytes')
   target['program_sha256']=program['program_sha256'];target['program_source_sha']=program['program_source_sha']
   runs=list((folder/'xctestrun').glob('*.xctestrun'));need(runs,'sealed actual xctestrun missing')
   target['xctestrun_files']=[]
   for path in runs:
    tree=plistlib.loads(path.read_bytes())
    entries=[]
    def visit(value):
     if isinstance(value,dict):
      selected={k:v for k,v in value.items() if k in ('TargetName','TestTargetName','UITargetAppPath','UITargetAppBundleIdentifier','TargetApplicationBundleID','TestBundlePath','TestHostPath','IsUITestBundle') and isinstance(v,(str,bool,int))}
      if selected:entries.append(selected)
      for v in value.values():visit(v)
     elif isinstance(value,list):
      for v in value:visit(v)
    visit(tree)
    target['xctestrun_files'].append({'name':path.name,'sha256':sha(path),'bytes':path.stat().st_size,'target_fields':entries})
  else:need(not result['collection_complete'],'complete result lacks program')
  bundle=folder/'launch.xcresult'
  if bundle.exists():
   _,perf=extract_metrics(bundle,with_cases=True);need(perf==json.loads((folder/'performance-cases.json').read_text()),'independent native metric parse')
   statuses=load_results(bundle);need(statuses==json.loads((folder/'test-cases.json').read_text()),'independent native status parse')
   obs=observations(folder);need(obs==json.loads((folder/'observations.json').read_text()),'actual native observations')
   events=[{'test':o['test'],'samples':[launch_events(s) for s in o['samples']]} for o in obs if 'Launch' in o.get('test','')]
   need(events==json.loads((folder/'launch-events.json').read_text()),'independent candidate event summary')
   target.update({'native_test_cases':statuses,'native_performance_cases':perf,'launch_events':events,'reader_observations':[o for o in obs if 'Reader' in o.get('test','')]})
  control=folder/'window-control';control_bundle=control/'scene.xcresult'
  if control_bundle.exists():
   _,control_performance=extract_metrics(control_bundle,with_cases=True)
   need(control_performance==json.loads((control/'performance-cases.json').read_text()),'independent separate control metrics')
   control_cases=load_results(control_bundle);need(control_cases==json.loads((control/'test-cases.json').read_text()),'independent separate control status')
   control_observations=observations(control);need(control_observations==json.loads((control/'observations.json').read_text()),'independent separate control observations')
   target['separate_window_capability']={'native_cases':control_cases,'observations':control_observations,'tti_acceptance':False}
  if platform=='macos':
   binding=runtime_binding_report(observations(folder),observations(control),target.get('program_sha256'),identity()['source_sha'])
   target.update(binding)
   if result['collection_complete'] and binding['runtime_program_binding']!='matched':runtime_binding_violations.append(platform)
  report['targets'][platform]=target
 report['authenticated']=True;report['required_runtime_binding_violations']=runtime_binding_violations
 save(out/'report.json',report);print('LAUNCH_DIAG_AUDIT',json.dumps(report),flush=True)
 need(not runtime_binding_violations,'complete result requires every measured/warmup sample runtime row and phase PID to match; row assessments retained in report.json')
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['native','seal','audit']);parser.add_argument('--platform',choices=['macos','iphone']);args=parser.parse_args()
 if args.mode in ('native','seal'):need(args.platform,'platform required')
 {'native':lambda:native(args.platform),'seal':lambda:seal(args.platform),'audit':audit}[args.mode]()
