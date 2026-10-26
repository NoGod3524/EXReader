"""Build frozen SDK plus exact-source host and independent observer in Actions."""
import hashlib,json,os,pathlib,plistlib,re,shutil,subprocess,sys,tarfile,traceback
assert os.environ.get('GITHUB_ACTIONS')=='true' and sys.platform=='darwin'
root=pathlib.Path.cwd();out=root/'build/d17';out.mkdir(parents=True,exist_ok=True)
sdk=out/'sdk';resources=out/'resources';project=out/'project';derived=out/'derived';commands=[];cases=[];program={};code=1
os.environ.update(EXR_APPLE_SDK_VERSION='3.41.0',EXR_APPLE_PAGE_THEME='ON',EXR_APPLE_RAW3='OFF')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run(name,args,timeout=1800,required=True):
    with (out/(name+'.log')).open('w') as f:
        try:r=subprocess.run(list(map(str,args)),stdout=f,stderr=subprocess.STDOUT,timeout=timeout);rc=r.returncode
        except subprocess.TimeoutExpired:rc=124
    commands.append(dict(name=name,returncode=rc));print(json.dumps(commands[-1]),flush=True)
    if rc:
        lines=(out/(name+'.log')).read_text(errors='replace').splitlines();print('\n'.join(x for x in lines if any(w in x for w in ('error:','failed','D17_ACTION','XCTAssert','caught error'))));print('\n'.join(lines[-60:]),flush=True)
        # Preserve the full native picker hierarchy in job logs too, so a failed
        # final round is diagnosable without another artifact-inspection run.
        printing=False
        for line in lines:
            if 'D17_PICKER_TREE' in line or 'D17_PICKER_CONTROL' in line or 'D17_PICKER_SCREENS' in line:printing=True
            if printing:print(line,flush=True)
            if 'D17_PICKER_TREE END' in line or 'D17_PICKER_CONTROL' in line or 'D17_PICKER_SCREENS' in line:printing=False
        if required:raise RuntimeError(name+' failed '+str(rc))
    return rc
try:
    run('sdk-configure',['cmake','-S','.', '-B',out/'sdk-build','-DCMAKE_BUILD_TYPE=Release','-DEXR_BUILD_TESTS=OFF','-DEXR_BUILD_TOOLS=OFF','-DEXR_ENABLE_AAC=OFF'])
    run('sdk-build',['cmake','--build',out/'sdk-build','--parallel','4'])
    run('sdk-install',['cmake','--install',out/'sdk-build','--prefix',sdk])
    run('products',[sys.executable,'tools/build_apple_product.py','--sdk',sdk,'--target','macos','--build',out/'product-build','--sdk-version','3.41.0'])
    run('sdk-identity',[sys.executable,'tests/apple_host/evidence_contract.py','sdk','--root',sdk,'--platform','macos','--output',out/'sdk-identity.json'])
    run('fixtures',[sys.executable,'tests/apple_host/prepare_fixtures.py','--resources',resources])
    staging=out/'accessibility/ui';staging.mkdir(parents=True);shutil.copyfile(root/'tests/reader_wave3_d17/Actions.swift',staging/'Actions.swift')
    run('project',['ruby','tests/apple_host/make_xcodeproj.rb',project,resources,staging])
    pbx=(project/'EXReaderHost.xcodeproj/project.pbxproj').read_text();assert 'EXR_APPLE_HOST_REVIEW' not in pbx and 'EXR_APPLE_IMPORT_REVIEW' not in pbx and 'EXR_APPLE_PAGE_THEME' in pbx
    observer=out/'sdk-observer';run('observer-build',['xcrun','clang++','-std=c++17','-include','cstring','-include','algorithm',root/'tests/reader_wave3_d17/state.cpp','-I'+str(sdk/'include'),'-L'+str(sdk/'lib'),'-lexreader','-Wl,-rpath,'+str(sdk/'lib'),'-o',observer])
    config=dict(python=sys.executable,observe_script=str(root/'tests/reader_wave3_d17/observe.py'),observer=str(observer),sdk_lib=str(sdk/'lib'),out=str(out),source_sha=os.environ['GITHUB_SHA'],run_id=os.environ['GITHUB_RUN_ID'],attempt=os.environ['GITHUB_RUN_ATTEMPT'],broken=str(resources/'Broken.epub'))
    pathlib.Path('/tmp/exreader-wave3-d17.json').write_text(json.dumps(config));(out/'configuration.json').write_text(json.dumps(config,indent=2))
    code=run('native-actions',['xcodebuild','test','-project',project/'EXReaderHost.xcodeproj','-scheme','EXReaderHost-macOS','-destination','platform=macOS','-derivedDataPath',derived,'-resultBundlePath',out/'native.xcresult','-parallel-testing-enabled','NO','-test-timeouts-enabled','YES','-default-test-execution-time-allowance','600','-maximum-test-execution-time-allowance','900','EXR_SDK_DIR='+str(sdk),'CODE_SIGNING_ALLOWED=NO','CODE_SIGNING_REQUIRED=NO'],required=False)
    sys.path.insert(0,str(root/'tests/apple_host'));from collect_evidence import load_results
    cases=load_results(out/'native.xcresult')
    run('attachments',['xcrun','xcresulttool','export','attachments','--path',out/'native.xcresult','--output-path',out/'attachments'],required=False)
except Exception:traceback.print_exc()
finally:
    app=derived/'Build/Products/Debug/EXReaderHost.app';binary=app/'Contents/MacOS/EXReaderHost'
    if binary.is_file():
        info=plistlib.loads((app/'Contents/Info.plist').read_bytes());assert info['EXRSourceSHA']==os.environ['GITHUB_SHA']
        program=dict(sha256=sha(binary),bytes=binary.stat().st_size,mode=binary.stat().st_mode&0o7777,is_symlink=binary.is_symlink(),source_sha=info['EXRSourceSHA'],before_zip=True)
        with tarfile.open(out/'actual-app.tar.gz','w:gz') as tar:tar.add(app,arcname='EXReaderHost.app')
    report=dict(source_sha=os.environ['GITHUB_SHA'],run_id=os.environ['GITHUB_RUN_ID'],attempt=os.environ['GITHUB_RUN_ATTEMPT'],commands=commands,test_cases=cases,program=program,accepted=code==0 and bool(program) and len(cases)==2 and all(x['result']=='Passed' for x in cases),complete_product=False,keyboard_focus_accepted=False,physical_device_accepted=False)
    report['files']={p.relative_to(out).as_posix():dict(bytes=p.stat().st_size,sha256=sha(p)) for p in out.rglob('*') if p.is_file() and not any(x in p.relative_to(out).parts for x in ('sdk','sdk-build','product-build','derived','native.xcresult','resources','project','accessibility'))}
    (out/'execution.json').write_text(json.dumps(report,indent=2));print('D17_EXECUTION '+json.dumps(report),flush=True)
assert report['accepted'],'native execution incomplete or failed'
