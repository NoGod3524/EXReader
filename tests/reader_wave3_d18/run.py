"""Fresh same-source native iPhone/iPad apps, independent observer, real XCTest."""
import json, os, pathlib, plistlib, shutil, subprocess, sys, tarfile, traceback
from common import ROOT, OUT, SDK_SOURCE, identity, digest, write
from observer import Observer
from probe import build
assert sys.platform=='darwin';info=identity();host=sys.argv[1];assert host in ('iphone','ipad')
out=OUT/host;out.mkdir(parents=True,exist_ok=True)
executions=[];program={};cases=[];configuration={};observer=None;sdk_identities={}
env=dict(os.environ,EXR_APPLE_SDK_VERSION='3.41.0',EXR_APPLE_PAGE_THEME='ON',EXR_APPLE_RAW3='OFF')
def run(name,args,timeout=1800,required=True):
    with (out/(name+'.log')).open('w') as log:
        try: code=subprocess.run(list(map(str,args)),cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,env=env,timeout=timeout).returncode
        except subprocess.TimeoutExpired: code=124
    executions.append(dict(name=name,returncode=code));print(json.dumps(executions[-1]),flush=True)
    if code:
        lines=(out/(name+'.log')).read_text(errors='replace').splitlines()
        print('\n'.join(l for l in lines if any(x in l for x in ['error:','failed','D18_ACTION','caught error','XCTAssert'])),flush=True)
        print('\n'.join(lines[-100:]),flush=True)
    if required: assert code==0,(name,code)
    return code
try:
    sys.path.insert(0,str(ROOT/'tests/apple_host'))
    from evidence_contract import validate_sdk
    from collect_evidence import load_results
    for kind in ['macos',host]:
        sdk=OUT/(kind+'-producer')/'sdk';sdk_identity=json.loads((sdk.parent/'sdk-identity.json').read_text())
        validate_sdk(sdk,sdk_identity,'72c6bbdd14ebf3be453fa7f0da81119d52675eb5','40203714083','1','macos' if kind=='macos' else 'iphonesimulator')
        sdk_identities[kind]=sdk_identity
    macsdk=OUT/'macos-producer/sdk';sdk=OUT/(host+'-producer')/'sdk'
    public_probe=build(macsdk)
    # Preserve the frozen SDK dynamic libraries while rebuilding product packages
    # from this checkout, never linking old producer product code as new-source.
    frozen={p.name:digest(p) for p in (sdk/'lib').glob('libexreader*.dylib')}
    run('current-product',[sys.executable,'tools/build_apple_product.py','--sdk',sdk,'--sdk-version','3.41.0','--target','iphonesimulator','--build',OUT/'product-build'])
    assert frozen=={p.name:digest(p) for p in (sdk/'lib').glob('libexreader*.dylib')}
    resources=OUT/'resources';project=OUT/'project';derived=OUT/'derived'
    run('fixtures',[sys.executable,'tests/apple_host/prepare_fixtures.py','--resources',resources])
    run('project',['ruby','tests/apple_host/make_xcodeproj.rb',project,resources,ROOT/'tests/reader_wave3_d18/accessibility/ui'])
    pbx=project/'EXReaderHost.xcodeproj/project.pbxproj';body=pbx.read_text()
    assert 'EXR_APPLE_HOST_REVIEW' not in body and 'EXR_APPLE_IMPORT_REVIEW' not in body and 'EXR_APPLE_PAGE_THEME' in body
    configuration=dict(review_macros_present=False,page_theme_enabled=True,raw3_enabled=False,signing_allowed=False,generated_project_sha256=digest(pbx),frozen_sdk_dylibs=frozen,product_manifest=json.loads((sdk/'share/exreader-apple/product.json').read_text()))
    devices=json.loads(subprocess.check_output(['xcrun','simctl','list','devices','available','--json']))
    prefix='iPhone' if host=='iphone' else 'iPad';choices=[(runtime,d['name'],d['udid']) for runtime,rows in devices['devices'].items() for d in rows if d.get('isAvailable') and d['name'].startswith(prefix)]
    runtime,device,udid=max(choices);destination='platform=iOS Simulator,id='+udid
    configuration.update(device=device,runtime=runtime,udid=udid,destination=destination)
    # A prebooted selected device is not a failed operation; query before boot.
    state=next(d['state'] for rows in devices['devices'].values() for d in rows if d['udid']==udid)
    if state!='Booted':run('boot',['xcrun','simctl','boot',udid])
    run('boot-ready',['xcrun','simctl','bootstatus',udid,'-b'])
    observer=Observer(host,udid,public_probe,resources);observer.start()
    result=out/'native.xcresult'
    run('native-actions',['xcodebuild','test','-project',project/'EXReaderHost.xcodeproj','-scheme','EXReaderHost-iOS','-destination',destination,'-derivedDataPath',derived,'-resultBundlePath',result,'-parallel-testing-enabled','NO','-test-timeouts-enabled','YES','-default-test-execution-time-allowance','600','-maximum-test-execution-time-allowance','900','EXR_SDK_DIR='+str(sdk),'CODE_SIGNING_ALLOWED=NO','CODE_SIGNING_REQUIRED=NO'],required=False)
    app=derived/'Build/Products/Debug-iphonesimulator/EXReaderHost.app';exe=app/'EXReaderHost'
    assert exe.is_file();metadata=plistlib.loads((app/'Info.plist').read_bytes());assert metadata['EXRSourceSHA']==info['source_sha']
    program=dict(sha256=digest(exe),bytes=exe.stat().st_size,mode=exe.stat().st_mode & 0o7777,is_symlink=exe.is_symlink(),observed_before_zip=True,info_plist=metadata)
    with tarfile.open(out/'actual-app.tar.gz','w:gz') as tar:tar.add(app,arcname='EXReaderHost.app')
    installed=pathlib.Path(subprocess.check_output(['xcrun','simctl','get_app_container',udid,'org.exreader.host','app'],text=True).strip())/'EXReaderHost'
    program['installed_sha256']=digest(installed);assert program['installed_sha256']==program['sha256']
    cases=load_results(result)
    run('export-attachments',['xcrun','xcresulttool','export','attachments','--path',result,'--output-path',out/'attachments'])
    print('D18_NATIVE_ROWS_BEGIN',flush=True)
    for line in (out/'native-actions.log').read_text(errors='replace').splitlines():
        if 'D18_ACTION ' in line:print(line,flush=True)
    assert len(cases)==1 and all(c['result']=='Passed' for c in cases),cases
except Exception:
    traceback.print_exc();executions.append(dict(name='environment-or-harness',returncode=1))
finally:
    if observer:observer.server.shutdown()
    report=dict(**info,host=host,seed='d263ce5228838ac90c0a0dc13a5193d4a7739681',sdk_source=SDK_SOURCE,sdk_identities=sdk_identities,configuration=configuration,program=program,test_cases=cases,executions=executions,accepted=bool(program) and all(x['returncode']==0 for x in executions),physical_device=False,physical_keyboard=False,keyboard_focus=False,complete_product=False)
    report['files']={p.relative_to(out).as_posix():dict(bytes=p.stat().st_size,sha256=digest(p)) for p in out.rglob('*') if p.is_file()}
    write(out/'execution.json',report);print('D18_EXECUTION '+json.dumps({k:v for k,v in report.items() if k not in ('files','sdk_identities')}),flush=True)
assert report['accepted']
