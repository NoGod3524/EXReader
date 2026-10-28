"""Actions-only real Windows author/conflict/explicit-resolution phases."""
import argparse, ctypes as C, hashlib, importlib.util, json, os, shutil, sqlite3, sys, traceback
from ctypes import wintypes as W
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tests/reader_d23_relay'))
import relay
import service
spec=importlib.util.spec_from_file_location('retained_windows_relay',ROOT/'tests/reader_d23_relay/windows.py')
old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
u=old.ui
u.U.PostMessageW.argtypes=[W.HWND,W.UINT,W.WPARAM,W.LPARAM]
u.U.PostMessageW.restype=W.BOOL
class ConflictApp(u.App):
    # SearchApp.dialog identifies search controls; this package opens metadata.
    # Keep the retained metadata dialog selector rather than accepting any popup.
    def dialog(self):return u.M.MetadataApp.dialog(self)

def main():
    p=argparse.ArgumentParser()
    for n in ('phase','previous','profile','package','out'):p.add_argument('--'+n,required=True)
    a=p.parse_args();out=Path(a.out);out.mkdir(parents=True,exist_ok=False)
    assert os.environ.get('GITHUB_ACTIONS')=='true' and os.name=='nt'
    data=json.loads(Path(a.previous).read_text())['data'];key=data['windows_book'];checks=[]
    shutil.copytree(a.profile,out/'profile');package=Path(a.package)
    identity=hashlib.sha256((package/'EXReader.exe').read_bytes()).hexdigest();assert identity==data['windows_program_sha256']
    dav,user,password=service.start(out,a.previous);app=None
    def sql(q,args=()):return old.sql(app,q,args)
    def wires():return dict(sql('SELECT revision_id,body_json FROM reader_revisions'))
    def record(n):checks.append(n);print(json.dumps({'check':n,'pass':True}),flush=True)
    def edit(title,new):
        d=app.details_for(title);u.ACCOUNT.set_text(u.U.GetDlgItem(d,u.M.TITLE),new)
        u.send(u.U.GetDlgItem(d,u.M.SAVE),0xF5);app.closed(d);app.wait_idle()
    def bind():
        d=app.open_account();app.fill(d,root=dav.base+'/dav/',user=user,password=password,remember=False);app.apply(d,'仅本次会话');return d
    try:
        app=ConflictApp((package/'EXReader.exe').resolve(),(package/'Reader.otf').resolve(),out/'profile',existing=True)
        app.wait_initial_shelf();app.wait_idle();before=wires()
        if a.phase=='windows-offline':
            title=sql('SELECT title FROM reader_books WHERE book_key=?',(key,))[0][0]
            edit(title,'Windows offline version')
            assert not dav.requests, 'Offline edit made a network request'
            added=set(wires())-set(before);assert len(added)==1
            rev=json.loads(wires()[added.pop()]);data['win_offline_revision']=rev
            record('windows_real_ui_offline_edit_retains_original_parent')
            d=bind();app.run_sync(d);app.close_account(d)
        elif a.phase=='windows-final':
            d=bind();app.run_sync(d);app.close_account(d)
            tag=data['gtk_tag'];assert sql('SELECT deleted FROM reader_tags WHERE tag_id=?',(tag,))==[(0,)]
            current=[json.loads(v) for v in wires().values()]
            assert all(r in current for r in data['tag_final_revisions'])
            assert data['resolution_revision'] in current
            assert all(wires().get(k)==v for k,v in before.items())
            app.open('Explicit merged version');app.wait_idle();app.click('select');app.click('copy')
            assert 'Windows authored original.' in u.ACCOUNT.clipboard_text(app)
            u.M.screenshot(app.window,out/'windows-final-original.bmp')
            record('windows_receives_tag_delete_restore_history_and_reopens_same_original')
        else:
            # Native owner cancellation during a paused authenticated listing.
            d=bind();dav.pause=True;app.press(d,u.ACCOUNT.SYNC)
            app.wait(lambda:dav.blocked.is_set(),timeout=40);app.press(d,u.ACCOUNT.CANCEL);dav.release.set()
            app.wait_note(d,'CANCELLED');app.wait(lambda:app.enabled(d,u.ACCOUNT.RETRY))
            assert all(wires().get(k)==v for k,v in before.items())
            record('windows_cancel_retains_local_revisions_and_allows_retry')
            app.press(d,u.ACCOUNT.RETRY);app.wait_note(d,'并发 1',timeout=240)
            u.M.screenshot(d,out/'windows-conflict-status.bmp');app.close_account(d)
            rows=sql("SELECT body_json FROM reader_revisions WHERE entity_kind='book' AND entity_key=?",(key,))
            current=[json.loads(v[0]) for v in rows]
            assert data['win_offline_revision'] in current and data['gtk_offline_revision'] in current
            record('windows_received_both_actual_offline_revisions_and_displays_conflict')
            title=sql('SELECT title FROM reader_books WHERE book_key=?',(key,))[0][0];d=app.details_for(title)
            assert not u.U.IsWindowEnabled(u.U.GetDlgItem(d,u.M.SAVE))
            assert u.U.IsWindowEnabled(u.U.GetDlgItem(d,18999))
            u.M.screenshot(d,out/'windows-explicit-resolution.bmp')
            # Post asynchronous button press because a modal native question runs its loop.
            u.U.PostMessageW(u.U.GetDlgItem(d,18999),0xF5,0,0)
            def question():
                found=[]
                @u.ENUM
                def visit(w,_):
                    if u.U.IsWindowVisible(w) and u.text(w)=='明确处理版本冲突':found.append(w)
                    return True
                u.U.EnumWindows(visit,0);return found[0] if found else None
            confirm=app.wait(question);u.send(u.U.GetDlgItem(confirm,6),0xF5)
            app.wait(lambda:u.U.IsWindowEnabled(u.U.GetDlgItem(d,u.M.SAVE)))
            u.ACCOUNT.set_text(u.U.GetDlgItem(d,u.M.TITLE),'Explicit merged version')
            u.send(u.U.GetDlgItem(d,u.M.SAVE),0xF5);app.closed(d);app.wait_idle()
            merged=[json.loads(v[0]) for v in sql("SELECT body_json FROM reader_revisions WHERE entity_kind='book' AND entity_key=?",(key,))]
            hit=[r for r in merged if r.get('payload',{}).get('title')=='Explicit merged version'];assert len(hit)==1
            assert set(hit[0]['parents'])=={data['win_offline_revision']['id'],data['gtk_offline_revision']['id']}
            data['resolution_revision']=hit[0]
            assert all(wires().get(k)==v for k,v in before.items())
            record('explicit_native_resolution_parents_both_heads_without_deleting_history')
            d=bind();app.run_sync(d);app.close_account(d)
            app.open('Explicit merged version');app.wait_idle();app.click('select');app.click('copy')
            assert 'Windows authored original.' in u.ACCOUNT.clipboard_text(app)
            u.M.screenshot(app.window,out/'windows-original-after-resolution.bmp')
            record('original_still_opens_after_cancel_conflict_and_resolution')
        data['checks_'+a.phase]=checks;data['program_'+a.phase]=identity
        (out/'retained-revisions.json').write_text(json.dumps(wires(),ensure_ascii=False,indent=2),encoding='utf-8')
        app.process.kill();app.process.wait(timeout=20);app=None
        relay.save(dav,out,a.phase,data);dav=None
    except Exception:
        if app:app.diagnose(out)
        raise
    finally:
        if app and app.process.poll() is None:app.process.kill();app.process.wait(timeout=20)
        if dav:
            (out/'failed-requests.json').write_text(json.dumps(dav.requests));dav.release.set();dav.server.shutdown();dav.server.server_close();(out/'key.pem').unlink(missing_ok=True)
if __name__=='__main__':main()
