"""Authenticate original artifact ZIP in Actions, then fail closed on identity/gaps."""
import datetime,hashlib,io,json,os,urllib.request,zipfile
from pathlib import Path
assert os.environ['GITHUB_ACTIONS']=='true'
run=os.environ['GITHUB_RUN_ID'];attempt=os.environ['GITHUB_RUN_ATTEMPT'];sha=os.environ['GITHUB_SHA'];repo=os.environ['GITHUB_REPOSITORY']
base='https://api.github.com/repos/'+repo
headers={'Authorization':'Bearer '+os.environ['GH_TOKEN'],'Accept':'application/vnd.github+json'}
def get(path,raw=False):
    with urllib.request.urlopen(urllib.request.Request(base+path,headers=headers),timeout=120) as r: data=r.read()
    return data if raw else json.loads(data)
r=get('/actions/runs/'+run);assert r['head_sha']==sha and str(r['run_attempt'])==attempt
jobs=get('/actions/runs/'+run+'/attempts/'+attempt+'/jobs')['jobs'];producer=[j for j in jobs if j['name']=='GTK native scale audit'];assert len(producer)==1 and producer[0]['conclusion']=='success',producer
artifacts=get('/actions/runs/'+run+'/artifacts')['artifacts'];name='reader-final-d03-'+run+'-'+attempt
chosen=[a for a in artifacts if a['name']==name];assert len(chosen)==1
art=chosen[0];assert not art['expired'] and datetime.datetime.fromisoformat(art['expires_at'].replace('Z','+00:00'))>datetime.datetime.now(datetime.timezone.utc)
raw=get('/actions/artifacts/'+str(art['id'])+'/zip',True);digest=hashlib.sha256(raw).hexdigest();assert len(raw)==art['size_in_bytes']
assert art.get('digest')=='sha256:'+digest,art
z=zipfile.ZipFile(io.BytesIO(raw));assert len(z.namelist())==len(set(z.namelist()))
reports=[]
for mode in ('OFF','ON'):
 for config in ('normal','scale2','dark','large'):
  path=mode+'-'+config+'/result.json';d=json.loads(z.read(path));assert d['harness_sha']==sha and d['target_sha']=='9fc407a5cce5a0bfe644a60bd8dc29f84dea6d0e' and d['sdk_source']=='edddc463c06ed5731195cdb8f06b2df6dff7699e' and d['run_id']==run and d['attempt']==attempt and d['compact']==mode
  for rel,m in d['files'].items():
   b=z.read(mode+'-'+config+'/'+rel);assert len(b)==m['bytes'] and hashlib.sha256(b).hexdigest()==m['sha256'],rel
  assert d['snapshots'] and all(s['png_sha256'] for s in d['snapshots'])
  reports.append(dict(configuration=mode+'-'+config,**{k:d[k] for k in ('program_sha256','audit_completed','keyboard_accepted','contrast_accepted','screen_reader_accepted','checks','findings','pending')}))
result=dict(harness_sha=sha,run_id=run,attempt=attempt,producer_job=producer[0]['id'],artifact={k:art[k] for k in ('id','name','size_in_bytes','expires_at')},zip_sha256=digest,zip_verified=True,configurations=reports,accepted=False,audit_completed=all(d['audit_completed'] for d in reports),keyboard_accepted=all(d['keyboard_accepted'] for d in reports),contrast_accepted=False,screen_reader_accepted=False)
Path('verification.json').write_text(json.dumps(result,indent=2));print('D03 VERIFIED '+json.dumps(result),flush=True)
# Audit evidence validity is separate from product acceptance. Incomplete execution is a failure.
assert result['audit_completed'],'One or more phases incomplete; original evidence retained'
