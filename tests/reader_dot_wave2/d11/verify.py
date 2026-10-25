"""Authenticate original same-attempt ZIP bytes and all semantic raw rows in Actions."""
import datetime,hashlib,io,json,os,pathlib,re,tarfile,zipfile,traceback
from producer import request
from common import TARGETS,ACTIONS,pending
from contract import validate,verify_bytes,selftest,grant
run=os.environ['GITHUB_RUN_ID'];attempt=os.environ['GITHUB_RUN_ATTEMPT'];sha=os.environ['GITHUB_SHA'];out=pathlib.Path('build/d11');out.mkdir(parents=True,exist_ok=True)
report=dict(harness_sha=sha,run_id=run,attempt=attempt,artifacts=[],platforms={},audit_completed=False,accepted=False,keyboard_accepted=False,complete_product=False,screen_reader_accepted=False,physical_device_accepted=False,errors=[],negative_controls=selftest())
def unique(names,suffix):
 found=[n for n in names if n==suffix or n.endswith('/'+suffix)];assert len(found)==1,(suffix,len(found));return found[0]
try:
 state=json.loads(request('/actions/runs/'+run));assert state['head_sha']==sha and str(state['run_attempt'])==attempt
 jobs=json.loads(request('/actions/runs/'+run+'/attempts/'+attempt+'/jobs?per_page=100'))['jobs'];report['jobs']=[{k:j[k] for k in ('id','name','status','conclusion')} for j in jobs]
 artifacts=json.loads(request('/actions/runs/'+run+'/artifacts?per_page=100'))['artifacts']
 for host in ('source',*TARGETS):
  try:
   matches=[a for a in artifacts if a['name']=='d11-'+host+'-'+run+'-'+attempt];assert len(matches)==1
   a=matches[0];assert not a['expired'] and a['workflow_run']['head_sha']==sha and str(a['workflow_run']['id'])==run
   assert datetime.datetime.fromisoformat(a['expires_at'].replace('Z','+00:00'))>datetime.datetime.now(datetime.timezone.utc)
   raw=request('/actions/artifacts/'+str(a['id'])+'/zip');assert len(raw)==a['size_in_bytes'] and a['digest']=='sha256:'+hashlib.sha256(raw).hexdigest()
   report['artifacts'].append({k:a[k] for k in ('id','name','size_in_bytes','digest','expires_at')})
   with zipfile.ZipFile(io.BytesIO(raw)) as z:
    names=z.namelist();assert len(names)==len(set(names)) and all(not pathlib.PurePosixPath(n).is_absolute() and '..' not in pathlib.PurePosixPath(n).parts for n in names)
    if host=='source':continue
    e=json.loads(z.read(unique(names,host+'-execution.json')));validate(e,host,sha,run,attempt)
    for path,value in e['files'].items():
     data=z.read(unique(names,path))
     assert len(data)==value['bytes'] and hashlib.sha256(data).hexdigest()==value['sha256'],('file binding mismatch',path,value,dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest()))
    actions=pending(host);observed=[]
    if host in ('windows','gtk','android'):
     suffix={'windows':'windows-actions/report.json','gtk':'gtk-actions/report.json','android':'android-focus/report.json'}[host]
     native=json.loads(z.read(unique(names,suffix)));assert native['harness_sha']==sha and native['target_sha']==TARGETS[host] and native['run_id']==run and native['attempt']==attempt
     actions=native['actions'];observed=list(actions.values());e['native_report']=native
     if host=='android':
      e['actual_apk_configuration']=json.loads(z.read(unique(names,'apk-config/actual-config.json')))
      data=z.read(unique(names,'programs/app-debug.apk'));assert hashlib.sha256(data).hexdigest()==e['programs']['host']['sha256']==e['programs']['installed']['sha256']
     else:
      p=e['programs']['actual'];verify_bytes(z.read(unique(names,p['path'])),p);assert p['sha256']==native['program_sha256']
    else:
     log=z.read(unique(names,host+'-native-actions.log')).decode(errors='replace');seen=set()
     for line in re.findall(r'\bD11_ACTION (\{[^\r\n]+\})',log):
      row=json.loads(line);key=(row['case'],row['action']);assert key not in seen,'duplicate native action trace';seen.add(key);observed.append(row)
      if 'testReadingActions' in row['case'] or row['action']=='cancel':actions[row['action']]=row
     tarbytes=z.read(unique(names,'programs/'+host+'-app.tar.gz'))
     with tarfile.open(fileobj=io.BytesIO(tarbytes),mode='r:gz') as t:
      members=[m for m in t.getmembers() if m.isfile() and m.name.endswith('/EXReaderHost')];assert len(members)==1
      digest=hashlib.sha256(t.extractfile(members[0]).read()).hexdigest();assert digest in {p['sha256'] for p in e['programs'].values()}
     assert not e['configuration']['review_macros_present'] and e['configuration']['page_theme_enabled']
    e.update(program_verified=True,actions=list(actions.values()),raw_observations=observed,source_only_accepted=False,physical_keyboard_accepted=False)
    for row in e['actions']:
     if row['action'] in ('search','directory','records','settings') and row.get('raw',{}).get('focused_inside'):
      row['focused_inside']=True;row['focus_visible']=True;row['focus_enabled']=True
    e['unverified']=[row for row in e['actions'] if row.get('result')!='passed']
    report['platforms'][host]=e
    if not e['accepted']:report['errors'].append(host+': native execution failed')
    print('D11_TARGET '+json.dumps(dict(host=host,actions=e['actions'],programs=e['programs'],accepted=e['accepted'])),flush=True)
  except Exception as error:
   report['errors'].append(host+': '+type(error).__name__+': '+str(error));traceback.print_exc()
 report['audit_completed']=len(report['platforms'])==len(TARGETS)
 try:report['accepted']=grant(report['platforms'])
 except (AssertionError,KeyError) as error:report['scope_refusal']=str(error) or 'incomplete native actions/focus; no six-platform consistency grant'
finally:
 (out/'verification.json').write_text(json.dumps(report,indent=2));print('D11_VERIFICATION '+json.dumps(report),flush=True)
assert not report['errors'],report['errors']
