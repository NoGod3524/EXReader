"""Authenticate retained second-round native logs within Actions, never regrant them."""
import datetime,hashlib,io,json,os,pathlib,zipfile
from producer import request
run=40215565178;source='9f5358bfa4ba8d4de06d254442baf4def4b0fbb3';out=pathlib.Path('build/d06');out.mkdir(parents=True,exist_ok=True)
state=json.loads(request('/actions/runs/'+str(run)));assert state['status']=='completed' and state['head_sha']==source
rows=[]
for a in json.loads(request('/actions/runs/'+str(run)+'/artifacts'))['artifacts']:
 if not any(a['name'].startswith('d06-'+host+'-') for host in ('macos','iphone','ipad')):continue
 assert not a['expired'] and a['workflow_run']['id']==run and a['workflow_run']['head_sha']==source
 assert datetime.datetime.fromisoformat(a['expires_at'].replace('Z','+00:00'))>datetime.datetime.now(datetime.timezone.utc)
 data=request('/actions/artifacts/'+str(a['id'])+'/zip');assert len(data)==a['size_in_bytes'] and 'sha256:'+hashlib.sha256(data).hexdigest()==a['digest']
 row={key:a[key] for key in ('id','name','size_in_bytes','digest','expires_at')};row['logs']={}
 with zipfile.ZipFile(io.BytesIO(data)) as z:
  for name in z.namelist():
   if name.endswith('-native-actions.log'):
    raw=z.read(name);row['logs'][name]={'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'tail':'\n'.join(raw.decode(errors='replace').splitlines()[-100:])};print('RETAINED FAILURE '+a['name']+'\n'+row['logs'][name]['tail'],flush=True)
 rows.append(row)
(out/'prior-failures.json').write_text(json.dumps({'run_id':run,'source_sha':source,'accepted':False,'artifacts':rows},indent=2))
