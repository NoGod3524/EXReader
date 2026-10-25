"""Same-run original ZIP authentication; product findings cannot grant authentication."""
import copy,hashlib,json,os,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
TARGET=ROOT/'target'
sys.path.insert(0,str(TARGET/'tests/reader_hosts_integration'))
sys.path.insert(0,str(TARGET/'tests/reader_windows_raw3'))
from final import Bundle,fetch,require
import mac_peer
SOURCE='9321de84eb9c8d3d57cafbeaa8b0a28fe2a26a08'
NULL='2a490dc51d514032a2815e802c8b3f48'

def validate(report,manifest):
 require(report['harness_source']==os.environ['GITHUB_SHA'] and report['target_source']==SOURCE and str(report['run_id'])==os.environ['GITHUB_RUN_ID'] and str(report['attempt'])==os.environ['GITHUB_RUN_ATTEMPT'],'report identity')
 expected={x['revision_id']:x for x in manifest['reading_records']};require(len(expected)==11,'original eleven')
 positive=report['positive'];negative=report['null']
 require(len(positive)==2 and len(negative)==2,'two new GUI processes per scope')
 pids=[x['pid'] for x in positive+negative];require(all(type(x)is int and x>0 for x in pids) and len(set(pids))==4,'distinct actual native processes')
 granted=[];unverified=[];failed=[]
 for iteration,p in enumerate(positive):
  require(p['target_source']==SOURCE and p['harness_source']==os.environ['GITHUB_SHA'],'GUI source split')
  require(p['exit_code']==0 and p['history_unchanged'] is True,'GUI unchanged history and clean exit')
  rows=p['records'];require(len(rows)==11 and {x['revision_id'] for x in rows}==set(expected),'complete exact original record ID set')
  for row in rows:
   rid=row['revision_id'];original=expected[rid];require(row['capture']==original['capture'],'original capture changed')
   mode,unit,start,end=map(int,original['capture']['numbers'])
   got=row.get('after',{});oracle=row.get('independent_oracle',{})
   fixed=mode==3 and got.get('fixed')==1 and got.get('page')==unit and got.get('selection_bytes')==end-start
   public=oracle.get('revision_id')==rid and all(oracle.get(k)is True for k in ('actual_owner_READ','found','retained_manifest_capture_equal','fresh_capture_equal','NULL_callback_negative_refused'))
   explicit=row.get('ui_action_executed') is True and '独立原书与当前绘图文档中找到并定位' in row.get('message','')
   actual=fixed and public and explicit and not row.get('failure')
   require(row['accepted'] is actual and row['exact_jump_verified'] is actual,'GUI acceptance not supported by actual observations')
   (granted if actual else failed if row.get('failure') else unverified).append(str(iteration)+':'+rid)
  require(p['accepted'] is all(r['accepted'] for r in rows),'positive acceptance mismatch')
 for n in negative:
  require(n['target_revision']==NULL and n.get('exit_code')==0,'NULL identity/exit')
  actual=all(not v['enabled'] for v in n.get('controls',{}).values()) and set(n.get('controls',{}))=={'220','217','219'} and n.get('navigation_refused')is True and n.get('history_unchanged')is True and n.get('history_after_reopen_actions_unchanged')is True
  require(n['accepted'] is actual,'NULL acceptance not supported')
 allpassed=all(p['accepted'] for p in positive+negative) and not report['failures']
 require(report['accepted'] is allpassed,'aggregate acceptance mismatch')
 return {'exact_fixed_gui_granted':granted,'exact_reflow_or_missing_observation':unverified,'failed_gui':failed,'NULL_process_results':[x['accepted'] for x in negative],'product_accepted':allpassed}

def main():
 require(os.environ.get('GITHUB_ACTIONS')=='true','Actions only')
 runid=os.environ['GITHUB_RUN_ID'];attempt=os.environ['GITHUB_RUN_ATTEMPT'];head=os.environ['GITHUB_SHA'];out=ROOT/'build/d12-auth';out.mkdir(parents=True,exist_ok=True)
 report={'accepted':False,'product_accepted':False,'harness_source':head,'run_id':runid,'attempt':attempt}
 try:
  run=fetch('actions/runs/'+runid);require(run['head_sha']==head and str(run['run_attempt'])==attempt and run['path']=='.github/workflows/reader-dot-d12.yml','own run identity')
  jobs=fetch(f'actions/runs/{runid}/attempts/{attempt}/jobs?per_page=100')['jobs'];producer=[x for x in jobs if x['name']=='windows'];require(len(producer)==1 and producer[0]['status']=='completed' and producer[0]['head_sha']==head,'terminal unique producer job')
  artifacts=fetch('actions/runs/'+runid+'/artifacts?per_page=100')['artifacts'];name=f'd12-{head}-{runid}-{attempt}';matching=[x for x in artifacts if x['name']==name];require(len(matching)==1,'unique own original ZIP');meta=matching[0]
  require(meta['workflow_run']['id']==int(runid) and meta['workflow_run']['head_sha']==head,'own ZIP source/run')
  report.update(artifact=meta,producer_job=producer[0]['id'],producer_conclusion=producer[0]['conclusion'])
  b=Bundle(meta)
  try:
   result=b.report('result.json')
   for path,entry in result['files'].items():
    raw=b.bytes('evidence/'+path,128*1024**2);require(len(raw)==entry['bytes'] and hashlib.sha256(raw).hexdigest()==entry['sha256'],'inventoried raw evidence differs: '+path)
   target=b.report('target-auth.json');require(target['target_source']==SOURCE and target['artifact']['id']==12610050539,'target auth provenance')
   for name,expected in target['programs'].items():require(hashlib.sha256(b.bytes('programs/'+name+'.exe',128*1024**2)).hexdigest()==expected,'actual program identity')
   consumer_hash=hashlib.sha256(b.bytes("consumer/windows-peer-owner.exe",128*1024**2)).hexdigest()
   for index,label in enumerate(("first","reopen")):
    owner=b.report("evidence/oracle-"+label+".json")
    require(owner["source_sha"]==head and str(owner["run_id"])==runid and str(owner["attempt"])==attempt and owner["program_sha256"]==consumer_hash and owner["owner_source_sha256"]==hashlib.sha256((TARGET/"apps/reader/desktop/windows_records_owner.cpp").read_bytes()).hexdigest(),"actual independent consumer provenance")
    require(result["positive"][index]["program_sha256"]==target["programs"]["EXReaderShelfReview"] and result["positive"][index]["oracle_program_sha256"]==consumer_hash,"GUI and oracle executable identities")
   with tempfile.TemporaryDirectory() as tmp:
    proof,manifest,wires,originals,operations=mac_peer.load(Path(tmp)/'mac')
    require(proof==result['mac_proof'],'independently authenticated original Mac proof')
    byid={rid:(data,h) for rid,data,h in operations}
    for row in result['null_original_graph']:
     data,h=byid[row['id']];require(b.bytes('evidence/original-null-wires/'+row['id']+'.json',2*1024**2)==data and row['sha256']==h and row['parents']==json.loads(data)['parents'],'genuine original DB NULL graph bytes')
    require(NULL in {x['id'] for x in result['null_original_graph']},'actual NULL missing')
    scope=validate(result,manifest)
    controls=[]
    for label,mutate in [('missing-record',lambda r:r['positive'][0]['records'].pop()),('forged-target',lambda r:r.update(target_source=head)),('duplicate-process',lambda r:r['null'][0].update(pid=r['positive'][0]['pid'])),('false-total',lambda r:r.update(accepted=not r['accepted']))]:
     bad=copy.deepcopy(result);mutate(bad)
     try:validate(bad,manifest)
     except (ValueError,KeyError,AssertionError):controls.append(label)
     else:raise ValueError('negative control accepted: '+label)
    report.update(scope=scope,negative_controls=controls,accepted=True,product_accepted=scope['product_accepted'])
  finally:b.close()
 except Exception:
  import traceback
  report['failure']=traceback.format_exc()
 finally:
  (out/'authentication.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps(report),flush=True)
 if not report['accepted']:raise SystemExit('D12 original evidence authentication failed')
if __name__=='__main__':main()
