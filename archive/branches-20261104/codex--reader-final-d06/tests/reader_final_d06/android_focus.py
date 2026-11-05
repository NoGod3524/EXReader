"""Real adb key/touch input plus raw UiAutomator focus observations."""
import hashlib,json,os,pathlib,re,subprocess,time,traceback,xml.etree.ElementTree as ET
assert os.environ.get('GITHUB_ACTIONS')=='true'
out=pathlib.Path.cwd()/'build/d06/android-focus';out.mkdir(parents=True);records=[];sequence=0;accepted=False
PACKAGE='org.exreader.host'
def adb(*args):return subprocess.check_output(['adb',*map(str,args)],timeout=90)
def tree(label):
 global sequence
 sequence+=1;adb('shell','uiautomator','dump','/sdcard/d06-window.xml');raw=adb('exec-out','cat','/sdcard/d06-window.xml');(out/(str(sequence)+'-'+label+'.xml')).write_bytes(raw)
 return ET.fromstring(raw)
def find(t,id=None,text=None,cls=None):
 return [n for n in t.iter('node') if (id is None or n.get('resource-id')==PACKAGE+':id/'+id) and (text is None or n.get('text')==text) and (cls is None or n.get('class')==cls)]
def wait(label,predicate):
 end=time.monotonic()+75
 while time.monotonic()<end:
  t=tree(label)
  if predicate(t):return t
  time.sleep(.3)
 raise AssertionError('native state not reached: '+label)
def tap(node):
 coords=list(map(int,re.findall(r'\d+',node.attrib['bounds'])));assert len(coords)==4 and node.get('enabled')=='true'
 adb('shell','input','tap',(coords[0]+coords[2])//2,(coords[1]+coords[3])//2)
def mark(name,t,condition=True):
 data=adb('exec-out','screencap','-p');(out/(name+'.png')).write_bytes(data)
 row=dict(name=name,passed=bool(condition),focused=[n.attrib for n in t.iter('node') if n.get('focused')=='true'],screenshot_sha256=hashlib.sha256(data).hexdigest());records.append(row);print(json.dumps(row),flush=True);assert condition,row
try:
 adb('shell','am','start','-W','-n',PACKAGE+'/.MainActivity')
 t=wait('open-reader',lambda t:bool(find(t,id='page_label')) or bool(find(t,id='book_list')))
 if not find(t,id='page_label'):
  listing=find(t,id='book_list')[0];items=list(listing);assert items,'native shelf has no retained fixture';tap(items[0]);t=wait('reader',lambda t:bool(find(t,id='page_label')))
 before=find(t,id='page_label')[0].get('text');assert before
 tap(find(t,id='reader_more')[0]);t=wait('more',lambda t:bool(find(t,text='书内搜索')));tap(find(t,text='书内搜索')[0])
 t=wait('query',lambda t:bool(find(t,cls='android.widget.EditText')));tap(find(t,cls='android.widget.EditText')[0]);adb('shell','input','text','abc')
 for code in (21,22,62,29):
  adb('shell','input','keyevent',code);t=tree('query-key-'+str(code));query=find(t,cls='android.widget.EditText');mark('query-key-'+str(code),t,len(query)==1 and query[0].get('focused')=='true')
 # First Back may dismiss IME; second closes dialog. Observe instead of assuming.
 for _ in range(3):
  adb('shell','input','keyevent',4);t=tree('search-back')
  if find(t,id='page_label'):break
 assert find(t,id='page_label');mark('search-back-page-preserved',t,find(t,id='page_label')[0].get('text')==before)
 tap(find(t,id='reader_more')[0]);t=wait('records-menu',lambda t:bool(find(t,text='阅读记录')));tap(find(t,text='阅读记录')[0]);t=wait('records',lambda t:bool(find(t,text='阅读记录')));mark('records-native-entry',t)
 adb('shell','input','keyevent',4);t=wait('records-back',lambda t:bool(find(t,id='page_label')));mark('records-back-page-preserved',t,find(t,id='page_label')[0].get('text')==before)
 tap(find(t,id='back_button')[0]);t=wait('shelf',lambda t:bool(find(t,id='book_list')));count=len(list(find(t,id='book_list')[0]));mark('return-shelf',t)
 tap(find(t,id='import_button')[0]);t=wait('picker',lambda t:any(n.get('package') not in (PACKAGE,'com.android.systemui') for n in t.iter('node')));mark('native-import-picker',t)
 adb('shell','input','keyevent',4);t=wait('picker-cancel',lambda t:bool(find(t,id='book_list')));mark('import-cancel-preserves-shelf',t,len(list(find(t,id='book_list')[0]))==count)
 accepted=True
except Exception:
 traceback.print_exc()
finally:
 report=dict(accepted=accepted,checks=records,harness_sha=os.environ['GITHUB_SHA'],run_id=os.environ['GITHUB_RUN_ID'],attempt=os.environ['GITHUB_RUN_ATTEMPT'],keyboard_accepted=False,scope='emulator adb input on query; not physical keyboard or hardware-mode DPAD')
 (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
assert accepted
