"""Independent Actions-only original-ZIP audit; never grants full P0."""
import copy, hashlib, json, os, pathlib, re, stat, sys, zipfile
SOURCE='c45d01c8fdec63851c5f4539813a8f66885eceb1'
RUN=41022476473
JOB=123952756428
ARTIFACT=12962371134
SIZE=198573
SHA='b23f790c642d04a57dbd22970974ed242541cf334a6ad9d0d903041b54b3415e'
BASE=pathlib.Path('build/publish-independent-audit')
def digest(b): return hashlib.sha256(b).hexdigest()
def obj(path): return json.loads((BASE/path).read_bytes())
def check(value,why): assert value,why
def native_hex(s,n): return isinstance(s,str) and re.fullmatch('[0-9a-f]{'+str(n)+'}',s) is not None
def metadata(run,job,artifact):
 check(run['id']==RUN and run['run_attempt']==1 and run['head_sha']==SOURCE,'run identity')
 check(run['repository']['full_name']=='NoGod3524/EXReader','repository')
 check(run['head_branch']=='codex/p0-win-crossdir-publish-20261030','branch')
 check(run['path']=='.github/workflows/migration-windows-publish-20261030.yml','workflow')
 check(run['status']=='completed' and run['conclusion']=='success','producer terminal success')
 check(job['id']==JOB and job['run_id']==RUN and job['run_attempt']==1 and job['head_sha']==SOURCE,'job identity')
 check(job['status']=='completed' and job['conclusion']=='success','job terminal success')
 required={'Frozen source and qualification identity','Additive scope admission without weakening original guard',
 'Build installed SDK and separately opted-in production record library',
 'Build actual installed consumer and original Windows refusal fixture',
 'Actual NTFS records, full-width collision controls and retained old-format refusals',
 'Build installed publication primitive and separate installed consumer',
 'Original eight Windows recovery capability refusals','Run actions/upload-artifact@v4'}
 steps={s['name']:s for s in job['steps']}
 check(required<=steps.keys() and all(steps[n]['conclusion']=='success' for n in required),'required steps')
 check(artifact['id']==ARTIFACT and artifact['name']=='windows-publish-primitive-'+SOURCE,'artifact identity')
 check(artifact['size_in_bytes']==SIZE and artifact['expired'] is False,'artifact size/expiry')
 check(artifact['digest']=='sha256:'+SHA,'API digest')
 check(artifact['workflow_run']['id']==RUN and artifact['workflow_run']['head_sha']==SOURCE,'artifact source')
def unpack(raw):
 check(len(raw)==SIZE and digest(raw)==SHA,'independently downloaded original ZIP bytes/SHA')
 import io
 result={};seen=set()
 with zipfile.ZipFile(io.BytesIO(raw)) as z:
  check(len(z.infolist())<=1024,'member count')
  total=0
  for item in z.infolist():
   name=item.filename;parts=name.rstrip('/').split('/')
   check(name not in seen and not name.startswith('/') and '\\' not in name and ':' not in name and
         all(p not in ('','.','..') for p in parts),'safe unique member path')
   seen.add(name)
   check(not item.flag_bits&1 and not stat.S_ISLNK(item.external_attr>>16),'no encrypted/symlink members')
   check(item.file_size<=16*1024*1024,'member bound');total+=item.file_size
   check(total<=64*1024*1024,'aggregate bound')
   if not item.is_dir():result[name]=z.read(item)
 return result
def document(files,name):
 check(name in files,'missing '+name)
 return json.loads(files[name])
P='build/publish-evidence/'
R='build/record-evidence/'
REC_LIB='migration-stage/lib/exreader-migration-windows-record.lib'
PUB_LIB='publish-stage/lib/exreader-migration-windows-publish.lib'
def validate(files):
 receipt=document(files,P+'receipt.json')
 check(receipt.get('source')==SOURCE and receipt.get('run')==str(RUN) and receipt.get('attempt')=='1','publish identity')
 check(receipt.get('passed') is True and receipt.get('full_p0_acceptance') is False and receipt.get('physical_power_loss') is False,'publish scope')
 results=receipt.get('results')
 check(isinstance(results,list) and len(results)==3,'three native phases')
 normal=results[0]
 check(normal.get('source')==SOURCE and normal.get('passed') is True and type(normal.get('checks')) is int and normal['checks']==28 and normal.get('failed')==0,'normal 28')
 check(native_hex(normal.get('identity'),48) and native_hex(normal.get('sha256'),64),'full identity/hash')
 check(normal.get('sdk_open_attempts')==0 and normal.get('recovery_admission') is False and normal.get('full_p0_acceptance') is False,'native scope')
 for item,mode in zip(results[1:],('before','after')):
  check(item.get('mode')==mode and item.get('terminated') is True and item.get('retained') is True,'death cut '+mode)
  check(item.get('recovery_admission') is False and item.get('commit_acknowledged') is False,'no crash acknowledgement')
 body=b'private-to-public complete bytes\n'
 for name in (P+'normal/published.bin',P+'before/private/source.bin',P+'after/published.bin'):
  check(files.get(name)==body,'retained native bytes '+name)
 check(digest(body)==normal['sha256'],'normal payload hash')
 for name in (P+'normal/private/source.bin',P+'before/published.bin',P+'after/private/source.bin'):
  check(name not in files,'absent namespace '+name)
 check(files.get(P+'normal/collision.bin')==b'retain','existing destination unchanged')
 check(files.get(P+'normal/private/new-sibling.bin')==b'','explicit child-write tradeoff fixture')
 observed=json.loads(files[P+'normal/stdout.txt'])
 check(observed==normal and files[P+'normal/stderr.txt']==b'','native raw stdout and stderr')
 record=document(files,R+'native.json');rr=document(files,R+'receipt.json')
 check(record.get('source')==SOURCE and record.get('checks')==27 and record.get('expected')==27 and record.get('passed') is True,'old record27')
 check(record.get('identity_bytes')==49 and native_hex(record.get('target'),48),'record full ID')
 check(record.get('sdk_open_attempts')==0 and record.get('recovery_admission') is False and record.get('directory_fsync_equivalent') is False,'record no admission')
 check(rr.get('source')==SOURCE and rr.get('run')==str(RUN) and rr.get('checks')==record and rr.get('full_p0_acceptance') is False,'record receipt identity')
 check(set(rr['files'])=={'target.fixture','record-00.json'},'original record manifest')
 for name,pin in rr['files'].items():
  raw=files.get(R+'private-state/'+name)
  check(raw is not None and len(raw)==pin['bytes'] and digest(raw)==pin['sha256'],'record original manifest '+name)
 wire=document(files,R+'private-state/record-00.json')
 check(wire['magic']=='EXRWINRECOVERY1' and wire['version']==1 and wire['source']==SOURCE,'record format/source')
 check(all(native_hex(wire[k],48) for k in ('root','parent','target')) and wire['target']==record['target'],'wire full IDs')
 canonical=(json.dumps({k:v for k,v in wire.items() if k!='seal'},separators=(',',':'))+'\n').encode()
 check(native_hex(wire.get('seal'),64) and digest(canonical)==wire['seal'],'record canonical seal')
 check(REC_LIB in files and digest(files[REC_LIB])==rr['installed_library_sha256'],'record installed provider hash')
 refusal=document(files,'build/recovery-integration/evidence.json')
 check(refusal.get('source_sha')==SOURCE and refusal.get('run_id')==str(RUN) and refusal.get('attempt')=='1','refusal identity')
 check(refusal.get('passed') is True and refusal.get('expected_cases')==8 and len(refusal['cases'])==8,'original refusal8')
 check(len({c['name'] for c in refusal['cases']})==8,'unique refusal cases')
 check(all(c['passed'] is True and c['checks'] and all(x['passed'] is True for x in c['checks']) for c in refusal['cases']),'all original checks')
 for key in ('product_admission','full_p0_acceptance','physical_cleanup_verified','historical_rollback_proven'):
  check(refusal.get(key) is False,'refusal scope '+key)
 for path in (PUB_LIB,REC_LIB,'publish-stage/include/exreader-migration-candidate/lm_win_publish.h',
              'migration-stage/include/exreader-migration-candidate/lm_recovery_win32_record.h',
              'build/publish-check/publish-consumer.map','build/record-check/record-consumer.map'):
  check(path in files and len(files[path])>0,'installed evidence '+path)
 mapping=files['build/publish-check/publish-consumer.map'].decode('utf-8',errors='strict').lower()
 check(all(s in mapping for s in ('lm_wp_publish_prepared','lm_wp_custody_prepare','exreader-migration-windows-publish','exreader-migration-windows-record')),'installed consumer map bindings')
 header=files['publish-stage/include/exreader-migration-candidate/lm_win_publish.h']
 check(header==pathlib.Path('extras/migration/windows_publish_20261030/include/lm_win_publish.h').read_bytes(),'installed header equals pinned producer source')
 return {'native_controls':28,'death_cuts':['before','after'],'original_record_controls':27,'original_refusal_cases':8,
         'publish_installed_archive_sha256':digest(files[PUB_LIB]),'record_installed_archive_sha256':digest(files[REC_LIB])}
def rejection_controls(files,run,job,artifact,raw):
 passed=[]
 def rejected(name,fn):
  try:fn()
  except (AssertionError,KeyError,ValueError):passed.append(name)
  else:raise AssertionError('negative control accepted: '+name)
 rejected('wrong-original-zip-bytes',lambda:unpack(raw+b'x'))
 bad=copy.deepcopy(run);bad['head_sha']='0'*40
 rejected('wrong-run-source',lambda:metadata(bad,job,artifact))
 for name,path,key,value in (
  ('wrong-publish-source',P+'receipt.json','source','0'*40),
  ('wrong-record-count',R+'native.json','checks',26),
  ('false-refusal-pass','build/recovery-integration/evidence.json','passed',False),
  ('escalated-P0',P+'receipt.json','full_p0_acceptance',True)):
  q=dict(files);d=json.loads(q[path]);d[key]=value;q[path]=json.dumps(d).encode()
  rejected(name,lambda q=q:validate(q))
 q=dict(files);del q[P+'before/private/source.bin']
 rejected('missing-before-original',lambda:validate(q))
 q=dict(files);q[REC_LIB]=q[REC_LIB]+b'x'
 rejected('changed-installed-provider',lambda:validate(q))
 q=dict(files);d=json.loads(q[P+'receipt.json']);d['results'][1]['commit_acknowledged']=True;q[P+'receipt.json']=json.dumps(d).encode()
 rejected('false-crash-acknowledgement',lambda:validate(q))
 check(len(passed)==9,'nine auditor rejection controls')
 return passed
def main():
 check(not sys.flags.optimize,'assertions enabled')
 run,job,artifact=obj('run.json'),obj('job.json'),obj('artifact.json')
 metadata(run,job,artifact)
 raw=(BASE/'original.zip').read_bytes();files=unpack(raw);checks=validate(files)
 controls=rejection_controls(files,run,job,artifact,raw)
 result=dict(passed=True,scope='Windows publication primitive only',producer_source=SOURCE,producer_run=RUN,
  producer_attempt=1,producer_job=JOB,artifact_id=ARTIFACT,original_zip_bytes=len(raw),original_zip_sha256=digest(raw),
  independent_zip_rehash=True,audit_source=os.environ['GITHUB_SHA'],audit_run=os.environ['GITHUB_RUN_ID'],
  audit_attempt=os.environ['GITHUB_RUN_ATTEMPT'],checks=checks,rejection_controls=controls,
  member_manifest={k:{'bytes':len(v),'sha256':digest(v)} for k,v in sorted(files.items())},
  full_p0_acceptance=False,migration_admission=False,physical_power_loss=False,
  limitations=['No separately archived built publication archive: built==installed byte equality is not independently proved.',
   'Process-death cuts prove retained byte state, not restart admission or durable COMMIT acknowledgement.'])
 (BASE/'audit-result.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps({k:v for k,v in result.items() if k!='member_manifest'},indent=2))
if __name__=='__main__':main()
