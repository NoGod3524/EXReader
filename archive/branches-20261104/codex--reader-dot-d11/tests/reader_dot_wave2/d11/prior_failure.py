"""Authenticate and preserve D06 original native failure logs, never regrant them."""
import datetime,hashlib,io,json,os,pathlib,zipfile
from producer import request
out=pathlib.Path('build/d11');out.mkdir(parents=True,exist_ok=True);rows=[]
for run,source in [(40215565178,'9f5358bfa4ba8d4de06d254442baf4def4b0fbb3'),(40217793667,'9e01b2b5b079d1058f3206052e21e63c97d32c94')]:
 state=json.loads(request('/actions/runs/'+str(run)));assert state['status']=='completed' and state['head_sha']==source and state['run_attempt']==1
 jobs=json.loads(request('/actions/runs/'+str(run)+'/attempts/1/jobs?per_page=100'))['jobs']
 for a in json.loads(request('/actions/runs/'+str(run)+'/artifacts?per_page=100'))['artifacts']:
  if not any(a['name'].startswith('d06-'+host+'-') for host in ('macos','iphone','ipad','android')):continue
  assert not a['expired'] and a['workflow_run']['id']==run and a['workflow_run']['head_sha']==source
  assert datetime.datetime.fromisoformat(a['expires_at'].replace('Z','+00:00'))>datetime.datetime.now(datetime.timezone.utc)
  data=request('/actions/artifacts/'+str(a['id'])+'/zip');assert len(data)==a['size_in_bytes'] and 'sha256:'+hashlib.sha256(data).hexdigest()==a['digest']
  row={key:a[key] for key in ('id','name','size_in_bytes','digest','expires_at')};row.update(run_id=run,source_sha=source,attempt=1,jobs=[{k:j[k] for k in ('id','name','conclusion')} for j in jobs],accepted=False,logs={})
  with zipfile.ZipFile(io.BytesIO(data)) as z:
   names=z.namelist();assert len(names)==len(set(names)) and all(not pathlib.PurePosixPath(n).is_absolute() and '..' not in pathlib.PurePosixPath(n).parts for n in names)
   for name in names:
    if name.endswith('-native-actions.log') or name.endswith('android-focus.log'):
     raw=z.read(name);dest=out/'prior-logs'/str(run)/pathlib.PurePosixPath(name);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
     row['logs'][name]={'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'retained_path':dest.relative_to(out).as_posix()};print('RETAINED FAILURE '+a['name']+'\n'+'\n'.join(raw.decode(errors='replace').splitlines()[-50:]),flush=True)
  rows.append(row)
(out/'prior-failures.json').write_text(json.dumps({'accepted':False,'artifacts':rows},indent=2))
