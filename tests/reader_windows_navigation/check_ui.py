"""Actions-only native controls, independent progress oracles and live fault gates."""
import argparse
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
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'reader_windows_search'))
from check_ui import SearchApp,U,ENUM,send,text,M
from check_formats import ReviewSearchApp
from check_keyboard import A

BUTTON,ROWS,OPEN,CHILDREN,UP,PREVIOUS,NEXT,CANCEL,CLOSE,MESSAGE=range(190,200)
REQUIRED=['native-directory-secondary-entry','authored-order-and-duplicates',
 'child-unicode-and-parent-roundtrip','listing-keeps-progress-and-history',
 'fragment-native-resolution-opens-second-chapter','missing-fragment-refuses-implicit-jump',
 'missing-fragment-explicit-part-start','external-link-not-launched',
 '32-row-first-page','tail-page-author-order','previous-restores-first-page',
 'duplicate-spine-needs-explicit-choice','explicit-second-spine-is-preserved',
 'full-cfi-from-author-row-resolves-public-sdk-point',
 'pdf-by-pages-is-not-outline','pdf-stable-third-page','cbz-by-pages-can-render',
 'empty-authored-directory','changed-original-refuses-stale-row',
 'switch-book-destroys-directory','restart-discards-directory',
 'real-ctrl-g-and-accessible-names','real-enter-locates-and-escape-restores-focus',
 'cancel-inside-f2-keeps-view','cancel-unpublished-rows-keeps-view',
 'close-dialog-during-f2-discards-result','switch-book-during-f2-discards-result',
 'close-host-during-f2-joins-worker','original-files-unchanged','no-product-history-or-notes-written']

def load_generator(name,path):
 spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

class NavigationApp(SearchApp):
 def visible_directory(self):
   found=[]
   @ENUM
   def visit(window,unused):
    pid=W.DWORD();U.GetWindowThreadProcessId(window,C.byref(pid))
    if pid.value==self.process.pid and U.IsWindowVisible(window) and U.GetDlgItem(window,ROWS):found.append(window)
    return True
   U.EnumWindows(visit,0);assert len(found)<=1
   return found[0] if found else None
 def dialog(self):return self.wait(self.visible_directory)

class ReviewNavigationApp(NavigationApp,ReviewSearchApp):
 def wait_idle(self):self.wait(lambda:self.q(14)==0,timeout=90)

def main():
 assert os.environ.get('GITHUB_ACTIONS')=='true' and os.name=='nt'
 p=argparse.ArgumentParser()
 for name in ('candidate','review','font','cfi','output'):p.add_argument('--'+name,type=Path,required=True)
 args=p.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
 gen=load_generator('navigation_fixtures',Path(__file__).resolve().parents[1]/'reader_navigation/make_navigation_fixtures.py')
 fixed=load_generator('reading_fixtures',Path(__file__).resolve().parents[1]/'reader_reading_state/make_fixtures.py')
 def book(name,navigation=None,duplicate=False):
  path=out/(name+'.epub');gen.epub(path,navigation=navigation,duplicate=duplicate)
  with zipfile.ZipFile(path) as z:entries={n:z.read(n) for n in z.namelist()}
  entries['OPS/book.opf']=entries['OPS/book.opf'].replace(b'Navigation fixture',name.encode())
  with zipfile.ZipFile(path,'w') as z:
   for n,data in entries.items():gen.entry(z,n,data)
  return path
 authored=book('Authored',gen.NAV3)
 many_nav='<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><body><nav epub:type="toc"><ol>'+''.join(
  '<li><a href="../Text/c.xhtml">Row %02d</a></li>'%i for i in range(41))+'</ol></nav></body></html>'
 many=book('Many',many_nav);repeated=book('Repeated',gen.REPEATED_NAV,True);empty=book('Empty')
 cfi=subprocess.check_output([str(args.cfi.resolve()),str(authored)],text=True,encoding='utf-8',timeout=60).strip()
 assert cfi.startswith('epubcfi(') and cfi.endswith(')')
 cfi_nav=gen.REPEATED_NAV.replace('../Text/a.xhtml#start','../Text/a.xhtml#'+cfi)
 cfi_book=book('CFI',cfi_nav)
 pdf=out/'Pages.pdf';gen.pdf(pdf)
 cbz=out/'Image.cbz';fixed.cbz(cbz)
 files=[authored,many,repeated,empty,cfi_book,pdf,cbz]
 hashes={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in files}
 checks=[];problems=[];app=None;phase='launch'
 report=dict(accepted=False,source_sha=os.environ['GITHUB_SHA'],run_id=os.environ['GITHUB_RUN_ID'],
  attempt=os.environ['GITHUB_RUN_ATTEMPT'],checks=checks,problems=problems,complete_product=False,
  screen_reader_accepted=False,performance_accepted=False,transport='SendInput+UIAutomation+Win32',
  inputs=hashes,fixture_cfi=cfi)
 def record(name,condition):
  assert condition,name
  assert name not in checks;checks.append(name);print(json.dumps({'name':name,'pass':True}),flush=True)
 def sql(query,parameters=(),product=False):
  with sqlite3.connect(str(app.db)+('.product.sqlite' if product else '')) as db:return db.execute(query,parameters).fetchall()
 def state():return {t:sql('SELECT * FROM '+t) for t in ('notes','epub_notes','fixed_notes','epub_progress','book_progress')}|{'positions':sql('SELECT id,position FROM books ORDER BY id')}
 def history():return tuple(sql('SELECT * FROM '+t,product=True) for t in ('reader_revisions','reader_outbox'))
 def readonly():return tuple(sql('SELECT * FROM '+t) for t in ('notes','epub_notes','fixed_notes'))
 def launch(exe,profile,review=False,existing=False):
  result=(ReviewNavigationApp if review else NavigationApp)(exe.resolve(),args.font.resolve(),profile,existing=existing)
  result.wait_initial_shelf();result.wait_idle();return result
 def import_book(path,count):
  app.import_file(path);app.wait(lambda:send(app.control('books'),0x18B)==count);app.wait_idle()
 def rows(d):
  box=U.GetDlgItem(d,ROWS);result=[]
  for i in range(send(box,0x18B)):
   length=send(box,0x18A,i);value=C.create_unicode_buffer(length+1);send(box,0x189,i,C.addressof(value));result.append(value.value)
  return result
 def settle(d):
  app.wait(lambda:not U.IsWindowEnabled(U.GetDlgItem(d,CANCEL)),timeout=90);app.wait_idle()
 def show():
  app.wait_idle();send(U.GetDlgItem(app.window,BUTTON),0xF5);d=app.dialog();settle(d);return d
 def press(d,identifier):send(U.GetDlgItem(d,identifier),0xF5);settle(d);return text(U.GetDlgItem(d,MESSAGE))
 def select(d,i):send(U.GetDlgItem(d,ROWS),0x186,i)
 def close(d):send(U.GetDlgItem(d,CLOSE),0xF5);app.wait(lambda:not U.IsWindow(d));app.wait_idle()
 try:
  app=launch(args.candidate,out/'profile')
  for i,f in enumerate(files,1):phase='import-'+f.name;import_book(f,i)
  initial_history=history();initial_notes=readonly()
  phase='authored';app.open('Authored');app.wait_idle();before=state();d=show()
  record('native-directory-secondary-entry',bool(d) and '作者目录' in text(U.GetDlgItem(d,MESSAGE)))
  expected=[r[3] for r in gen.NAV3_ROWS if r[1]==-1]
  record('authored-order-and-duplicates',rows(d)==expected and rows(d).count('Chapter')==1)
  select(d,0);press(d,CHILDREN)
  record('child-unicode-and-parent-roundtrip',rows(d)==['子节 🙂'])
  record('listing-keeps-progress-and-history',state()==before and history()==initial_history)
  select(d,0);message=press(d,OPEN)
  record('fragment-native-resolution-opens-second-chapter','已独立核对' in message and sql('SELECT part,path FROM epub_progress WHERE book_id=(SELECT id FROM books WHERE title=?)',('Authored',))==[(1,gen.B)])
  press(d,UP);assert rows(d)==expected
  select(d,2);before=state();message=press(d,OPEN)
  record('missing-fragment-refuses-implicit-jump','片段已不存在' in message and state()==before)
  message=press(d,OPEN)
  record('missing-fragment-explicit-part-start','已独立核对' in message and sql('SELECT part,path FROM epub_progress WHERE book_id=(SELECT id FROM books WHERE title=?)',('Authored',))==[(2,gen.C)])
  select(d,3);before=state();message=press(d,OPEN)
  record('external-link-not-launched','外部链接' in message and state()==before)
  phase='pagination';app.open('Many');app.wait_idle();record('switch-book-destroys-directory',not U.IsWindow(d));d=show()
  record('32-row-first-page',rows(d)==['Row %02d'%i for i in range(32)])
  press(d,NEXT);record('tail-page-author-order',rows(d)==['Row %02d'%i for i in range(32,41)])
  press(d,PREVIOUS);record('previous-restores-first-page',rows(d)==['Row %02d'%i for i in range(32)])
  phase='duplicate';app.open('Repeated');app.wait_idle();d=show();before=state();select(d,0);press(d,OPEN)
  record('duplicate-spine-needs-explicit-choice',rows(d)==['书内顺序 1','书内顺序 2'] and state()==before)
  select(d,1);message=press(d,OPEN)
  record('explicit-second-spine-is-preserved','已独立核对' in message and sql('SELECT part,path FROM epub_progress WHERE book_id=(SELECT id FROM books WHERE title=?)',('Repeated',))==[(1,gen.A)])
  phase='cfi';app.open('CFI');app.wait_idle();d=show();select(d,0);message=press(d,OPEN)
  record('full-cfi-from-author-row-resolves-public-sdk-point','已独立核对' in message and sql('SELECT part,path FROM epub_progress WHERE book_id=(SELECT id FROM books WHERE title=?)',('CFI',))==[(1,gen.B)])
  phase='pdf';app.open('Pages');app.wait_idle();d=show()
  record('pdf-by-pages-is-not-outline','不是作者目录' in text(U.GetDlgItem(d,MESSAGE)) and len(rows(d))==3 and all('Authored Outline Title' not in r for r in rows(d)))
  select(d,2);message=press(d,OPEN);record('pdf-stable-third-page','已独立核对' in message and sql('SELECT position FROM books WHERE title=?',('Pages',))==[(2,)])
  phase='cbz';app.open('Image');app.wait_idle();d=show();select(d,len(rows(d))-1);message=press(d,OPEN)
  record('cbz-by-pages-can-render','已独立核对' in message and 'CBZ' in text(U.GetDlgItem(app.window,124)))
  phase='empty';app.open('Empty');app.wait_idle();d=show()
  record('empty-authored-directory',rows(d)==[] and '没有目录项' in text(U.GetDlgItem(d,MESSAGE)))
  phase='changed-source';app.open('Many');app.wait_idle();d=show();before=state();saved=many.read_bytes()
  sql('UPDATE books SET source=? WHERE title=?',(saved+b'changed','Many'))
  try:message=press(d,OPEN);record('changed-original-refuses-stale-row','未跳转' in message and state()==before)
  finally:sql('UPDATE books SET source=? WHERE title=?',(saved,'Many'))
  close(d);app.close();assert app.process.returncode==0
  phase='restart';app=launch(args.candidate,out/'profile',existing=True);app.open('Many');app.wait_idle()
  record('restart-discards-directory',not app.visible_directory())
  phase='keyboard';A.USER32.SetForegroundWindow(app.window);app.wait(lambda:A.USER32.GetForegroundWindow()==app.window)
  A.tap(ord('G'),(A.VK_CONTROL,));d=app.dialog();settle(d)
  names=[A.auto.ControlFromHandle(U.GetDlgItem(d,i)).Name for i in (ROWS,OPEN,CHILDREN,UP,PREVIOUS,NEXT,CANCEL,CLOSE)]
  record('real-ctrl-g-and-accessible-names',all(names) and '目录项' in names[0])
  item=A.auto.ControlFromHandle(U.GetDlgItem(d,ROWS));item.SetFocus();app.wait(lambda:A.focus_of(app.process.pid)==U.GetDlgItem(d,ROWS))
  A.tap(0x0D);app.wait(lambda:'已独立核对' in text(U.GetDlgItem(d,MESSAGE)));settle(d)
  A.tap(A.VK_ESCAPE);app.wait(lambda:not U.IsWindow(d));app.wait(lambda:A.focus_of(app.process.pid)==app.control('page'))
  record('real-enter-locates-and-escape-restores-focus',A.focus_of(app.process.pid)==app.control('page'))
  record('no-product-history-or-notes-written',history()==initial_history and readonly()==initial_notes)
  app.close();assert app.process.returncode==0
  phase='live-f2';app=launch(args.review,out/'review',review=True);import_book(many,1);import_book(empty,2);app.open('Many');app.wait_idle();d=show()
  before=state();before_rows=rows(d)
  for gate,name in ((6,'cancel-inside-f2-keeps-view'),(7,'cancel-unpublished-rows-keeps-view')):
   app.gate(gate);send(U.GetDlgItem(d,NEXT),0xF5);app.stage(gate);send(U.GetDlgItem(d,CANCEL),0xF5);app.release();settle(d)
   record(name,'已取消' in text(U.GetDlgItem(d,MESSAGE)) and state()==before and rows(d)==before_rows)
  app.gate(6);send(U.GetDlgItem(d,NEXT),0xF5);app.stage(6);send(U.GetDlgItem(d,CLOSE),0xF5);app.release();app.wait_idle()
  record('close-dialog-during-f2-discards-result',not U.IsWindow(d) and state()==before)
  d=show();app.gate(6);send(U.GetDlgItem(d,NEXT),0xF5);app.stage(6);app.open('Empty',wait=False);app.release();app.wait_idle()
  record('switch-book-during-f2-discards-result',not U.IsWindow(d) and app.q(10)==sql('SELECT id FROM books WHERE title=?',('Empty',))[0][0])
  app.open('Many');app.wait_idle();d=show();app.gate(6);send(U.GetDlgItem(d,NEXT),0xF5);app.stage(6)
  U.PostMessageW(app.window,0x10,0,0);app.process.wait(timeout=20);record('close-host-during-f2-joins-worker',app.process.returncode==0)
  record('original-files-unchanged',all(hashlib.sha256(f.read_bytes()).hexdigest()==hashes[str(f)] for f in files))
  assert set(checks)==set(REQUIRED) and len(checks)==len(REQUIRED)
  report['accepted']=True
 except Exception as error:
  problems.append(phase+': '+type(error).__name__+': '+str(error));traceback.print_exc()
  if app and app.process.poll() is None:report['native_status']=app.status()
 finally:
  if app:app.close()
  report['count']=len(checks);report['consumer_sha256']=hashlib.sha256(args.candidate.read_bytes()).hexdigest()
  report['review_sha256']=hashlib.sha256(args.review.read_bytes()).hexdigest()
  (out/'navigation-ui.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
  print(json.dumps(report,ensure_ascii=True),flush=True)
 if not report['accepted']:raise SystemExit('Windows navigation UI checks failed')

if __name__=='__main__':main()
