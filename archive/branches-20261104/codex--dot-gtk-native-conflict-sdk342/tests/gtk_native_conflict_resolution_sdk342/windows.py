"""Actions-only Windows native receive of the actual GTK three-head resolution."""
import argparse,hashlib,importlib.util,json,os,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tests/reader_d23_relay'));sys.path.insert(0,str(ROOT/'tests/windows_gtk_conflict_recovery'))
import relay,service
spec=importlib.util.spec_from_file_location('accepted_conflict_windows',ROOT/'tests/windows_gtk_conflict_recovery/windows.py')
old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old);u=old.u

def main():
    p=argparse.ArgumentParser()
    for name in ('previous','profile','package','out'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
    assert os.environ.get('GITHUB_ACTIONS')=='true' and os.name=='nt'
    data=json.loads(a.previous.read_text())['data'];key=data['windows_book'];checks=[]
    shutil.copytree(a.profile,a.out/'profile');program=a.package/'EXReader.exe'
    identity=hashlib.sha256(program.read_bytes()).hexdigest();assert identity==data['windows_program_sha256']
    dav,user,password=service.start(a.out,a.previous);app=None
    def wires():return dict(old.old.sql(app,'SELECT revision_id,body_json FROM reader_revisions'))
    def sync():
        d=app.open_account();app.fill(d,root=dav.base+'/dav/',user=user,password=password,remember=False);app.apply(d,'仅本次会话');app.run_sync(d);app.close_account(d)
    def record(name):checks.append(name);print(json.dumps({'check':name,'pass':True}),flush=True)
    try:
        app=old.ConflictApp(program.resolve(),(a.package/'Reader.otf').resolve(),a.out/'profile',existing=True);app.wait_initial_shelf();app.wait_idle()
        before=wires();sync();received=wires();assert all(received.get(k)==v for k,v in before.items())
        values=[json.loads(v) for v in received.values()]
        for r in (data['win_offline_revision'],data['gtk_offline_revision'],data['gtk_native_third_revision'],data['gtk_native_resolution']):assert r in values
        records=[r for r in values if r['entity_kind']=='book' and r['entity_key']==key]
        heads={r['id'] for r in records}-{p for r in records for p in r['parents']}
        assert heads=={data['gtk_native_resolution']['id']}
        assert old.old.sql(app,'SELECT title FROM reader_books WHERE book_key=?',(key,))==[('GTK native explicit merged version',)]
        record('windows_receives_gtk_three_head_resolution_and_retains_all_original_revisions')
        sync();assert wires()==received
        app.open('GTK native explicit merged version');app.wait_idle();app.click('select');app.click('copy')
        assert 'Windows authored original.' in u.ACCOUNT.clipboard_text(app)
        u.M.screenshot(app.window,a.out/'windows-reopened-gtk-resolution.bmp')
        readback=a.out/'sdk-readback';readback.mkdir();request=a.out/'readback.spec'
        request.write_text('cmd=readback\nlibrary=%s\nout=%s\n'%(app.db,readback),encoding='utf-8')
        result=subprocess.run([str((a.package/'cloud-probe.exe').resolve()),str(request.resolve())],check=True,capture_output=True,text=True,encoding='utf-8',timeout=120)
        report=json.loads(result.stdout);assert report['ok']==1 and all(b['read_ok']==1 for b in report['books'])
        (a.out/'public-sdk-readback.json').write_text(result.stdout)
        hashes={hashlib.sha256((readback/('book-%d.bin'%b['id'])).read_bytes()).hexdigest() for b in report['books']}
        assert data['windows_original_sha256'] in hashes
        record('windows_repeat_sync_native_original_reopen_and_public_sdk_bytes_match')
        data['checks_windows-native']=checks;data['program_windows-native']=identity
        (a.out/'retained-revisions.json').write_text(json.dumps(received,ensure_ascii=False,indent=2))
        app.process.kill();app.process.wait(timeout=20);app=None
        relay.save(dav,a.out,'windows-native',data);dav=None
    finally:
        if app and app.process.poll() is None:app.diagnose(a.out);app.process.kill();app.process.wait(timeout=20)
        if dav:
            (a.out/'failed-requests.json').write_text(json.dumps(dav.requests));dav.server.shutdown();dav.server.server_close();(a.out/'key.pem').unlink(missing_ok=True)
if __name__=='__main__':main()
