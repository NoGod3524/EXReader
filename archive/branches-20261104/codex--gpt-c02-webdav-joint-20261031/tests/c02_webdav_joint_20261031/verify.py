import copy,hashlib,importlib.util,io,json,os,stat,subprocess,sys,zipfile
from pathlib import Path,PurePosixPath
from common import *
def need(value,reason):
 if not value:raise AssertionError(reason)
def c02_image(image,uid):
 sys.path.insert(0,str(ROOT/'tests/migration/c02_completion_audit_20261031'))
 from posix_protocols import binding,states
 for row in image.values():
  raw=bytes.fromhex(row['bytes_hex'])
  need(row['uid']==uid and row['nlink']==1 and row['mode']==0o600,'native private owner')
  need(len(raw)==row['size'] and hashlib.sha256(raw).hexdigest()==row['sha256'],'native raw bytes')
 grant=binding(bytes.fromhex(image['binding']['bytes_hex']))
 history=states(bytes.fromhex(image['state']['bytes_hex']))
 need(grant['state']==(image['state']['dev'],image['state']['ino']),'native state identity')
 need(grant['identity']==(image['binding']['dev'],image['binding']['ino']),'native binding identity')
 return grant,history
def cross_check(result,ui):
 need(result['passed'] and result['uid']!=0 and result['source']==os.environ['GITHUB_SHA'],'cross source')
 rows={r['name']:r for r in result['rows']}
 need(len(rows)==6 and all(r['passed'] for r in rows.values()),'six cross groups')
 a=rows['01-refuse-before-recovery']
 need(a['managed_namespace_absent'] and a['observed'].get('managed',{}).get('started') in (None,'0'),'admission before recovery')
 a=rows['02-reader-excludes-migrator']
 need(a['refusal']['returncode']==2 and a['holder_pid']>0 and a['before']==a['after'],'reader custody')
 need(a['target_before']==a['target_after'],'published target preserved')
 grant,history=c02_image(a['before'],result['uid'])
 need(grant['target']==(a['target_before']['dev'],a['target_before']['ino']),'held library native identity')
 a=rows['03-network-and-close-retain-lease']
 need(a['active_refusal']['returncode']==a['idle_refusal']['returncode']==2,'asynchronous custody')
 need(a['closed_observed']['account']['session_present']=='0' and
      a['closed_observed']['account']['closed_generation']==a['closed_observed']['account']['session_generation'],'acknowledged session close')
 need(a['exit']==0 and a['after_final_join']['returncode']==0,'final join before release')
 grant,history=c02_image(a['authority_after'],result['uid'])
 need(grant['target']==(a['target_after']['dev'],a['target_after']['ino']),'published binding native identity')
 need(history[-1]['kind']=='C' and history[-1]['seal']==grant['grant'],'explicit migration CLEAN grant')
 a=rows['04-migrator-pending-survives-death']
 need(a['signal_sent']==9 and a['returncode']==-9 and a['owner_pid']>0,'actual SIGKILL')
 need(a['pending_before']==a['pending_after_death'],'pending retained')
 pending=bytes.fromhex(a['pending_before']['state']['bytes_hex'])
 need(len(pending)>0 and len(pending)%368==0 and pending[-360]==ord('B'),'C02 pending state')
 grant,history=c02_image(a['pending_before'],result['uid'])
 need(history[-1]['kind']=='B' and history[-1]['generation']>grant['generation'],'pending is not a grant')
 need(a['live_refusal'].get('managed',{}).get('started') in (None,'0') and
      a['dead_refusal'].get('managed',{}).get('started') in (None,'0'),'pending forbids cleanup')
 need(a['recovery']['returncode']==0,'explicit C02 recovery')
 a=rows['05-cleanup-pending-never-grants-migration-clean']
 need(a['original_gtk_records']==21 and len(a['authorities'])==3,'independent pending scopes')
 for image in a['authorities'].values():
  grant,history=c02_image(image,result['uid'])
  need(history[-1]['kind'] in ('I','C') and history[-1]['generation']==grant['generation'] and history[-1]['seal']==grant['grant'],'native CLEAN grant')
 retry=next(r for r in ui['records'] if r['name']=='gtk-cleanup-only-retry')
 need(retry['request_count_before']==retry['request_count_after'] and retry['target_before']==retry['target_after'],'cleanup only')
 return dict(passed=True,groups=6,power_loss=False)
def unpack_native(data):
 result={};seen=set()
 with zipfile.ZipFile(io.BytesIO(data)) as z:
  need(len(z.infolist())<=32768 and sum(x.file_size for x in z.infolist())<=768*1024**2,'native ZIP bounds')
  for i in z.infolist():
   n=i.filename;p=PurePosixPath(n)
   need(n and not p.is_absolute() and '..' not in p.parts and '\\' not in n and ':' not in n and '\0' not in n,'native ZIP path')
   need(n.rstrip('/')==str(p) and n.casefold() not in seen and not i.flag_bits&1,'native ZIP duplicate')
   seen.add(n.casefold());need(i.file_size<=256*1024**2,'native ZIP member bound')
   if not i.is_dir():result[n]=z.read(i)
 return result
def main():
 actions();overlay()
 old=ROOT/'tests/gtk_managed_webdav_20261031/verify.py'
 spec=importlib.util.spec_from_file_location('frozen_web_verify',old);w=importlib.util.module_from_spec(spec);spec.loader.exec_module(w)
 target=OUT/'independent';target.mkdir(parents=True,exist_ok=True)
 result=dict(source=os.environ['GITHUB_SHA'],run=os.environ['GITHUB_RUN_ID'],attempt=os.environ['GITHUB_RUN_ATTEMPT'],passed=False,errors=[],artifacts=[])
 def api(path):return subprocess.check_output(['gh','api','repos/NoGod3524/EXReader/'+path],timeout=120)
 try:
  runmeta=json.loads(api('actions/runs/'+os.environ['GITHUB_RUN_ID']))
  need(runmeta['head_sha']==os.environ['GITHUB_SHA'] and runmeta['run_attempt']==1,'run identity')
  jobs=json.loads(api('actions/runs/'+os.environ['GITHUB_RUN_ID']+'/jobs?per_page=100'))['jobs']
  for name in ('admission','c02_linux','gtk','Legacy Windows','Legacy macOS'):
   matches=[j for j in jobs if j['name']==name]
   need(len(matches)==1 and matches[0]['conclusion']=='success','producer job '+name)
  artifacts=json.loads(api('actions/runs/'+os.environ['GITHUB_RUN_ID']+'/artifacts?per_page=100'))['artifacts'];all_files={}
  for role in ('c02-linux','gtk','Windows','macOS'):
   name='joint-'+role+'-'+os.environ['GITHUB_RUN_ID']+'-'+os.environ['GITHUB_RUN_ATTEMPT']
   found=[a for a in artifacts if a['name']==name];need(len(found)==1,'artifact '+role);a=found[0]
   need(not a['expired'] and a['workflow_run']['head_sha']==os.environ['GITHUB_SHA'],'artifact source')
   raw=api('actions/artifacts/'+str(a['id'])+'/zip')
   need(len(raw)==a['size_in_bytes'] and 'sha256:'+hashlib.sha256(raw).hexdigest()==a['digest'],'original ZIP identity')
   (target/(role+'.zip')).write_bytes(raw)
   files=unpack_native(raw) if role=='c02-linux' else w.unpack(raw);all_files[role]=files
   result['artifacts'].append(dict(role=role,id=a['id'],bytes=len(raw),digest=a['digest']))
   if role in ('Windows','macOS'):
    c=json.loads(files['compat.json'])
    need(c['source']==os.environ['GITHUB_SHA'] and c['legacy_default'] and c['tls']['accepted'] and c['session']['accepted'],'legacy result')
    need(c['tls']['count']==(76 if role=='Windows' else 77) and c['session']['count']==20,'legacy original counts')
  gtk=all_files['gtk']
  wf={p[len('gtk-managed/'):]:b for p,b in gtk.items() if p.startswith('gtk-managed/')}
  need(bool(wf),'GTK archive layout')
  result['webdav']=w.check_linux(wf);result['webdav_controls']=w.controls(wf)
  cross=json.loads(gtk['c02-webdav-joint/cross/result.json']);ui=json.loads(wf['ui/results.json'])
  result['cross']=cross_check(cross,ui)
  from negatives import controls
  result['joint_controls']=controls(cross,ui)
  c02=all_files['c02-linux'];receipt=json.loads(c02['c02-result.json'])
  need(receipt['source']==os.environ['GITHUB_SHA'] and receipt['passed'] and receipt['actual_cases']==36 and receipt['repair_cases']==20,'C02 original completion')
  migration=json.loads(c02['migration/migration-result.json'])
  need(migration['source']==os.environ['GITHUB_SHA'] and migration['cases']==36 and migration['failed']==0 and
       len(migration['results'])==36 and all(r['passed'] for r in migration['results']),'original actual migration assertions')
  cuts=[]
  for path,raw in c02.items():
   if path.startswith('migration/') and path.endswith('-observation.json'):
    r=json.loads(raw)
    if 'kill_signal' in r:
     need(r['kill_signal']==9 and r['wait_returncode']==-9 and r['owner_uid']==r['observer_euid'] and r['owner_pid']!=r['observer_pid'],'original native process death')
     cuts.append(r['owner_pid'])
  need(len(cuts)>=20,'original process cuts retained');result['migration_process_cuts']=len(cuts)
  observed=json.loads(c02['native-independent/fstat.json'])
  native_files={p[len('native-independent/original/'):]:b for p,b in c02.items() if p.startswith('native-independent/original/')}
  tool=c02['c02-check/posix-c02-admission-check'];producer=json.loads(native_files['receipt.json'])
  need(producer['tool']['bytes']==len(tool) and producer['tool']['sha256']==hashlib.sha256(tool).hexdigest(),'original native consumer bytes')
  ns=native_decoder()
  result['native']=ns['audit'](native_files,observed['objects'],source=os.environ['GITHUB_SHA'],
    run=os.environ['GITHUB_RUN_ID'],attempt=os.environ['GITHUB_RUN_ATTEMPT'],euid=observed['euid'])
  sys.path.insert(0,str(ROOT/'tests/migration/c02_completion_audit_20261031'))
  import gtk_snapshots
  gf={p[len('c02-webdav-joint/gtk-original/'):]:b for p,b in gtk.items() if p.startswith('c02-webdav-joint/gtk-original/')}
  result['gtk_borrows']=gtk_snapshots.audit_gtk_snapshots(gf)
  result['gtk_borrow_controls']=gtk_snapshots.pending_negative_controls(gf,'',target/'gtk-negative-controls')
  result['passed']=True
 except Exception as e:result['errors'].append(type(e).__name__+': '+str(e))
 finally:
  save(target/'summary.json',result);print('JOINT-INDEPENDENT '+json.dumps(result),flush=True)
 if not result['passed']:raise SystemExit(1)
if __name__=='__main__':main()
