"""Actual Windows host phases; no synthesized revision or object is sent."""
import argparse, ctypes as C, hashlib, importlib.util, json, os, sqlite3, sys, traceback
from ctypes import wintypes as W
from pathlib import Path
import relay
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('interop_ui',ROOT/'tests/reader_windows_import_organize/check_ui.py')
ui=importlib.util.module_from_spec(spec);spec.loader.exec_module(ui)

def sql(app,query,args=()):
    with sqlite3.connect(str(app.db)+'.product.sqlite') as db:return db.execute(query,args).fetchall()
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

def main():
    p=argparse.ArgumentParser();p.add_argument('--phase',choices=['windows-first','windows-return'],required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--previous',type=Path);p.add_argument('--package',type=Path,required=True);p.add_argument('--probe',type=Path,required=True);a=p.parse_args()
    assert os.name=='nt' and os.environ.get('GITHUB_ACTIONS')=='true'
    a.out.mkdir(parents=True,exist_ok=False);checks=[];dav=None;app=None
    exe=a.package/'EXReader.exe';font=a.package/'Reader.otf';identity=hashlib.sha256(exe.read_bytes()).hexdigest()
    data={}
    try:
        if a.previous:
            previous=json.loads(a.previous.read_text(encoding='utf-8'));data=previous['data'];assert previous['phase']=='gtk-first'
            assert data['windows_program_sha256']==identity
        dav,user,password=relay.start(a.out,a.previous)
        app=ui.App(exe,font,a.out/'profile');app.wait_initial_shelf();app.wait_idle()
        if a.phase=='windows-first':
            source=a.out/'Relay Windows.txt';source.write_bytes(('Windows authored original.\n'*90).encode());digest=hashlib.sha256(source.read_bytes()).hexdigest()
            import_book(app,source);app.wait(lambda:app.has_row('Relay Windows'),timeout=60)
            data.update(windows_book='txt:'+digest,windows_original_sha256=digest,windows_program_sha256=identity)
            checks.append('windows_imports_original_in_native_host')
        else:
            checks.append('windows_same_binary_as_first_phase')
        dialog=app.open_account();app.fill(dialog,root=dav.base+'/dav/',user=user,password=password,remember=False);app.apply(dialog,'仅本次会话');app.close_account(dialog)
        dialog=app.open_account();app.run_sync(dialog);app.close_account(dialog)
        if a.phase=='windows-first':
            assert sql(app,"SELECT count(*) FROM reader_revisions WHERE entity_kind='book' AND entity_key=?",(data['windows_book'],))==[(1,)]
            assert any(r['method']=='PUT' and '/objects/' in r['path'] for r in dav.requests)
            checks.append('windows_sync_publishes_real_book_and_original')
        else:
            key=data['windows_book'];tag=data['gtk_tag']
            assert sql(app,'SELECT count(*) FROM reader_book_tags WHERE tag_id=? AND book_key=?',(tag,key))==[(1,)]
            assert sql(app,'SELECT count(*) FROM reader_local_books WHERE book_key=?',(data['gtk_book'],))==[(1,)]
            readback=a.out/'sdk-readback';readback.mkdir();spec=a.out/'readback.spec'
            spec.write_text('cmd=readback\nlibrary=%s\nout=%s\n'%(app.db,readback),encoding='utf-8')
            result=subprocess.run([str(a.probe.resolve()),str(spec)],check=True,capture_output=True,text=True,encoding='utf-8',timeout=120)
            audit=json.loads(result.stdout);assert audit['ok']==1 and all(book['read_ok']==1 for book in audit['books'])
            hashes={hashlib.sha256((readback/('book-%d.bin'%book['id'])).read_bytes()).hexdigest() for book in audit['books']}
            assert data['gtk_original_sha256'] in hashes and data['windows_original_sha256'] in hashes
            checks.append('windows_public_sdk_reads_exact_gtk_original')
            app.wait(lambda:app.has_row('Relay Windows'),timeout=60)
            ui.U.SetForegroundWindow(app.window);ui.A.tap(ord('O'),(ui.A.VK_CONTROL,ui.A.VK_SHIFT));d=app.io_dialog()
            app.wait(lambda:not ui.U.IsWindowEnabled(ui.U.GetDlgItem(d,ui.CANCEL)))
            box=ui.U.GetDlgItem(d,ui.ROWS);items=ui.A.auto.ControlFromHandle(box).GetChildren()
            match=[x for x in items if 'Relay Windows' in x.Name];assert len(match)==1;match[0].GetSelectionItemPattern().Select()
            ui.send(ui.U.GetDlgItem(d,ui.ACTION),0x14E,5);ui.send(d,0x111,(1<<16)|ui.ACTION,ui.U.GetDlgItem(d,ui.ACTION))
            app.wait(lambda:not ui.U.IsWindowEnabled(ui.U.GetDlgItem(d,ui.CANCEL)))
            group=ui.U.GetDlgItem(d,ui.GROUPS);rows=[]
            for i in range(ui.send(group,0x18B)):
                n=ui.send(group,0x18A,i);buf=C.create_unicode_buffer(n+1);ui.send(group,0x189,i,C.addressof(buf));rows.append(buf.value)
            assert any('GTK relay tag' in x for x in rows),rows
            ui.send(group,0x186,next(i for i,v in enumerate(rows) if 'GTK relay tag' in v));ui.send(ui.U.GetDlgItem(d,ui.GO),0xF5)
            app.wait(lambda:not ui.U.IsWindowEnabled(ui.U.GetDlgItem(d,ui.CANCEL)),timeout=120)
            assert sql(app,'SELECT count(*) FROM reader_book_tags WHERE tag_id=? AND book_key=?',(tag,key))==[(0,)]
            message=ui.text(ui.U.GetDlgItem(d,ui.MESSAGE));assert 'committed=1' in message,message
            ui.M.screenshot(d,a.out/'windows-membership.bmp')
            ui.send(ui.U.GetDlgItem(d,ui.CLOSE),0xF5);app.wait(lambda:not ui.U.IsWindow(d));app.wait_idle()
            checks.append('windows_native_ui_removes_gtk_tag_membership')
            source=a.out/'Relay return.txt';source.write_bytes(('Windows return original.\n'*95).encode());digest=hashlib.sha256(source.read_bytes()).hexdigest()
            import_book(app,source);app.wait(lambda:app.has_row('Relay return'),timeout=60)
            data.update(return_book='txt:'+digest,return_original_sha256=digest)
            dialog=app.open_account();app.run_sync(dialog);app.close_account(dialog)
            assert any(r['method']=='PUT' and '/revisions/' in r['path'] for r in dav.requests)
            assert any(r['method']=='PUT' and '/objects/' in r['path'] and digest in r['path'] for r in dav.requests)
            checks.append('windows_publishes_membership_change_and_second_original')
        data['checks_'+a.phase]=checks;data['program_'+a.phase]=identity
        relay.save(dav,a.out,a.phase,data);dav=None
    except Exception:
        traceback.print_exc();raise
    finally:
        if app and app.process.poll() is None:app.process.kill();app.process.wait(timeout=20)
        if dav:
            dav.server.shutdown();dav.server.server_close();(a.out/'key.pem').unlink(missing_ok=True)
    print(json.dumps({'phase':a.phase,'source':os.environ['GITHUB_SHA'],'program_sha256':identity,'checks':checks}),flush=True)
if __name__=='__main__':main()
