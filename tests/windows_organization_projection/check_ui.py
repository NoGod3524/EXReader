"""Real packaged Windows hosts and local authenticated HTTPS WebDAV fixture."""
import base64
import ctypes as C
from ctypes import wintypes as W
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
import zipfile

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
    count=C.c_ssize_t(ui.send(box,0x18B)).value
    if count<0:return []
    for i in range(count):
        n=C.c_ssize_t(ui.send(box,0x18A,i)).value
        if n<0:return []
        buf=C.create_unicode_buffer(n+1);ui.send(box,0x189,i,C.addressof(buf));values.append(buf.value)
    return values
def import_book(app,path):
    ui.U.SetForegroundWindow(app.window);ui.A.tap(ord('O'),(ui.A.VK_CONTROL,))
    def owned():
        found=[]
        @ui.ENUM
        def visit(window,unused):
            pid=W.DWORD();ui.U.GetWindowThreadProcessId(window,C.byref(pid))
            name=C.create_unicode_buffer(100);ui.U.GetClassNameW(window,name,100)
            if pid.value==app.process.pid and window!=app.window and ui.U.IsWindowVisible(window) and name.value=='#32770' and ui.U.GetDlgItem(window,1):found.append(window)
            return True
        ui.U.EnumWindows(visit,0);return found[-1] if found else None
    dialog=app.wait(owned,timeout=20);candidates=[]
    ui.U.GetParent.argtypes=[W.HWND];ui.U.GetParent.restype=W.HWND
    ui.U.GetDlgCtrlID.argtypes=[W.HWND];ui.U.GetDlgCtrlID.restype=C.c_int
    ui.U.EnumChildWindows.argtypes=[W.HWND,ui.ENUM,W.LPARAM]
    @ui.ENUM
    def child(window,unused):
        name=C.create_unicode_buffer(100);ui.U.GetClassNameW(window,name,100)
        if name.value=='Edit' and ui.U.IsWindowVisible(window):
            parent=window
            for _ in range(5):
                if ui.U.GetDlgCtrlID(parent) in (1148,1152):candidates.append(window);break
                parent=ui.U.GetParent(parent)
                if not parent or parent==dialog:break
        return True
    ui.U.EnumChildWindows(dialog,child,0);assert len(candidates)==1
    ui.ACCOUNT.set_text(candidates[0],str(path.resolve()));ui.send(dialog,0x111,1)
    app.wait(lambda:not ui.U.IsWindow(dialog),timeout=30);app.wait_idle()
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
    import_book(a,book);a.wait(lambda:ui.send(a.control('books'),0x18B)==1,timeout=60)
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
    ui.send(ui.U.GetDlgItem(dialog,ui.ACTION),0x14E,2);ui.send(dialog,0x111,(1<<16)|ui.ACTION,ui.U.GetDlgItem(dialog,ui.ACTION))
    b.wait(lambda:any('Parent shelf' in x for x in names(dialog,ui.GROUPS)),timeout=30)
    group=ui.U.GetDlgItem(dialog,ui.GROUPS);rows=names(dialog,ui.GROUPS)
    ui.send(group,0x186,next(i for i,value in enumerate(rows) if 'Parent shelf' in value));ui.send(dialog,0x111,(2<<16)|ui.GROUPS,group)
    b.wait(lambda:not ui.U.IsWindowEnabled(ui.U.GetDlgItem(dialog,ui.CANCEL)))
    b.wait(lambda:any('Child shelf' in x for x in names(dialog,ui.GROUPS)),timeout=30)
    record('native-organizer-shows-hierarchy',True)
    ui.send(ui.U.GetDlgItem(dialog,ui.ACTION),0x14E,6);ui.send(dialog,0x111,(1<<16)|ui.ACTION,ui.U.GetDlgItem(dialog,ui.ACTION))
    b.wait(lambda:any('Remote series' in x for x in names(dialog,ui.GROUPS)),timeout=30);record('native-organizer-shows-series',True)
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
    deleted_readback=out/'deleted-readback';deleted_readback.mkdir();deleted_spec=out/'deleted-readback.spec'
    deleted_spec.write_text('cmd=readback\nlibrary=%s\nout=%s\n'%(b.db,deleted_readback),encoding='utf-8')
    deleted_probe=subprocess.run([str(ROOT/'build/cloud-readback/cloud-probe.exe'),str(deleted_spec)],capture_output=True,text=True,encoding='utf-8',timeout=120)
    assert deleted_probe.returncode==0,deleted_probe.stderr
    deleted_audit=json.loads(deleted_probe.stdout);report['deleted_readback']=deleted_audit;report['deleted_original_sha256']=sha(book)
    record('deleted-book-original-retained',deleted_audit['ok']==1 and len(deleted_audit['books'])==1 and deleted_audit['books'][0]['read_ok']==1 and sha(deleted_readback/('book-%d.bin'%deleted_audit['books'][0]['id']))==sha(book))
    restored=revision(87,shard=0x61,kind='book',key=bookkey,payload=original['payload'],parents=[deleted['id']],operation='restore');add_remote(restored)
    d,message,detail=sync(b);record('book-explicit-restore','同步完成' in message and sql(b,'SELECT deleted FROM reader_books WHERE book_key=?',(bookkey,))==[(0,)] and sql(b,'SELECT count(*) FROM reader_local_books WHERE book_key=?',(bookkey,))==[(1,)])
    b.close_account(d);b.wait(lambda:b.has_row('Book'),timeout=60);record('restored-book-visible',True)
    phase='group-tombstones';group_deletes=[]
    for n,value in enumerate((values[1],values[2],values[3]),100):
        removed=revision(n,shard=0x61,kind=value['entity_kind'],key=value['entity_key'],parents=[value['id']],operation='delete')
        add_remote(removed);group_deletes.append(removed)
    d,message,detail=sync(b)
    record('group-tombstones-applied','接收尚未完成' in message and all(sql(b,'SELECT deleted FROM '+table+' WHERE '+column+'=?',(ident,))==[(1,)] for table,column,ident in [('reader_shelves','shelf_id',child),('reader_tags','tag_id',tag),('reader_series','series_id',series)]))
    b.close_account(d)
    for n,(value,removed) in enumerate(zip((values[1],values[2],values[3]),group_deletes),110):
        add_remote(revision(n,shard=0x61,kind=value['entity_kind'],key=value['entity_key'],payload=value['payload'],parents=[removed['id']],operation='restore'))
    d,message,detail=sync(b)
    record('group-explicit-restores','同步完成' in message and all(sql(b,'SELECT deleted FROM '+table+' WHERE '+column+'=?',(ident,))==[(0,)] for table,column,ident in [('reader_shelves','shelf_id',child),('reader_tags','tag_id',tag),('reader_series','series_id',series)]))
    b.close_account(d)
    phase='pending-barrier';pending=Path(str(b.db)+'.product.sqlite.bulk.pending');pending.write_bytes(b'preserve unfinished request')
    d,message,detail=sync(b);record('pending-local-intent-blocks-receive','请先恢复' in message and pending.read_bytes()==b'preserve unfinished request')
    ui.M.screenshot(d,out/'pending.bmp');pending.unlink();b.press(d,ui.ACCOUNT.RETRY)
    b.wait(lambda:'同步完成' in b.note(d),timeout=240);record('retry-after-local-recovery',True);b.close_account(d)
    phase='cancel-original-import'
    large_file=out/'large.cbz';ui.ACCOUNT.make_cbz(large_file)
    with zipfile.ZipFile(large_file,'a',compression=zipfile.ZIP_STORED) as archive:archive.writestr('padding.bin',b'\0'*(100*1024*1024))
    big=large_file.read_bytes();big_hash=hashlib.sha256(big).hexdigest();big_key='cbz:'+big_hash
    large=revision(90,shard=0x61,kind='book',key=big_key,payload={'format':'cbz','source_sha256':big_hash,'source_bytes':len(big),'title':'ZZ large book','author':'','favorite':False});add_remote(large)
    prefix='/dav/exreader-sync-v1/objects/'+big_hash[:2]+'/';dav.directories.add('/dav/exreader-sync-v1/objects/');dav.directories.add(prefix);dav.entries[prefix+big_hash+'.cbz']=big
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
    readback=out/'cancel-readback';readback.mkdir();spec=out/'cancel-readback.spec'
    spec.write_text('cmd=readback\nlibrary=%s\nout=%s\n'%(c.db,readback),encoding='utf-8')
    probe=ROOT/'build/cloud-readback/cloud-probe.exe';value=subprocess.run([str(probe),str(spec)],capture_output=True,text=True,encoding='utf-8',timeout=240)
    assert value.returncode==0,value.stderr
    audit=json.loads(value.stdout);report['cancel_readback']=audit;report['cancel_input_hashes']=[sha(book),big_hash]
    record('cancel-resume-original-hashes',audit['ok']==1 and len(audit['books'])==2 and all(item['read_ok']==1 for item in audit['books']) and {sha(readback/('book-%d.bin'%item['id'])) for item in audit['books']}==set(report['cancel_input_hashes']))
    phase='mapping-repair';other=ui.App(exe,font,out/'device-d');devices.append(other);other.wait_initial_shelf();other.wait_idle()
    d=other.open_account();other.fill(d,dav.base+'/dav/',user,password,False);other.apply(d,'仅本次会话');other.press(d,ui.ACCOUNT.SYNC)
    other.wait(lambda:'正在应用云端书籍' in other.note(d),timeout=240)
    other.wait(lambda:sql(other,'SELECT count(*) FROM reader_books')[0][0]>=2 and sql(other,'SELECT count(*) FROM reader_local_books WHERE book_key=?',(bookkey,))==[(1,)],timeout=120)
    def other_reads():
        value=Io();assert kernel.GetProcessIoCounters(int(other.process._handle),C.byref(value));return value.read_bytes
    before=other_reads();deadline=time.monotonic()+60
    while other_reads()-before<1024*1024 and time.monotonic()<deadline and other.enabled(d,ui.ACCOUNT.CANCEL):time.sleep(.001)
    assert other_reads()-before>=1024*1024 and other.enabled(d,ui.ACCOUNT.CANCEL),'second import never entered active reading'
    lock=None;deadline=time.monotonic()+30
    while time.monotonic()<deadline:
        try:
            lock=sqlite3.connect(str(other.db)+'.product.sqlite',timeout=.05,isolation_level=None);lock.execute('BEGIN IMMEDIATE');break
        except sqlite3.OperationalError:
            if lock:lock.close()
            lock=None
        time.sleep(.003)
    assert lock is not None,'no committed first mapping before second mapping fault'
    try:other.wait_note(d,'映射待恢复',300)
    finally:lock.rollback();lock.close()
    other.close_account(d)
    deadline=time.monotonic()+120
    while time.monotonic()<deadline:
        try:
            if sql(other,'SELECT count(*) FROM reader_local_books')==[(2,)] and other.has_row('Book'):break
        except sqlite3.OperationalError:pass
        ui.send(ui.U.GetDlgItem(other.window,ui.ACCOUNT.REFRESH),ui.ACCOUNT.BM_CLICK);time.sleep(1)
    with sqlite3.connect(str(other.db)) as db:sdk_count=db.execute('SELECT count(*) FROM books').fetchone()[0]
    record('mapping-repair-reaches-shelf-without-reimport',sql(other,'SELECT count(*) FROM reader_local_books')==[(2,)] and other.has_row('Book') and sdk_count==2)
    record('authenticated-webdav-traffic',any(r['method']=='PUT' and r['authenticated'] for r in dav.requests) and any(r['method']=='GET' and r['authenticated'] for r in dav.requests))
    phase='native-create-groups'
    d,message,detail=sync(a);assert '同步完成' in message;a.close_account(d)
    a.wait_idle();ui.U.SetForegroundWindow(a.window);ui.A.tap(ord('O'),(ui.A.VK_CONTROL,ui.A.VK_SHIFT));dialog=a.io_dialog()
    a.wait(lambda:not ui.U.IsWindowEnabled(ui.U.GetDlgItem(dialog,ui.CANCEL)),timeout=120)
    name_control,create_control=256,257
    metadata_consumer=ROOT/'build/organization-consumer/metadata-consumer.exe'
    product=str(a.db)+'.product.sqlite';pending=product+'.commands.pending'
    staged=subprocess.run([str(metadata_consumer),'group',product,pending,'1','-','Recovery tag','-','0','0','stage'],
                          capture_output=True,text=True,encoding='utf-8',timeout=60)
    assert staged.returncode==0 and json.loads(staged.stdout)['status']==0 and Path(pending).exists(),staged.stdout+staged.stderr
    report['metadata_consumer_sha256']=sha(metadata_consumer)
    ui.send(ui.U.GetDlgItem(dialog,258),ui.ACCOUNT.BM_CLICK)
    a.wait(lambda:sql(a,'SELECT count(*) FROM reader_tags WHERE name=? AND deleted=0',('Recovery tag',))==[(1,)],timeout=120)
    a.wait(lambda:not ui.U.IsWindowEnabled(ui.U.GetDlgItem(dialog,ui.CANCEL)),timeout=120)
    record('native-recover-staged-group',not Path(pending).exists())
    def select_action(action):
        ui.send(ui.U.GetDlgItem(dialog,ui.ACTION),0x14E,action)
        ui.send(dialog,0x111,(1<<16)|ui.ACTION,ui.U.GetDlgItem(dialog,ui.ACTION))
        a.wait(lambda:not ui.U.IsWindowEnabled(ui.U.GetDlgItem(dialog,ui.CANCEL)),timeout=120)
    def create(name,table):
        ui.ACCOUNT.set_text(ui.U.GetDlgItem(dialog,name_control),name)
        ui.send(ui.U.GetDlgItem(dialog,create_control),ui.ACCOUNT.BM_CLICK)
        a.wait(lambda:sql(a,'SELECT count(*) FROM '+table+' WHERE name=? AND deleted=0',(name,))==[(1,)],timeout=120)
        a.wait(lambda:not ui.U.IsWindowEnabled(ui.U.GetDlgItem(dialog,ui.CANCEL)),timeout=120)
    select_action(2)
    before=sql(a,'SELECT count(*) FROM reader_shelves')
    ui.send(ui.U.GetDlgItem(dialog,create_control),ui.ACCOUNT.BM_CLICK)
    record('native-empty-group-name-refused',sql(a,'SELECT count(*) FROM reader_shelves')==before and not ui.U.IsWindowEnabled(ui.U.GetDlgItem(dialog,ui.CANCEL)))
    ui.ACCOUNT.set_text(ui.U.GetDlgItem(dialog,name_control),'x'*257)
    ui.send(ui.U.GetDlgItem(dialog,create_control),ui.ACCOUNT.BM_CLICK)
    record('native-long-group-name-refused',sql(a,'SELECT count(*) FROM reader_shelves')==before and not ui.U.IsWindowEnabled(ui.U.GetDlgItem(dialog,ui.CANCEL)))
    create('Local shelf 父','reader_shelves')
    values=names(dialog,ui.GROUPS);index=values.index('Local shelf 父')
    ui.send(ui.U.GetDlgItem(dialog,ui.GROUPS),0x186,index)
    ui.send(dialog,0x111,(2<<16)|ui.GROUPS,ui.U.GetDlgItem(dialog,ui.GROUPS))
    a.wait(lambda:not ui.U.IsWindowEnabled(ui.U.GetDlgItem(dialog,ui.CANCEL)),timeout=120)
    create('Local shelf 子','reader_shelves')
    select_action(4);create('Local tag 标签','reader_tags')
    create('🍀'*256,'reader_tags')
    record('native-256-scalar-group-name-preserved',sql(a,'SELECT count(*) FROM reader_tags WHERE name=? AND deleted=0',('🍀'*256,))==[(1,)] and '🍀'*256 in names(dialog,ui.GROUPS))
    select_action(6);create('Local series 系列','reader_series')
    parent=sql(a,'SELECT shelf_id FROM reader_shelves WHERE name=?',('Local shelf 父',))[0][0]
    record('native-create-shelf-tag-series-and-child',sql(a,'SELECT parent_id FROM reader_shelves WHERE name=?',('Local shelf 子',))==[(parent,)])
    ui.send(ui.U.GetDlgItem(dialog,ui.CLOSE),ui.ACCOUNT.BM_CLICK);a.wait(lambda:not ui.U.IsWindow(dialog),timeout=20)
    d,message,detail=sync(a);assert '同步完成' in message;a.close_account(d)
    d,message,detail=sync(b)
    record('native-created-groups-sync-to-second-host','同步完成' in message and
        sql(b,'SELECT parent_id FROM reader_shelves WHERE name=?',('Local shelf 子',))==[(parent,)] and
        sql(b,'SELECT count(*) FROM reader_tags WHERE name=? AND deleted=0',('Local tag 标签',))==[(1,)] and
        sql(b,'SELECT count(*) FROM reader_tags WHERE name=? AND deleted=0',('🍀'*256,))==[(1,)] and
        sql(b,'SELECT count(*) FROM reader_tags WHERE name=? AND deleted=0',('Recovery tag',))==[(1,)] and
        sql(b,'SELECT count(*) FROM reader_series WHERE name=? AND deleted=0',('Local series 系列',))==[(1,)])
    b.close_account(d)
    phase='native-group-browsing'
    a.wait(lambda:ui.send(a.control('books'),0x18B)>=2,timeout=120)
    def organizer():
        a.wait_idle();ui.U.SetForegroundWindow(a.window);ui.A.tap(ord('O'),(ui.A.VK_CONTROL,ui.A.VK_SHIFT));w=a.io_dialog()
        a.wait(lambda:not ui.U.IsWindowEnabled(ui.U.GetDlgItem(w,ui.CANCEL)),timeout=120);return w
    def tag_selection(w,label):
        ui.send(ui.U.GetDlgItem(w,ui.ACTION),0x14E,4)
        ui.send(w,0x111,(1<<16)|ui.ACTION,ui.U.GetDlgItem(w,ui.ACTION))
        a.wait(lambda:label in names(w,ui.GROUPS),timeout=60)
        group=ui.U.GetDlgItem(w,ui.GROUPS);ui.send(group,0x186,names(w,ui.GROUPS).index(label))
    def membership_action(action,label,table,column,group_id,present):
        w=organizer()
        ui.send(ui.U.GetDlgItem(w,ui.ACTION),0x14E,action)
        ui.send(w,0x111,(1<<16)|ui.ACTION,ui.U.GetDlgItem(w,ui.ACTION))
        a.wait(lambda:label in names(w,ui.GROUPS),timeout=60)
        group=ui.U.GetDlgItem(w,ui.GROUPS)
        ui.send(group,0x186,names(w,ui.GROUPS).index(label))
        items=ui.A.auto.ControlFromHandle(ui.U.GetDlgItem(w,ui.ROWS)).GetChildren()
        matches=[item for item in items if 'Book' in item.Name];assert len(matches)==1
        matches[0].GetSelectionItemPattern().Select()
        ui.send(ui.U.GetDlgItem(w,ui.GO),ui.ACCOUNT.BM_CLICK)
        query='SELECT count(*) FROM '+table+' WHERE '+column+'=? AND book_key=?'
        a.wait(lambda:sql(a,query,(group_id,bookkey))==[(present,)],timeout=120)
        a.wait(lambda:ui.U.IsWindowEnabled(ui.U.GetDlgItem(w,ui.ACK)),timeout=120)
        ui.send(ui.U.GetDlgItem(w,ui.ACK),ui.ACCOUNT.BM_CLICK)
        a.wait(lambda:not ui.U.IsWindowEnabled(ui.U.GetDlgItem(w,ui.CANCEL)),timeout=120)
        ui.send(ui.U.GetDlgItem(w,ui.CLOSE),ui.ACCOUNT.BM_CLICK)
        a.wait(lambda:not ui.U.IsWindow(w),timeout=20)
    series_id=sql(a,'SELECT series_id FROM reader_series WHERE name=?',('Local series 系列',))[0][0]
    membership_action(2,'Local shelf 父','reader_book_shelves','shelf_id',parent,1)
    membership_action(6,'Local series 系列','reader_book_series','series_id',series_id,1)
    d,message,detail=sync(a);assert '同步完成' in message;a.close_account(d)
    d,message,detail=sync(b);assert '同步完成' in message;b.close_account(d)
    record('native-shelf-series-memberships-sync',
        sql(b,'SELECT count(*) FROM reader_book_shelves WHERE shelf_id=? AND book_key=?',(parent,bookkey))==[(1,)] and
        sql(b,'SELECT count(*) FROM reader_book_series WHERE series_id=? AND book_key=?',(series_id,bookkey))==[(1,)])
    membership_action(3,'Local shelf 父','reader_book_shelves','shelf_id',parent,0)
    membership_action(7,'Local series 系列','reader_book_series','series_id',series_id,0)
    d,message,detail=sync(a);assert '同步完成' in message;a.close_account(d)
    d,message,detail=sync(b);assert '同步完成' in message;b.close_account(d)
    record('native-shelf-series-removals-sync',
        sql(b,'SELECT count(*) FROM reader_book_shelves WHERE shelf_id=? AND book_key=?',(parent,bookkey))==[(0,)] and
        sql(b,'SELECT count(*) FROM reader_book_series WHERE series_id=? AND book_key=?',(series_id,bookkey))==[(0,)])
    dialog=organizer();tag_selection(dialog,'Local tag 标签')
    items=ui.A.auto.ControlFromHandle(ui.U.GetDlgItem(dialog,ui.ROWS)).GetChildren()
    matches=[item for item in items if 'Book' in item.Name];assert len(matches)==1
    matches[0].GetSelectionItemPattern().Select();ui.send(ui.U.GetDlgItem(dialog,ui.GO),ui.ACCOUNT.BM_CLICK)
    tag_id=sql(a,'SELECT tag_id FROM reader_tags WHERE name=?',('Local tag 标签',))[0][0]
    a.wait(lambda:sql(a,'SELECT count(*) FROM reader_book_tags WHERE tag_id=? AND book_key=?',(tag_id,bookkey))==[(1,)],timeout=120)
    a.wait(lambda:ui.U.IsWindowEnabled(ui.U.GetDlgItem(dialog,ui.ACK)),timeout=120)
    ui.send(ui.U.GetDlgItem(dialog,ui.ACK),ui.ACCOUNT.BM_CLICK)
    a.wait(lambda:not ui.U.IsWindowEnabled(ui.U.GetDlgItem(dialog,ui.CANCEL)),timeout=120)
    ui.send(ui.U.GetDlgItem(dialog,260),ui.ACCOUNT.BM_CLICK)
    a.wait(lambda:not ui.U.IsWindow(dialog),timeout=20)
    a.wait(lambda:ui.send(a.control('books'),0x18B)==1 and a.has_row('Book'),timeout=60)
    record('native-tag-browse-shows-only-members',not a.has_row('ZZ large book') and 'Local tag 标签' in ui.text(ui.U.GetDlgItem(a.window,118)))
    ui.ACCOUNT.set_text(ui.U.GetDlgItem(a.window,126),'ZZ')
    a.wait(lambda:ui.send(a.control('books'),0x18B)==0,timeout=60)
    ui.ACCOUNT.set_text(ui.U.GetDlgItem(a.window,126),'')
    a.wait(lambda:ui.send(a.control('books'),0x18B)==1 and a.has_row('Book'),timeout=60)
    record('native-group-search-stays-within-group',True)
    dialog=organizer();tag_selection(dialog,'Recovery tag')
    ui.send(ui.U.GetDlgItem(dialog,260),ui.ACCOUNT.BM_CLICK);a.wait(lambda:not ui.U.IsWindow(dialog),timeout=20)
    a.wait(lambda:ui.send(a.control('books'),0x18B)==0,timeout=60)
    record('native-empty-group-shows-no-books',ui.send(a.control('books'),0x18B)==0 and 'Recovery tag' in ui.text(ui.U.GetDlgItem(a.window,118)))
    dialog=organizer();ui.send(ui.U.GetDlgItem(dialog,261),ui.ACCOUNT.BM_CLICK)
    a.wait(lambda:not ui.U.IsWindow(dialog),timeout=20)
    a.wait(lambda:ui.send(a.control('books'),0x18B)>=2 and a.has_row('Book'),timeout=60)
    record('native-return-to-all-books',ui.text(ui.U.GetDlgItem(a.window,118))=='书架')
    d,message,detail=sync(a);assert '同步完成' in message;a.close_account(d)
    d,message,detail=sync(b);assert '同步完成' in message;b.close_account(d)
    tag_added=sql(b,'SELECT count(*) FROM reader_book_tags WHERE tag_id=? AND book_key=?',(tag_id,bookkey))==[(1,)]
    membership_action(5,'Local tag 标签','reader_book_tags','tag_id',tag_id,0)
    d,message,detail=sync(a);assert '同步完成' in message;a.close_account(d)
    d,message,detail=sync(b);assert '同步完成' in message;b.close_account(d)
    record('native-tag-membership-and-removal-sync',tag_added and
        sql(b,'SELECT count(*) FROM reader_book_tags WHERE tag_id=? AND book_key=?',(tag_id,bookkey))==[(0,)])
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
