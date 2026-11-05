"""Authenticate original artifact ZIP in Actions, then fail closed on identity/gaps."""
import datetime,hashlib,io,json,os,re,urllib.request,urllib.error,urllib.parse,zipfile
from pathlib import Path
from contract import validate,refusals
assert os.environ['GITHUB_ACTIONS']=='true'
run=os.environ['GITHUB_RUN_ID'];attempt=os.environ['GITHUB_RUN_ATTEMPT'];sha=os.environ['GITHUB_SHA'];repo=os.environ['GITHUB_REPOSITORY']
base='https://api.github.com/repos/'+repo
headers={'Authorization':'Bearer '+os.environ['GH_TOKEN'],'Accept':'application/vnd.github+json'}
def get(path,raw=False):
    request=urllib.request.Request(base+path,headers=headers)
    if not raw:
        with urllib.request.urlopen(request,timeout=120) as r:return json.load(r)
    # Reuse the original GTK aggregate's no-credential redirect pattern.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,request,response,code,message,response_headers,new_url):return None
    try:
        urllib.request.build_opener(NoRedirect()).open(request,timeout=60)
        raise AssertionError('artifact ZIP must use its signed redirect')
    except urllib.error.HTTPError as response:
        assert response.code==302;url=response.headers['Location']
    assert urllib.parse.urlsplit(url).scheme=='https'
    with urllib.request.urlopen(url,timeout=120) as r:data=r.read(256*1024*1024+1)
    assert len(data)<=256*1024*1024
    return data
r=get('/actions/runs/'+run);assert r['head_sha']==sha and str(r['run_attempt'])==attempt
# Keep the first environment failure authenticated, separate from this run.
oldrun='40215023319';oldsha='834e9c57be3b9dc4c9da26be0175747250e64d19'
old=get('/actions/runs/'+oldrun);assert old['status']=='completed' and old['head_sha']==oldsha and old['run_attempt']==1
oldarts=get('/actions/runs/'+oldrun+'/artifacts')['artifacts'];oldarts=[x for x in oldarts if x['name']=='reader-final-d03-'+oldrun+'-1'];assert len(oldarts)==1
oldart=oldarts[0];oldbytes=get('/actions/artifacts/'+str(oldart['id'])+'/zip',True);oldhash=hashlib.sha256(oldbytes).hexdigest()
assert not oldart['expired'] and len(oldbytes)==oldart['size_in_bytes'] and oldart['digest']=='sha256:'+oldhash
prior=dict(run_id=oldrun,attempt=1,harness_sha=oldsha,artifact=oldart['id'],bytes=len(oldbytes),sha256=oldhash,expires_at=oldart['expires_at'],reason='Missing xrdb executable during environment readback; actual OFF and ON build succeeded but no host audit ran')
print('D03 RETAINED FAILURE '+json.dumps(prior),flush=True)
oldrun2='40215548145';oldsha2='12bd1f1e0caf939b847804c62369963a46df9563'
old2=get('/actions/runs/'+oldrun2);assert old2['status']=='completed' and old2['head_sha']==oldsha2 and old2['run_attempt']==1
oldarts2=[x for x in get('/actions/runs/'+oldrun2+'/artifacts')['artifacts'] if x['name']=='reader-final-d03-'+oldrun2+'-1'];assert len(oldarts2)==1
oldart2=oldarts2[0];oldbytes2=get('/actions/artifacts/'+str(oldart2['id'])+'/zip',True);oldhash2=hashlib.sha256(oldbytes2).hexdigest()
assert not oldart2['expired'] and len(oldbytes2)==oldart2['size_in_bytes'] and oldart2['digest']=='sha256:'+oldhash2
oldz=zipfile.ZipFile(io.BytesIO(oldbytes2));oldreports=[]
for mode in ('OFF','ON'):
 for config in ('normal','scale2','dark','large'):
  prefix=mode+'-'+config;oldreport=json.loads(oldz.read(prefix+'/result.json'))
  assert oldreport['harness_sha']==oldsha2 and oldreport['run_id']==oldrun2 and oldreport['attempt']=='1'
  oldreports.append(dict(configuration=prefix,audit_completed=oldreport['audit_completed'],program_sha256=oldreport['program_sha256'],failed_checks=[x['name'] for x in oldreport['checks'] if not x['passed']],import_failure_tree_sha256=hashlib.sha256(oldz.read(prefix+'/import-open-failed.json')).hexdigest()))
prior2=dict(run_id=oldrun2,attempt=1,harness_sha=oldsha2,artifact=oldart2['id'],bytes=len(oldbytes2),sha256=oldhash2,expires_at=oldart2['expires_at'],configurations=oldreports,reason='Chooser real import did not finish; downstream reader checks cannot diagnose product. Verifier separately failed signed-redirect authentication with HTTP 401.')
print('D03 RETAINED FAILURE '+json.dumps(prior2),flush=True)
jobs=get('/actions/runs/'+run+'/attempts/'+attempt+'/jobs')['jobs'];producer=[j for j in jobs if j['name']=='GTK native scale audit'];assert len(producer)==1
artifacts=get('/actions/runs/'+run+'/artifacts')['artifacts'];name='reader-final-d03-'+run+'-'+attempt
chosen=[a for a in artifacts if a['name']==name];assert len(chosen)==1
art=chosen[0];assert not art['expired'] and datetime.datetime.fromisoformat(art['expires_at'].replace('Z','+00:00'))>datetime.datetime.now(datetime.timezone.utc)
raw=get('/actions/artifacts/'+str(art['id'])+'/zip',True);digest=hashlib.sha256(raw).hexdigest();assert len(raw)==art['size_in_bytes']
assert art.get('digest')=='sha256:'+digest,art
z=zipfile.ZipFile(io.BytesIO(raw));assert len(z.namelist())==len(set(z.namelist()))
assert len(z.namelist())<20000 and sum(x.file_size for x in z.infolist())<1024*1024*1024
print('D03 ZIP AUTHENTICATED '+json.dumps(dict(id=art['id'],bytes=len(raw),sha256=digest,expires_at=art['expires_at'],producer=producer[0]['conclusion'])),flush=True)
assert producer[0]['conclusion']=='success',producer
for filename in z.namelist():
 b=z.read(filename)
 assert not re.search(rb'(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)',b),'Credential-shaped material found: '+filename
reports=[]
programs={}
for mode in ('OFF','ON'):
 manifest=json.loads(z.read('programs/'+mode+'/build.json'));binary=z.read('programs/'+mode+'/exreader-linux')
 assert manifest['source_sha']=='9fc407a5cce5a0bfe644a60bd8dc29f84dea6d0e' and manifest['sdk_version']=='3.41.0' and manifest['abi']==1
 programs[mode]=hashlib.sha256(binary).hexdigest();assert programs[mode]==manifest['files']['bin/exreader-linux']
 assert ('EXR_READER_GTK_COMPACT:BOOL='+mode).encode() in z.read('programs/'+mode+'/CMakeCache.txt')
sdk_header=z.read('programs/sdk-base.h');assert b'#define EXR_VERSION "3.41.0"' in sdk_header and b'#define EXR_CORE_VERSION "3.40.0"' in sdk_header
for mode in ('OFF','ON'):
 for config in ('normal','scale2','dark','large'):
  path=mode+'-'+config+'/result.json';d=json.loads(z.read(path));assert d['harness_sha']==sha and d['target_sha']=='9fc407a5cce5a0bfe644a60bd8dc29f84dea6d0e' and d['sdk_source']=='edddc463c06ed5731195cdb8f06b2df6dff7699e' and d['run_id']==run and d['attempt']==attempt and d['compact']==mode
  for rel,m in d['files'].items():
   b=z.read(mode+'-'+config+'/'+rel);assert len(b)==m['bytes'] and hashlib.sha256(b).hexdigest()==m['sha256'],rel
  assert d['snapshots'] and all(s['png_sha256'] for s in d['snapshots'])
  for snap in d['snapshots']:
   for ext,key in (('png','png_sha256'),('json','tree_sha256')):
    assert hashlib.sha256(z.read(mode+'-'+config+'/'+snap['name']+'.'+ext)).hexdigest()==snap[key]
  reader=lambda rel:z.read(mode+'-'+config+'/'+rel)
  validate(d,sha,run,attempt,mode,programs[mode],reader)
  negative_count=refusals(d,sha,run,attempt,mode,programs[mode],reader)
  print('D03 NEGATIVE CHECKS '+mode+'-'+config+' '+str(negative_count),flush=True)
  reports.append(dict(configuration=mode+'-'+config,environment=d['environment'],measured_contrast=d.get('measured_contrast'),geometry=[{k:s.get(k) for k in ('name','geometry','screen_pixels','offscreen_candidates')} for s in d['snapshots'] if s['name'] in ('shelf','page-turn','notes-panel','small-window')],**{k:d[k] for k in ('program_sha256','audit_completed','keyboard_accepted','contrast_accepted','screen_reader_accepted','checks','findings','pending')}))
result=dict(harness_sha=sha,run_id=run,attempt=attempt,producer_job=producer[0]['id'],artifact={k:art[k] for k in ('id','name','size_in_bytes','expires_at')},zip_sha256=digest,zip_verified=True,credential_pattern_scan='pass',retained_failures=[prior,prior2],configurations=reports,accepted=False,audit_completed=all(d['audit_completed'] for d in reports),keyboard_accepted=all(d['keyboard_accepted'] for d in reports),contrast_accepted=False,screen_reader_accepted=False)
Path('verification.json').write_text(json.dumps(result,indent=2));print('D03 VERIFIED '+json.dumps(result),flush=True)
# Audit evidence validity is separate from product acceptance. Incomplete execution is a failure.
assert result['audit_completed'],'One or more phases incomplete; original evidence retained'
