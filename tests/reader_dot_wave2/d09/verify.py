"""Authenticate original artifact ZIP in Actions, then fail closed on identity/gaps."""
import datetime,hashlib,io,json,os,re,urllib.request,urllib.error,urllib.parse,zipfile
from pathlib import Path
from contract import validate,refusals,semantic_refusals,scope_ready,modal_focus_ok,CONFIGS,REQUIRED
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
# Reauthenticate D03 final raw ZIP; its presence-only focus result stays revoked.
oldrun='40218375669';oldsha='81a67f582ddfe8906b64e6eef4e7969127415ba8'
old=get('/actions/runs/'+oldrun);assert old['status']=='completed' and old['head_sha']==oldsha and old['run_attempt']==1
oldarts=[x for x in get('/actions/runs/'+oldrun+'/artifacts')['artifacts'] if x['name']=='reader-final-d03-'+oldrun+'-1'];assert len(oldarts)==1
oldart=oldarts[0];oldbytes=get('/actions/artifacts/'+str(oldart['id'])+'/zip',True);oldhash=hashlib.sha256(oldbytes).hexdigest()
assert not oldart['expired'] and len(oldbytes)==oldart['size_in_bytes'] and oldart['digest']=='sha256:'+oldhash
assert oldhash=='a60100c94b4033f236536efb2274cfd4fd38727e51e9fc63e31bd970187d4496'
oldz=zipfile.ZipFile(io.BytesIO(oldbytes));revoked=[]
for mode in ('OFF','ON'):
 for config in ('normal','scale2','dark','large'):
  d=json.loads(oldz.read(mode+'-'+config+'/result.json'))
  c=next(c for c in d['checks'] if c['name']=='records-dialog-focus')
  assert c['passed'] and c['actual'] and all('/frame[EXReader Linux]' in f['path'] and '/dialog[Reading records]' not in f['path'] for f in c['actual'])
  revoked.append(dict(configuration=mode+'-'+config,old_raw_pass=c['passed'],focus=c['actual'],accepted=False,reason='Focus in main frame, not modal descendant; old presence predicate invalid'))
prior=dict(run_id=oldrun,attempt=1,harness_sha=oldsha,artifact=oldart['id'],bytes=len(oldbytes),sha256=oldhash,expires_at=oldart['expires_at'],revoked=revoked,retained_failed_runs=['40215023319','40215548145','40218375669'])
print('D09 PRIOR D03 REVOKED '+json.dumps(prior),flush=True)
jobs=get('/actions/runs/'+run+'/attempts/'+attempt+'/jobs')['jobs'];producer=[j for j in jobs if j['name']=='GTK native scale audit'];assert len(producer)==1
artifacts=get('/actions/runs/'+run+'/artifacts')['artifacts'];name='reader-dot-d09-'+run+'-'+attempt
chosen=[a for a in artifacts if a['name']==name];assert len(chosen)==1
art=chosen[0];assert not art['expired'] and datetime.datetime.fromisoformat(art['expires_at'].replace('Z','+00:00'))>datetime.datetime.now(datetime.timezone.utc)
raw=get('/actions/artifacts/'+str(art['id'])+'/zip',True);digest=hashlib.sha256(raw).hexdigest();assert len(raw)==art['size_in_bytes']
assert art.get('digest')=='sha256:'+digest,art
z=zipfile.ZipFile(io.BytesIO(raw));assert len(z.namelist())==len(set(z.namelist()))
assert len(z.namelist())<20000 and sum(x.file_size for x in z.infolist())<1024*1024*1024
print('D09 ZIP AUTHENTICATED '+json.dumps(dict(id=art['id'],bytes=len(raw),sha256=digest,expires_at=art['expires_at'],producer=producer[0]['conclusion'])),flush=True)
assert producer[0]['conclusion']=='success',producer
for filename in z.namelist():
 b=z.read(filename)
 assert not re.search(rb'(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)',b),'Credential-shaped material found: '+filename
reports=[]
raw_reports={}
programs={}
semantic_negatives=semantic_refusals()
print('D09 SEMANTIC REFUSALS '+json.dumps(semantic_negatives),flush=True)
for mode in ('ON',):
 manifest=json.loads(z.read('programs/'+mode+'/build.json'));binary=z.read('programs/'+mode+'/exreader-linux')
 assert manifest['source_sha']=='803098e9df1a365a9b8e206805c2d179aca8501f' and manifest['sdk_version']=='3.41.0' and manifest['abi']==1
 programs[mode]=hashlib.sha256(binary).hexdigest();assert programs[mode]==manifest['files']['bin/exreader-linux']
 attributes=json.loads(z.read('programs/'+mode+'/program-attributes.json'));assert attributes['sha256']==programs[mode] and attributes['bytes']==len(binary) and attributes['mode'] & 64 and not attributes['is_symlink']
 assert ('EXR_READER_GTK_COMPACT:BOOL='+mode).encode() in z.read('programs/'+mode+'/CMakeCache.txt')
 assert b'EXR_READER_GTK_RAW3:BOOL=ON' in z.read('programs/'+mode+'/CMakeCache.txt')
 commands=json.loads(z.read('programs/'+mode+'/compile_commands.json'));host_commands=[x for x in commands if x['file'].endswith('/examples/linux/reader.c')]
 assert len(host_commands)==1 and 'EXR_READER_GTK_RAW3=1' in host_commands[0]['command'] and 'EXR_READER_GTK_COMPACT=1' in host_commands[0]['command']
 assert 'EXR_LINUX_REVIEW' not in host_commands[0]['command'] and 'EXR_HOST_WORKER_REVIEW' not in host_commands[0]['command']
sdk_header=z.read('programs/sdk-base.h');assert b'#define EXR_VERSION "3.41.0"' in sdk_header and b'#define EXR_CORE_VERSION "3.40.0"' in sdk_header
for mode in ('ON',):
 for config in ('normal','scale2','dark','large'):
  path=mode+'-'+config+'/result.json';d=json.loads(z.read(path));assert d['harness_sha']==sha and d['target_sha']=='803098e9df1a365a9b8e206805c2d179aca8501f' and d['sdk_source']=='edddc463c06ed5731195cdb8f06b2df6dff7699e' and d['run_id']==run and d['attempt']==attempt and d['compact']==mode
  for rel,m in d['files'].items():
   b=z.read(mode+'-'+config+'/'+rel);assert len(b)==m['bytes'] and hashlib.sha256(b).hexdigest()==m['sha256'],rel
  assert d['snapshots'] and all(s['png_sha256'] for s in d['snapshots'])
  for snap in d['snapshots']:
   for ext,key in (('png','png_sha256'),('json','tree_sha256')):
    assert hashlib.sha256(z.read(mode+'-'+config+'/'+snap['name']+'.'+ext)).hexdigest()==snap[key]
  reader=lambda rel:z.read(mode+'-'+config+'/'+rel)
  validate(d,sha,run,attempt,mode,programs[mode],reader)
  for check in d['checks']:
   if check['name'].endswith('-dialog-focus'):assert check['passed']==modal_focus_ok(check['actual']),check
  raw_reports[mode+'-'+config]=d
  negative_count=refusals(d,sha,run,attempt,mode,programs[mode],reader)
  print('D09 NEGATIVE CHECKS '+mode+'-'+config+' '+str(negative_count),flush=True)
  reports.append(dict(configuration=mode+'-'+config,environment=d['environment'],measured_contrast=d.get('measured_contrast'),geometry=[{k:s.get(k) for k in ('name','geometry','screen_pixels','offscreen_candidates')} for s in d['snapshots'] if s['name'] in ('shelf','page-turn','notes-panel','small-window')],**{k:d[k] for k in ('program_sha256','audit_completed','keyboard_accepted','contrast_accepted','screen_reader_accepted','checks','findings','pending')}))
result=dict(harness_sha=sha,run_id=run,attempt=attempt,producer_job=producer[0]['id'],artifact={k:art[k] for k in ('id','name','size_in_bytes','expires_at')},zip_sha256=digest,zip_verified=True,credential_pattern_scan='pass',retained_failures=[prior],semantic_negative_controls=semantic_negatives,programs=programs,configurations=reports,accepted=scope_ready(raw_reports),audit_completed=all(d['audit_completed'] for d in reports),keyboard_accepted=all(d['keyboard_accepted'] for d in reports),contrast_accepted=False,screen_reader_accepted=False)
Path('verification.json').write_text(json.dumps(result,indent=2));print('D09 VERIFIED '+json.dumps({k:v for k,v in result.items() if k not in ('configurations','retained_failures')}),flush=True)
for d in reports:
 print('D09 CONFIG '+json.dumps(dict(configuration=d['configuration'],checks=[dict(name=x['name'],passed=x['passed']) for x in d['checks']],findings=d['findings'],environment=d['environment'])),flush=True)
# Audit evidence validity is separate from product acceptance. Incomplete execution is a failure.
assert result['accepted'],'Required scope failed or incomplete; raw facts and authentication retained, no production repair' 
