"""Unsigned actual native SwiftUI action paths; no release signing or private API."""
import hashlib,json,os,pathlib,subprocess,sys,traceback,shutil,tarfile
assert os.environ.get('GITHUB_ACTIONS')=='true' and sys.platform=='darwin'
host=sys.argv[1];root=pathlib.Path.cwd();out=root/'build/d11';producer=out/(host+'-producer');target=root/'target';executions=[];programs={};destination='platform=macOS';cases=[];sdk_identity={};configuration={}
def run(name,args,timeout=1500):
 env=dict(os.environ,EXR_APPLE_SDK_VERSION='3.41.0',EXR_APPLE_PAGE_THEME='ON',EXR_APPLE_RAW3='OFF')
 with (out/(host+'-'+name+'.log')).open('w') as log:
  try:r=subprocess.run(list(map(str,args)),cwd=target,stdout=log,stderr=subprocess.STDOUT,env=env,timeout=timeout);code=r.returncode
  except subprocess.TimeoutExpired:code=124
 executions.append(dict(name=name,returncode=code));print(json.dumps(executions[-1]),flush=True)
 if code:
  lines=(out/(host+'-'+name+'.log')).read_text(errors='replace').splitlines()
  print('\n'.join(line for line in lines if any(word in line for word in ('error:', 'failed', 'D11_ACTION', 'XCTAssert', 'caught error'))),flush=True)
  print('\n'.join(lines[-90:]),flush=True)
 return code
try:
 sdk=producer/'sdk';assert (sdk/'lib/libexreader.dylib').is_file()
 sys.path.insert(0,str(target/'tests/apple_host'))
 from evidence_contract import validate_sdk
 sdk_identity=json.loads((producer/'sdk-identity.json').read_text())
 validate_sdk(sdk,sdk_identity,'72c6bbdd14ebf3be453fa7f0da81119d52675eb5','40203714083','1','macos' if host=='macos' else 'iphonesimulator')
 resources=out/(host+'-resources');project=out/(host+'-project');derived=out/(host+'-derived')
 assert run('fixtures',[sys.executable,'tests/apple_host/prepare_fixtures.py','--resources',resources])==0
 staging=out/(host+'-tests')/'accessibility/ui';staging.mkdir(parents=True)
 shutil.copyfile(root/'tests/reader_dot_wave2/d11/apple/ActionFocusTests.swift',staging/'ActionFocusTests.swift')
 assert run('project',['ruby','tests/apple_host/make_xcodeproj.rb',project,resources,staging])==0
 pbx=project/'EXReaderHost.xcodeproj/project.pbxproj';pbx_text=pbx.read_text()
 assert 'EXR_APPLE_HOST_REVIEW' not in pbx_text and 'EXR_APPLE_IMPORT_REVIEW' not in pbx_text
 assert 'EXR_APPLE_PAGE_THEME' in pbx_text
 configuration={'test_source_directory':str(staging),'generated_project_sha256':hashlib.sha256(pbx.read_bytes()).hexdigest(),'review_macros_present':False,'page_theme_enabled':True,'signing_allowed':False}
 if host!='macos':
  devices=json.loads(subprocess.check_output(['xcrun','simctl','list','devices','available','--json']))
  prefix='iPhone' if host=='iphone' else 'iPad'
  choices=[(runtime,d['name'],d['udid']) for runtime,rows in devices['devices'].items() for d in rows if d.get('isAvailable') and d['name'].startswith(prefix)]
  runtime,device,udid=max(choices);destination='platform=iOS Simulator,id='+udid
  run('boot',['xcrun','simctl','boot',udid]);assert run('boot-ready',['xcrun','simctl','bootstatus',udid,'-b'])==0
 scheme='EXReaderHost-macOS' if host=='macos' else 'EXReaderHost-iOS'
 run('native-actions',['xcodebuild','test','-project',project/'EXReaderHost.xcodeproj','-scheme',scheme,'-destination',destination,'-derivedDataPath',derived,'-resultBundlePath',out/(host+'.xcresult'),'-parallel-testing-enabled','NO','-test-timeouts-enabled','YES','-default-test-execution-time-allowance','240','-maximum-test-execution-time-allowance','300','EXR_SDK_DIR='+str(sdk),'CODE_SIGNING_ALLOWED=NO','CODE_SIGNING_REQUIRED=NO'],timeout=1800)
 (out/'programs').mkdir(exist_ok=True)
 for bundle in derived.rglob('EXReaderHost.app'):
  with tarfile.open(out/'programs'/(host+'-app.tar.gz'),'w:gz') as tar:tar.add(bundle,arcname='EXReaderHost.app')
  break
 for p in derived.rglob('EXReaderHost'):
  if p.is_file():programs[str(p.relative_to(derived))]={'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size,'mode':p.stat().st_mode & 0o7777,'is_symlink':p.is_symlink(),'observed_before_zip':True}
 sys.path.insert(0,str(target/'tests/apple_host'))
 from collect_evidence import load_results
 cases=load_results(out/(host+'.xcresult'))
 run('export-attachments',['xcrun','xcresulttool','export','attachments','--path',out/(host+'.xcresult'),'--output-path',out/(host+'-attachments')])
 assert len(cases)==2 and all(c['result']=='Passed' for c in cases),cases
except Exception:
 traceback.print_exc();executions.append(dict(name='environment-or-harness',returncode=1))
finally:
 report=dict(harness_sha=os.environ['GITHUB_SHA'],target_sha=subprocess.check_output(['git','-C',str(target),'rev-parse','HEAD'],text=True).strip(),producer=json.loads((out/(host+'-producer-identity.json')).read_text()),sdk_source='edddc463c06ed5731195cdb8f06b2df6dff7699e',sdk_producer_source='72c6bbdd14ebf3be453fa7f0da81119d52675eb5',run_id=os.environ['GITHUB_RUN_ID'],attempt=os.environ['GITHUB_RUN_ATTEMPT'],host=host,destination=destination,programs=programs,executions=executions,accepted=bool(programs) and all(r['returncode']==0 for r in executions),keyboard_accepted=False,complete_product=False,screen_reader_accepted=False,signing_allowed=False)
 report['files']={p.relative_to(out).as_posix():{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in out.rglob('*') if p.is_file() and '-producer' not in str(p.relative_to(out)) and '-derived' not in str(p.relative_to(out)) and p.suffix in ('.json','.png','.log','.txt','.gz')}
 report['test_cases']=cases
 report['sdk_identity']=sdk_identity
 report['configuration']=configuration
 (out/(host+'-execution.json')).write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
assert report['accepted']
