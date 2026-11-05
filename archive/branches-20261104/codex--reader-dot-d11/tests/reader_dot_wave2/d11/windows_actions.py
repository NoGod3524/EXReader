"""Native Win32 actions and focus, without review messages or private dispatch."""
import ctypes as C
from ctypes import wintypes as W
import json,os,pathlib,sys,time,traceback
from common import *
assert os.name=='nt'
sys.stdout.reconfigure(encoding='utf-8');sys.stderr.reconfigure(encoding='utf-8')
root=pathlib.Path.cwd();target=root/'target';out=root/'build/d11/windows-actions';out.mkdir(parents=True)
sys.path.insert(0,str(target/'tests/reader_windows_preferences'))
import check_ui as P
U=P.U;A=P.A;send=P.send
U.GetPropW.argtypes=[W.HWND,W.LPCWSTR];U.GetPropW.restype=W.HANDLE
U.IsChild.argtypes=[W.HWND,W.HWND];U.IsChild.restype=W.BOOL
U.GetParent.argtypes=[W.HWND];U.GetParent.restype=W.HWND
U.GetDlgCtrlID.argtypes=[W.HWND];U.GetDlgCtrlID.restype=C.c_int
U.EnumChildWindows.argtypes=[W.HWND,P.ENUM,W.LPARAM]
binary=root/'build/d11-evidence/programs/EXReaderProduct.exe';font=binary.parent/'Reader.otf';app=None;rows=pending('windows');report=dict(**identity('windows'),actions=rows,accepted=False,program_sha256=sha(binary),keyboard_accepted=False,screen_reader_accepted=False)
def visible(id):return bool(U.IsWindowVisible(U.GetDlgItem(app.window,id)))
def focus():
 f=A.focus_of(app.process.pid);return dict(hwnd=int(f or 0),parent=int(U.GetParent(f) or 0),visible=bool(U.IsWindowVisible(f)),enabled=bool(U.IsWindowEnabled(f)))
def record(key,passed=True,**raw):
 rows[key]=dict(action=key,exposed=True,enabled=raw.pop('enabled',True),executed=True,result='passed' if passed else 'failed',input='native Win32/SendInput',focus=focus(),raw=raw);print('D11_ACTION '+json.dumps(rows[key]),flush=True);assert passed,key

def dialog(child=None):
 found=[]
 @P.ENUM
 def visit(w,_):
  pid=W.DWORD();U.GetWindowThreadProcessId(w,C.byref(pid))
  if pid.value==app.process.pid and w!=app.window and U.IsWindowVisible(w):
   name=C.create_unicode_buffer(100);U.GetClassNameW(w,name,100)
   if (child is not None and U.GetDlgItem(w,child)) or (child is None and name.value=='#32770' and U.GetDlgItem(w,1)):found.append(w)
  return True
 U.EnumWindows(visit,0);return found[-1] if found else None

def picker(path=None):
 app.focus();A.tap(ord('O'),(A.VK_CONTROL,));d=app.wait(lambda:dialog(),timeout=25)
 app.wait(lambda:U.IsChild(d,A.focus_of(app.process.pid)))
 if path is None:A.tap(A.VK_ESCAPE);app.wait(lambda:not U.IsWindow(d));return
 candidates=[]
 @P.ENUM
 def visit(w,_):
  name=C.create_unicode_buffer(100);U.GetClassNameW(w,name,100)
  if name.value=='Edit' and U.IsWindowVisible(w):
   parent=w
   for _ in range(5):
    if U.GetDlgCtrlID(parent) in (1148,1152):candidates.append(w);break
    parent=U.GetParent(parent)
    if not parent or parent==d:break
  return True
 U.EnumChildWindows(d,visit,0);assert len(candidates)==1
 control=A.auto.ControlFromHandle(candidates[0]);control.Click();A.tap(ord('A'),(A.VK_CONTROL,));control.GetValuePattern().SetValue(str(path.resolve()));A.tap(0x0D);app.wait(lambda:not U.IsWindow(d),timeout=30);app.wait_idle()
try:
 app=P.App(binary,font,out/'profile');app.wait_idle();app.focus();app.wait(lambda:U.IsWindowVisible(app.window),timeout=15)
 app.wait(lambda:(U.GetPropW(app.control('books'),'EXReaderShelfSnapshot') or 0)>=2 and (U.GetPropW(app.control('books'),'EXReaderShelfSnapshot') or 0)%2==0,timeout=30)
 report['initial_controls']={str(i):dict(hwnd=int(U.GetDlgItem(app.window,i) or 0),visible=bool(U.IsWindowVisible(U.GetDlgItem(app.window,i))),enabled=bool(U.IsWindowEnabled(U.GetDlgItem(app.window,i)))) for i in (119,123,46002)}
 resume=U.GetDlgItem(app.window,46002);assert U.IsWindowVisible(resume) and not U.IsWindowEnabled(resume)
 # Real mouse to disabled exposed control; no BM_CLICK bypass.
 rect=W.RECT();U.GetWindowRect(resume,C.byref(rect));A.auto.Click((rect.left+rect.right)//2,(rect.top+rect.bottom)//2);app.wait_idle();record('disabled_noop',not visible(123),enabled=False,control='Continue reading')
 picker();record('cancel',send(app.control('books'),0x18B)==0)
 source=out/'D11.txt';source.write_text('D11 semantic audit\n'+'long reading page searchable words\n'*1600,encoding='utf-8');original=sha(source);picker(source);record('import',send(app.control('books'),0x18B)==1)
 send(app.control('books'),0x186,0);app.click('open');app.wait_idle();app.wait(lambda:visible(123));first=app.label()
 app.click('next');app.wait_idle();app.wait(lambda:app.label()!=first);record('next',True,before=first,after=app.label());app.click('previous');app.wait_idle();record('previous',app.label()==first)
 inventory=database_inventory(out/'profile')
 for key,code,child in [('search',ord('F'),171),('directory',ord('G'),191),('records',ord('L'),211),('settings',0xBC,261)]:
  app.focus();A.tap(code,(A.VK_CONTROL,));d=app.wait(lambda:dialog(child),timeout=30);app.wait(lambda:U.IsChild(d,A.focus_of(app.process.pid)) and U.IsWindowEnabled(A.focus_of(app.process.pid)) and U.IsWindowVisible(A.focus_of(app.process.pid)));record(key,True,modal=int(d),focused_inside=True)
  A.tap(A.VK_ESCAPE);app.wait(lambda:not U.IsWindow(d),timeout=30);app.wait_idle();app.wait(lambda:A.focus_of(app.process.pid)==app.control('page'));record('close.'+key,app.label()==first)
 record('no_unexpected_revision',sha(source)==original and valid_inventory(inventory) and inventory==database_inventory(out/'profile'),before=inventory,after=database_inventory(out/'profile'),source_before=original,source_after=sha(source))
 app.focus();A.tap(0x25,(0x12,));app.wait(lambda:visible(119) and not visible(123));record('back')
 A.auto.ControlFromHandle(U.GetDlgItem(app.window,46002)).Click();app.wait(lambda:visible(123));record('resume',app.label()==first)
 app.click('next');app.wait_idle();record('continue_after_return',app.label()!=first);report['accepted']=True
except Exception:report['error']=traceback.format_exc();print(report['error'],flush=True)
finally:
 if app:
  if app.process.poll() is None:
   U.PostMessageW(app.window,0x10,0,0)
   try:app.process.wait(timeout=20)
   except __import__('subprocess').TimeoutExpired:app.process.kill();app.process.wait()
  app.log.close()
 (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report),flush=True)
assert report['accepted']
