"""Actual emulator touch/key actions, with state-aware DocumentsUI cancellation."""
import hashlib,json,os,pathlib,re,subprocess,time,traceback,xml.etree.ElementTree as ET
from common import *
out=pathlib.Path.cwd()/'build/d11/android-focus';out.mkdir(parents=True);rows=pending('android');sequence=0;PACKAGE='org.exreader.host';report=dict(**identity('android'),actions=rows,accepted=False,keyboard_accepted=False,screen_reader_accepted=False)
def adb(*args):return subprocess.check_output(['adb',*map(str,args)],timeout=90)
def tree(label):
 global sequence
 sequence+=1;adb('shell','uiautomator','dump','/sdcard/d11-window.xml');raw=adb('exec-out','cat','/sdcard/d11-window.xml');(out/(str(sequence)+'-'+label+'.xml')).write_bytes(raw);return ET.fromstring(raw)
def find(t,id=None,text=None,cls=None):return [n for n in t.iter('node') if (id is None or n.get('resource-id')==PACKAGE+':id/'+id) and (text is None or n.get('text')==text) and (cls is None or n.get('class')==cls)]
def wait(label,predicate):
 end=time.monotonic()+60
 while time.monotonic()<end:
  t=tree(label)
  if predicate(t):return t
  time.sleep(.3)
 raise AssertionError('native state not reached: '+label)
def tap(n):
 c=list(map(int,re.findall(r'\d+',n.attrib['bounds'])));assert len(c)==4 and n.get('enabled')=='true';adb('shell','input','tap',(c[0]+c[2])//2,(c[1]+c[3])//2)
def record(key,t,passed=True,**raw):
 (out/(key+'.png')).write_bytes(adb('exec-out','screencap','-p'));rows[key]=dict(action=key,exposed=True,enabled=raw.pop('enabled',True),executed=True,result='passed' if passed else 'failed',input='emulator adb touch/key; not external keyboard',focus=[n.attrib for n in t.iter('node') if n.get('focused')=='true'],raw=raw);print('D11_ACTION '+json.dumps(rows[key]),flush=True);assert passed,key

def cancel_picker(t):
 seen=[]
 for _ in range(8):
  if find(t,id='book_list'):return t
  packages={n.get('package') for n in t.iter('node')};assert any('documentsui' in p for p in packages if p),packages
  close=[n for n in t.iter('node') if n.get('content-desc') in ('Navigate up','Close drawer','Cancel','Close') and n.get('enabled')=='true']
  signature=ET.tostring(t);seen.append(hashlib.sha256(signature).hexdigest())
  # Back is allowed only after verifying we remain in the actual document provider;
  # Download -> root -> dismiss are distinct observed transitions, not one assumed cancel.
  adb('shell','input','keyevent',4);time.sleep(.4);t=tree('picker-back-observed')
  if find(t,id='book_list'):report['picker_cancel_states']=seen;return t
 raise AssertionError('DocumentsUI cancellation did not return to originating shelf')
def page(t):return find(t,id='page_label')[0].get('text')
def turn(t,next):
 n=find(t,id='reader_view')[0];c=list(map(int,re.findall(r'\d+',n.get('bounds'))));x=c[0]+int((c[2]-c[0])*(.9 if next else .1));y=(c[1]+c[3])//2;adb('shell','input','tap',x,y)
try:
 assert adb('shell','pm','clear',PACKAGE).strip()==b'Success';adb('shell','am','start','-W','-n',PACKAGE+'/.MainActivity');t=wait('shelf',lambda t:bool(find(t,id='book_list')))
 # Empty native disabled Open/Continue may not exist; keep missing separate from disabled proof.
 rows['disabled_noop'].update(result='pending',reason='no disabled reading control observed on empty shelf; do not force product state')
 source=out/'D11.txt';source.write_text('D11 semantic audit\n'+'A long reading page with searchable sample text.\n'*1600);original=sha(source);adb('push',source,'/sdcard/Download/D11.txt')
 tap(find(t,id='import_button')[0]);t=wait('picker',lambda t:any('documentsui' in (n.get('package') or '') for n in t.iter('node')));t=cancel_picker(t);record('cancel',t,not list(find(t,id='book_list')[0]))
 tap(find(t,id='import_button')[0]);t=wait('picker-import',lambda t:any('documentsui' in (n.get('package') or '') for n in t.iter('node')))
 if not find(t,text='D11.txt'):
  downloads=[n for n in t.iter('node') if n.get('text') in ('Downloads','Download') and n.get('enabled')=='true']
  if not downloads:
   roots=[n for n in t.iter('node') if n.get('content-desc') in ('Show roots','Open navigation drawer')];assert roots,'native roots control not exposed';tap(roots[0]);t=tree('roots');downloads=[n for n in t.iter('node') if n.get('text') in ('Downloads','Download') and n.get('enabled')=='true']
  assert downloads;tap(downloads[0]);t=wait('download-folder',lambda t:bool(find(t,text='D11.txt')))
 tap(find(t,text='D11.txt')[0]);t=wait('import-complete',lambda t:bool(find(t,id='page_label')) or (bool(find(t,id='book_list')) and bool(list(find(t,id='book_list')[0]))));record('import',t)
 if not find(t,id='page_label'):tap(list(find(t,id='book_list')[0])[0]);t=wait('reader',lambda t:bool(find(t,id='page_label')))
 first=page(t);turn(t,True);t=wait('next',lambda t:bool(find(t,id='page_label')) and page(t)!=first);record('next',t,before=first,after=page(t));turn(t,False);t=wait('previous',lambda t:bool(find(t,id='page_label')) and page(t)==first);record('previous',t)
 for key,title in [('search','书内搜索'),('directory','目录 / 按页入口'),('records','阅读记录'),('settings','阅读设置')]:
  tap(find(t,id='reader_more')[0]);t=wait('menu-'+key,lambda t:bool(find(t,text=title)));tap(find(t,text=title)[0]);t=tree('dialog-'+key)
  assert not find(t,id='reader_more'),'dialog did not own active window';record(key,t,True,active_dialog_tree=True)
  if key=='search':
   edit=find(t,cls='android.widget.EditText');assert edit;tap(edit[0]);adb('shell','input','text','D11_UNMATCHED');t=tree('search-typed');assert any(n.get('focused')=='true' for n in find(t,cls='android.widget.EditText'));report['query_focus']=find(t,cls='android.widget.EditText')[0].attrib
  for _ in range(3):
   adb('shell','input','keyevent',4);t=tree('dialog-back-'+key)
   if find(t,id='page_label'):break
  assert find(t,id='page_label');record('close.'+key,t,page(t)==first)
 # Source bytes preserved; revision/outbox not independently observed on device remains pending.
 report['source_unchanged']=hashlib.sha256(adb('exec-out','cat','/sdcard/Download/D11.txt')).hexdigest()==original
 rows['no_unexpected_revision'].update(reason='source file preserved; device revision/outbox independent inventory pending')
 tap(find(t,id='back_button')[0]);t=wait('back',lambda t:bool(find(t,id='book_list')));record('back',t);tap(list(find(t,id='book_list')[0])[0]);t=wait('resume',lambda t:bool(find(t,id='page_label')));record('resume',t,page(t)==first,dedicated_continue='missing; actual book reopen');turn(t,True);t=wait('continue',lambda t:bool(find(t,id='page_label')) and page(t)!=first);record('continue_after_return',t);report['accepted']=True
except Exception:report['error']=traceback.format_exc();print(report['error'],flush=True)
finally:
 adb('shell','am','force-stop',PACKAGE);(out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
assert report['accepted']
