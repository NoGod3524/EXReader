"""Actions-only native reading records, installed public oracles and crash gates."""
import argparse
import copy
import ctypes as C
from ctypes import wintypes as W
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import traceback
import uuid
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'reader_windows_search'))
from check_ui import SearchApp,U,ENUM,send,text,M
from check_formats import ReviewSearchApp
from check_keyboard import A

BUTTON,ROWS,MESSAGE,BODY,PROGRESS,BOOKMARK,HIGHLIGHT,EDIT,DELETE,RESTORE,OPEN,PREVIOUS,NEXT,REFRESH,RETRY,DISCARD,CANCEL,CLOSE=range(210,228)
REQUIRED=['secondary-native-records-entry','empty-list-is-read-only','real-ctrl-l-and-uia-names',
 'txt-progress-public-point-v2','bookmark-public-point-and-global-id','highlight-real-selection-v2',
 'note-edit-keeps-exact-location','delete-retains-tombstone-and-disables-implicit-open',
 'restore-shows-real-version-list','explicit-restore-recaptures-original-location',
 'record-open-is-independent-and-current-found','sdk-notes-not-mirrored','32-row-keyset-first-page',
 'keyset-tail-has-no-duplicates','keyset-previous-restores-same-page',
 'concurrent-record-shows-no-body-or-implicit-action','pending-parent-record-shows-no-body',
 'restart-keeps-records-and-discards-transient-history',
 'epub-progress-preserves-explicit-part','epub-note-public-v2-and-found',
 'pdf-progress-preserves-stable-page-id','cbz-empty-text-public-point-and-found',
 'cancel-before-publication-has-no-intent-or-write','close-before-publication-discards-late-result',
 'kill-before-commit-retains-exact-request','restart-never-auto-submits-pending',
 'retry-before-commit-uses-exact-request-once','kill-after-commit-retains-exact-request',
 'retry-after-commit-has-no-extra-history-or-outbox','completed-retry-stays-complete-after-reopen',
 'switch-book-destroys-records-window','original-files-unchanged']

class RecordsApp(SearchApp):
 def dialog(self):
  def found():
   windows=[]
   @ENUM
   def visit(window,unused):
    pid=W.DWORD();U.GetWindowThreadProcessId(window,C.byref(pid))
    if pid.value==self.process.pid and U.IsWindowVisible(window) and U.GetDlgItem(window,ROWS):windows.append(window)
    return True
   U.EnumWindows(visit,0);assert len(windows)<=1
   return windows[0] if windows else None
  return self.wait(found)

class ReviewRecordsApp(RecordsApp,ReviewSearchApp):
 def wait_idle(self):self.wait(lambda:self.q(14)==0,timeout=90)

def main():
 assert os.environ.get('GITHUB_ACTIONS')=='true' and os.name=='nt'
 p=argparse.ArgumentParser()
 for name in ('candidate','review','font','capture-probe','revision-consumer','output'):p.add_argument('--'+name,type=Path,required=True)
 args=p.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
 spec=importlib.util.spec_from_file_location('records_fixtures',Path(__file__).resolve().parents[1]/'reader_reading_state/make_fixtures.py')
 fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
 txt=out/'Records original.txt';txt.write_text(''.join('Paragraph %03d unique 中文🙂. '%i+'reading text '*70+'\n' for i in range(90)),encoding='utf-8')
 epub=out/'Records EPUB.epub';fixture.epub(epub)
 with zipfile.ZipFile(epub) as book:entries={name:book.read(name) for name in book.namelist()}
 entries['book.opf']=entries['book.opf'].replace(b'<dc:title>Reading state fixture</dc:title>',b'<dc:title>Records EPUB</dc:title>')
 with zipfile.ZipFile(epub,'w') as book:
  for name,data in entries.items():fixture.entry(book,name,data)
 pdf=out/'Records PDF.pdf';fixture.pdf(pdf)
 cbz=out/'Records CBZ.cbz';fixture.cbz(cbz)
 files=[txt,epub,pdf,cbz];hashes={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in files}
 checks=[];problems=[];app=None;phase='launch';resolutions=[];shots=[]
 report=dict(accepted=False,source_sha=os.environ['GITHUB_SHA'],run_id=os.environ['GITHUB_RUN_ID'],attempt=os.environ['GITHUB_RUN_ATTEMPT'],
  checks=checks,problems=problems,transport='SendInput+UIAutomation+Win32',complete_product=False,
  performance_accepted=False,screen_reader_accepted=False,inputs=hashes,public_resolutions=resolutions,screenshots=shots)
 def record(name,condition):
  assert condition,name
  assert name not in checks;checks.append(name);print(json.dumps({'name':name,'pass':True}),flush=True)
 def sql(query,parameters=(),product=True):
  with sqlite3.connect(str(app.db)+('.product.sqlite' if product else '')) as db:return db.execute(query,parameters).fetchall()
 def execute(query):
  with sqlite3.connect(str(app.db)+'.product.sqlite') as db:db.execute(query)
 def counts():return sql('SELECT (SELECT count(*) FROM reader_revisions),(SELECT count(*) FROM reader_outbox)')[0]
 def notes():return tuple(sql('SELECT * FROM '+table,product=False) for table in ('notes','epub_notes','fixed_notes'))
 def source_state():return tuple(sql('SELECT * FROM '+table,product=False) for table in ('notes','epub_notes','fixed_notes','epub_progress','book_progress'))
 def latest(kind='annotation'):
  raw=sql('SELECT body_json FROM reader_revisions WHERE entity_kind=? ORDER BY rowid DESC LIMIT 1',(kind,))[0][0]
  return json.loads(raw)
 def launch(exe,profile,review=False,existing=False):
  result=(ReviewRecordsApp if review else RecordsApp)(exe.resolve(),args.font.resolve(),profile,existing=existing)
  result.wait_initial_shelf();result.wait_idle();return result
 def settle(d):
  app.wait(lambda:not U.IsWindowEnabled(U.GetDlgItem(d,CANCEL)),timeout=90);app.wait_idle()
 def show():
  app.wait_idle();send(U.GetDlgItem(app.window,BUTTON),0xF5);d=app.dialog();settle(d);return d
 def press(d,id):
  send(U.GetDlgItem(d,id),0xF5);settle(d);return text(U.GetDlgItem(d,MESSAGE))
 def labels(d):
  result=[];box=U.GetDlgItem(d,ROWS)
  for i in range(send(box,0x18B)):
   n=send(box,0x18A,i);buf=C.create_unicode_buffer(n+1);send(box,0x189,i,C.addressof(buf));result.append(buf.value)
  return result
 def select(d,index):
  send(U.GetDlgItem(d,ROWS),0x186,index);send(d,0x111,(1<<16)|ROWS,U.GetDlgItem(d,ROWS))
 def select_label(d,value):
  values=labels(d);select(d,next(i for i,line in enumerate(values) if value in line))
 def body(d,value):M.set_text(U.GetDlgItem(d,BODY),value)
 def close(d):send(U.GetDlgItem(d,CLOSE),0xF5);app.wait(lambda:not U.IsWindow(d));app.wait_idle()
 def confirm(d,id):
  U.PostMessageW(d,0x111,id,0)
  def modal():
   found=[]
   @ENUM
   def visit(w,unused):
    pid=W.DWORD();U.GetWindowThreadProcessId(w,C.byref(pid));name=C.create_unicode_buffer(80);U.GetClassNameW(w,name,80)
    if pid.value==app.process.pid and name.value=='#32770' and U.IsWindowVisible(w):found.append(w)
    return True
   U.EnumWindows(visit,0);return found[0] if found else None
  box=app.wait(modal);send(U.GetDlgItem(box,1),0xF5);app.wait(lambda:not U.IsWindow(box));settle(d)
 def audit(value):
  command=[str(args.capture_probe.resolve()),'resolve',str(app.db),str(app.db)+'.product.sqlite',str(args.font.resolve()),str(out/'scratch.sqlite'),value['id']]
  result=subprocess.run(command,capture_output=True,text=True,encoding='utf-8',timeout=90)
  assert result.returncode==0,result.stderr
  report=json.loads(result.stdout);assert report['decoded'] and report['status']=='OK' and report['state']=='FOUND',report
  resolutions.append(report);return report
 def receive(value):
  raw=json.dumps(value,ensure_ascii=False,separators=(',',':')).encode();path=out/(value['id']+'.wire');path.write_bytes(raw)
  result=subprocess.run([str(args.revision_consumer.resolve()),'receive',str(app.db)+'.product.sqlite',str(path),hashlib.sha256(raw).hexdigest()],
   capture_output=True,text=True,encoding='utf-8',timeout=90)
  assert result.returncode==0 and json.loads(result.stdout)['status']==0,result.stdout+result.stderr
 def kill():
  app.process.kill();app.process.wait(timeout=20);app.log.close();assert app.process.returncode!=0
 def shot(d,name):M.screenshot(d,out/name);shots.append(name)
 try:
  app=launch(args.candidate,out/'profile')
  for i,f in enumerate(files,1):app.import_file(f);app.wait(lambda:send(app.control('books'),0x18B)==i);app.wait_idle()
  app.open('Records original');app.wait_idle();before=counts();before_notes=notes();before_source=source_state()
  record('secondary-native-records-entry',bool(U.GetDlgItem(app.window,BUTTON)))
  d=show();record('empty-list-is-read-only',len(labels(d))==1 and counts()==before and source_state()==before_source)
  close(d);U.SetForegroundWindow(app.window);A.tap(ord('L'),(A.VK_CONTROL,));d=app.dialog();settle(d)
  names=[A.auto.ControlFromHandle(U.GetDlgItem(d,id)).Name for id in range(PROGRESS,CLOSE+1)]
  record('real-ctrl-l-and-uia-names',bool(d) and all(names) and '阅读记录' in A.auto.ControlFromHandle(U.GetDlgItem(d,ROWS)).Name)
  press(d,PROGRESS);progress=latest('progress');loc=progress['payload']['location'];proof=audit(progress)
  record('txt-progress-public-point-v2',counts()==(before[0]+2,before[1]+2) and loc['anchor_version']==2 and loc['selector']['exact']=='' and proof['match_start']==proof['match_end'])
  body(d,'Point 中文🙂');press(d,BOOKMARK);bookmark=latest();aid=bookmark['payload']['annotation_id'];audit(bookmark)
  record('bookmark-public-point-and-global-id',len(aid)==32 and bookmark['payload']['location']['selector']['exact']=='' and len(labels(d))==2)
  close(d);app.click('select');app.wait_idle();d=show();body(d,'Original highlight');press(d,HIGHLIGHT);highlight=latest();audit(highlight)
  record('highlight-real-selection-v2',highlight['payload']['location']['selector']['exact'] and highlight['payload']['text']=='Original highlight')
  select_label(d,'Original highlight');body(d,'Edited 中文🙂');press(d,EDIT);edited=latest()
  record('note-edit-keeps-exact-location',edited['parents']==[highlight['id']] and edited['payload']['location']==highlight['payload']['location'] and edited['payload']['text']=='Edited 中文🙂')
  select_label(d,'Edited 中文🙂');confirm(d,DELETE);deleted=latest();select_label(d,'已删除')
  record('delete-retains-tombstone-and-disables-implicit-open',deleted['operation']=='delete' and deleted['parents']==[edited['id']] and not U.IsWindowEnabled(U.GetDlgItem(d,OPEN)) and U.IsWindowEnabled(U.GetDlgItem(d,RESTORE)))
  press(d,RESTORE);version_labels=labels(d);record('restore-shows-real-version-list',len(version_labels)==2 and any('Edited 中文🙂' in v for v in version_labels) and all('版本' in v for v in version_labels))
  select_label(d,'Edited 中文🙂');confirm(d,RESTORE);restored=latest();audit(restored)
  record('explicit-restore-recaptures-original-location',restored['operation']=='restore' and restored['parents']==[deleted['id']] and restored['payload']['text']=='Edited 中文🙂' and restored['payload']['location']==edited['payload']['location'])
  select_label(d,'Edited 中文🙂');message=press(d,OPEN)
  record('record-open-is-independent-and-current-found','独立原书与当前绘图文档' in message)
  record('sdk-notes-not-mirrored',notes()==before_notes)
  phase='keyset'
  for i in range(35):body(d,'Page item %02d'%i);press(d,BOOKMARK)
  press(d,REFRESH);first=labels(d)[1:];record('32-row-keyset-first-page',len(first)==32 and U.IsWindowEnabled(U.GetDlgItem(d,NEXT)))
  press(d,NEXT);tail=labels(d)[1:];record('keyset-tail-has-no-duplicates',len(tail)==5 and len(set(first+tail))==37 and not U.IsWindowEnabled(U.GetDlgItem(d,NEXT)))
  press(d,PREVIOUS);record('keyset-previous-restores-same-page',labels(d)[1:]==first)
  phase='non-safe';foreign=copy.deepcopy(bookmark);foreign['id']=uuid.uuid4().hex;foreign['parents']=[];foreign['payload']['text']='PRIVATE CONCURRENT BODY';receive(foreign)
  pending=copy.deepcopy(bookmark);pending['id']=uuid.uuid4().hex;pending['parents']=[uuid.uuid4().hex];pid=uuid.uuid4().hex
  pending['entity_key']=pending['payload']['book_key']+':'+pid;pending['payload']['annotation_id']=pid;pending['payload']['text']='PRIVATE PENDING BODY';receive(pending)
  press(d,REFRESH)
  def locate_any(value):
   press(d,REFRESH)
   for _ in range(3):
    if any(value in line for line in labels(d)):select_label(d,value);return
    assert U.IsWindowEnabled(U.GetDlgItem(d,NEXT));press(d,NEXT)
   raise AssertionError('state not visible: '+value)
  locate_any('存在冲突');record('concurrent-record-shows-no-body-or-implicit-action','PRIVATE CONCURRENT BODY' not in '\n'.join(labels(d)) and not U.IsWindowEnabled(U.GetDlgItem(d,OPEN)) and not U.IsWindowEnabled(U.GetDlgItem(d,EDIT)) and text(U.GetDlgItem(d,BODY))=='')
  locate_any('等待历史');record('pending-parent-record-shows-no-body','PRIVATE PENDING BODY' not in '\n'.join(labels(d)) and not U.IsWindowEnabled(U.GetDlgItem(d,RESTORE)))
  shot(d,'01-real-states.bmp');close(d);saved_counts=counts();app.close();app=launch(args.candidate,out/'profile',existing=True)
  app.open('Records original');app.wait_idle();d=show();record('restart-keeps-records-and-discards-transient-history',counts()==saved_counts and len(labels(d))==33)
  close(d);phase='epub';app.open('Records EPUB');app.wait_idle();app.click('next');app.wait_idle();d=show();press(d,PROGRESS);ep=latest('progress');audit(ep)
  record('epub-progress-preserves-explicit-part',ep['payload']['location']['mode']=='epub_chapter' and ep['payload']['location']['anchor_version']==2 and ep['payload']['location']['part']==1 and ep['payload']['location']['part_path']=='b.xhtml')
  close(d);app.click('select');app.wait_idle();d=show();body(d,'EPUB current selection');press(d,HIGHLIGHT);epnote=latest();audit(epnote)
  record('epub-note-public-v2-and-found',epnote['payload']['location']['part_path']==ep['payload']['location']['part_path'])
  close(d);app.open('Records PDF');app.wait_idle();app.click('next');app.wait_idle();d=show();press(d,PROGRESS);fixed=latest('progress');proof=audit(fixed)
  record('pdf-progress-preserves-stable-page-id',fixed['payload']['location']['page_id'] and proof['resolved_page']==fixed['payload']['location']['page'])
  close(d);app.open('Records CBZ');app.wait_idle();d=show();press(d,PROGRESS);image=latest('progress');audit(image)
  record('cbz-empty-text-public-point-and-found',image['payload']['location']['selector']['exact']=='' and image['payload']['location']['page_id'])
  close(d);app.close();app=launch(args.review,out/'review',review=True);app.import_file(txt);app.wait(lambda:send(app.control('books'),0x18B)==1);app.wait_idle();app.open('Records original');app.wait_idle();d=show()
  journal=Path(str(app.db)+'.product.sqlite.reading.pending');phase='cancel-before-publication';baseline=counts();app.gate(8);send(U.GetDlgItem(d,BOOKMARK),0xF5);app.stage(8);send(U.GetDlgItem(d,CANCEL),0xF5);app.release();settle(d)
  record('cancel-before-publication-has-no-intent-or-write',counts()==baseline and not journal.exists() and '取消' in text(U.GetDlgItem(d,MESSAGE)))
  app.gate(8);send(U.GetDlgItem(d,BOOKMARK),0xF5);app.stage(8);send(U.GetDlgItem(d,CLOSE),0xF5);app.release();app.wait_idle()
  record('close-before-publication-discards-late-result',not U.IsWindow(d) and counts()==baseline and not journal.exists())
  d=show();phase='kill-before-commit';app.gate(9);send(U.GetDlgItem(d,BOOKMARK),0xF5);app.stage(9);original_request=journal.read_bytes();kill()
  record('kill-before-commit-retains-exact-request',journal.read_bytes()==original_request and counts()==baseline)
  app=launch(args.review,out/'review',review=True,existing=True);app.open('Records original');app.wait_idle();d=show()
  record('restart-never-auto-submits-pending',journal.read_bytes()==original_request and counts()==baseline and U.IsWindowEnabled(U.GetDlgItem(d,RETRY)) and not U.IsWindowEnabled(U.GetDlgItem(d,BOOKMARK)))
  press(d,RETRY);new=latest();record('retry-before-commit-uses-exact-request-once',new['id'].encode() in original_request and counts()==(baseline[0]+2,baseline[1]+2) and not journal.exists())
  phase='kill-after-commit';baseline=counts();app.gate(10);body(d,'Lost response');send(U.GetDlgItem(d,BOOKMARK),0xF5);app.stage(10);original_request=journal.read_bytes();committed=latest();committed_counts=counts();kill()
  record('kill-after-commit-retains-exact-request',committed['id'].encode() in original_request and journal.read_bytes()==original_request and committed_counts==(baseline[0]+1,baseline[1]+1))
  app=launch(args.review,out/'review',review=True,existing=True);app.open('Records original');app.wait_idle();d=show();press(d,RETRY)
  record('retry-after-commit-has-no-extra-history-or-outbox',counts()==committed_counts and not journal.exists() and latest()==committed)
  close(d);app.close();app=launch(args.candidate,out/'review',existing=True);app.open('Records original');app.wait_idle();d=show()
  record('completed-retry-stays-complete-after-reopen',counts()==committed_counts and not journal.exists() and any('Lost response' in line for line in labels(d)))
  app.import_file(pdf);app.wait_idle();app.open('Records PDF');app.wait_idle();record('switch-book-destroys-records-window',not U.IsWindow(d))
  record('original-files-unchanged',all(hashlib.sha256(f.read_bytes()).hexdigest()==hashes[str(f)] for f in files))
  assert set(checks)==set(REQUIRED) and len(checks)==len(REQUIRED);report['accepted']=True
 except Exception as error:
  problems.append(phase+': '+type(error).__name__+': '+str(error));traceback.print_exc()
  print('::error::Windows records '+problems[-1],flush=True)
  if app and app.process.poll() is None:report['native_status']=app.status()
 finally:
  if app:app.close()
  report['count']=len(checks);report['consumer_sha256']=hashlib.sha256(args.candidate.read_bytes()).hexdigest()
  report['review_sha256']=hashlib.sha256(args.review.read_bytes()).hexdigest();report['capture_probe_sha256']=hashlib.sha256(args.capture_probe.read_bytes()).hexdigest()
  report['revision_consumer_sha256']=hashlib.sha256(args.revision_consumer.read_bytes()).hexdigest()
  (out/'records-ui.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(report,ensure_ascii=True),flush=True)
 if not report['accepted']:raise SystemExit('Windows reading records checks failed')

if __name__=='__main__':main()
