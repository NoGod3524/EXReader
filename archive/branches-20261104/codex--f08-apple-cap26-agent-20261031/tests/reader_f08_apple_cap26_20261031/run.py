# SPDX-License-Identifier: MIT
# A bounded environment capability probe over authenticated, unchanged77b apps.
import argparse, hashlib, importlib.util, io, json, os, plistlib, shutil, signal, stat, subprocess, sys, time, traceback, zipfile
from pathlib import Path, PurePosixPath
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
OUT=ROOT/'build/f08-apple-cap26'
EVIDENCE=OUT/'evidence'
PROFILE=json.loads((HERE/'profile.json').read_text())
BASE=PROFILE['source_base']
ALLOWED={'.github/workflows/dot-f08-apple-cap26-20261031.yml','tests/reader_f08_apple_cap26_20261031/run.py','tests/reader_f08_apple_cap26_20261031/profile.json'}
def need(v,message):
    if not v:raise ValueError(message)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,v):
    Path(p).parent.mkdir(parents=True,exist_ok=True);Path(p).write_text(json.dumps(v,indent=2,allow_nan=False)+'\n')
def command(args,**kw):
    kw.setdefault('timeout',120)
    return subprocess.check_output(list(map(str,args)),cwd=ROOT,**kw)
def identity():return {'source_sha':os.environ['GITHUB_SHA'],'run_id':os.environ['GITHUB_RUN_ID'],'attempt':os.environ['GITHUB_RUN_ATTEMPT']}
def guard():
    need(os.environ.get('GITHUB_ACTIONS')=='true','Actions only')
    need(command(['git','rev-parse','HEAD'],text=True).strip()==identity()['source_sha'],'head identity')
    command(['git','merge-base','--is-ancestor',BASE,'HEAD'])
    need(set(command(['git','diff','--name-only',BASE,'HEAD'],text=True).splitlines())==ALLOWED,'capability-only source scope')
def api(path):return json.loads(command(['gh','api','repos/NoGod3524/EXReader/'+path]))
def archive_bytes(meta):return command(['gh','api','repos/NoGod3524/EXReader/actions/artifacts/'+str(meta['id'])+'/zip'])
def validate_zip(data):
    z=zipfile.ZipFile(io.BytesIO(data));infos=z.infolist()
    need(0<len(infos)<100000 and sum(x.file_size for x in infos)<4*1024**3,'archive bounds')
    seen=set()
    for i in infos:
        p=PurePosixPath(i.filename);key=str(p).casefold()
        need(str(p)!='.' and not p.is_absolute() and '..' not in p.parts and '\\' not in i.filename and ':' not in i.filename and key not in seen,'archive path')
        seen.add(key);need(not i.flag_bits&1 and stat.S_IFMT(i.external_attr>>16) in (0,stat.S_IFDIR,stat.S_IFREG),'archive entry kind')
    manifest=json.loads(z.read('f08-manifest.json'))
    files={i.filename for i in infos if not i.is_dir()}
    need(files==set(manifest['files'])|{'f08-manifest.json'},'archive complete inventory')
    for name,item in manifest['files'].items():
        b=z.read(name);need(len(b)==item['bytes'] and hashlib.sha256(b).hexdigest()==item['sha256'],'archive file bytes '+name)
    return z,manifest

def inputs(folder,metadata_folder=None):
    metadata_folder=metadata_folder or EVIDENCE/'inputs'
    result={}
    producer=api('actions/runs/'+str(PROFILE['producer_run']))
    need(producer['head_sha']==BASE and producer['run_attempt']==PROFILE['producer_attempt'],'original producer')
    for row in PROFILE['inputs']:
        meta=api('actions/artifacts/'+str(row['id']))
        need(not meta['expired'] and meta['workflow_run']['head_sha']==BASE and meta['workflow_run']['id']==PROFILE['producer_run'],'original artifact producer')
        data=archive_bytes(meta);digest=hashlib.sha256(data).hexdigest()
        need(len(data)==meta['size_in_bytes']==row['bytes'] and digest==row['sha256'] and meta['digest']=='sha256:'+digest,'original ZIP identity')
        z,m=validate_zip(data)
        need(m['source_sha']==BASE and m['run_id']==str(PROFILE['producer_run']) and m['attempt']==str(PROFILE['producer_attempt']) and m['kind']==row['kind'],'original manifest identity')
        dest=folder/row['kind'];dest.mkdir(parents=True)
        prefix='program/EXReaderHost.app/' if not row['kind'].endswith('-sdk') else None
        for name in m['files']:
            if prefix is not None and not name.startswith(prefix):continue
            if prefix is None and not (name.startswith(('sdk/','raw-products/')) or name.endswith('.json')):continue
            p=dest/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(z.read(name))
        result[row['kind']]={'root':dest,'metadata':meta,'manifest':m,'sha256':digest,'bytes':len(data)}
        save(metadata_folder/(row['kind']+'.json'),{'metadata':meta,'zip_sha256':digest,'zip_bytes':len(data),'original_manifest':m})
        print('CAP26_INPUT',row['kind'],row['id'],digest,flush=True)
    return result

def load_native_tools():
    spec=importlib.util.spec_from_file_location('original_apple_measurements',ROOT/'tests/reader_f08_apple_20261031/run.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    sys.path.insert(0,str(ROOT/'tests/apple_host'))
    from collect_evidence import load_results
    return module.extract_metrics,load_results

def binary(app,platform):return app/('Contents/MacOS/EXReaderHost' if platform=='macos' else 'EXReaderHost')
def verify_app(app,platform,entry):
    expected={n.removeprefix('program/EXReaderHost.app/'):i for n,i in entry['manifest']['files'].items() if n.startswith('program/EXReaderHost.app/')}
    actual={p.relative_to(app).as_posix() for p in app.rglob('*') if p.is_file()}
    need(actual==set(expected),'complete original app inventory')
    for n,item in expected.items():need(sha(app/n)==item['sha256'] and (app/n).stat().st_size==item['bytes'],'original program file '+n)
    row=next(r for r in PROFILE['inputs'] if r['kind']==platform)
    need(sha(binary(app,platform))==row['program_sha256'],'original binary SHA')
    info=plistlib.loads((app/('Contents/Info.plist' if platform=='macos' else 'Info.plist')).read_bytes())
    need(info['EXRSourceSHA']==BASE and info['EXRSDKVersion']=='3.42.0','original app source/version')
    return expected

SCROLL=r'''
final class F08CapScrollUITests: XCTestCase {
    private var app: XCUIApplication!
    private var captured: [[String: Any]] = []
    private var metrics: [XCTMetric] = []
    override func setUpWithError() throws {
        continueAfterFailure = false
        app = XCUIApplication()
        app.launchArguments = ["-EXRShelfSeed", "-EXRFreshState", "1"]
        metrics = [XCTClockMetric(), XCTMemoryMetric(application: app),
            XCTOSSignpostMetric.scrollingAndDecelerationMetric,
            XCTOSSignpostMetric(subsystem: "org.exreader.f08", category: "NativeUI", name: "ShelfScroll")]
        if #available(macOS 26, iOS 26, *) { metrics.append(XCTHitchMetric(application: app)) }
        record("configured", ["configured_native_metric_types": metrics.map { String(describing: type(of: $0)) },
            "runtime": ProcessInfo.processInfo.operatingSystemVersionString,
            "iterations": 1, "default_warmup_retained": true])
        app.launch()
    }
    override func tearDownWithError() throws {
        record("final", state() ?? [:])
        let data = try JSONSerialization.data(withJSONObject: ["test": name, "observations": captured], options: [.sortedKeys])
        let a = XCTAttachment(string: String(decoding: data, as: UTF8.self)); a.name = "cap26-scroll-observations"; a.lifetime = .keepAlways; add(a)
        app?.terminate()
    }
    private func record(_ phase: String, _ value: [String: Any]) { captured.append(["phase": phase, "value": value, "uptime_s": ProcessInfo.processInfo.systemUptime]) }
    private func node(_ id: String) -> XCUIElement { app.descendants(matching: .any).matching(identifier: id).firstMatch }
    private func state() -> [String: Any]? {
        guard let root = try? node("library.shelf.state").snapshot() else { return nil }
        var nodes = [root], parts: [Int: String] = [:], count: Int?
        while let n = nodes.popLast() {
            let v = n.label.isEmpty ? (n.value as? String) ?? "" : n.label
            if n.identifier == "library.shelf.count" { count = Int(v) }
            let p = "library.shelf.part."
            if n.identifier.hasPrefix(p), let i = Int(n.identifier.dropFirst(p.count)) { parts[i] = v }
            nodes.append(contentsOf: n.children)
        }
        guard let count, (1...256).contains(count), parts.count == count,
            (0..<count).allSatisfy({ parts[$0] != nil }),
            let data = (0..<count).map({ parts[$0]! }).joined().data(using: .utf8) else { return nil }
        return (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
    }
    private func ready() -> [String: Any] {
        let end = Date().addingTimeInterval(60); var previous = "", stableAt = Date()
        while Date() < end {
            if let v = state(), v["query"] as? String == "", v["loading"] as? Bool == false,
                v["restoring_layout"] as? Bool == false, v["generation"] as? Int == v["applied_generation"] as? Int,
                let visible = v["visible_keys"] as? [String], !visible.isEmpty,
                let top = v["top_key"] as? String, !top.isEmpty {
                let signature = top + "|" + visible.joined(separator: "|")
                if signature != previous { previous = signature; stableAt = Date() }
                if Date().timeIntervalSince(stableAt) >= 0.35 { return v }
            }
            RunLoop.current.run(until: Date().addingTimeInterval(0.1))
        }
        XCTFail("Original2202 shelf did not become ready: \(String(describing: state()))")
        return [:]
    }
    private func scroll(_ back: Bool) {
        let list = node("library.list"); XCTAssertTrue(list.exists)
#if os(macOS)
        list.scroll(byDeltaX: 0, deltaY: back ? 260 : -260)
#else
        if back { list.swipeDown(velocity: .slow) } else { list.swipeUp(velocity: .slow) }
#endif
    }
    func test01MinimalNativeScrollMetricCapability() {
        _ = ready()
        let options = XCTMeasureOptions(); options.iterationCount = 1; options.invocationOptions = [.manuallyStop]
        measure(metrics: metrics, options: options) {
            let before = ready(); scroll(false); let after = ready()
            stopMeasuring()
            XCTAssertNotEqual(before["top_key"] as? String, after["top_key"] as? String, "Real shelf viewport did not move")
            record("forward", ["before": before, "after": after,
                "top_changed": before["top_key"] as? String != after["top_key"] as? String])
            scroll(true); record("returned", ready())
        }
        let a = XCTAttachment(screenshot: app.screenshot()); a.name = "cap26-real-scroll"; a.lifetime = .keepAlways; add(a)
    }
}
'''
FONT=r'''
extension F08ReaderUITests {
    @objc func test15FrozenNarrowFont48PageCapability() {
        openShelf("Book 0201")
        let window = app.windows.firstMatch
        let originalWindow = window.frame
#if os(macOS)
        let corner = window.coordinate(withNormalizedOffset: CGVector(dx: 1, dy: 1))
        corner.press(forDuration: 0.1, thenDragTo: corner.withOffset(CGVector(dx: 380 - originalWindow.width, dy: 460 - originalWindow.height)))
#endif
        defer {
#if os(macOS)
            if window.exists {
                let current = window.frame
                let corner = window.coordinate(withNormalizedOffset: CGVector(dx: 1, dy: 1))
                corner.press(forDuration: 0.1, thenDragTo: corner.withOffset(CGVector(dx: originalWindow.width - current.width, dy: originalWindow.height - current.height)))
            }
#endif
        }
        let baseline = reader()
        var stages: [[String: Any]] = []
        for _ in 0..<16 {
            let before = reader()
            if (before["font_size"] as? Int ?? 0) >= 48 { break }
            tap("reader.font.increase"); stages.append(reader())
        }
        XCTAssertEqual(reader()["font_size"] as? Int, 48)
        tap("reader.first"); let first = reader()
        let firstScreen = XCTAttachment(screenshot: app.screenshot()); firstScreen.name = "cap26-frozen-font48-first"; firstScreen.lifetime = .keepAlways; add(firstScreen)
        tap("reader.next")
        XCTAssertTrue(wait { !self.node("reader.busy").exists })
        let next = readerObservation() ?? [:]
        let nextError = text("reader.error")
        samples.append(["phase": "next-once", "cohort": "frozen-2202", "baseline": baseline,
            "font_stages": stages, "first": first, "next": next, "native_error": nextError,
            "window_before": [originalWindow.origin.x, originalWindow.origin.y, originalWindow.width, originalWindow.height],
            "window_after": [window.frame.origin.x, window.frame.origin.y, window.frame.width, window.frame.height],
            "reader_page_frame": [node("reader.page").frame.width, node("reader.page").frame.height],
            "next_observation_valid": (next["bitmap_sha256"] as? String)?.count == 64,
            "location_changed": !(next["location"] as? String ?? "").isEmpty && next["location"] as? String != first["location"] as? String,
            "bitmap_changed": (next["bitmap_sha256"] as? String)?.count == 64 && next["bitmap_sha256"] as? String != first["bitmap_sha256"] as? String,
            "scope": "One native window/font observation; no all-viewport single-page inference"])
        let nextScreen = XCTAttachment(screenshot: app.screenshot()); nextScreen.name = "cap26-frozen-font48-next"; nextScreen.lifetime = .keepAlways; add(nextScreen)
        tap("reader.first"); let reset = reader(); locate("bytes."); let located = reader()
        samples.append(["phase": "exact-locate-once", "query": "bytes.", "reset": reset, "located": located,
            "cross_page_location_changed": reset["location"] as? String != located["location"] as? String,
            "bitmap_changed": reset["bitmap_sha256"] as? String != located["bitmap_sha256"] as? String])
        XCTAssertEqual((next["bitmap_sha256"] as? String)?.count, 64, "Next-page accepted bitmap observation missing")
        if !nextError.isEmpty { XCTFail("Native next-page action reported: \(nextError)") }
    }
}
'''

def native():
    guard();EVIDENCE.mkdir(parents=True,exist_ok=True)
    save(EVIDENCE/'profile.json',PROFILE)
    report={**identity(),'f08_accepted':False,'capability_only':True,'program_source_sha':BASE,'collection_complete':False,'commands':[],'problems':[]}
    deadline=time.monotonic()+900
    def run(args,role,timeout=180,required=True):
        args=list(map(str,args));timeout=min(timeout,max(1,deadline-time.monotonic()))
        print('CAP26_PHASE',role,flush=True);log=EVIDENCE/(role+'.log');log.parent.mkdir(parents=True,exist_ok=True)
        timed=False
        with log.open('wb') as f:
            proc=subprocess.Popen(args,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
            try:proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed=True
                for sig,grace in ((signal.SIGINT,20),(signal.SIGTERM,10),(signal.SIGKILL,5)):
                    try:os.killpg(proc.pid,sig)
                    except ProcessLookupError:break
                    try:proc.wait(timeout=grace);break
                    except subprocess.TimeoutExpired:continue
                if proc.returncode is None:proc.wait(timeout=5)
        report['commands'].append({'role':role,'argv':args,'returncode':proc.returncode,'timed_out':timed,'collector_limit_s':timeout})
        if timed or proc.returncode:
            report['problems'].append(role+(' collection timeout' if timed else ' exit '+str(proc.returncode)))
            print('\n'.join(log.read_text(errors='replace').splitlines()[-40:]),flush=True)
            if required:raise RuntimeError(role+' failed')
            return False
        return True
    try:
        version=command(['sw_vers'],text=True);xcode=command(['xcodebuild','-version'],text=True)
        need(int(command(['sw_vers','-productVersion'],text=True).split('.')[0])==26 and xcode.startswith('Xcode 26.2\n'),'predeclared host/Xcode26.2')
        save(EVIDENCE/'environment.json',{'os':version,'xcode':xcode,'developer_dir':os.environ.get('DEVELOPER_DIR'),'arch':command(['uname','-m'],text=True),'runner_image':os.environ.get('ImageVersion'),'hardware':command(['sysctl','hw.model','hw.ncpu','hw.memsize'],text=True)})
        run(['system_profiler','SPDisplaysDataType','-json'],'display-before',timeout=30)
        installed=inputs(OUT/'input')
        resources=installed['macos']['root']/'program/EXReaderHost.app/Contents/Resources'
        seed=json.loads((resources/'shelf-seed.json').read_text());need(seed['books']==2202 and len(set(seed['source_keys']))==2202,'frozen corpus')
        extract_metrics,load_results=load_native_tools()
        test_dir=OUT/'driver/shelf/ui';test_dir.mkdir(parents=True)
        original=(ROOT/'tests/apple_host/shelf/ui/ShelfUITests.swift').read_text();insertion=(ROOT/'tests/reader_f08_apple_20261031/Metrics.swift').read_text()
        inside,marker,standalone=insertion.partition('// F08_STANDALONE_CLASSES');need(marker,'original split')
        at=original.rfind('}');candidate=original[:at]+inside+original[at:]+standalone+SCROLL+FONT
        driver=test_dir/'ShelfUITests.swift';driver.write_text(candidate);shutil.copyfile(driver,EVIDENCE/'ShelfUITests.swift')
        save(EVIDENCE/'driver.json',{'original_sha256':sha(ROOT/'tests/apple_host/shelf/ui/ShelfUITests.swift'),'metrics_sha256':sha(ROOT/'tests/reader_f08_apple_20261031/Metrics.swift'),'candidate_sha256':sha(driver),'original_bodies_unchanged':True,'additional_scroll_sha256':hashlib.sha256(SCROLL.encode()).hexdigest(),'font_capability_sha256':hashlib.sha256(FONT.encode()).hexdigest()})
        project=OUT/'project';run(['ruby','tests/reader_team24_apple/make_project.rb',project,resources,test_dir,'wave3'],'project',timeout=45)
        run(['ruby','-rxcodeproj','-e','p=Xcodeproj::Project.open(ARGV[0]);p.targets.each{|t|next unless t.product_type=="com.apple.product-type.application";t.build_configurations.each{|c|c.build_settings["SWIFT_ACTIVE_COMPILATION_CONDITIONS"]+=" EXR_APPLE_F08_REVIEW"}};p.save',project/'EXReaderHost.xcodeproj'],'observer-flags',timeout=30)
        config=json.loads(command(['ruby','-rxcodeproj','-rjson','-e','p=Xcodeproj::Project.open(ARGV[0]);v={};p.targets.each{|t|next unless t.product_type=="com.apple.product-type.application";t.build_configurations.each{|c|v[t.name+"/"+c.name]=c.build_settings["SWIFT_ACTIVE_COMPILATION_CONDITIONS"]}};puts JSON.generate(v)',project/'EXReaderHost.xcodeproj'],text=True))
        need(len(config)==4 and all({'EXR_APPLE_F08_REVIEW','EXR_APPLE_SHELF_REVIEW','EXR_APPLE_RAW3','EXR_APPLE_WAVE3','EXR_APPLE_PAGE_THEME'}<=set(x.split()) for x in config.values()),'full product feature flags')
        save(EVIDENCE/'project-configuration.json',config)
        for scheme in (project/'EXReaderHost.xcodeproj/xcshareddata/xcschemes').glob('*.xcscheme'):
            tree=ET.parse(scheme)
            for tag in ('TestAction','LaunchAction'):
                action=tree.getroot().find(tag);need(action is not None,'scheme action')
                action.attrib.update({'buildConfiguration':'Release','selectedDebuggerIdentifier':'','selectedLauncherIdentifier':'Xcode.IDEFoundation.Launcher.PosixSpawn','codeCoverageEnabled':'NO','disableMainThreadChecker':'YES','enableAddressSanitizer':'NO','enableThreadSanitizer':'NO','enableUBSanitizer':'NO'})
            tree.write(scheme,encoding='utf-8',xml_declaration=True)
            dest=EVIDENCE/'schemes'/scheme.name;dest.parent.mkdir(exist_ok=True);shutil.copyfile(scheme,dest)
        owned_device=None
        for platform in ('macos','iphone'):
            need(time.monotonic()<deadline-45,'native capability collector deadline')
            folder=EVIDENCE/platform;folder.mkdir()
            target='macos' if platform=='macos' else 'iphonesimulator';sdk=installed[target+'-sdk']['root']
            if platform=='macos':destination='platform=macOS';scheme='EXReaderHost-macOS';test_target='EXReaderHostUITests-macOS';suffix='Release';signing='YES'
            else:
                runtimes=json.loads(command(['xcrun','simctl','list','runtimes','--json']))
                devices=json.loads(command(['xcrun','simctl','list','devicetypes','--json']))
                save(folder/'runtime-inventory.json',runtimes);save(folder/'device-types.json',devices)
                rt=PROFILE['simulator']['runtime'];need(any(x['identifier']==rt and x.get('isAvailable') for x in runtimes['runtimes']),'predeclared iOS26.2 runtime unavailable')
                matches=[x for x in devices['devicetypes'] if x['name']==PROFILE['simulator']['name']];need(len(matches)==1,'predeclared SE3 type unavailable')
                owned_device=command(['xcrun','simctl','create','F08-Cap26-SE3',matches[0]['identifier'],rt],text=True).strip()
                (folder/'destination.txt').write_text(owned_device+'\n'+PROFILE['simulator']['name']+'\n'+rt+'\n')
                run(['xcrun','simctl','boot',owned_device],'iphone/boot',timeout=30)
                run(['xcrun','simctl','bootstatus',owned_device,'-b'],'iphone/boot-ready',timeout=180)
                destination='platform=iOS Simulator,id='+owned_device;scheme='EXReaderHost-iOS';test_target='EXReaderHostUITests-iOS';suffix='Release-iphonesimulator';signing='NO'
            derived=OUT/('derived-'+platform)
            build=['-project',project/'EXReaderHost.xcodeproj','-scheme',scheme,'-destination',destination,'-derivedDataPath',derived,'-configuration','Release','EXR_SDK_DIR='+str(sdk/'sdk'),'EXR_PRODUCTS_DIR='+str(sdk/'raw-products'),'CODE_SIGNING_ALLOWED='+signing,'SWIFT_OPTIMIZATION_LEVEL=-O','GCC_OPTIMIZATION_LEVEL=s','ONLY_ACTIVE_ARCH=YES']
            common=[*build,'-enableCodeCoverage','NO','-enableAddressSanitizer','NO','-enableThreadSanitizer','NO','-enableUndefinedBehaviorSanitizer','NO','-parallel-testing-enabled','NO','-test-timeouts-enabled','YES','-default-test-execution-time-allowance','180','-maximum-test-execution-time-allowance','180']
            settings=json.loads(command(['xcodebuild','-showBuildSettings','-json',*build]));save(folder/'build-settings.json',settings)
            run(['xcodebuild','build-for-testing',*common],platform+'/build',timeout=300)
            app=derived/'Build/Products'/suffix/'EXReaderHost.app';need(app.resolve().is_relative_to(OUT.resolve()),'owned build product path')
            shutil.rmtree(app);shutil.copytree(installed[platform]['root']/'program/EXReaderHost.app',app)
            binary(app,platform).chmod(0o755);expected=verify_app(app,platform,installed[platform])
            save(folder/'program-identity.json',{'program_source_sha':BASE,'program_sha256':sha(binary(app,platform)),'complete_original_files':expected,'test_harness_source_sha':identity()['source_sha'],'destination':destination})
            shutil.copytree(app,folder/'program/EXReaderHost.app')
            bundle=folder/'capability.xcresult';cases=PROFILE['macos_cases'] if platform=='macos' else PROFILE['ios_cases']
            run(['xcodebuild','test-without-building',*common,'-resultBundlePath',bundle,*['-only-testing:'+test_target+'/'+x for x in cases]],platform+'/native',timeout=240 if platform=='macos' else 420,required=False)
            verify_app(app,platform,installed[platform])
            if bundle.exists():
                objects,performance=extract_metrics(bundle,with_cases=True);save(folder/'xcresult-objects.json',objects);save(folder/'performance-cases.json',performance)
                statuses=load_results(bundle);save(folder/'test-cases.json',statuses)
                expected_names={x.rsplit('/',1)[-1]+'()' for x in cases}
                if {x['name'] for x in statuses}!=expected_names or any(x['result']!='Passed' for x in statuses):report['problems'].append(platform+' native case set/status incomplete')
                run(['xcrun','xcresulttool','export','attachments','--path',bundle,'--output-path',folder/'attachments'],platform+'/attachments',timeout=60,required=False)
            report[platform]={'program_sha256':sha(binary(app,platform)),'cases_requested':cases,'program_verified_before_after':True}
            if owned_device:run(['xcrun','simctl','shutdown',owned_device],'iphone/shutdown',timeout=30,required=False)
        run(['system_profiler','SPDisplaysDataType','-json'],'display-after',timeout=30)
        report['collection_complete']=not report['problems']
    except BaseException as e:
        report['problems'].append(repr(e));report['traceback']=traceback.format_exc()
    finally:
        save(EVIDENCE/'result.json',report);print('CAP26_RESULT',json.dumps(report),flush=True)
    need(report['collection_complete'],'capability collection incomplete; observations retained')

def seal():
    guard();EVIDENCE.mkdir(parents=True,exist_ok=True)
    paths=[p for p in EVIDENCE.rglob('*') if p.is_file() and p.name!='f08-manifest.json']
    save(EVIDENCE/'f08-manifest.json',{**identity(),'f08_accepted':False,'capability_only':True,'files':{p.relative_to(EVIDENCE).as_posix():{'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(paths)}})

def audit():
    guard();out=ROOT/'build/f08-apple-cap26-audit';out.mkdir(parents=True)
    ident=identity();producer=api('actions/runs/'+ident['run_id']);need(producer['head_sha']==ident['source_sha'] and str(producer['run_attempt'])==ident['attempt'],'cap producer')
    rows=api('actions/runs/'+ident['run_id']+'/artifacts?per_page=100')['artifacts'];name='f08-apple-cap26-native-'+ident['run_id']+'-'+ident['attempt'];matches=[a for a in rows if a['name']==name];need(len(matches)==1,'cap artifact')
    meta=api('actions/artifacts/'+str(matches[0]['id']));data=archive_bytes(meta);digest=hashlib.sha256(data).hexdigest();need(len(data)==meta['size_in_bytes'] and meta['digest']=='sha256:'+digest and meta['workflow_run']['head_sha']==ident['source_sha'],'cap ZIP identity')
    z,m=validate_zip(data);need(all(m.get(k)==v for k,v in ident.items()) and m['f08_accepted'] is False and m['capability_only'] is True,'cap manifest')
    raw=out/'raw';raw.mkdir()
    for n in m['files']:
        p=raw/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(z.read(n))
    need((raw/'profile.json').read_bytes()==(HERE/'profile.json').read_bytes(),'cap profile')
    trusted=inputs(out/'original-input',metadata_folder=out/'original-metadata')
    for row in PROFILE['inputs']:
        saved=json.loads((raw/'inputs'/(row['kind']+'.json')).read_text());current=trusted[row['kind']]
        need(current['metadata']==saved['metadata'] and current['manifest']==saved['original_manifest'],'independent original ZIP metadata/manifest')
        need(current['sha256']==row['sha256'] and current['bytes']==row['bytes'],'independent original ZIP bytes')
    original=(ROOT/'tests/apple_host/shelf/ui/ShelfUITests.swift').read_text();insertion=(ROOT/'tests/reader_f08_apple_20261031/Metrics.swift').read_text()
    inside,marker,standalone=insertion.partition('// F08_STANDALONE_CLASSES');need(marker,'original split')
    at=original.rfind('}');need((raw/'ShelfUITests.swift').read_text()==original[:at]+inside+original[at:]+standalone+SCROLL+FONT,'unchanged original bodies and exact capability additions')
    extract_metrics,load_results=load_native_tools();result=json.loads((raw/'result.json').read_text())
    report={**ident,'authenticated':True,'artifact_id':meta['id'],'archive_sha256':digest,'archive_bytes':len(data),'capability_only':True,'f08_accepted':False,'collection_complete':result['collection_complete'],'problems':result['problems'],'targets':{}}
    for platform in ('macos','iphone'):
        folder=raw/platform
        if not (folder/'program-identity.json').exists():continue
        app=folder/'program/EXReaderHost.app';verify_app(app,platform,trusted[platform])
        identity_data=json.loads((folder/'program-identity.json').read_text());need(identity_data['program_sha256']==sha(binary(app,platform)) and identity_data['program_source_sha']==BASE,'audit program source')
        target={'program_sha256':identity_data['program_sha256'],'program_source_sha':BASE,'native_hitch':'missing','native_frames':'missing','cases':[]}
        bundle=folder/'capability.xcresult'
        if bundle.exists() and (folder/'performance-cases.json').exists():
            _,cases=extract_metrics(bundle,with_cases=True);need(cases==json.loads((folder/'performance-cases.json').read_text()),'independent native metrics')
            statuses=load_results(bundle);need(statuses==json.loads((folder/'test-cases.json').read_text()),'independent case statuses')
            target['case_statuses']=statuses;target['cases']=cases
            requested=PROFILE['macos_cases'] if platform=='macos' else PROFILE['ios_cases']
            if result['collection_complete']:need({x['name'] for x in statuses}=={x.rsplit('/',1)[-1]+'()' for x in requested} and all(x['result']=='Passed' for x in statuses),'complete native case set/status')
            configurations=[];observations=[]
            attachment_manifest=folder/'attachments/manifest.json'
            if attachment_manifest.exists():
                for item in json.loads(attachment_manifest.read_text()):
                    for a in item.get('attachments',[]):
                        human=a.get('suggestedHumanReadableName','');path=folder/'attachments'/a['exportedFileName']
                        if human.startswith('f08-native-metric-configuration'):configurations.append({'test':item['testIdentifier'],'configuration':json.loads(path.read_text())})
                        elif human.startswith('cap26-scroll-observations'):
                            payload=json.loads(path.read_text());observations.append(payload)
                            configurations.extend({'test':item['testIdentifier'],'configuration':x['value']} for x in payload['observations'] if x['phase']=='configured')
                        elif human.startswith('f08-reader-observations'):observations.append(json.loads(path.read_text()))
            target['actual_metric_configurations']=configurations;target['observations']=observations
            target['xcthitchmetric_configured']=any(any('XCTHitchMetric' in name for name in x['configuration'].get('configured_native_metric_types',[])) for x in configurations)
            target['per_case_native_coverage']=[]
            for c in cases:
                fields=c.get('performance_metrics',[])
                hitch=[x for x in fields if 'hitch' in (x.get('identifier',{}).get('_value','')+' '+x.get('displayName',{}).get('_value','')).lower()]
                frames=[x for x in fields if 'frame' in x.get('identifier',{}).get('_value','').lower() and 'count' in x.get('identifier',{}).get('_value','').lower()]
                frame_values=[v['_value'] for x in frames for v in x.get('measurements',{}).get('_values',[])]
                positive=bool(frame_values) and all(float(v)>0 for v in frame_values)
                target['per_case_native_coverage'].append({'case':c.get('identifier',c.get('name')),'status':c.get('status'),
                    'native_hitch_metrics':hitch,'xcthitch_output_candidates':[x for x in hitch if 'ossignpost' not in x.get('identifier',{}).get('_value','').lower()],
                    'native_frame_count_metrics':frames,'all_native_frame_counts_positive':positive if frames else 'missing',
                    'native_frame_count_unit_is_frames':all(x.get('unitOfMeasurement',{}).get('_value')=='frames' for x in frames) if frames else 'missing'})
            fields=[m for c in cases for m in c.get('performance_metrics',[])]
            if any('hitch' in x.get('identifier',{}).get('_value','').lower() for x in fields):target['native_hitch']='emitted; inspect per-case native unit/values'
            if any('frame' in x.get('identifier',{}).get('_value','').lower() and 'count' in x.get('identifier',{}).get('_value','').lower() for x in fields):target['native_frames']='emitted; inspect per-case positive coverage'
        report['targets'][platform]=target
    save(out/'report.json',report);print('CAP26_AUDIT',json.dumps(report),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=('native','seal','audit'));args=p.parse_args()
    {'native':native,'seal':seal,'audit':audit}[args.mode]()
