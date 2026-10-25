"""Same-run ZIP authentication and named native results; retain every refusal."""
import datetime,hashlib,io,json,os,pathlib,re,zipfile
from producer import request
from contract import validate,verify_bytes,selftest,TARGETS
run=os.environ['GITHUB_RUN_ID'];attempt=os.environ['GITHUB_RUN_ATTEMPT'];sha=os.environ['GITHUB_SHA'];out=pathlib.Path('build/d06');out.mkdir(parents=True,exist_ok=True)
report=dict(harness_sha=sha,run_id=run,attempt=attempt,artifacts=[],platforms={},audit_completed=False,accepted=False,keyboard_accepted=False,complete_product=False,errors=[],negative_controls=selftest())
def actions(z,names,host,require_complete):
 rows=[]
 patterns={'windows':('windows-default-keyboard/keyboard-uia.json','windows-text-repeat/report.json','windows-compact/report.json'),'gtk':('gtk-compact/report.json',),'android':('android-search/first-report.json','android-search/reopen-report.json','android-navigation/first-report.json','android-navigation/reopen-report.json','android-focus/report.json')}
 for suffix in patterns.get(host,()):
  found=[n for n in names if n==suffix or n.endswith('/'+suffix)]
  if not found:
   assert not require_complete,'missing named action report: '+suffix
   continue
  assert len(found)==1,suffix
  raw=json.loads(z.read(found[0]));checks=raw.get('checks',[])
  assert raw.get('source_sha',raw.get('harness_sha'))==sha and str(raw.get('run_id'))==run and str(raw.get('attempt'))==attempt,suffix
  if require_complete:
   expected={'windows-default-keyboard/keyboard-uia.json':17,'windows-text-repeat/report.json':8,'windows-compact/report.json':22,'gtk-compact/report.json':45,'android-search/first-report.json':13,'android-search/reopen-report.json':2,'android-navigation/first-report.json':16,'android-navigation/reopen-report.json':2,'android-focus/report.json':10}
   assert len(checks)==expected[suffix] and raw.get('accepted',raw.get('passed')) is True,(suffix,len(checks))
  for index,c in enumerate(checks):
   if isinstance(c,str):c={'name':c,'passed':True}
   name=c.get('name',c.get('action',str(index)))
   rows.append({'group':suffix,'name':name,'index':index,'passed':c.get('passed',c.get('pass',False)),'raw':c})
 if host in ('macos','iphone','ipad'):
  found=[n for n in names if n.endswith(host+'-native-actions.log')]
  if found:
   for index,name in enumerate(re.findall(r'\bD06_ACTION ([^\r\n]+)',z.read(found[0]).decode(errors='replace'),re.M)):
    rows.append({'group':'actual-XCTest-log','name':name,'index':index,'passed':True})
  if require_complete:assert [x['name'] for x in rows]==['shelf','import-fixture-native-entry','open','next-page','search-text-focus','search-result','search-close','directory','records','back-shelf'],'incomplete or duplicate XCTest action steps'
 return rows
try:
 artifacts=json.loads(request('/actions/runs/'+run+'/artifacts'))['artifacts']
 for host in ('source',*TARGETS):
  try:
   name='d06-'+host+'-'+run+'-'+attempt;matches=[a for a in artifacts if a['name']==name];assert len(matches)==1,(name,len(matches))
   a=matches[0];assert not a['expired'] and a['workflow_run']['head_sha']==sha and str(a['workflow_run']['id'])==run
   assert datetime.datetime.fromisoformat(a['expires_at'].replace('Z','+00:00'))>datetime.datetime.now(datetime.timezone.utc)
   raw=request('/actions/artifacts/'+str(a['id'])+'/zip');digest=hashlib.sha256(raw).hexdigest();assert len(raw)==a['size_in_bytes'] and a['digest']=='sha256:'+digest
   report['artifacts'].append({k:a[k] for k in ('id','name','size_in_bytes','digest','expires_at')})
   with zipfile.ZipFile(io.BytesIO(raw)) as z:
    names=z.namelist();assert len(names)==len(set(names)) and all(not pathlib.PurePosixPath(n).is_absolute() and '..' not in pathlib.PurePosixPath(n).parts for n in names)
    if host=='source':continue
    names2=[n for n in names if n.endswith(host+'-execution.json')];assert len(names2)==1
    e=json.loads(z.read(names2[0]));validate(e,host,sha,run,attempt)
    for path,value in e['files'].items():
     path=path.replace('\\','/')
     candidates=[n for n in names if n==path or n.endswith('/'+path)];assert len(candidates)==1,path
     verify_bytes(z.read(candidates[0]),value)
    observed=actions(z,names,host,e['accepted'])
    e.update(mapping_completed=True,executed_actions=observed,passed=[x for x in observed if x['passed']],failed=[x for x in observed if not x['passed']],pending=['complete modal/focus matrix','repeat-submit across all dialogs','screen reader speech','physical external keyboard'])
    if not e['accepted']:
     report['errors'].append(host+': native execution failure')
     for n in names:
      if n.endswith('.log') and not '/profile' in n:
       print('RAW FAILURE LOG '+host+' '+n+'\n'+'\n'.join(z.read(n).decode(errors='replace').splitlines()[-50:]),flush=True)
    report['platforms'][host]=e
  except Exception as error:
   report['errors'].append(host+': '+type(error).__name__+': '+str(error))
 report['audit_completed']=len(report['platforms'])==len(TARGETS)
finally:
 (out/'verification.json').write_text(json.dumps(report,indent=2));print('D06_VERIFICATION '+json.dumps(report),flush=True)
assert not report['errors'],report['errors']
