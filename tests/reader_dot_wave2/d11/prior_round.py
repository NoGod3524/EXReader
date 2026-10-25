"""Read prior own original evidence only in Actions before another full iteration."""
import datetime,hashlib,io,json,os,pathlib,zipfile
from producer import request
RUN=40225647982;SOURCE='9eb9f65ba258f3e00f6e67f9d090dbce8a879029'
state=json.loads(request('/actions/runs/'+str(RUN)));assert state['status']=='completed' and state['head_sha']==SOURCE and state['run_attempt']==1
out=pathlib.Path('build/d11/prior-round');out.mkdir(parents=True,exist_ok=True);rows=[]
for a in json.loads(request('/actions/runs/'+str(RUN)+'/artifacts?per_page=100'))['artifacts']:
 if not a['name'].startswith('d11-'):continue
 assert not a['expired'] and a['workflow_run']['id']==RUN and a['workflow_run']['head_sha']==SOURCE
 assert datetime.datetime.fromisoformat(a['expires_at'].replace('Z','+00:00'))>datetime.datetime.now(datetime.timezone.utc)
 raw=request('/actions/artifacts/'+str(a['id'])+'/zip');assert len(raw)==a['size_in_bytes'] and 'sha256:'+hashlib.sha256(raw).hexdigest()==a['digest']
 rows.append({k:a[k] for k in ('id','name','size_in_bytes','digest','expires_at')})
 with zipfile.ZipFile(io.BytesIO(raw)) as z:
  for name in z.namelist():
   if name.endswith('-execution.json'):
    value=json.loads(z.read(name))
    for path,want in value.get('files',{}).items():
     found=[n for n in z.namelist() if n==path or n.endswith('/'+path)]
     if len(found)!=1:print('PRIOR_MISSING '+path,flush=True);continue
     data=z.read(found[0]);actual=dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
     if actual!=want:print('PRIOR_BINDING_MISMATCH '+json.dumps(dict(artifact=a['name'],path=path,want=want,actual=actual)),flush=True)
   if name.endswith('-native-actions.log'):
    text=z.read(name).decode(errors='replace');lines=text.splitlines();selected=[]
    for i,line in enumerate(lines):
     if any(word in line for word in ('error:', 'failed', 'XCTAssert', 'caught error', 'D11_ACTION')):selected += lines[max(0,i-4):i+5]
    print('PRIOR_APPLE '+a['name']+'\n'+'\n'.join(selected),flush=True)
    (out/(a['name']+'-native.log')).write_text(text)
   elif name.endswith('verification.json'):
    value=json.loads(z.read(name));print('PRIOR_VERIFY '+json.dumps({k:value.get(k) for k in ('errors','scope_refusal','artifacts')}),flush=True)
(out/'identities.json').write_text(json.dumps(dict(run=RUN,source=SOURCE,attempt=1,artifacts=rows,accepted=False),indent=2))
