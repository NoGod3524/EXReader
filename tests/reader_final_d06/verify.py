"""Authenticate same-run artifacts, manifests, original evidence hashes and grants."""
import datetime,hashlib,io,json,os,pathlib,zipfile
from producer import request
run=os.environ['GITHUB_RUN_ID'];attempt=os.environ['GITHUB_RUN_ATTEMPT'];sha=os.environ['GITHUB_SHA'];out=pathlib.Path('build/d06');out.mkdir(parents=True,exist_ok=True)
report=dict(harness_sha=sha,run_id=run,attempt=attempt,artifacts=[],platforms={},audit_completed=False,accepted=False,keyboard_accepted=False,complete_product=False,errors=[])
try:
 artifacts=json.loads(request('/actions/runs/'+run+'/artifacts'))['artifacts']
 for host in ('source','windows','gtk'):
  name='d06-'+host+'-'+run+'-'+attempt;matches=[a for a in artifacts if a['name']==name];assert len(matches)==1,(name,len(matches))
  a=matches[0];assert not a['expired'] and a['workflow_run']['head_sha']==sha
  assert datetime.datetime.fromisoformat(a['expires_at'].replace('Z','+00:00'))>datetime.datetime.now(datetime.timezone.utc)
  raw=request('/actions/artifacts/'+str(a['id'])+'/zip');digest=hashlib.sha256(raw).hexdigest();assert len(raw)==a['size_in_bytes'] and a['digest']=='sha256:'+digest
  report['artifacts'].append({k:a[k] for k in ('id','name','size_in_bytes','digest','expires_at')})
  with zipfile.ZipFile(io.BytesIO(raw)) as z:
   names=z.namelist();assert len(names)==len(set(names)) and all('..' not in pathlib.PurePosixPath(n).parts for n in names)
   if host=='source':continue
   names2=[n for n in names if n.endswith(host+'-execution.json')];assert len(names2)==1
   e=json.loads(z.read(names2[0]));assert e['harness_sha']==sha and e['run_id']==run and e['attempt']==attempt
   for path,value in e['files'].items():
    candidates=[n for n in names if n==path or n.endswith('/'+path)];assert len(candidates)==1,path
    data=z.read(candidates[0]);assert len(data)==value['bytes'] and hashlib.sha256(data).hexdigest()==value['sha256'],path
   report['platforms'][host]=e
 report['audit_completed']=True
 for host in ('macOS','iPhone','iPad','Android'):
  report['platforms'][host]=dict(mapping_completed=True,executed_actions=[],passed=[],failed=[],pending=['native event/focus execution','external keyboard','screen reader'],keyboard_accepted=False)
 assert all(report['platforms'][host]['accepted'] for host in ('windows','gtk')),'Native execution failures retained, no acceptance'
except Exception as error:
 report['errors'].append(type(error).__name__+': '+str(error));raise
finally:
 (out/'verification.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
