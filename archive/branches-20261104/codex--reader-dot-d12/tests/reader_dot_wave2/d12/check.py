"""Real controls only. Product SQL is read-only; SDK data is public-consumer only."""
import base64,ctypes as C,hashlib,json,os,sqlite3,subprocess,sys,tempfile,traceback
from ctypes import wintypes as W
from pathlib import Path
from prepare import ROOT,TARGET,OUT,SOURCE
sys.path.insert(0,str(TARGET/'tests/reader_windows_account'))
sys.path.insert(0,str(TARGET/'tests/reader_windows_raw3'))
import check_account_ui as account
import mac_peer
U,send,M,ENUM=account.U,account.send,account.M,account.ENUM
BUTTON,ROWS,MESSAGE,BODY,PROGRESS,BOOKMARK,HIGHLIGHT,EDIT,DELETE,RESTORE,OPEN,PREVIOUS,NEXT,REFRESH,RETRY,DISCARD,CANCEL,CLOSE=range(210,228)
NULL='2a490dc51d514032a2815e802c8b3f48'
E=OUT/'evidence'
FONT=TARGET/'build/host-font-cache/Reader.otf'

def save(path,obj):path.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def query(profile,sql,args=()):
 path=profile/'library.sqlite.product.sqlite'
 with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True) as db:return db.execute(sql,args).fetchall()
def retained(profile):return query(profile,'SELECT revision_id,CAST(body_json AS BLOB),body_sha256 FROM reader_revisions ORDER BY revision_id')
def history(profile):
 return {'revisions':[(a,hashlib.sha256(b).hexdigest(),c) for a,b,c in retained(profile)],'outbox':query(profile,'SELECT * FROM reader_outbox ORDER BY rowid')}
def labels(d):
 box=U.GetDlgItem(d,ROWS);rows=[]
 for i in range(send(box,0x18B)):
  n=send(box,0x18A,i);buf=C.create_unicode_buffer(n+1);send(box,0x189,i,C.addressof(buf));rows.append(buf.value)
 return rows
class App(account.Device):
 def __init__(self,*args,**kwargs):
  super().__init__(*args,**kwargs)
  # Initial native shelf refresh can overlap account load; observe the published
  # even shelf serial before opening the account, never retry a dispatched action.
  U.GetPropW.argtypes=[W.HWND,W.LPCWSTR];U.GetPropW.restype=W.HANDLE
  self.wait(lambda:(U.GetPropW(self.control("books"),"EXReaderShelfSnapshot") or 0)>=2 and (U.GetPropW(self.control("books"),"EXReaderShelfSnapshot") or 0)%2==0 and U.IsWindowEnabled(self.control("import")),timeout=90)
  self.wait_idle()
 def record_dialog(self):
  def find():
   found=[]
   @ENUM
   def visit(w,unused):
    p=W.DWORD();U.GetWindowThreadProcessId(w,C.byref(p))
    if p.value==self.process.pid and U.IsWindowVisible(w) and U.GetDlgItem(w,ROWS):found.append(w)
    return True
   U.EnumWindows(visit,0);assert len(found)<=1;return found[0] if found else None
  return self.wait(find)
 def records(self):
  self.wait_idle();send(U.GetDlgItem(self.window,BUTTON),0xF5);d=self.record_dialog();self.record_idle(d);return d
 def record_idle(self,d):
  self.wait(lambda:not U.IsWindowEnabled(U.GetDlgItem(d,CANCEL)),timeout=90);self.wait_idle()
 def close_records(self,d):
  send(U.GetDlgItem(d,CLOSE),0xF5);self.wait(lambda:not U.IsWindow(d));self.wait_idle()
 def frame(self):
  return {'book_id':self.q(10),'page':self.q(11),'fixed':self.q(15),'selection_bytes':self.q(16),'session_book':self.q(19),'status':self.status()}

def receive(label,wires,originals):
 out=E/label;out.mkdir();profile=out/'profile';app=None;server=None
 report={'accepted':False,'harness_source':os.environ['GITHUB_SHA'],'target_source':SOURCE,'program_sha256':sha(OUT/'programs/EXReaderProduct.exe')}
 try:
  with tempfile.TemporaryDirectory(prefix='d12-private-',dir=os.environ['RUNNER_TEMP']) as private:
   server=mac_peer.fixture(Path(private)/'tls',out/'fixed-tls-fixture.py');mac_peer.populate(server,wires,originals)
   user,password=base64.b64decode(server.auth.split(' ',1)[1]).decode().split(':',1)
   app=App(OUT/'programs/EXReaderProduct.exe',FONT,profile);report['pid']=app.process.pid
   send(app.window,0x111,account.ACCOUNT);d=app.account_dialog();app.settle(d)
   app.fill(d,server.url,user,password,False);app.apply(d,'仅本次会话');app.run_sync(d,timeout=300)
   report['detail']=app.detail(d);assert 'FINISHED' in report['detail']
   M.screenshot(d,out/'account.bmp');app.close_account(d)
   app.wait(lambda:len(query(profile,'SELECT book_key FROM reader_local_books'))==len(originals),timeout=120)
   actual={a:(c,b) for a,b,c in retained(profile)}
   assert all(actual.get(a)==(b,c) for a,b,c in wires),'Exact received original wire mismatch'
   report['retained']=[{'id':a,'sha256':b,'bytes':len(c),'parents':json.loads(c)['parents']} for a,b,c in wires]
   report['books']=query(profile,'SELECT book_key,title FROM reader_books ORDER BY book_key')
   app.close();report['exit_code']=app.process.returncode;assert app.process.returncode==0;app=None
   with server.lock:requests=list(server.requests)
   assert requests and all(x['authenticated'] for x in requests)
   shards={x['path'] for x in requests if x['method']=='PROPFIND' and x['path'].startswith('/dav/exreader-sync-v1/revisions/') and len(x['path'].removeprefix('/dav/exreader-sync-v1/revisions/'))==3}
   assert shards=={'/dav/exreader-sync-v1/revisions/%02x/'%i for i in range(256)}
   save(out/'requests.json',requests);report['authenticated_shards']=256
   for p in profile.rglob('*'):
    if p.is_file():
     data=p.read_bytes()
     assert all(secret not in data and secret.decode().encode('utf-16-le') not in data for secret in (password.encode(),server.auth.encode()))
   report['accepted']=True
 except Exception:report['failure']=traceback.format_exc();print(report['failure'],flush=True)
 finally:
  if app:
   try:app.diagnose(out)
   except Exception:pass
   app.close()
  if server:server.close()
  save(out/'receive.json',report);print(json.dumps({'receive':label,**report},ensure_ascii=True),flush=True)
 return profile,report

def oracle(profile,packet,label):
 expected=E/'expected.bin'
 if not expected.exists():subprocess.run([sys.executable,TARGET/'tests/reader_windows_raw3/peer-owner/prepare.py','--packet',packet,'--output',expected],check=True)
 path=E/('oracle-'+label+'.json');program=OUT/'consumer/windows-peer-owner.exe'
 p=subprocess.run([str(program),str(profile),str(packet),str(expected),str(FONT),str(path)],capture_output=True,text=True,encoding='utf-8',timeout=300)
 (E/('oracle-'+label+'.log')).write_text(p.stdout+p.stderr,encoding='utf-8')
 assert p.returncode==0,p.stdout+p.stderr
 result=json.loads(path.read_text());assert result['accepted'] and result['source_sha']==os.environ['GITHUB_SHA'] and result['program_sha256']==sha(program)
 return result

def positive(profile,manifest,wires,iteration,oracle_report):
 app=None;rows=[];out=E/('ui-'+iteration);out.mkdir();byid={rid:json.loads(data) for rid,h,data in wires};before=history(profile)
 result={'accepted':False,'pid':None,'records':rows,'target_source':SOURCE,'harness_source':os.environ['GITHUB_SHA'],'program_sha256':sha(OUT/'programs/EXReaderShelfReview.exe'),'read_only_review_queries':[10,11,15,16,19],'oracle_program_sha256':oracle_report['program_sha256']}
 try:
  app=App(OUT/'programs/EXReaderShelfReview.exe',FONT,profile,existing=True);result['pid']=app.process.pid
  titles=dict(query(profile,'SELECT book_key,title FROM reader_books'))
  for record in manifest['reading_records']:
   rid=record['revision_id'];row={'revision_id':rid,'capture':record['capture'],'kind':record['kind'],'role':record['role'],'accepted':False,'ui_action_executed':False,'exact_jump_verified':False};rows.append(row);d=None
   try:
    send(app.window,0x111,46001);app.open(titles[record['capture']['route'][0]]);app.wait_idle();d=app.records();values=labels(d);row['labels']=values
    payload=byid[rid]['payload']
    if record['kind']=='progress':index=0
    else:
     body=payload['text'];matches=[i for i,v in enumerate(values) if body and body in v];assert len(matches)==1,('not uniquely observable',body,values);index=matches[0]
    box=U.GetDlgItem(d,ROWS);send(box,0x186,index);send(d,0x111,(1<<16)|ROWS,box)
    row['selected_index']=send(box,0x188);assert row['selected_index']==index
    row['enabled']={str(c):bool(U.IsWindowEnabled(U.GetDlgItem(d,c))) for c in (OPEN,EDIT,RESTORE)}
    row['before']=app.frame();M.screenshot(d,out/(rid+'-controls.bmp'))
    assert row['enabled'][str(OPEN)],'Open control disabled'
    send(U.GetDlgItem(d,OPEN),0xF5);row['ui_action_executed']=True;app.record_idle(d)
    row['message']=M.text(U.GetDlgItem(d,MESSAGE));row['after']=app.frame();M.screenshot(app.window,out/(rid+'-frame.bmp'))
    assert '独立原书与当前绘图文档中找到并定位' in row['message'],'Native jump did not confirm resolution'
    expected=[int(x) for x in record['capture']['numbers']]
    row['independent_oracle']=next(x for x in oracle_report['records'] if x['revision_id']==rid)
    row['selection_matches_expected']=row['after']['selection_bytes']==expected[3]-expected[2]
    if not row['selection_matches_expected']:
     row['failure']='Observed selection length mismatch: expected %d, actual %d'%(expected[3]-expected[2],row['after']['selection_bytes'])
    if expected[0]==3:
     row['exact_jump_verified']=row['after']['fixed']==1 and row['after']['page']==expected[1] and row['after']['selection_bytes']==expected[3]-expected[2]
     row['observation_scope']='Actual fixed frame page and selection byte length; independent public SDK exact capture/unique page ID'
    else:
     row['unverified_reason']='Existing read-only review exposes page but not frame range or EPUB part. Native FOUND message alone does not establish exact reflow target.'
    row['accepted']=row['exact_jump_verified']
   except Exception:row['failure']=traceback.format_exc()
   finally:
    if d and U.IsWindow(d):app.close_records(d)
    print(json.dumps({'ui_record':row,'iteration':iteration},ensure_ascii=True),flush=True)
  result['history_unchanged']=history(profile)==before
  assert result['history_unchanged'],'GUI navigation changed product history/outbox'
  result['accepted']=len(rows)==11 and all(x['accepted'] for x in rows)
 except Exception:result['failure']=traceback.format_exc()
 finally:
  if app:app.close();result['exit_code']=app.process.returncode
  save(out/'report.json',result)
 return result

def null_ui(profile,key,iteration):
 out=E/('null-ui-'+iteration);out.mkdir();app=None;result={'accepted':False,'target_revision':NULL,'target_source':SOURCE,'program_sha256':sha(OUT/'programs/EXReaderShelfReview.exe')};before=history(profile)
 try:
  app=App(OUT/'programs/EXReaderShelfReview.exe',FONT,profile,existing=True);result['pid']=app.process.pid
  titles=dict(query(profile,'SELECT book_key,title FROM reader_books'));send(app.window,0x111,46001);app.open(titles[key]);app.wait_idle();d=app.records();values=labels(d);result['labels']=values
  # This isolated profile has exactly one annotation entity: the genuine NULL
  # head and its ancestor. The progress pseudo-row is not a selectable substitute.
  assert len(values)==2,('isolated NULL annotation row',values)
  box=U.GetDlgItem(d,ROWS);send(box,0x186,1);send(d,0x111,(1<<16)|ROWS,box)
  result['selected_index']=send(box,0x188);assert result['selected_index']==1
  result['before']=app.frame();result['controls']={str(c):{'enabled':bool(U.IsWindowEnabled(U.GetDlgItem(d,c))),'label':M.text(U.GetDlgItem(d,c))} for c in (OPEN,EDIT,RESTORE)}
  result['body']=M.text(U.GetDlgItem(d,BODY));M.screenshot(d,out/'controls.bmp')
  # Observe the exposed action, never execute editing or restoration. A disabled
  # native button is not bypassed with WM_COMMAND. Enabled navigation is exercised.
  if result['controls'][str(OPEN)]['enabled']:
   send(U.GetDlgItem(d,OPEN),0xF5);app.record_idle(d);result['navigation_attempted']=True
   result['message']=M.text(U.GetDlgItem(d,MESSAGE));result['after']=app.frame();M.screenshot(d,out/'after-open.bmp')
   result['navigation_refused']='找到并定位' not in result['message'] and result['after']==result['before']
  else:result['navigation_attempted']=False;result['navigation_refused']=True
  if result['controls'][str(EDIT)]['enabled']:
   M.set_text(U.GetDlgItem(d,BODY),'D12 genuine NULL must refuse editing')
   send(U.GetDlgItem(d,EDIT),0xF5);app.record_idle(d)
   result['edit_attempted']=True;result['edit_message']=M.text(U.GetDlgItem(d,MESSAGE))
   result['edit_refused']='操作未确认' in result['edit_message'] and history(profile)==before
   result['after_edit']=app.frame();M.screenshot(d,out/'after-edit.bmp')
  else:result['edit_attempted']=False;result['edit_refused']=True
  result['history_unchanged']=history(profile)==before
  result['unsafe_actions_disabled']=all(not x['enabled'] for x in result['controls'].values())
  result['accepted']=result['unsafe_actions_disabled'] and result['navigation_refused'] and result['edit_refused'] and result['history_unchanged']
  app.close_records(d)
 except Exception:result['failure']=traceback.format_exc()
 finally:
  if app:app.close();result['exit_code']=app.process.returncode
  result['history_after_reopen_actions_unchanged']=history(profile)==before
  save(out/'report.json',result);print(json.dumps({'real_NULL':result,'iteration':iteration},ensure_ascii=True),flush=True)
 return result

def main():
 assert os.environ.get('GITHUB_ACTIONS')=='true' and sys.platform=='win32';E.mkdir(parents=True,exist_ok=False)
 result={'accepted':False,'harness_source':os.environ['GITHUB_SHA'],'target_source':SOURCE,'run_id':os.environ['GITHUB_RUN_ID'],'attempt':os.environ['GITHUB_RUN_ATTEMPT'],'positive':[],'null':[],'physical_device_accepted':False,'screen_reader_accepted':False,'same_source_bidirectional':False,'failures':[]}
 try:
  proof,manifest,wires,originals,operations=mac_peer.load(E/'mac');result['mac_proof']=proof
  save(E/'original-manifest.json',manifest)
  profile,received=receive('positive-receive',wires,originals);result['positive_receive']=received
  if received['accepted']:
   for iteration in ('first','reopen'):
    try:
     owner=oracle(profile,E/'mac/sender',iteration)
     assert {x['revision_id'] for x in owner['records']}=={x['revision_id'] for x in manifest['reading_records']}
     result['positive'].append(positive(profile,manifest,wires,iteration,owner))
    except Exception:result['failures'].append(traceback.format_exc())
  # Materialize byte-identical real original operations rows, not reconstructed JSON.
  mapping={rid:(data,h) for rid,data,h in operations};closure={};visiting=set()
  def visit(rid):
   assert rid not in visiting,'cycle';
   if rid in closure:return
   visiting.add(rid);data,h=mapping[rid];assert hashlib.sha256(data).hexdigest()==h
   for parent in json.loads(data)['parents']:visit(parent)
   visiting.remove(rid);closure[rid]=(data,h)
  visit(NULL);null=json.loads(mapping[NULL][0]);key=null['payload']['book_key'];assert null['payload']['location']['selector']['exact']['base64'] is None
  assert key in originals
  metadata=[(rid,data,h) for rid,(data,h) in mapping.items() if json.loads(data)['entity_kind']=='book' and json.loads(data)['entity_key']==key]
  assert metadata,'real operations book metadata required'
  for rid,data,h in metadata:visit(rid)
  null_wires=[(rid,h,data) for rid,(data,h) in closure.items()]
  wireout=E/'original-null-wires';wireout.mkdir()
  for rid,h,data in null_wires:(wireout/(rid+'.json')).write_bytes(data)
  result['null_original_graph']=[{'id':rid,'sha256':h,'bytes':len(data),'parents':json.loads(data)['parents']} for rid,h,data in null_wires]
  profile,received=receive('null-receive',null_wires,{key:originals[key]});result['null_receive']=received
  if received['accepted']:
   for iteration in ('first','reopen'):result['null'].append(null_ui(profile,key,iteration))
  result['accepted']=len(result['positive'])==2 and len(result['null'])==2 and all(x['accepted'] for x in result['positive']+result['null']) and not result['failures']
 except Exception:result['failures'].append(traceback.format_exc())
 finally:
  # All child logs are closed before the inventory is sealed.
  result['files']={p.relative_to(E).as_posix():{'bytes':p.stat().st_size,'sha256':sha(p)} for p in E.rglob('*') if p.is_file()}
  save(OUT/'result.json',result);print(json.dumps(result,ensure_ascii=True),flush=True)
 if not result['accepted']:raise SystemExit('D12 incomplete or failed; exact per-record and NULL facts retained')
if __name__=='__main__':main()
