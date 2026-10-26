"""Real packaged Windows hosts and local authenticated HTTPS WebDAV fixture."""
import base64
import ctypes as C
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time
import traceback
import uuid

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('import_organize_ui',ROOT/'tests/reader_windows_import_organize/check_ui.py')
ui=importlib.util.module_from_spec(spec);spec.loader.exec_module(ui)
sys.path.insert(0,str(ROOT/'tests/reader_sync'))
from check_sync import revision, raw
out=ROOT/'build/organization-ui';out.mkdir(parents=True,exist_ok=False)
exe=ROOT/'build/c09/package/EXReader/EXReader.exe';font=exe.parent/'Reader.otf'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
checks=[];problems=[];devices=[];dav=None;phase='setup'
report=dict(accepted=False,source_sha=os.environ['GITHUB_SHA'],run_id=os.environ['GITHUB_RUN_ID'],attempt=os.environ['GITHUB_RUN_ATTEMPT'],checks=checks,problems=problems)
def record(name,condition):
    assert condition,name
    checks.append(name);print(name,flush=True)
def sql(device,query,args=()):
    with sqlite3.connect(str(device.db)+'.product.sqlite',timeout=10) as db:return db.execute(query,args).fetchall()
def add_remote(value):
    body=raw(value);prefix='/dav/exreader-sync-v1/revisions/'+value['id'][:2]+'/'
    dav.directories.add('/dav/exreader-sync-v1/');dav.directories.add('/dav/exreader-sync-v1/revisions/');dav.directories.add(prefix)
    dav.entries[prefix+value['id']+'-'+hashlib.sha256(body).hexdigest()+'.json']=body
def sync(device):
    dialog=device.open_account();device.press(dialog,ui.ACCOUNT.SYNC)
    device.wait(lambda: not device.enabled(dialog,ui.ACCOUNT.CANCEL) and ('同步完成' in device.note(dialog) or '接收尚未完成' in device.note(dialog) or '请先恢复' in device.note(dialog)),timeout=240)
    message=device.note(dialog);detail=device.detail(dialog);return dialog,message,detail
def names(dialog,control):
    box=ui.U.GetDlgItem(dialog,control);values=[]
    for i in range(ui.send(box,0x18B)):
        n=ui.send(box,0x18A,i);buf=C.create_unicode_buffer(n+1);ui.send(box,0x189,i,C.addressof(buf));values.append(buf.value)
    return values
try:
    assert os.name=='nt' and os.environ.get('GITHUB_ACTIONS')=='true'
    certs=out/'certificates';certs.mkdir();key=certs/'server.key';cert=certs/'server.crt'
    openssl=shutil.which('openssl') or r'C:\Program Files\Git\usr\bin\openssl.exe'
    subprocess.run([openssl,'req','-x509','-newkey','rsa:2048','-nodes','-days','1','-keyout',str(key),'-out',str(cert),'-subj','/CN=127.0.0.1','-addext','subjectAltName=IP:127.0.0.1'],check=True,capture_output=True)
    subprocess.run(['certutil','-addstore','-f','Root',str(cert)],check=True,capture_output=True)
    user='fixture-user';password='secret-'+uuid.uuid4().hex
    auth='Basic '+base64.b64encode((user+':'+password).encode()).decode();dav=ui.ACCOUNT.Dav(cert,key,auth)
    report['server']={'base':dav.base,'certificate_sha256':sha(cert),'source_sha256':sha(ROOT/'tests/reader_windows_account/check_account_ui.py')}
    book=out/'Book.txt';book.write_text('A real synchronized book. '*100,encoding='utf-8');bookkey='txt:'+sha(book)
    a=ui.App(exe,font,out/'device-a');devices.append(a);a.wait_initial_shelf();a.wait_idle()
    ui.ACCOUNT.set_text(a.control('path'),str(book));ui.send(a.control('import'),ui.ACCOUNT.BM_CLICK,timeout=5000)
    a.wait(lambda:'已导入' in a.status() or '去重' in a.status(),timeout=180);a.wait_idle()
    d=a.open_account();a.fill(d,dav.base+'/dav/',user,password,False);a.apply(d,'仅本次会话');a.close_account(d)
    d,message,detail=sync(a);record('producer-book-sync','同步完成' in message);a.close_account(d)
    original=json.loads(sql(a,"SELECT body_json FROM reader_revisions WHERE entity_kind='book' AND entity_key=?",(bookkey,))[0][0])
    # Child sorts before its parent; extra rows cross the eight-row page boundary.
    parent='f'*32;child='1'*32;tag='2'*32;series='3'*32
    values=[revision(1,shard=0x61,kind='shelf',key=parent,payload={'name':'Parent shelf','parent_id':None,'ordinal':0}),
            revision(2,shard=0x61,kind='shelf',key=child,payload={'name':'Child shelf','parent_id':parent,'ordinal':1}),
            revision(3,shard=0x61,kind='tag',key=tag,payload={'name':'Remote tag'}),
            revision(4,shard=0x61,kind='series',key=series,payload={'name':'Remote series'})]
    for n in range(10):values.append(revision(20+n,shard=0x61,kind='shelf',key=('%032x'%(0x40+n)),payload={'name':'Extra %02d'%n,'parent_id':None,'ordinal':n}))
    members=[]
    for n,kind,ident in [(5,'shelf',child),(6,'tag',tag),(7,'series',series)]:
        members.append(revision(n,shard=0x61,kind='membership',key=kind+':'+ident+':'+bookkey,payload={'collection_kind':kind,'collection_id':ident,'book_key':bookkey,'ordinal':0}))
    for value in values+members:add_remote(value)
    missing=revision(80,shard=0x61,kind='tag',key='4'*32,payload={'name':'Missing parent tag'},parents=['e'*32])
    conflict1=revision(81,shard=0x61,kind='tag',key='5'*32,payload={'name':'Conflict A'})
    conflict2=revision(82,shard=0x61,kind='tag',key='5'*32,payload={'name':'Conflict B'})
    for value in (missing,conflict1,conflict2):add_remote(value)
    b=ui.App(exe,font,out/'device-b');devices.append(b);b.wait_initial_shelf();b.wait_idle()
    d=b.open_account();b.fill(d,dav.base+'/dav/',user,password,False);b.apply(d,'仅本次会话');b.close_account(d)
    phase='first-receive';d,message,detail=sync(b)
    record('unresolved-history-not-complete','接收尚未完成' in message and '并发 1' in message and '缺祖先 1' in message)
    record('hierarchy-and-pagination',sql(b,"SELECT name,parent_id FROM reader_shelves WHERE shelf_id=?",(child,))==[('Child shelf',parent)] and sql(b,'SELECT count(*) FROM reader_shelves WHERE deleted=0')==[(12,)])
    record('three-memberships',all(sql(b,'SELECT count(*) FROM '+table)==[(1,)] for table in ('reader_book_shelves','reader_book_tags','reader_book_series')))
    record('unsafe-tags-not-projected',sql(b,"SELECT count(*) FROM reader_tags WHERE tag_id IN (?,?)",('4'*32,'5'*32))==[(0,)])
    ui.M.screenshot(d,out/'unresolved.bmp');b.close_account(d)
    b.wait(lambda:b.has_row('Book'),timeout=60)
    ui.U.SetForegroundWindow(b.window);ui.A.tap(ord('O'),(ui.A.VK_CONTROL,ui.A.VK_SHIFT));dialog=b.io_dialog()
    b.wait(lambda:not ui.U.IsWindowEnabled(ui.U.GetDlgItem(dialog,ui.CANCEL)))
    ui.send(ui.U.GetDlgItem(dialog,ui.ACTION),0x14E,4);ui.send(dialog,0x111,(1<<16)|ui.ACTION,ui.U.GetDlgItem(dialog,ui.ACTION))
    b.wait(lambda:any('Remote tag' in x for x in names(dialog,ui.GROUPS)),timeout=30)
    record('native-organizer-shows-remote-tag',True);ui.M.screenshot(dialog,out/'organizer.bmp')
    ui.send(ui.U.GetDlgItem(dialog,ui.CLOSE),0xF5);b.wait(lambda:not ui.U.IsWindow(dialog));b.wait_idle()
    ancestor=revision(83,shard=0x61,kind='tag',key='4'*32,payload={'name':'Ancestor'});ancestor['id']='e'*32
    resolved=revision(84,shard=0x61,kind='tag',key='5'*32,payload={'name':'Resolved'},parents=[conflict1['id'],conflict2['id']])
    tombstone=revision(85,shard=0x61,kind='membership',key=members[0]['entity_key'],parents=[members[0]['id']],operation='delete')
    for value in (ancestor,resolved,tombstone):add_remote(value)
    phase='resolution';d,message,detail=sync(b)
    record('retry-after-history-resolution','同步完成' in message and sql(b,"SELECT name FROM reader_tags WHERE tag_id IN (?,?) ORDER BY name",('4'*32,'5'*32))==[('Missing parent tag',),('Resolved',)])
    record('membership-tombstone-applied',sql(b,'SELECT count(*) FROM reader_book_shelves')==[(0,)] and sql(b,'SELECT count(*) FROM reader_book_tags')==[(1,)])
    b.close_account(d)
    phase='book-tombstone';deleted=revision(86,shard=0x61,kind='book',key=bookkey,parents=[original['id']],operation='delete');add_remote(deleted)
    d,message,detail=sync(b);record('book-tombstone-soft-deletes','接收尚未完成' in message and sql(b,'SELECT deleted FROM reader_books WHERE book_key=?',(bookkey,))==[(1,)] and sql(b,'SELECT count(*) FROM reader_local_books WHERE book_key=?',(bookkey,))==[(1,)])
    b.close_account(d);b.wait(lambda:not b.has_row('Book'),timeout=60)
    record('deleted-book-removed-from-shelf',True)
    restored=revision(87,shard=0x61,kind='book',key=bookkey,payload=original['payload'],parents=[deleted['id']],operation='restore');add_remote(restored)
    d,message,detail=sync(b);record('book-explicit-restore','同步完成' in message and sql(b,'SELECT deleted FROM reader_books WHERE book_key=?',(bookkey,))==[(0,)] and sql(b,'SELECT count(*) FROM reader_local_books WHERE book_key=?',(bookkey,))==[(1,)])
    b.close_account(d);b.wait(lambda:b.has_row('Book'),timeout=60);record('restored-book-visible',True)
    phase='pending-barrier';pending=Path(str(b.db)+'.product.sqlite.bulk.pending');pending.write_bytes(b'preserve unfinished request')
    d,message,detail=sync(b);record('pending-local-intent-blocks-receive','请先恢复' in message and pending.read_bytes()==b'preserve unfinished request')
    ui.M.screenshot(d,out/'pending.bmp');pending.unlink();b.press(d,ui.ACCOUNT.RETRY)
    b.wait(lambda:'同步完成' in b.note(d),timeout=240);record('retry-after-local-recovery',True);b.close_account(d)
    phase='cancel-original-import'
    big=(b'large synchronized original text. '*900000);big_hash=hashlib.sha256(big).hexdigest();big_key='txt:'+big_hash
    large=revision(90,shard=0x61,kind='book',key=big_key,payload={'format':'txt','source_sha256':big_hash,'source_bytes':len(big),'title':'ZZ large book','author':'','favorite':False});add_remote(large)
    prefix='/dav/exreader-sync-v1/objects/'+big_hash[:2]+'/';dav.directories.add('/dav/exreader-sync-v1/objects/');dav.directories.add(prefix);dav.entries[prefix+big_hash+'.txt']=big
    c=ui.App(exe,font,out/'device-c');devices.append(c);c.wait_initial_shelf();c.wait_idle()
    d=c.open_account();c.fill(d,dav.base+'/dav/',user,password,False);c.apply(d,'仅本次会话');c.press(d,ui.ACCOUNT.SYNC)
    c.wait(lambda:'正在应用云端书籍' in c.note(d),timeout=240)
    c.wait(lambda:sql(c,'SELECT count(*) FROM reader_books WHERE book_key=?',(big_key,))==[(1,)] and sql(c,'SELECT count(*) FROM reader_local_books WHERE book_key=?',(bookkey,))==[(1,)],timeout=120)
    class Io(C.Structure):
        _fields_=[(name,C.c_ulonglong) for name in ('read_ops','write_ops','other_ops','read_bytes','write_bytes','other_bytes')]
    kernel=C.WinDLL('kernel32',use_last_error=True);kernel.GetProcessIoCounters.argtypes=[C.c_void_p,C.POINTER(Io)];kernel.GetProcessIoCounters.restype=C.c_int
    def reads():
        value=Io();assert kernel.GetProcessIoCounters(int(c.process._handle),C.byref(value));return value.read_bytes
    before=reads();deadline=time.monotonic()+60
    while reads()-before<1024*1024 and time.monotonic()<deadline and c.enabled(d,ui.ACCOUNT.CANCEL):time.sleep(.001)
    delta=reads()-before
    assert delta>=1024*1024 and c.enabled(d,ui.ACCOUNT.CANCEL),('import did not expose an active read boundary',delta,c.note(d))
    c.press(d,ui.ACCOUNT.CANCEL);c.wait(lambda:'接收已取消' in c.note(d),timeout=120)
    record('cancel-active-original-read',sql(c,'SELECT count(*) FROM reader_local_books WHERE book_key=?',(big_key,))==[(0,)] and sql(c,'SELECT count(*) FROM reader_local_books WHERE book_key=?',(bookkey,))==[(1,)])
    c.press(d,ui.ACCOUNT.RETRY);c.wait(lambda:'同步完成' in c.note(d),timeout=240)
    record('resume-import-without-duplicate',sql(c,'SELECT count(*) FROM reader_local_books WHERE book_key IN (?,?)',(bookkey,big_key))==[(2,)] and sql(c,'SELECT count(*) FROM reader_local_books WHERE book_key=?',(big_key,))==[(1,)])
    c.close_account(d)
    record('authenticated-webdav-traffic',any(r['method']=='PUT' and r['authenticated'] for r in dav.requests) and any(r['method']=='GET' and r['authenticated'] for r in dav.requests))
    report['accepted']=True
except Exception as error:
    problems.append(phase+': '+type(error).__name__+': '+str(error));traceback.print_exc()
    try:ui.M.screenshot(ui.U.GetDesktopWindow(),out/'failure.bmp')
    except Exception:pass
finally:
    for device in devices:
        try:
            if device.process.poll() is None:device.process.kill();device.process.wait(timeout=20)
            if not device.log.closed:device.log.close()
        except Exception:pass
    if dav:dav.release.set();dav.server.shutdown();dav.server.server_close();report['requests']=dav.requests
    for p in out.glob('certificates/*.key'):p.unlink()
    if exe.exists():report['program_sha256']=sha(exe)
    (out/'report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8');print(json.dumps(report,ensure_ascii=True),flush=True)
if not report['accepted']:raise SystemExit('Windows organization UI rejected')
