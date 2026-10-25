"""Actions-only real TLS, native selection, installed readback and product audits.

Inputs and names below are fixed before launch. Production host is never linked
with a test hook; database reads are independent observations, not host reports.
"""
import argparse
import base64
import ctypes as C
from ctypes import wintypes as W
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
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
 'cancel-preserves-committed-and-unrun-report','resume-uses-retained-original-request','original-inputs-unchanged']

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
 for name in ('candidate','font','fixtures','cloud-probe','command-consumer','output'):p.add_argument('--'+name,type=Path,required=True)
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
 def select_books(d,n=2):
  items=[item for item in A.auto.ControlFromHandle(U.GetDlgItem(d,ROWS)).GetChildren() if item.ControlTypeName=='ListItemControl']
  items[0].GetSelectionItemPattern().Select()
  for item in items[1:n]:item.GetSelectionItemPattern().AddToSelection()
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
 try:
  certs=out/'certificates';certs.mkdir();key=certs/'server.key';cert=certs/'server.crt'
  openssl=shutil.which('openssl') or r'C:\Program Files\Git\usr\bin\openssl.exe'
  subprocess.run([openssl,'req','-x509','-newkey','rsa:2048','-nodes','-days','1','-keyout',str(key),'-out',str(cert),'-subj','/CN=127.0.0.1','-addext','subjectAltName=IP:127.0.0.1'],check=True,capture_output=True)
  subprocess.run(['certutil','-addstore','-f','Root',str(cert)],check=True,capture_output=True)
  user='fixture-user';password='fixture-secret-'+uuid.uuid4().hex
  auth='Basic '+base64.b64encode((user+':'+password).encode()).decode();dav=ACCOUNT.Dav(cert,key,auth)
  dav.directories.add('/dav/books/')
  for name,data in originals.items():dav.entries['/dav/books/'+name.replace(' ','%20')]=data
  app=launch();phase='account'
  d=app.open_account();app.fill(d,root=dav.base+'/dav/',user=user,password=password,remember=False);app.apply(d,'仅本次会话');app.close_account(d)
  phase='cloud';d=show(CLOUD);record('native-ctrl-shift-i-opens-cloud-picker',bool(d))
  record('configured-account-real-tls-listing',any(r['method']=='PROPFIND' and r['authenticated'] for r in dav.requests) and any('books' in x for x in labels(d)))
  before=sql('SELECT count(*) FROM books',product=False)[0][0]
  record('no-implicit-book-selection',send(U.GetDlgItem(d,ROWS),0x188)==-1 and 'committed=1' not in press(d,GO) and sql('SELECT count(*) FROM books',product=False)[0][0]==before)
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
  close(d);dav.pause=True;U.SetForegroundWindow(app.window);A.tap(ord('I'),(A.VK_CONTROL,A.VK_SHIFT));d=app.io_dialog();app.wait(lambda:dav.blocked.is_set())
  send(U.GetDlgItem(d,CLOSE),0xF5);dav.release.set();app.wait(lambda:not U.IsWindow(d));app.wait_idle()
  record('cancel-close-rejects-late-listing',sql('SELECT count(*) FROM books',product=False)==[(9,)] and U.IsWindowEnabled(app.window))
  phase='401';d=app.open_account();app.fill(d,password='wrong-password');app.apply(d,'仅本次会话');app.close_account(d)
  d=show(CLOUD);record('401-no-plaintext-fallback','HTTP=401' in text(U.GetDlgItem(d,MESSAGE)) and not labels(d) and 'wrong-password' not in (out/'profile/account.ini').read_text());close(d)
  phase='bulk';d=show(BULK);record('native-ctrl-shift-o-opens-extended-selection',len(labels(d))==9 and send(U.GetDlgItem(d,ROWS),0x190)==0)
  names=select_books(d);record('uia-real-multiple-selection',send(U.GetDlgItem(d,ROWS),0x190)==2)
  before=sql('SELECT book_key,favorite FROM reader_books ORDER BY book_key');message=press(d,GO)
  selected_keys={row[0] for row in sql('SELECT book_key FROM reader_books WHERE favorite=1')}
  record('favorite-only-explicit-selection',len(selected_keys)==2 and 'committed=2' in message and len(labels(d,REPORT))==2 and sum(row[1] for row in before)==0)
  saved=counts();receipts=labels(d,REPORT);close(d);d=show(BULK)
  record('completed-journal-reopens-with-original-receipts',labels(d,REPORT)==receipts and counts()==saved)
  app.process.kill();app.process.wait(timeout=20);app.log.close();app=launch(existing=True);d=show(BULK);message=press(d,RESUME)
  record('real-process-kill-and-original-request-replay',counts()==saved and labels(d,REPORT)==receipts and 'complete=1' in message);ack(d)
  select_books(d);action(d,1);message=press(d,GO)
  record('favorite-clear-only-explicit-selection','committed=2' in message and sql('SELECT sum(favorite) FROM reader_books')==[(0,)]);ack(d);close(d)
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
  (out/'import-organize-ui.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8');print(json.dumps(report,ensure_ascii=True),flush=True)
 if not report['accepted']:raise SystemExit('Windows cloud import / organization native acceptance failed')

if __name__=='__main__':main()
