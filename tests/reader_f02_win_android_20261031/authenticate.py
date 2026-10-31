"""Separate Actions job: authenticate original ZIPs and recompute sender/Android semantics."""
import base64,copy,json,re
from fetch_sender import *
CHECKS={
 'online':['strict_sdk342_shared_provider','fresh_activity_empty_sdk_and_mapping','actual_sync_scans_sender_wire_without_import','corrupt_original_rejected','truncated_original_rejected','cancel_blocked_receive_preserves_empty_library','explicit_receive_imports_exact_original','duplicate_receive_keeps_one_sdk_mapping','actual_online_reader','cancelled_copy_has_no_publication','abandoned_copy_has_no_publication','wrong_original_is_refused','closed_host_sdk_original'],
 'offline':['fresh_process_with_server_stopped_cache_removed','actual_sdk_backed_offline_reader','recovered_copy_hash_and_saved_path','closed_offline_sdk_original'],
 'reopen':['second_process_reuses_verified_reader_copy','actual_second_offline_reader','closed_second_sdk_original']}
def compare(sender,files,receipt):
 r=json.loads(files['report.json']);b=json.loads(files['build.json'])
 need(r['identity']==identity() and r['accepted'] is True,'receiver identity')
 need(r['book_key']==sender['book_key'] and r['original_bytes']==sender['original_bytes'] and r['original_sha256']==sender['original_sha256'],'cross-host key')
 need(r['sender_artifact']==receipt and b['identity']==identity() and b['accepted'] and b['sdk_source']==LOCK['sdk'],'input/build binding')
 for role in ('host','test'):
  raw=files['artifacts/'+role+'.apk'];expected=b['files'][role+'.apk']
  need(len(raw)==expected['bytes'] and sha(raw)==expected['sha256'] and r['runtime_apks'][role]['expected_sha256']==sha(raw),'runtime APK')
 online=r['phases'][0]['observed']['sdk']
 need(len(online)==4 and online[0]=='3.42.0' and online[1]==online[2] and 'libexreader.so' in online[1] and 'libexreader_host.so' in online[3],'runtime SDK342')
 need([p['phase'] for p in r['phases']]==list(CHECKS),'three phases')
 pids=[];books=[]
 for p in r['phases']:
  phase=p['phase'];need(p['identity']==identity() and p['passed'] and p['sdk_version']=='3.42.0','phase identity')
  need([c['name'] for c in p['checks']]==CHECKS[phase] and all(c['passed'] for c in p['checks']) and p['count']==len(CHECKS[phase]),'exact Activity checks')
  native=files['proc-'+phase+'.txt'];pid=int(re.search(rb'^Pid:\s+([0-9]+)',native,re.M)[1]);uid=int(re.search(rb'^Uid:\s+([0-9]+)',native,re.M)[1])
  need(pid>0 and uid>0 and p['pid']==pid and p['uid']==uid and r['processes'][phase]==dict(pid=pid,uid=uid),'observed process')
  pids.append(pid)
  for role in ('host','test'):
   need(p['observed']['runtime_apks'][role]['sha256']==sha(files['artifacts/'+role+'.apk']),'runtime APK')
  opened=p['observed']['open'];readback=p['observed']['sdk_readback'];books.append(readback['book'])
  need(opened['reader_visible']==1 and opened['error'] is False and opened['end']>opened['start'] and opened['book']==readback['book']>0 and opened['source_key']==sender['book_key'] and opened['semantic_frame']['source_key']==sender['book_key'],'actual open')
  raw=files['sdk-'+phase+'.txt']
  need(len(raw)==sender['original_bytes'] and sha(raw)==sender['original_sha256'] and readback['bytes']==len(raw) and readback['sha256']==sha(raw) and readback['books']==1 and readback['book_key']==sender['book_key'],'SDK original')
  need(p['observed']['sdk_worker_terminated'] and p['observed']['native_sessions_after_close']==0,'owner close')
  need(files[phase+'.png'].startswith(b'\x89PNG\r\n\x1a\n') and len(files[phase+'.png'])>128,'actual screenshot')
 need(len(set(pids))==3,'process restart');need(len(set(books))==1,'stable local mapping')
 events=json.loads(files['events.json'])
 need(all(e['authenticated'] and e['seq']==i+1 for i,e in enumerate(events)),'request sequence')
 need(any(e['method']=='GET' and e['path']==sender['object_path'] and e['status']==200 and e['response_bytes']==sender['original_bytes'] and e['response_sha256']==sender['original_sha256'] for e in events),'actual GET')
 need(any(e['path']==sender['object_path'] and e['status']==200 and e['response_bytes']<e['declared_bytes'] for e in events),'actual truncated GET')
 need(any(e['path']==sender['object_path'] and e['status']==200 and e['response_bytes']==sender['original_bytes'] and e['response_sha256']!=sender['original_sha256'] for e in events),'actual corrupt GET')
 need({w['id'] for w in r['wire']}=={w['id'] for w in sender['book_revisions']},'received wire inventory')
 for row in sender['book_revisions']:
  target=next(w for w in r['wire'] if w['id']==row['id']);raw=files[target['path']]
  need(sha(raw)==row['sha256'] and sha(raw)==target['sha256'] and len(raw)==target['bytes'],'received exact Windows wire')
 need(r['eviction']['before']['exists'] and r['eviction']['before']['size']==sender['original_bytes'] and r['eviction']['before']['sha256']==sender['original_sha256'] and not r['eviction']['after']['exists'],'cache really removed')
 need(r['offline']['server_stopped'] and r['offline']['requests_before']==r['offline']['requests_after']==len(events),'offline server stopped')
 raw=files['reader-original.txt'];restored=r['reader_copy']
 need(restored['exists'] and restored['size']==len(raw)==sender['original_bytes'] and restored['sha256']==sha(raw)==sender['original_sha256'],'SDK-backed reader copy')
 saved=r['phases'][1]['observed']['reader_copy']
 need(saved['bytes']==len(raw) and saved['sha256']==sha(raw) and saved['path'].endswith('/reader-originals/'+sender['original_sha256']+'.txt'),'saved verified reader path')
 need(r['F02_accepted'] is False and r['formal']=='95/108','scope')
 return dict(passed=True,checks=sum(len(v) for v in CHECKS.values()),processes=pids,receiver_sdk_id=books[0],same_source_windows=False,physical_device=False,F02_accepted=False)
def current_artifact(role,directory):
 name='f02-android-'+role+'-'+str(identity()['run'])+'-'+str(identity()['attempt'])
 allmeta=api('actions/runs/'+str(identity()['run'])+'/artifacts?per_page=100')['artifacts'];found=[a for a in allmeta if a['name']==name]
 need(len(found)==1,'current artifact '+role);meta=found[0]
 need(not meta['expired'] and meta['workflow_run']['id']==identity()['run'] and meta['workflow_run']['head_sha']==identity()['source'],'current artifact source')
 raw=api('actions/artifacts/'+str(meta['id'])+'/zip',True)
 need(len(raw)==meta['size_in_bytes'] and 'sha256:'+sha(raw)==meta['digest'],'current original ZIP')
 (directory/(role+'.zip')).write_bytes(raw)
 return unpack_current(raw),dict(id=meta['id'],name=name,bytes=len(raw),sha256=sha(raw),identity=identity())
def negatives(sender,w,r,receipt,directory):
 frozen=old_verifier();results=[]
 def altered(files,name,fn):
  out=dict(files);v=json.loads(out[name]);fn(v);out[name]=json.dumps(v).encode();return out
 def run(name,role,base,changed,call,expected):
  try:call(changed)
  except AssertionError as exc:need(str(exc)==expected,'wrong rejection '+name);reason=str(exc)
  else:raise AssertionError('negative accepted '+name)
  delta=[dict(path=p,original_sha256=sha(base[p]),mutated_sha256=sha(b),mutated_bytes=len(b),mutated_base64=base64.b64encode(b).decode()) for p,b in changed.items() if base.get(p)!=b]
  record=dict(name=name,role=role,rejected=True,reason=reason,delta=delta)
  save(directory/(name+'.json'),record);results.append(dict(name=name,rejected=True,reason=reason))
 run('sender-source','sender',w,altered(w,'report.json',lambda v:v['identity'].update(source='0'*40)),frozen.verify_sender,'sender identity')
 run('sender-PUT','sender',w,altered(w,'events.json',lambda v:v.clear()),frozen.verify_sender,'actual PUT')
 run('wire-hash','sender',w,altered(w,'report.json',lambda v:v['book_revisions'][0].update(sha256='0'*64)),frozen.verify_sender,'wire identity')
 cases=[
  ('receiver-attempt','receiver identity',lambda f:altered(f,'report.json',lambda v:v['identity'].update(attempt=999))),
  ('receiver-key','cross-host key',lambda f:altered(f,'report.json',lambda v:v.update(book_key='txt:'+'0'*64))),
  ('receiver-GET','actual GET',lambda f:dict(f,**{'events.json':b'[]'})),
  ('receiver-SDK-bytes','SDK original',lambda f:dict(f,**{'sdk-online.txt':b'changed'})),
  ('receiver-open','actual open',lambda f:altered(f,'report.json',lambda v:v['phases'][0]['observed']['open'].update(reader_visible=0))),
  ('runtime-sdk','runtime SDK342',lambda f:altered(f,'report.json',lambda v:v['phases'][0]['observed']['sdk'].__setitem__(0,'3.41.0'))),
  ('runtime-apk','runtime APK',lambda f:altered(f,'report.json',lambda v:v['runtime_apks']['host'].update(expected_sha256='0'*64))),
  ('cache-eviction','cache really removed',lambda f:altered(f,'report.json',lambda v:v['eviction']['after'].update(exists=True)))]
 for name,reason,mutation in cases:run(name,'receiver',r,mutation(r),lambda f:compare(sender,f,receipt),reason)
 changed=dict(r);v=json.loads(changed['report.json']);pid=v['phases'][0]['pid'];v['phases'][1]['pid']=pid;v['processes']['offline']['pid']=pid;changed['report.json']=json.dumps(v).encode()
 changed['proc-offline.txt']=re.sub(rb'^Pid:\s+[0-9]+',b'Pid:\\t'+str(pid).encode(),changed['proc-offline.txt'],flags=re.M)
 run('process-restart','receiver',r,changed,lambda f:compare(sender,f,receipt),'process restart')
 need(len(results)==12,'twelve semantic controls')
 return results
def provenance_negatives(proof,receipt,sdk_files,directory):
 meta=proof['metadata'][0];aid=receipt['artifact_id'];digest=receipt['sha256'];job=proof['job'];prefix=LOCK['sender']['artifact_prefix']
 results=[]
 def test(name,original,mutated,call,reason):
  try:call(mutated)
  except AssertionError as error:need(str(error)==reason,'wrong provenance rejection '+name)
  else:raise AssertionError('provenance negative accepted '+name)
  save(directory/(name+'.json'),dict(name=name,rejected=True,reason=reason,original=original,mutated=mutated))
  results.append(dict(name=name,rejected=True,reason=reason))
 old=copy.deepcopy(meta);old['id']=LOCK['archived_sender']['sender_artifact'];old['name']=LOCK['archived_sender']['sender_name']
 old['workflow_run'].update(id=LOCK['archived_sender']['run'],head_sha=LOCK['archived_sender']['source'])
 call=lambda value:verify_producer_meta(value,aid,prefix,digest,job)
 test('old-artifact',meta,old,call,'same-source artifact identity')
 changed=copy.deepcopy(meta);changed['workflow_run']['head_sha']='0'*40
 test('cross-source',meta,changed,call,'same-source artifact source')
 changed=copy.deepcopy(meta);changed['name']=prefix+'-'+str(identity()['run'])+'-999'
 test('wrong-attempt',meta,changed,call,'same-source artifact attempt')
 manifest=json.loads(sdk_files['manifest.json']);changed=copy.deepcopy(manifest)
 changed['contract']['sdk_source']='0'*40;changed['fingerprint']=contract_fingerprint(changed['contract'])
 test('wrong-sdk-fingerprint',manifest,changed,lambda value:verify_sdk_contract(value,'windows'),'SDK fingerprint')
 need(len(results)==4,'four provenance controls');return results
def main():
 actions();target=OUT/'independent';target.mkdir(parents=True,exist_ok=True)
 result=dict(identity=identity(),passed=False,errors=[],F02_accepted=False,formal='95/108',same_source_windows=False)
 try:
  meta=api('actions/runs/'+str(identity()['run']))
  need(meta['head_sha']==identity()['source'] and meta['run_attempt']==1,'audit run identity')
  jobs=api('actions/runs/'+str(identity()['run'])+'/attempts/1/jobs?per_page=100')['jobs']
  for name in ('admission','windows','android'):
   found=[j for j in jobs if j['name']==name];need(len(found)==1 and found[0]['conclusion']=='success','upstream '+name)
  inputs,ir=current_artifact('input',target);receiver,rr=current_artifact('receiver',target)
  original,windows,sender,receipt,proof,sdk_raw=current_sender(target)
  need(inputs['sender.zip']==original,'consumed ZIP equals independently fetched Windows ZIP')
  need(inputs['windows-sdk.zip']==sdk_raw,'consumed SDK ZIP equals independently fetched Windows SDK ZIP')
  need(json.loads(inputs['sender-receipt.json'])==receipt,'input receipt same-source producer')
  result['receiver']=compare(sender,receiver,receipt)
  result['controls']=negatives(sender,windows,receiver,receipt,target/'negative-controls')
  sdk_files=unpack_current(sdk_raw)
  result['windows_sdk']=verify_sdk_proof(sdk_files,'windows',sender=windows)
  android_files={p[len('android-sdk-proof/'):]:data for p,data in receiver.items() if p.startswith('android-sdk-proof/')}
  result['android_sdk']=verify_sdk_proof(android_files,'android',receiver=receiver)
  need(json.loads(receiver['build.json'])['sdk_trees']==LOCK['sdk_contract']['sdk_trees'],'Android actual SDK trees')
  need(result['windows_sdk']['fingerprint']==result['android_sdk']['fingerprint']==receipt['sdk_fingerprint'],'cross-host SDK contract')
  result['provenance_controls']=provenance_negatives(proof,receipt,sdk_files,target/'provenance-controls')
  result['receiver']['same_source_windows']=True
  save(target/'producer-proof.json',proof);save(target/'windows-sdk-manifest.json',json.loads(sdk_files['manifest.json']))
  save(target/'android-sdk-manifest.json',json.loads(android_files['manifest.json']))
  result.update(passed=True,same_source_windows=True,input_artifact=ir,receiver_artifact=rr,windows_source=identity()['source'],
   windows_run=identity()['run'],windows_attempt=identity()['attempt'],windows_artifact=receipt,producer_job=proof['job'],
   windows_checks=sender['count'],original_bytes=sender['original_bytes'],original_sha256=sender['original_sha256'],
   original_archives_byte_equal=True,physical_device=False)
 except Exception as exc:result['errors'].append(type(exc).__name__+': '+str(exc))
 finally:
  save(target/'summary.json',result);print('F02_ANDROID_AUTH '+json.dumps(result),flush=True)
 need(result['passed'],'independent verification')
if __name__=='__main__':main()
