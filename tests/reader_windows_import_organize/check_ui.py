"""Actions-only real TLS, native selection, installed readback and product audits.

Inputs and names below are fixed before launch. Production host is never linked
with a test hook; database reads are independent observations, not host reports.
"""
import argparse
import copy
import base64
import ctypes as C
from ctypes import wintypes as W
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import subprocess
import sys
import threading
import traceback
import uuid

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tests/reader_windows_search'))
from check_ui import SearchApp,U,ENUM,send,text,M
from check_keyboard import A
sys.path.insert(0,str(ROOT/'tests/reader_windows_account'))
import check_account_ui as ACCOUNT

CLOUD,BULK,ROWS,MESSAGE,GO,CANCEL,CLOSE,TOP,UP,ACTION,GROUPS,MORE,RESUME,ACK,CLEAN,REPORT=range(240,256)
INPUTS=[('One text.txt','sample.txt'),('Two webpage.html','sample.html'),('Three fiction.fb2','sample.fb2'),
 ('Four EPUB.epub','sample.epub'),('Five document.docx','sample.docx'),('Six richtext.rtf','sample.rtf'),
 ('Seven mobi.mobi','sample.mobi'),('Eight PDF.pdf','pdf-public-text.pdf'),('Nine comic.cbz','comic.cbz')]
REQUIRED=['native-ctrl-shift-i-opens-cloud-picker','configured-account-real-tls-listing','no-implicit-book-selection',
 'real-directory-navigation','format-txt','format-html','format-fb2','format-epub','format-docx','format-rtf','format-mobi','format-pdf','format-cbz',
 'independent-public-sdk-original-readback','duplicate-keeps-one-original-and-one-mapping',
 'download-http-failure-retains-real-receipt-and-cleans','cancel-close-rejects-late-listing','401-no-plaintext-fallback',
 'native-ctrl-shift-o-opens-extended-selection','uia-real-multiple-selection','favorite-only-explicit-selection',
 'completed-journal-reopens-with-original-receipts','real-process-kill-and-original-request-replay',
 'favorite-clear-only-explicit-selection','existing-nested-shelf-add-remove','existing-tag-add-remove','existing-series-add-remove',
 'cancel-preserves-committed-and-unrun-report','resume-uses-retained-original-request',
 'committed-cloud-import-retains-refused-staging-owner','corrupt-cloud-import-retains-refused-staging-owner',
 'cancelled-cloud-import-retains-refused-staging-owner','kill-before-import-reopens-explicit-orphan-cleanup',
 'bulk-kill-before-commit-keeps-exact-request','bulk-retry-after-kill-uses-original-revision',
 'bulk-commit-cleanup-denial-still-reports-committed','bulk-kill-after-commit-replay-does-not-duplicate',
 'concurrent-head-is-explicit-and-unselected-books-stay-unchanged',
 'profile-locks-exclude-second-host-through-owner-reopen','bootstrap-staged-kill-keeps-action-unexecuted',
 'bootstrap-cleanup-denial-does-not-claim-favorite-commit','bootstrap-replay-not-counted-as-favorite-commit',
 'normal-details-intent-is-not-a-bulk-action-receipt','stale-normal-details-recovery-is-explicit-conflict',
 'superseded-uncommitted-bootstrap-recovers-with-current-history',
 'original-inputs-unchanged']

class App(SearchApp,ACCOUNT.Device):
 def io_dialog(self):
  def find():
   found=[]
   @ENUM
   def visit(w,unused):
    pid=W.DWORD();U.GetWindowThreadProcessId(w,C.byref(pid))
    if pid.value==self.process.pid and U.IsWindowVisible(w) and U.GetDlgItem(w,ROWS):found.append(w)
    return True
   U.EnumWindows(visit,0);assert len(found)<=1;return found[0] if found else None
  return self.wait(find)

def main():
 assert os.name=='nt' and os.environ.get('GITHUB_ACTIONS')=='true','Actions only'
 p=argparse.ArgumentParser()
 for name in ('candidate','font','fixtures','cloud-probe','command-consumer','revision-consumer','output'):p.add_argument('--'+name,type=Path,required=True)
 args=p.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
 checks=[];problems=[];screenshots=[];app=None;dav=None;phase='fixtures'
 originals={name:(args.fixtures/fixture).read_bytes() for name,fixture in INPUTS}
 hashes={name:hashlib.sha256(data).hexdigest() for name,data in originals.items()}
 report=dict(accepted=False,source_sha=os.environ['GITHUB_SHA'],run_id=os.environ['GITHUB_RUN_ID'],attempt=os.environ['GITHUB_RUN_ATTEMPT'],
  checks=checks,problems=problems,inputs=hashes,screenshots=screenshots,transport='SendInput+UIAutomation+Win32',
  complete_product=False,performance_accepted=False,screen_reader_accepted=False)
 def record(name,condition=True):
  assert condition,name
  assert name not in checks;checks.append(name);print(json.dumps({'name':name,'pass':True}),flush=True)
 def sql(query,values=(),product=True):
  with sqlite3.connect(str(app.db)+('.product.sqlite' if product else '')) as db:return db.execute(query,values).fetchall()
 def counts():return sql('SELECT (SELECT count(*) FROM reader_revisions),(SELECT count(*) FROM reader_outbox)')[0]
 def launch(existing=False):
  value=App(args.candidate.resolve(),args.font.resolve(),out/'profile',existing=existing)
  value.wait_initial_shelf();value.wait_idle();return value
 def settle(d):app.wait(lambda:not U.IsWindowEnabled(U.GetDlgItem(d,CANCEL)),timeout=120)
 def show(mode):
  app.wait_idle();U.SetForegroundWindow(app.window);A.tap(ord('I' if mode==CLOUD else 'O'),(A.VK_CONTROL,A.VK_SHIFT))
  d=app.io_dialog();settle(d);return d
 def close(d):
  send(U.GetDlgItem(d,CLOSE),0xF5);app.wait(lambda:not U.IsWindow(d));app.wait_idle()
 def press(d,id):
  send(U.GetDlgItem(d,id),0xF5);settle(d);return text(U.GetDlgItem(d,MESSAGE))
 def labels(d,id=ROWS):
  box=U.GetDlgItem(d,id);values=[]
  for i in range(send(box,0x18B)):
   n=send(box,0x18A,i);buf=C.create_unicode_buffer(n+1);send(box,0x189,i,C.addressof(buf));values.append(buf.value)
  return values
 def choose(d,label,id=ROWS):
  values=labels(d,id);row=next(i for i,value in enumerate(values) if label in value)
  send(U.GetDlgItem(d,id),0x186,row);return row
 def select_books(d,n=2,start=0):
  items=[item for item in A.auto.ControlFromHandle(U.GetDlgItem(d,ROWS)).GetChildren() if item.ControlTypeName=='ListItemControl']
  items=items[start:start+n];items[0].GetSelectionItemPattern().Select()
  for item in items[1:]:item.GetSelectionItemPattern().AddToSelection()
  assert send(U.GetDlgItem(d,ROWS),0x190)==n
  return [item.Name for item in items[:n]]
 def action(d,value):
  send(U.GetDlgItem(d,ACTION),0x14E,value);send(d,0x111,(1<<16)|ACTION,U.GetDlgItem(d,ACTION));settle(d)
 def ack(d):
  assert U.IsWindowEnabled(U.GetDlgItem(d,ACK));press(d,ACK)
 def group(kind,name,parent='-'):
  filename=out/(name+'.txt');filename.write_text(name,encoding='utf-8')
  result=subprocess.run([str(args.command_consumer.resolve()),'group',str(app.db)+'.product.sqlite','-','-',str(kind),'0','-',str(filename),parent,'0'],capture_output=True,text=True,encoding='utf-8',timeout=60)
  assert result.returncode==0,result.stderr
  value=json.loads(result.stdout);assert value['status']==0 and value['created']==1,value
  return value['key']
 def shot(d,name):M.screenshot(d,out/name);screenshots.append(name)
 kernel=C.WinDLL('kernel32',use_last_error=True)
 U.ShowWindow.argtypes=[W.HWND,C.c_int];U.ShowWindow.restype=W.BOOL
 U.IsIconic.argtypes=[W.HWND];U.IsIconic.restype=W.BOOL
 kernel.OpenThread.argtypes=[W.DWORD,W.BOOL,W.DWORD];kernel.OpenThread.restype=W.HANDLE
 kernel.SuspendThread.argtypes=[W.HANDLE];kernel.SuspendThread.restype=W.DWORD
 kernel.ResumeThread.argtypes=[W.HANDLE];kernel.ResumeThread.restype=W.DWORD
 kernel.CloseHandle.argtypes=[W.HANDLE];kernel.CloseHandle.restype=W.BOOL
 kernel.CreateFileW.argtypes=[W.LPCWSTR,W.DWORD,W.DWORD,C.c_void_p,W.DWORD,W.DWORD,W.HANDLE];kernel.CreateFileW.restype=W.HANDLE
 kernel.WaitForSingleObject.argtypes=[W.HANDLE,W.DWORD];kernel.WaitForSingleObject.restype=W.DWORD
 kernel.GetThreadTimes.argtypes=[W.HANDLE,C.POINTER(W.FILETIME),C.POINTER(W.FILETIME),C.POINTER(W.FILETIME),C.POINTER(W.FILETIME)];kernel.GetThreadTimes.restype=W.BOOL
 class ThreadEntry(C.Structure):
  _fields_=[('size',W.DWORD),('usage',W.DWORD),('id',W.DWORD),('owner',W.DWORD),('base',W.LONG),('delta',W.LONG),('flags',W.DWORD)]
 kernel.CreateToolhelp32Snapshot.argtypes=[W.DWORD,W.DWORD];kernel.CreateToolhelp32Snapshot.restype=W.HANDLE
 kernel.Thread32First.argtypes=[W.HANDLE,C.POINTER(ThreadEntry)];kernel.Thread32First.restype=W.BOOL
 kernel.Thread32Next.argtypes=[W.HANDLE,C.POINTER(ThreadEntry)];kernel.Thread32Next.restype=W.BOOL
 def threads():
  snapshot=kernel.CreateToolhelp32Snapshot(4,0);assert snapshot and snapshot!=C.c_void_p(-1).value
  result=set();entry=ThreadEntry();entry.size=C.sizeof(entry)
  try:
   found=kernel.Thread32First(snapshot,C.byref(entry))
   while found:
    if entry.owner==app.process.pid:result.add(entry.id)
    found=kernel.Thread32Next(snapshot,C.byref(entry))
  finally:kernel.CloseHandle(snapshot)
  return result
 def kill():
  app.process.kill();app.process.wait(timeout=20);app.log.close();assert app.process.returncode!=0
 def pending_identity(raw):
  assert raw[:8]==b'EXRMETA1';at=8+6*8;fields=[]
  for _ in range(3):
   size=int.from_bytes(raw[at:at+8],'big');at+=8;fields.append(raw[at:at+size].decode());at+=size
  assert len(fields[2])==32
  return fields[1],fields[2]
 try:
  certs=out/'certificates';certs.mkdir();key=certs/'server.key';cert=certs/'server.crt'
  openssl=shutil.which('openssl') or r'C:\Program Files\Git\usr\bin\openssl.exe'
  subprocess.run([openssl,'req','-x509','-newkey','rsa:2048','-nodes','-days','1','-keyout',str(key),'-out',str(cert),'-subj','/CN=127.0.0.1','-addext','subjectAltName=IP:127.0.0.1'],check=True,capture_output=True)
  subprocess.run(['certutil','-addstore','-f','Root',str(cert)],check=True,capture_output=True)
  user='fixture-user';password='fixture-secret-'+uuid.uuid4().hex
  auth='Basic '+base64.b64encode((user+':'+password).encode()).decode();dav=ACCOUNT.Dav(cert,key,auth)
  gate=threading.Event();release=threading.Event();pause_get=[False]
  base_handler=dav.server.RequestHandlerClass
  class GatedHandler(base_handler):
   def do_GET(self):
    if pause_get[0]:
     pause_get[0]=False;gate.set()
     if not release.wait(40):self.reply(503);return
    super().do_GET()
  dav.server.RequestHandlerClass=GatedHandler
  dav.directories.add('/dav/books/')
  for name,data in originals.items():dav.entries['/dav/books/'+name.replace(' ','%20')]=data
  app=launch();phase='account'
  d=app.open_account();app.fill(d,root=dav.base+'/dav/',user=user,password=password,remember=False);app.apply(d,'仅本次会话');app.close_account(d)
  phase='cloud';d=show(CLOUD);record('native-ctrl-shift-i-opens-cloud-picker',bool(d))
  record('configured-account-real-tls-listing',any(r['method']=='PROPFIND' and r['authenticated'] for r in dav.requests) and any('books' in x for x in labels(d)))
  before=sql('SELECT count(*) FROM books',product=False)[0][0]
  selected=C.c_ssize_t(send(U.GetDlgItem(d,ROWS),0x188)).value
  print(json.dumps({'initial_selected':selected,'sdk_rows_before_selection':before}),flush=True)
  record('no-implicit-book-selection',selected==-1 and 'committed=1' not in press(d,GO) and sql('SELECT count(*) FROM books',product=False)[0][0]==before)
  choose(d,'books');press(d,GO);record('real-directory-navigation',len(labels(d))==len(INPUTS))
  for name,fixture in INPUTS:
   phase='import-'+fixture;choose(d,name);message=press(d,GO)
   assert 'committed=1' in message and 'created=1' in message and 'mapped=1' in message and 'staging_removed=1' in message,message
   record('format-'+fixture.rsplit('.',1)[1])
  shot(d,'01-cloud-receipts.bmp');close(d)
  phase='readback';readback=out/'readback';readback.mkdir();spec=out/'readback.spec'
  spec.write_text('cmd=readback\nlibrary=%s\nout=%s\n'%(app.db,readback),encoding='utf-8')
  value=subprocess.run([str(args.cloud_probe.resolve()),str(spec)],capture_output=True,text=True,encoding='utf-8',timeout=120)
  assert value.returncode==0,value.stderr
  audit=json.loads(value.stdout);assert audit['ok']==1,audit
  actual={hashlib.sha256((readback/('book-%d.bin'%book['id'])).read_bytes()).hexdigest() for book in audit['books']}
  record('independent-public-sdk-original-readback',len(audit['books'])==9 and actual==set(hashes.values()) and all(book['read_ok']==1 for book in audit['books']))
  report['public_readback']=audit
  d=show(CLOUD);choose(d,'books');press(d,GO);choose(d,INPUTS[0][0]);message=press(d,GO)
  record('duplicate-keeps-one-original-and-one-mapping','committed=1' in message and 'created=0' in message and sql('SELECT count(*) FROM books',product=False)==[(9,)] and sql('SELECT count(*) FROM reader_local_books')==[(9,)])
  dav.fail=500;message=press(d,GO);dav.fail=0
  receipt=(out/'profile/cloud-import.receipts').read_text()
  record('download-http-failure-retains-real-receipt-and-cleans','HTTP=500' in message and 'http=500' in receipt and not list((out/'profile/cloud-import').glob('cloud-*')))
  # Hold only the real UI thread after the native network worker has entered
  # GET. This creates a deterministic between-phases OS boundary, not a test
  # hook in the production binary. The worker still publishes the actual file.
  for outcome in ('committed','corrupt','cancelled','killed'):
   phase='staging-'+outcome;gate.clear();release.clear();pause_get[0]=True
   before_threads=threads();send(U.GetDlgItem(d,GO),0xF5);app.wait(gate.is_set)
   candidates=[]
   for identity in threads()-before_threads:
    handle=kernel.OpenThread(0x100000|0x800,False,identity)
    if handle:
     created,ended,system,user_time=(W.FILETIME() for _ in range(4))
     assert kernel.GetThreadTimes(handle,C.byref(created),C.byref(ended),C.byref(system),C.byref(user_time))
     candidates.append(((created.dwHighDateTime<<32)|created.dwLowDateTime,handle))
   assert candidates
   candidates.sort();worker=candidates[0][1]
   for _,handle in candidates[1:]:kernel.CloseHandle(handle)
   tid=U.GetWindowThreadProcessId(app.window,None);thread=kernel.OpenThread(2,False,tid);assert thread
   assert kernel.SuspendThread(thread)!=0xffffffff
   staged=None
   try:
    if outcome=='cancelled':assert U.PostMessageW(d,0x111,CANCEL,0)
    release.set()
    def published():
     values=list((out/'profile/cloud-import').glob('cloud-*'))
     return values[0] if len(values)==1 and values[0].stat().st_size==len(originals[INPUTS[0][0]]) else None
    staged=app.wait(published)
    assert kernel.WaitForSingleObject(worker,15000)==0,'network worker must finish before modifying a published staging copy'
    if outcome=='corrupt':staged.write_bytes(b'!'*len(originals[INPUTS[0][0]]))
    staged.chmod(stat.S_IREAD)
    if outcome=='killed':kill()
   finally:
    if app.process.poll() is None:assert kernel.ResumeThread(thread)!=0xffffffff
    kernel.CloseHandle(thread)
    kernel.CloseHandle(worker)
   if outcome=='killed':
    app=launch(existing=True)
    account=app.open_account();app.fill(account,user=user,password=password,remember=False);app.apply(account,'仅本次会话');app.close_account(account)
    d=show(CLOUD)
    assert not U.IsWindowEnabled(U.GetDlgItem(d,GO)) and U.IsWindowEnabled(U.GetDlgItem(d,CLEAN))
    press(d,CLEAN);assert staged.exists()
    staged.chmod(stat.S_IREAD|stat.S_IWRITE);press(d,CLEAN)
    record('kill-before-import-reopens-explicit-orphan-cleanup',not staged.exists() and sql('SELECT count(*) FROM books',product=False)==[(9,)])
    choose(d,'books');press(d,GO);choose(d,INPUTS[0][0])
   else:
    settle(d);message=text(U.GetDlgItem(d,MESSAGE))
    assert staged.exists() and 'retained=1' in message and U.IsWindowEnabled(U.GetDlgItem(d,CLEAN)),message
    assert ('committed=1' if outcome=='committed' else 'committed=0') in message,message
    if outcome=='committed':assert 'created=0' in message and 'staging_removed=0' in message,message
    staged.chmod(stat.S_IREAD|stat.S_IWRITE);press(d,CLEAN)
    record(outcome+'-cloud-import-retains-refused-staging-owner',not staged.exists() and sql('SELECT count(*) FROM books',product=False)==[(9,)])
  close(d);dav.pause=True;U.SetForegroundWindow(app.window);A.tap(ord('I'),(A.VK_CONTROL,A.VK_SHIFT));d=app.io_dialog();app.wait(lambda:dav.blocked.is_set())
  U.ShowWindow(d,6);assert U.IsIconic(d)
  send(U.GetDlgItem(d,CLOSE),0xF5);dav.release.set();app.wait(lambda:not U.IsWindow(d));app.wait_idle()
  record('cancel-close-rejects-late-listing',sql('SELECT count(*) FROM books',product=False)==[(9,)] and U.IsWindowEnabled(app.window))
  phase='401';d=app.open_account();app.fill(d,password='wrong-password');app.apply(d,'仅本次会话');app.close_account(d)
  d=show(CLOUD);record('401-no-plaintext-fallback','HTTP=401' in text(U.GetDlgItem(d,MESSAGE)) and not labels(d) and 'wrong-password' not in (out/'profile/account.ini').read_text());close(d)
  phase='bulk';d=show(BULK);record('native-ctrl-shift-o-opens-extended-selection',len(labels(d))==9 and send(U.GetDlgItem(d,ROWS),0x190)==0)
  names=select_books(d);record('uia-real-multiple-selection',send(U.GetDlgItem(d,ROWS),0x190)==2)
  before=sql('SELECT * FROM reader_books ORDER BY book_key')
  expected_keys={format+':'+hashes[name] for name,format in [(name,fixture.rsplit('.',1)[1]) for name,fixture in INPUTS]
                 if any(Path(name).stem in label for label in names)}
  assert len(expected_keys)==2
  phase='bootstrap-staged-kill'
  bootstrap=Path(str(app.db)+'.product.sqlite.bulk-bootstrap.pending')
  canonical=Path(str(app.db)+'.product.sqlite.commands.pending')
  pending=Path(str(app.db)+'.product.sqlite.bulk-action.pending')
  blocker=sqlite3.connect(str(app.db)+'.product.sqlite',timeout=10);blocker.execute('BEGIN IMMEDIATE')
  try:
   send(U.GetDlgItem(d,GO),0xF5);app.wait(bootstrap.exists,timeout=4)
   original_bootstrap=bootstrap.read_bytes();bootstrap_key,bootstrap_revision=pending_identity(original_bootstrap)
   assert not canonical.exists() and Path(str(app.db)+'.product.sqlite.bulk.pending').exists()
   action_lock=kernel.CreateFileW(str(pending)+'.lock',0x80000000,1|2,None,3,0x80,None)
   assert action_lock and action_lock!=C.c_void_p(-1).value
   kernel.CloseHandle(action_lock)  # J10 owner is closed, profile exclusion remains
   locks=[out/'profile/product.profile.lock',Path(str(app.db)+'.product.lock')]
   for lock in locks:
    C.set_last_error(0);handle=kernel.CreateFileW(str(lock),0x80000000,1|2,None,3,0x80,None)
    assert handle==C.c_void_p(-1).value and C.get_last_error()==32
   script=out/'second-host.steps';script.write_text('',encoding='utf-8')
   other=subprocess.run([str(args.candidate.resolve()),'--font',str(args.font.resolve()),'--data',str(out/'profile'),
    '--drive',str(script),'--evidence',str(out/'second-host-evidence')],capture_output=True,timeout=2)
   record('profile-locks-exclude-second-host-through-owner-reopen',other.returncode==2 and bootstrap.read_bytes()==original_bootstrap and not canonical.exists())
   kill()
  finally:blocker.rollback();blocker.close()
  for lock in locks:
   handle=kernel.CreateFileW(str(lock),0x80000000,1|2,None,3,0x80,None)
   assert handle and handle!=C.c_void_p(-1).value;kernel.CloseHandle(handle)
  app=launch(existing=True);d=show(BULK)
  record('bootstrap-staged-kill-keeps-action-unexecuted',bootstrap.read_bytes()==original_bootstrap and counts()==(0,0) and sql('SELECT sum(favorite) FROM reader_books')==[(0,)] and
   len(labels(d,REPORT))==2 and all('committed=0' in row for row in labels(d,REPORT)))
  held=kernel.CreateFileW(str(bootstrap),0x80000000,1|2,None,3,0x80,None)
  assert held and held!=C.c_void_p(-1).value
  try:
   message=press(d,RESUME)
   record('bootstrap-cleanup-denial-does-not-claim-favorite-commit',bootstrap.read_bytes()==original_bootstrap and not canonical.exists() and
    counts()==(1,1) and sql('SELECT sum(favorite) FROM reader_books')==[(0,)] and 'committed=0' in message and 'complete=0' in message and
    len(labels(d,REPORT))==2 and all('committed=0' in row for row in labels(d,REPORT)))
  finally:kernel.CloseHandle(held)
  message=press(d,RESUME)
  wire=[json.loads(row[0]) for row in sql("SELECT body_json FROM reader_revisions WHERE entity_kind='book' AND entity_key=? ORDER BY rowid",(bootstrap_key,))]
  record('bootstrap-replay-not-counted-as-favorite-commit',not bootstrap.exists() and len(wire)==2 and wire[0]['id']==bootstrap_revision and
   wire[0]['payload']['favorite'] is False and wire[1]['payload']['favorite'] is True and wire[1]['parents']==[bootstrap_revision] and
   len(labels(d,REPORT))==2 and all('revision='+bootstrap_revision not in row for row in labels(d,REPORT)))
  selected_keys={row[0] for row in sql('SELECT book_key FROM reader_books WHERE favorite=1')}
  record('favorite-only-explicit-selection',selected_keys==expected_keys and 'committed=2' in message and len(labels(d,REPORT))==2 and
   [row for row in before if row[0] not in expected_keys]==[row for row in sql('SELECT * FROM reader_books ORDER BY book_key') if row[0] not in expected_keys])
  saved=counts();receipts=labels(d,REPORT);close(d);d=show(BULK)
  record('completed-journal-reopens-with-original-receipts',labels(d,REPORT)==receipts and counts()==saved)
  app.process.kill();app.process.wait(timeout=20);app.log.close();app=launch(existing=True);d=show(BULK);message=press(d,RESUME)
  record('real-process-kill-and-original-request-replay',counts()==saved and labels(d,REPORT)==receipts and 'complete=1' in message);ack(d)
  select_books(d);action(d,1);message=press(d,GO)
  record('favorite-clear-only-explicit-selection','committed=2' in message and sql('SELECT sum(favorite) FROM reader_books')==[(0,)]);ack(d);close(d)
  phase='superseded-bootstrap';d=show(BULK);select_books(d,1,2);action(d,0)
  legacy_key,legacy_title=sql('SELECT book_key,title FROM reader_books ORDER BY sort_title,book_key')[2]
  assert not sql('SELECT revision_id FROM reader_revisions WHERE entity_key=?',(legacy_key,))
  blocker=sqlite3.connect(str(app.db)+'.product.sqlite',timeout=10);blocker.execute('BEGIN IMMEDIATE')
  try:
   send(U.GetDlgItem(d,GO),0xF5);app.wait(bootstrap.exists,timeout=4)
   obsolete=bootstrap.read_bytes();obsolete_key,obsolete_revision=pending_identity(obsolete)
   assert obsolete_key==legacy_key;original_request=Path(str(app.db)+'.product.sqlite.bulk.pending').read_bytes();kill()
  finally:blocker.rollback();blocker.close()
  app=launch(existing=True);send(app.control('books'),0x186,2);send(U.GetDlgItem(app.window,M.DETAILS),0xF5)
  editor=M.MetadataApp.dialog(app);assert text(U.GetDlgItem(editor,M.TITLE))==legacy_title
  current=json.loads(sql('SELECT body_json FROM reader_revisions WHERE entity_key=?',(legacy_key,))[0][0])
  assert current['id']!=obsolete_revision and current['parents']==[] and current['payload']['favorite'] is False
  send(U.GetDlgItem(editor,M.CANCEL),0xF5);app.wait(lambda:not U.IsWindow(editor));app.wait_idle()
  assert bootstrap.read_bytes()==obsolete and Path(str(app.db)+'.product.sqlite.bulk.pending').read_bytes()==original_request
  before_rows=sql('SELECT * FROM reader_books ORDER BY book_key');d=show(BULK);message=press(d,RESUME)
  wire=[json.loads(row[0]) for row in sql('SELECT body_json FROM reader_revisions WHERE entity_key=? ORDER BY rowid',(legacy_key,))]
  record('superseded-uncommitted-bootstrap-recovers-with-current-history','committed=1' in message and 'complete=1' in message and obsolete_revision in message and
   not bootstrap.exists() and len(wire)==2 and wire[0]==current and wire[1]['parents']==[current['id']] and wire[1]['payload']['favorite'] is True and
   not sql('SELECT revision_id FROM reader_revisions WHERE revision_id=?',(obsolete_revision,)) and
   not sql('SELECT revision_id FROM reader_outbox WHERE revision_id=?',(obsolete_revision,)) and
   len(labels(d,REPORT))==1 and legacy_key in labels(d,REPORT)[0] and 'revision='+wire[1]['id'] in labels(d,REPORT)[0] and
   [row for row in before_rows if row[0]!=legacy_key]==[row for row in sql('SELECT * FROM reader_books ORDER BY book_key') if row[0]!=legacy_key])
  ack(d);select_books(d,1,2);action(d,1);message=press(d,GO)
  assert 'committed=1' in message and sql('SELECT sum(favorite) FROM reader_books')==[(0,)]
  ack(d);close(d)
  root=group(0,'Root shelf');child=group(0,'Child shelf',root);tag=group(1,'Existing tag');series=group(2,'Existing series')
  for add,kind,gid,label,table,column in [(2,'nested-shelf',child,'Child shelf','reader_book_shelves','shelf_id'),(4,'tag',tag,'Existing tag','reader_book_tags','tag_id'),(6,'series',series,'Existing series','reader_book_series','series_id')]:
   phase='group-'+kind;d=show(BULK);select_books(d);action(d,add)
   if add==2:
    choose(d,'Root shelf',GROUPS);send(d,0x111,(2<<16)|GROUPS,U.GetDlgItem(d,GROUPS));settle(d)
   choose(d,label,GROUPS);message=press(d,GO)
   assert 'committed=2' in message and sql('SELECT count(*) FROM '+table+' WHERE '+column+'=?',(gid,))==[(2,)],message
   ack(d);action(d,add+1)
   if add==2:
    choose(d,'Root shelf',GROUPS);send(d,0x111,(2<<16)|GROUPS,U.GetDlgItem(d,GROUPS));settle(d)
   choose(d,label,GROUPS);message=press(d,GO)
   record('existing-'+kind+'-add-remove','committed=2' in message and sql('SELECT count(*) FROM '+table+' WHERE '+column+'=?',(gid,))==[(0,)])
   ack(d);close(d)
  phase='cancel-batch';d=show(BULK);select_books(d,9);action(d,0)
  send(U.GetDlgItem(d,GO),0xF5);send(U.GetDlgItem(d,CANCEL),0xF5);settle(d)
  rows=labels(d,REPORT);committed=sum('committed=1' in row for row in rows)
  record('cancel-preserves-committed-and-unrun-report',len(rows)==9 and sql('SELECT sum(favorite) FROM reader_books')==[(committed,)] and all('outcome=' in row for row in rows))
  message=press(d,RESUME)
  record('resume-uses-retained-original-request','complete=1' in message and sql('SELECT sum(favorite) FROM reader_books')==[(9,)] and len(labels(d,REPORT))==9)
  shot(d,'02-bulk-receipts.bmp');ack(d);close(d)
  # The installed metadata owner can read/prepare under a separate SQLite
  # RESERVED writer. Its actual apply waits at BEGIN IMMEDIATE. This gives the
  # production binary an external, deterministic pre-commit boundary.
  pending=Path(str(app.db)+'.product.sqlite.bulk-action.pending')
  for boundary in ('before','after'):
   phase='bulk-kill-'+boundary;d=show(BULK);select_books(d,1);action(d,1 if boundary=='before' else 0)
   before_counts=counts();before_favorites=sql('SELECT book_key,favorite FROM reader_books ORDER BY book_key')
   blocker=sqlite3.connect(str(app.db)+'.product.sqlite',timeout=10);blocker.execute('BEGIN IMMEDIATE')
   held=None
   try:
    send(U.GetDlgItem(d,GO),0xF5);app.wait(pending.exists,timeout=4)
    retained=pending.read_bytes();retained_key,retained_revision=pending_identity(retained)
    if boundary=='after':
     held=kernel.CreateFileW(str(pending),0x80000000,1|2,None,3,0x80,None)
     assert held and held!=C.c_void_p(-1).value
     blocker.rollback();settle(d);message=text(U.GetDlgItem(d,MESSAGE))
     committed_counts=counts();receipts=labels(d,REPORT)
     record('bulk-commit-cleanup-denial-still-reports-committed','committed=1' in message and 'complete=0' in message and pending.read_bytes()==retained and
      committed_counts==(before_counts[0]+1,before_counts[1]+1) and len(receipts)==1 and 'committed=1' in receipts[0])
    kill()
   finally:
    blocker.rollback();blocker.close()
    if held:kernel.CloseHandle(held)
   app=launch(existing=True);d=show(BULK)
   if boundary=='before':
    record('bulk-kill-before-commit-keeps-exact-request',pending.read_bytes()==retained and counts()==before_counts and sql('SELECT book_key,favorite FROM reader_books ORDER BY book_key')==before_favorites)
   else:
    assert counts()==committed_counts and pending.read_bytes()==retained
   message=press(d,RESUME);after_counts=counts()
   if boundary=='before':
    record('bulk-retry-after-kill-uses-original-revision','complete=1' in message and 'committed=1' in message and not pending.exists() and after_counts==(before_counts[0]+1,before_counts[1]+1) and
     sql('SELECT entity_key FROM reader_revisions WHERE revision_id=?',(retained_revision,))==[(retained_key,)] and labels(d,REPORT)[0].endswith('revision='+retained_revision))
   else:
    record('bulk-kill-after-commit-replay-does-not-duplicate','complete=1' in message and 'committed=1' in message and not pending.exists() and after_counts==committed_counts and
     labels(d,REPORT)[0].split('revision=')[-1]==receipts[0].split('revision=')[-1])
   ack(d);close(d)
  # A paused journal's NEXT item has no staged J10 revision. A normal Details
  # edit for that same book must not be mistaken for the requested favorite.
  phase='normal-editor-pending-ownership';d=show(BULK);select_books(d,9);action(d,1)
  ordered=sql('SELECT book_key,title,author FROM reader_books ORDER BY sort_title,book_key')
  next_key,next_title,next_author=ordered[1]
  blocker=sqlite3.connect(str(app.db)+'.product.sqlite',timeout=10);blocker.execute('BEGIN IMMEDIATE')
  try:
   send(U.GetDlgItem(d,GO),0xF5);app.wait(pending.exists,timeout=4)
   send(U.GetDlgItem(d,CANCEL),0xF5);blocker.rollback();settle(d)
   rows=labels(d,REPORT)
   assert len(rows)==9 and 'committed=1' in rows[0] and all('committed=0' in row for row in rows[1:])
  finally:blocker.rollback();blocker.close()
  close(d);send(app.control('books'),0x186,1);send(U.GetDlgItem(app.window,M.DETAILS),0xF5)
  editor=M.MetadataApp.dialog(app);assert text(U.GetDlgItem(editor,M.TITLE))==next_title
  M.set_text(U.GetDlgItem(editor,M.AUTHOR),'Unrelated retained normal edit')
  editor_counts=counts();blocker=sqlite3.connect(str(app.db)+'.product.sqlite',timeout=10);blocker.execute('BEGIN IMMEDIATE')
  try:
   send(U.GetDlgItem(editor,M.SAVE),0xF5);app.wait(canonical.exists,timeout=4)
   editor_pending=canonical.read_bytes();editor_key,editor_revision=pending_identity(editor_pending)
   assert editor_key==next_key and not pending.exists();kill()
  finally:blocker.rollback();blocker.close()
  app=launch(existing=True);d=show(BULK);message=press(d,RESUME)
  record('normal-details-intent-is-not-a-bulk-action-receipt','committed=9' in message and 'complete=1' in message and
   canonical.read_bytes()==editor_pending and not pending.exists() and counts()==(editor_counts[0]+8,editor_counts[1]+8) and
   sql('SELECT sum(favorite) FROM reader_books')==[(0,)] and sql('SELECT author FROM reader_books WHERE book_key=?',(next_key,))==[(next_author,)] and
   not sql('SELECT revision_id FROM reader_revisions WHERE revision_id=?',(editor_revision,)) and
   all('revision='+editor_revision not in row for row in labels(d,REPORT)))
  ack(d);close(d);send(app.control('books'),0x186,1);send(U.GetDlgItem(app.window,M.DETAILS),0xF5)
  recovery=M.MetadataApp.dialog(app,True);saved_counts=counts();send(U.GetDlgItem(recovery,M.RETRY),0xF5)
  app.wait(lambda:'别处' in text(U.GetDlgItem(M.MetadataApp.dialog(app,True),M.MESSAGE)))
  record('stale-normal-details-recovery-is-explicit-conflict',canonical.read_bytes()==editor_pending and counts()==saved_counts and
   sql('SELECT author,favorite FROM reader_books WHERE book_key=?',(next_key,))==[(next_author,0)])
  recovery=M.MetadataApp.dialog(app,True);send(U.GetDlgItem(recovery,M.DISCARD),0xF5)
  app.wait(lambda:not U.IsWindow(recovery));app.wait_idle();assert not canonical.exists()
  d=show(BULK);select_books(d);action(d,0);message=press(d,GO)
  assert 'committed=2' in message and sql('SELECT sum(favorite) FROM reader_books')==[(2,)]
  ack(d);close(d)
  phase='concurrent-head'
  ordered=sql('SELECT book_key FROM reader_books ORDER BY sort_title,book_key');conflict_key=ordered[0][0]
  original=json.loads(sql("SELECT body_json FROM reader_revisions WHERE entity_kind='book' AND entity_key=? ORDER BY rowid LIMIT 1",(conflict_key,))[0][0])
  concurrent=copy.deepcopy(original);concurrent['id']=uuid.uuid4().hex;concurrent['parents']=[]
  raw=json.dumps(concurrent,ensure_ascii=False,separators=(',',':')).encode();wire=out/'concurrent-book.wire';wire.write_bytes(raw)
  received=subprocess.run([str(args.revision_consumer.resolve()),'receive',str(app.db)+'.product.sqlite',str(wire),hashlib.sha256(raw).hexdigest()],capture_output=True,text=True,encoding='utf-8',timeout=60)
  assert received.returncode==0 and json.loads(received.stdout)['status']==0,received.stdout+received.stderr
  before_rows=sql('SELECT * FROM reader_books ORDER BY book_key')
  d=show(BULK);select_books(d);action(d,1);message=press(d,GO);rows=labels(d,REPORT)
  after_rows=sql('SELECT * FROM reader_books ORDER BY book_key')
  record('concurrent-head-is-explicit-and-unselected-books-stay-unchanged','conflict=1' in message and len(rows)==2 and 'conflict=1' in rows[0] and 'committed=1' in rows[1] and
   [row for row in before_rows if row[0]!=ordered[1][0]]==[row for row in after_rows if row[0]!=ordered[1][0]] and
   sql('SELECT favorite FROM reader_books WHERE book_key=?',(ordered[1][0],))==[(0,)])
  ack(d);close(d)
  record('original-inputs-unchanged',all(hashlib.sha256((args.fixtures/fixture).read_bytes()).hexdigest()==hashes[name] for name,fixture in INPUTS))
  assert len(checks)==len(REQUIRED) and set(checks)==set(REQUIRED)
  report['accepted']=True
 except Exception as error:
  problems.append(phase+': '+type(error).__name__+': '+str(error));traceback.print_exc()
  if app:
   report['native_status']=app.status()
   try:M.screenshot(U.GetDesktopWindow(),out/'failure-desktop.bmp')
   except Exception:pass
 finally:
  if app:
   try:
    if app.process.poll() is None:app.process.kill();app.process.wait(timeout=20)
    if not app.log.closed:app.log.close()
   except Exception:pass
  if dav:dav.server.shutdown();dav.server.server_close();report['requests']=dav.requests
  for key in out.glob('certificates/*.key'):key.unlink()
  report['count']=len(checks);report['consumer_sha256']=hashlib.sha256(args.candidate.read_bytes()).hexdigest()
  report['cloud_probe_sha256']=hashlib.sha256(args.cloud_probe.read_bytes()).hexdigest()
  report['command_consumer_sha256']=hashlib.sha256(args.command_consumer.read_bytes()).hexdigest()
  report['revision_consumer_sha256']=hashlib.sha256(args.revision_consumer.read_bytes()).hexdigest()
  (out/'import-organize-ui.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8');print(json.dumps(report,ensure_ascii=True),flush=True)
 if not report['accepted']:raise SystemExit('Windows cloud import / organization native acceptance failed')

if __name__=='__main__':main()
