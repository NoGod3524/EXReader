"""One bounded Actions-only audit of the original iPhone annotation xcresult."""
import datetime,hashlib,json,os,plistlib,re,shutil,stat,struct,subprocess,sys,traceback,zipfile
from pathlib import Path,PurePosixPath
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'build/iphone-annotation-evidence'
SOURCE='94fb236a4a2da87dfbaf4f1dd2a47885d615a230'
BRANCH='codex/gpt-iphone-annotation-evidence-20261031'
RUN=41170540560
ARTIFACT=13031773957
ZIP_BYTES=324049983
ZIP_SHA='7f32490e8692af06650494bbcb1be6c267214f90db1001bbb5a7b016ca66f4e7'
PROGRAM_BYTES=9636784
PROGRAM_SHA='e6ed87bd05b870621bbeff7d9175d88adaaeee22b1f9277a5e823f849ed5fdd6'
CASE='testNativeAnnotationPreviewConfirmCancelAndDuplicate'
TEST_PATH='tests/reader_team24_apple/ui/FeaturesUITests.swift'
OWNED=['.github/workflows/dot-iphone-annotation-evidence-20261031.yml',
 'tools/reader_composition/iphone_annotation_evidence_20261031.py',
 'docs/reader-total-progress/DOT_IPHONE_ANNOTATION_EVIDENCE_20261031.md']
FROZEN={TEST_PATH:'7b1b9d6b3d8093cf34744f3776a5f3b7ce3a1738',
 'tests/reader_team24_apple/run_ui.py':'f7f2e5b388cd0072e9b3379772a0fcc76e3f70c9',
 'tests/reader_team24_apple/verify.py':'99edf12381eef7aaf1aa1a2524dddbe4144d3948',
 'tests/apple_host/collect_evidence.py':'61743374a1ffa526eb4a463f36a0f5af98fced1c'}
ROWS=[
 ('import',[431,432],['native-picker-selected-file-EXReader-annotations.jsonl','native-preview-no-revisions-write','native-picker-valid-preview'],
  'Native Files selection returns to panel; preview status, summary and enabled confirmation are asserted.'),
 ('export',[253,336],['native-jsonl-folder-save','native-markdown-folder-save','jsonl-markdown-content-verified'],
  'Native folder save for JSONL/Markdown; exported status and content-consistency UI assertion.'),
 ('preview',[431,435],['native-preview-no-revisions-write','native-picker-valid-preview'],
  'Preview complete, summary exists; confirmation explicitly enabled on the repeated valid selection.'),
 ('confirm',[453,455],['confirmed-exact-duplicate'],
  'Explicit confirm; imported:1 status and disabled confirmation button.'),
 ('cancel',[451,452],['preview-cancel'],
  'Explicit discard; preview summary no longer exists.'),
 ('duplicate',[426,454],['jsonl-markdown-content-verified','confirmed-exact-duplicate'],
  'Repeat import of this test own exported bookmark; imported:1 status and disabled confirmation. No independent row-count claim.'),
 ('error_refusal',[436,445],['invalid-annotation-rejected','native-picker-invalid-rejected','invalid-import-revision-identity-unchanged'],
  'Direct invalid and native-picked invalid JSONL disable confirmation; revision identity stays equal to baseline.')]
def need(value,code):
 if not value:raise AssertionError(code)
def sha(data):return hashlib.sha256(data).hexdigest()
def digest(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as stream:
  for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
 return h.hexdigest()
def save(path,value):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT,text=True).strip()
def api(path):
 return json.loads(subprocess.check_output(['gh','api','repos/NoGod3524/EXReader/'+path],timeout=120))
def walk(value,path='$'):
 if isinstance(value,dict):
  yield path,value
  for key,item in value.items():yield from walk(item,path+'.'+str(key))
 elif isinstance(value,list):
  for n,item in enumerate(value):yield from walk(item,path+'['+str(n)+']')
def zip_members(archive,budget,readonly_nested=False):
 infos=archive.infolist();need(0<len(infos)<=100000,'zip_entry_budget')
 seen=set();total=0;files={}
 for info in infos:
  name=info.filename;p=PurePosixPath(name)
  need(name and not p.is_absolute() and '..' not in p.parts and '\\' not in name and ':' not in name and '\0' not in name,'zip_path')
  need(name.rstrip('/')==str(p) and name.casefold() not in seen,'zip_duplicate')
  seen.add(name.casefold());total+=info.file_size
  need(not info.flag_bits&1 and info.file_size<=1024**3 and total<=budget,'zip_expansion_budget')
  kind=stat.S_IFMT(info.external_attr>>16)
  need(kind in (0,stat.S_IFDIR,stat.S_IFREG) or (readonly_nested and kind==stat.S_IFLNK),'zip_nonregular')
  if not info.is_dir():files[name]=info
 return files
def tool_json(arguments,name,required=True):
 cmd=['xcrun','xcresulttool',*arguments]
 value=subprocess.run(cmd,capture_output=True,text=True,timeout=90 if required else 45)
 (OUT/(name+'.stdout.json')).write_text(value.stdout)
 (OUT/(name+'.stderr.txt')).write_text(value.stderr)
 save(OUT/(name+'.command.json'),dict(argv=cmd,exit_code=value.returncode))
 if value.returncode:
  if required:raise AssertionError('xcresulttool_'+name)
  return None
 try:return json.loads(value.stdout)
 except ValueError:
  if required:raise AssertionError('xcresulttool_json_'+name)
  return None
def source_admission():
 need(os.environ.get('GITHUB_ACTIONS')=='true' and sys.platform=='darwin','macOS_Actions_only')
 need(os.environ['GITHUB_RUN_ATTEMPT']=='1' and os.environ['GITHUB_EVENT_NAME']=='push'
      and os.environ['GITHUB_REF']=='refs/heads/'+BRANCH,'sole_branch_push_attempt')
 need(git('rev-parse','HEAD')==os.environ['GITHUB_SHA'],'audit_source')
 need(set(git('diff','--name-only',SOURCE,'HEAD').splitlines())==set(OWNED),'exact_three_additive_paths')
 for path,blob in FROZEN.items():need(git('rev-parse','HEAD:'+path)==blob,'frozen_source_'+path)
 text=(ROOT/TEST_PATH).read_text()
 need('continueAfterFailure = false' in text,'stop_on_assertion_failure')
 for _,_,markers,_ in ROWS:
  for marker in markers:
   if marker.startswith('native-picker-selected-file-'):continue
   need(marker in text,'source_checkpoint_'+marker)
 save(OUT/'source-contract.json',dict(source=SOURCE,blobs=FROZEN,catalog_blob='e0c52bf139da2374cf58dbce40ae6c093a59f39d',
  requirement='H.iphone.annotation_exchange',title='iPhone：宿主标注文件导入/导出、预览确认及错误拒绝',
  no_physical_device_addendum_in_catalog=True,rows=ROWS,source_lines=[dict(line=n+1,text=line) for n,line in enumerate(text.splitlines()) if 185<=n+1<=187 or 207<=n+1<=337 or 421<=n+1<=456]))
 save(OUT/'parser-environment.json',dict(tool=subprocess.check_output(['xcrun','--find','xcresulttool'],text=True).strip(),developer_dir=os.environ.get('DEVELOPER_DIR')))
 print('IPHONE_ANNOTATION_SOURCE exact3; frozen original tests; parse only',flush=True)
def metadata():
 run=api('actions/runs/'+str(RUN))
 need(run['id']==RUN and run['head_sha']==SOURCE and run['run_attempt']==1 and run['conclusion']=='failure','original_failed_run_identity')
 jobs=api('actions/runs/'+str(RUN)+'/attempts/1/jobs?per_page=100')['jobs']
 phone=next(j for j in jobs if j['id']==124448286008)
 auth=next(j for j in jobs if j['id']==124461696689)
 need(phone['name']=='Team24 Apple native iphone' and phone['head_sha']==SOURCE and phone['conclusion']=='success','iphone_job_identity')
 need(auth['head_sha']==SOURCE and auth['conclusion']=='failure','retained_aggregate_auth_failure')
 meta=api('actions/artifacts/'+str(ARTIFACT))
 need(meta['id']==ARTIFACT and meta['name']=='team24-apple-native-iphone-41170540560-1' and not meta['expired'],'artifact_identity')
 need(meta['workflow_run']['id']==RUN and meta['workflow_run']['head_sha']==SOURCE
      and meta['size_in_bytes']==ZIP_BYTES and meta['digest']=='sha256:'+ZIP_SHA,'artifact_source_bytes_digest')
 need(datetime.datetime.fromisoformat(meta['expires_at'].replace('Z','+00:00'))>datetime.datetime.now(datetime.timezone.utc),'original_artifact_unexpired')
 save(OUT/'original-metadata.json',dict(run={k:run[k] for k in ('id','head_sha','run_attempt','conclusion')},
  jobs=[{k:j[k] for k in ('id','name','head_sha','status','conclusion')} for j in jobs],artifact=meta))
 return meta
def original_zip():
 path=OUT/'original.zip'
 with path.open('wb') as stream:
  subprocess.run(['gh','api','repos/NoGod3524/EXReader/actions/artifacts/'+str(ARTIFACT)+'/zip'],stdout=stream,check=True,timeout=180)
 need(path.stat().st_size==ZIP_BYTES and digest(path)==ZIP_SHA,'original_ZIP_bytes_hash')
 print('IPHONE_ANNOTATION_ORIGINAL_ZIP '+json.dumps(dict(artifact_id=ARTIFACT,bytes=ZIP_BYTES,sha256=ZIP_SHA)),flush=True)
 return path
def verify_and_extract(path):
 work=OUT/'raw';work.mkdir()
 with zipfile.ZipFile(path) as archive:
  files=zip_members(archive,4*1024**3);result=json.loads(archive.read('result.json'))
  need((result['source_sha'],str(result['run_id']),str(result['attempt']))==(SOURCE,str(RUN),'1') and result['platform']=='iphone'
       and result['accepted'] is True and result['physical_device'] is False,'producer_identity')
  need('iPhone SE' in result['destination']['device'] and result['destination']['runtime'].endswith('iOS-26-2'),'SE3_iOS262_simulator')
  inventory=result['files']
  difference=dict(original_source=SOURCE,artifact_id=ARTIFACT,original_zip_sha256=ZIP_SHA,
   declared_count=len(inventory),actual_file_count=len(files),missing_declared=sorted(set(inventory)-set(files)),
   producer_exclusion="path.name != 'result.json'",unlisted=[])
  for name in sorted(set(files)-set(inventory)):
   h=hashlib.sha256();count=0
   with archive.open(files[name]) as stream:
    for block in iter(lambda:stream.read(1024*1024),b''):h.update(block);count+=len(block)
   difference['unlisted'].append(dict(path=name,bytes=count,sha256=h.hexdigest(),
    excluded_by_producer_basename_rule=PurePosixPath(name).name=='result.json'))
  save(OUT/'inventory-difference.json',difference)
  print('IPHONE_ANNOTATION_INVENTORY '+json.dumps(difference),flush=True)
  need(not difference['missing_declared'],'producer_declared_member_missing')
  for name,item in inventory.items():
   h=hashlib.sha256();count=0
   with archive.open(files[name]) as stream:
    for block in iter(lambda:stream.read(1024*1024),b''):h.update(block);count+=len(block)
   need(count==item['bytes'] and h.hexdigest()==item['sha256'],'original_file_hash_'+name)
  print('IPHONE_ANNOTATION_DECLARED_FILES '+json.dumps(dict(verified=len(inventory),missing=0,unlisted=len(difference['unlisted']))),flush=True)
  phase=next(p for p in result['phases'] if p['mode']=='wave3')
  need(phase['accepted'] is True and phase['expected_cases']==5 and not phase.get('failure') and not phase.get('result_parse_error'),'wave3_producer_status')
  cases=[c for c in phase['cases'] if CASE in c['name']];need(len(cases)==1 and cases[0]['result']=='Passed','original_target_case')
  command=[c for c in result['commands'] if c['role']=='wave3-native-ui']
  need(len(command)==1 and command[0]['exit']==0 and command[0]['argv'][0]=='xcodebuild' and command[0]['argv'][1]=='test','original_wave3_command_exit')
  program=phase['program'];need(program['bytes']==PROGRAM_BYTES and program['sha256']==PROGRAM_SHA and program['bundle_source_sha']==SOURCE
                              and program['bundle_id']=='org.exreader.host' and program['physical_device'] is False,'program_declaration')
  prefix='program-wave3/EXReaderHost.app/'
  raw=archive.read(prefix+'EXReaderHost');info=plistlib.loads(archive.read(prefix+'Info.plist'))
  need(len(raw)==PROGRAM_BYTES and sha(raw)==PROGRAM_SHA and info['EXRSourceSHA']==SOURCE and info['CFBundleIdentifier']=='org.exreader.host','actual_program_and_plist')
  nested=OUT/'program-original.zip';nested.write_bytes(archive.read(program['packaged_app']))
  with zipfile.ZipFile(nested) as app:
   entries=zip_members(app,1024**3,readonly_nested=True)
   for name in ('EXReaderHost.app/EXReaderHost','EXReaderHost.app/Info.plist'):
    need(name in entries and stat.S_IFMT(entries[name].external_attr>>16) in (0,stat.S_IFREG),'nested_program_regular')
   need(app.read('EXReaderHost.app/EXReaderHost')==raw,'nested_packaged_program_equals_actual')
   need(plistlib.loads(app.read('EXReaderHost.app/Info.plist'))['EXRSourceSHA']==SOURCE,'nested_source_identity')
  selected=[n for n in files if n.startswith('wave3.xcresult/')]
  need(bool(selected),'raw_wave3_bundle')
  for name in selected:
   target=work/name;target.parent.mkdir(parents=True,exist_ok=True)
   with archive.open(files[name]) as source,target.open('wb') as dest:shutil.copyfileobj(source,dest)
  log=archive.read('wave3-native-ui.log').decode('utf-8','replace')
  (OUT/'original-wave3-native-ui.log').write_text(log)
 save(OUT/'producer-result.json',result)
 proof=dict(program_bytes=len(raw),program_sha256=sha(raw),inventory_files=len(inventory),
  destination=result['destination'],physical_device=False,producer_steps=cases[0].get('steps'),wave3_command_exit=0)
 save(OUT/'program-and-inventory.json',proof)
 return work/'wave3.xcresult',log,proof
def scoped_log(log):
 lines=log.splitlines()
 starts=[i for i,line in enumerate(lines) if CASE in line and re.search(r'Test Case .+ started',line)]
 ends=[i for i,line in enumerate(lines) if CASE in line and re.search(r'Test Case .+ passed',line)]
 need(len(starts)==len(ends)==1 and starts[0]<ends[0],'single_original_target_invocation')
 block=lines[starts[0]:ends[0]+1]
 forbidden=re.compile(r'(Test Case .+ failed|XCTAssert.*failed|exceeded.*time allowance|test execution.*timed out|Test crashed|Testing failed)',re.I)
 need(not any(forbidden.search(line) for line in block),'no_target_failure_timeout_in_log')
 (OUT/'target-native-ui.log').write_text('\n'.join(block)+'\n')
 return block
def activity_hits(activities,marker):
 hits=[]
 def visit(value,path,inherited=None):
  if isinstance(value,dict):
   times={k:v for k,v in value.items() if any(t in k.lower() for t in ('timestamp','starttime','endtime','startdate','finishdate')) and isinstance(v,(str,int,float))}
   context=times or inherited or {}
   for key,item in value.items():
    if isinstance(item,str) and (item==marker or item.startswith(marker+'_') or ("named '"+marker+"'") in item):
     hits.append(dict(path=path+'.'+key,value=item,time=context))
    visit(item,path+'.'+key,context)
  elif isinstance(value,list):
   for n,item in enumerate(value):visit(item,path+'['+str(n)+']',inherited)
 visit(activities,'$')
 return hits
def attachments(bundle,tree):
 value=subprocess.run(['xcrun','xcresulttool','export','attachments','--path',str(bundle),'--output-path',str(OUT/'attachments')],capture_output=True,text=True,timeout=120)
 (OUT/'attachment-export.stderr.txt').write_text(value.stderr);need(value.returncode==0,'attachment_export')
 groups=json.loads((OUT/'attachments/manifest.json').read_text());need(isinstance(groups,list),'attachment_manifest')
 target=[g for g in groups if CASE in str(g.get('testIdentifier') or g.get('testName') or '')]
 need(len(target)==1,'target_attachment_owner')
 records=[];seen=set()
 pattern=r'(.+)_(?:0|[1-9]\d*)_[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}\.([A-Za-z0-9]+)'
 for item in target[0]['attachments']:
  filename=item['exportedFileName'];need(Path(filename).name==filename and filename not in seen,'attachment_filename');seen.add(filename)
  match=re.fullmatch(pattern,item['suggestedHumanReadableName']);need(match is not None,'attachment_name_envelope')
  role,extension=match.groups();data=(OUT/'attachments'/filename).read_bytes()
  need(data and item.get('isAssociatedWithFailure') is not True,'no_failure_attachment')
  if extension=='png':
   need(data.startswith(b'\x89PNG\r\n\x1a\n') and len(data)>24 and all(x>0 for x in struct.unpack('>II',data[16:24])),'nonempty_actual_screenshot')
  records.append(dict(role=role,file='attachments/'+filename,bytes=len(data),sha256=sha(data),metadata=item,timestamp={k:v for k,v in item.items() if 'timestamp' in k.lower() or k.lower()=='time'}))
 save(OUT/'target-attachments.json',records)
 return records
def audit(bundle,log):
 tree=tool_json(['get','test-results','tests','--path',str(bundle),'--format','json'],'test-tree')
 cases=[(p,n) for p,n in walk(tree) if n.get('nodeType')=='Test Case']
 need(len(cases)==5 and all(n.get('result')=='Passed' for _,n in cases),'raw_wave3_all_cases_passed')
 matched=[(p,n) for p,n in cases if CASE in n.get('name','')]
 need(len(matched)==1,'raw_target_unique');node_path,node=matched[0]
 summary=tool_json(['get','test-results','summary','--path',str(bundle),'--format','json'],'xcresult-summary')
 need(summary.get('failedTests')==0 and not summary.get('testFailures'),'no_hidden_xcresult_failures')
 candidates=[]
 for key in ('nodeIdentifier','testIdentifier','identifier','nodeIdentifierURL'):
  if isinstance(node.get(key),str):candidates.append(node[key])
 candidates+=['FeaturesUITests/'+CASE+'()','EXReaderHostUITests/FeaturesUITests/'+CASE+'()']
 activities=None
 for i,identifier in enumerate(dict.fromkeys(candidates)):
  if i>=5:break
  activities=tool_json(['get','test-results','activities','--path',str(bundle),'--test-id',identifier,'--format','json'],'activities-'+str(i),False)
  if activities is not None:break
 need(activities is not None,'original_target_activities_available')
 save(OUT/'target-activities.json',activities)
 block=scoped_log(log);records=attachments(bundle,tree);mapped=[]
 for category,source_lines,markers,assertion in ROWS:
  evidence=[];missing=[]
  for marker in markers:
   marks=[r for r in records if r['role']==marker and r['file'].endswith('.png')]
   hits=activity_hits(activities,marker)
   logged=[]
   for n,line in enumerate(block):
    if marker in line and ('attachment' in line.lower() or 'screenshot' in line.lower()):
     time=re.search(r't\s*=\s*([0-9.]+)\s*s',line)
     logged.append(dict(line=n+1,text=line,elapsed_seconds=float(time[1]) if time else None))
   timing=any(e.get('time') for e in hits) or any(e['elapsed_seconds'] is not None for e in logged) or any(r['timestamp'] for r in marks)
   if not marks or not hits or not timing:missing.append(dict(marker=marker,screenshots=len(marks),activity_hits=len(hits),timestamp_present=timing))
   evidence.append(dict(marker=marker,attachments=marks,activities=hits,original_log=logged))
  mapped.append(dict(operation=category,covered=not missing,source=dict(path=TEST_PATH,blob=FROZEN[TEST_PATH],lines=source_lines),
   original_assertion=assertion,assertion_basis='kept post-assertion screenshot plus timestamped original activity; single Passed invocation and continueAfterFailure=false',
   evidence=evidence,missing=missing))
 save(OUT/'seven-operations.json',mapped)
 return dict(seven_operations=mapped,raw_case=dict(path=node_path,node=node),raw_summary=summary,
  covered=sum(r['covered'] for r in mapped),all_seven_complete=all(r['covered'] for r in mapped),
  no_hidden_failures=True,original_target_invocations=1)
def main():
 OUT.mkdir(parents=True,exist_ok=False)
 result=dict(accepted=False,evidence_sufficient=False,requirement='H.iphone.annotation_exchange',original_source=SOURCE,
  original_run=RUN,original_attempt=1,artifact_id=ARTIFACT,formal='95/108',catalog_changed=False,physical_device=False,
  full_apple_run_accepted=False,errors=[],audit_source=os.environ.get('GITHUB_SHA'),audit_run=os.environ.get('GITHUB_RUN_ID'),audit_attempt=os.environ.get('GITHUB_RUN_ATTEMPT'))
 try:
  result['stage']='source_admission';source_admission()
  result['stage']='original_metadata';metadata()
  result['stage']='original_zip';path=original_zip()
  result['stage']='inventory_program_bundle';bundle,log,proof=verify_and_extract(path)
  result.update(original_zip_bytes=path.stat().st_size,original_zip_sha256=digest(path),program=proof)
  result['stage']='xcresult_operation_mapping';result.update(audit(bundle,log));result['evidence_sufficient']=result['all_seven_complete']
  result['accepted']=result['evidence_sufficient']
  if not result['accepted']:result['errors'].append('missing_per_operation_original_evidence')
  result['stage']='complete'
 except Exception as error:
  result['errors'].append(str(error) if isinstance(error,AssertionError) else type(error).__name__)
  result['failure_frames']=[dict(function=f.name,line=f.lineno) for f in traceback.extract_tb(error.__traceback__) if Path(f.filename).resolve()==Path(__file__).resolve()]
 finally:
  result['audited_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
  save(OUT/'summary.json',result)
  print('IPHONE_ANNOTATION_AUDIT '+json.dumps(result,ensure_ascii=False),flush=True)
 if not result['accepted']:raise SystemExit(1)
if __name__=='__main__':main()
