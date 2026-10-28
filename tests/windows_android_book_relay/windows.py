"""Real Windows application first/return stages. SQL is read-only evidence only."""
import argparse,base64,ctypes as C,hashlib,importlib.util,json,os,sqlite3,subprocess,sys,traceback
from pathlib import Path
import relay
ROOT=Path(__file__).resolve().parents[2]
def module(name,path):
 s=importlib.util.spec_from_file_location(name,ROOT/path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
D=module('d23_windows_original','tests/reader_d23_relay/windows.py')
ui=D.ui
def records_dialog(app):
 found=[]
 @ui.ENUM
 def visit(w,unused):
  pid=ui.W.DWORD();ui.U.GetWindowThreadProcessId(w,C.byref(pid))
  if pid.value==app.process.pid and ui.U.IsWindowVisible(w) and ui.U.GetDlgItem(w,211):found.append(w)
  return True
 ui.U.EnumWindows(visit,0);assert len(found)<=1;return found[0] if found else None
def rows(d):
 result=[];box=ui.U.GetDlgItem(d,211)
 for i in range(ui.send(box,0x18B)):
  n=ui.send(box,0x18A,i);buf=C.create_unicode_buffer(n+1);ui.send(box,0x189,i,C.addressof(buf));result.append(buf.value)
 return result
class App(ui.App):
 def focus(self):
  ui.U.SetForegroundWindow(self.window)
 def label(self):return ui.text(ui.U.GetDlgItem(self.window,124))
def sql(app,q,args=()):
 with sqlite3.connect('file:'+str(app.db)+'.product.sqlite?mode=ro',uri=True) as db:return db.execute(q,args).fetchall()
def progress(app,revision=None):
 # Remote arrival order is not graph order. Observe the exact sender revision;
 # the real records UI below independently selects/resolves the safe graph head.
 found=sql(app,"SELECT body_json FROM reader_revisions WHERE entity_kind='progress'")
 values=[json.loads(row[0]) for row in found]
 selected=[v for v in values if v['id']==revision] if revision else values
 assert len(selected)==1,(revision,values)
 row=json.dumps(selected[0])
 v=json.loads(row);l=v['payload']['location'];s=l['selector']
 def txt(v):return base64.b64decode(v['base64']).decode('utf-8') if isinstance(v,dict) else v
 return v,dict(part=l['part'],path=l['part_path'],start=s['start'],end=s['end'],exact=txt(s['exact']),prefix=txt(s['prefix']),suffix=txt(s['suffix']),parser=l['parser_version'],head=v['id'])
def records(app):
 app.focus();ui.A.tap(ord('L'),(ui.A.VK_CONTROL,));d=app.wait(lambda:records_dialog(app));settle(app,d);return d
def settle(app,d):app.wait(lambda:not ui.U.IsWindowEnabled(ui.U.GetDlgItem(d,226)),timeout=90)
def press(app,d,id):ui.send(ui.U.GetDlgItem(d,id),0xF5);settle(app,d)
def close(app,d):
 ui.send(ui.U.GetDlgItem(d,227),0xF5);app.wait(lambda:not ui.U.IsWindow(d));app.wait_idle()
def copy(app):
 app.click('select');app.click('copy');return ui.ACCOUNT.clipboard_text(app)
def main():
 p=argparse.ArgumentParser();p.add_argument('--phase',choices=['windows-first','windows-return'],required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--previous',type=Path);p.add_argument('--package',type=Path,required=True);p.add_argument('--original',type=Path);a=p.parse_args()
 assert os.name=='nt';identity=relay.identity();a.out.mkdir(parents=True,exist_ok=False)
 app=dav=None;data=dict(**identity,passed=False,checks=[]);checks=data['checks']
 try:
  exe=(a.package/'EXReader.exe').resolve();font=(a.package/'Reader.otf').resolve();data['program']={'sha256':hashlib.sha256(exe.read_bytes()).hexdigest(),'source_sha':identity['source_sha']}
  previous=relay.load(a.previous,'android')[0] if a.previous else None
  dav,user,password=relay.start(a.out,a.previous)
  subprocess.run(['certutil','-addstore','-f','Root',str(a.out/'cert.pem')],check=True,capture_output=True)
  app=App(exe,font,a.out/'profile');app.wait_initial_shelf();app.wait_idle()
  if a.phase=='windows-first':
   original=a.original.read_bytes();D.import_book(app,a.original);app.wait(lambda:ui.send(app.control('books'),0x18B)==1,timeout=60)
   digest=hashlib.sha256(original).hexdigest();data.update(original_sha256=digest,original_bytes=len(original),book_identity='epub:'+digest)
   title=sql(app,'SELECT title FROM reader_books')[0][0];data['remote_title']=title
   ui.send(app.control('books'),0x186,0);app.click('open');app.wait_idle()
   for _ in range(3):app.click('next');app.wait_idle()
   d=records(app);press(app,d,214);data['progress_wire'],data['location']=progress(app);close(app,d)
   assert data['location']['part']>0 or data['location']['start']>0
   data['page_text']=copy(app);assert data['page_text'];checks.append('real_windows_picker_import_three_pages_and_progress_save')
  else:
   for key in ('original_sha256','original_bytes','book_identity','remote_title'):data[key]=previous['data'][key]
  d=app.open_account();app.fill(d,root=dav.base+'/dav/',user=user,password=password,remember=False);app.apply(d,'仅本次会话');app.close_account(d)
  d=app.open_account();app.run_sync(d);app.close_account(d)
  if previous:
   assert any(r['method']=='GET' and '/objects/' in r['path'] for r in dav.requests)
   app.wait(lambda:ui.send(app.control('books'),0x18B)==1,timeout=60);ui.send(app.control('books'),0x186,0);app.click('open');app.wait_idle()
   expected=previous['data']['location'];wire,loc=progress(app,expected['head']);assert all(loc[k]==expected[k] for k in ('part','path','start','end','exact','prefix','suffix')),(loc,expected)
   d=records(app);labels=rows(d);index=next(i for i,v in enumerate(labels) if '阅读位置' in v);ui.send(ui.U.GetDlgItem(d,211),0x186,index);ui.send(d,0x111,(1<<16)|211,ui.U.GetDlgItem(d,211));press(app,d,220)
   message=ui.text(ui.U.GetDlgItem(d,212));assert 'FOUND' in message or '找到并定位' in message or '已跳转' in message,message
   close(app,d);text=copy(app);assert loc['suffix'] and loc['suffix'] in text,(loc,text)
   data.update(location=loc,expected_location=expected,page_text=text,restore_message=message,progress_wire=wire,received_progress_wires=[json.loads(r[0]) for r in sql(app,"SELECT body_json FROM reader_revisions WHERE entity_kind='progress'")])
   checks.append('fresh_windows_receives_original_and_exact_android_progress_native_jump_displays_anchor')
  original_path='/dav/exreader-sync-v1/objects/'+data['original_sha256'][:2]+'/'+data['original_sha256']+'.epub'
  assert hashlib.sha256(dav.entries[original_path]).hexdigest()==data['original_sha256']
  assert len(dav.entries[original_path])==data['original_bytes'];checks.append('authenticated_https_original_exact_sha256_and_length')
  if not previous:assert any(r['method']=='PUT' and '/objects/' in r['path'] for r in dav.requests)
  ui.M.screenshot(app.window,a.out/'actual-reader.bmp');data['passed']=True;relay.save(dav,a.out,a.phase,data);dav=None
 finally:
  if app and app.process.poll() is None:app.process.kill();app.process.wait(timeout=20);app.log.close()
  if dav:
   (a.out/'requests.json').write_text(json.dumps(dav.requests));dav.server.shutdown();dav.server.server_close();(a.out/'key.pem').unlink(missing_ok=True)
  (a.out/'report.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(data,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
