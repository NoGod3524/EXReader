"""Actions-only real GTK offline author and conflict reception, no injected DB."""
import argparse, configparser, hashlib, json, os, re, shutil, sqlite3, subprocess, sys, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'));sys.path.insert(0,str(ROOT/'tests/reader_d23_relay'))
from check_linux_host import Session,command
import relay
import service

def main():
    p=argparse.ArgumentParser()
    for n in ('phase','previous','profile','package','out'):p.add_argument('--'+n,required=True)
    a=p.parse_args();out=Path(a.out);out.mkdir(parents=True,exist_ok=False)
    assert os.environ.get('GITHUB_ACTIONS')=='true' and sys.platform.startswith('linux')
    data=json.loads(Path(a.previous).read_text())['data'];key=data['windows_book'];checks=[]
    shutil.copytree(a.profile,out/'profile');(out/'profile').chmod(0o700)
    package=Path(a.package);identity=hashlib.sha256((package/'bin/exreader-linux').read_bytes()).hexdigest();assert identity==data['gtk_program_sha256']
    dav,user,password=service.start(out,a.previous);host=Session((package/'bin/exreader-linux').resolve(),(package/'Reader.otf').resolve(),out)
    def sql(q,args=()):
        with sqlite3.connect(out/'profile/library.sqlite.product.sqlite') as db:return db.execute(q,args).fetchall()
    def wires():return dict(sql('SELECT revision_id,body_json FROM reader_revisions'))
    def record(n):checks.append(n);print(json.dumps({'check':n,'pass':True}),flush=True)
    def state(section):
        c=configparser.ConfigParser(interpolation=None);c.read(host.observe);return dict(c[section]) if c.has_section(section) else {}
    def wait(f,timeout=180):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            assert host.process.poll() is None
            if f():return
            time.sleep(.1)
        raise TimeoutError(str(state('account'))+' '+str(state('collections')))
    def window(title,present=True):
        end=time.monotonic()+30
        while time.monotonic()<end:
            r=subprocess.run(['xdotool','search','--onlyvisible','--all','--pid',str(host.process.pid),'--name','^'+re.escape(title)+'$'],capture_output=True,text=True)
            if bool(r.stdout.strip())==present:
                if present:
                    w=r.stdout.splitlines()[-1];command('xdotool','windowactivate','--sync',w);return w
                return
            time.sleep(.1)
        raise TimeoutError(title)
    def field(k,v):host.key('alt+'+k,'ctrl+a');host.paste(v)
    def search(title):
        command('xdotool','windowactivate','--sync',host.window);host.key('F2','ctrl+f','ctrl+a');host.paste(title)
        host.wait(lambda s:not s['shelf_loading'] and not s['shelf_restoring'] and s['books']==1,timeout=60)
        host.key('F2','Home')
    def ready():return state('account').get('owner_busy')=='0' and state('account').get('preparing')=='0'
    def sync(conflict=False):
        command('xdotool','windowactivate','--sync',host.window);host.key('F2','ctrl+shift+a');window('Account and Sync')
        field('w',dav.base+'/dav/');field('u',user);field('p',password);host.key('alt+h','alt+a');wait(lambda:ready() and state('account').get('bound')=='1')
        gen=int(state('account').get('session_generation','0'));host.key('alt+s')
        wait(lambda:ready() and int(state('account').get('session_generation','0'))>gen and state('account').get('session_state') in ('4','5'))
        assert state('account')['session_state']=='4',state('account')
        host.key('alt+r');wait(lambda:ready() and state('account').get('phase')=='0' and 'Sync finished.' in state('account').get('notice',''))
        if conflict:
            assert int(state('account')['conflicted'])>=1,state('account')
            command('import','-window',window('Account and Sync'),out/'gtk-conflict-account.png')
            (out/'conflict-ui.json').write_text(json.dumps(state('account'),indent=2))
        host.key('alt+F4');window('Account and Sync',False);wait(lambda:state('account').get('session_present')=='0')
    try:
        host.launch();before=wires()
        if a.phase=='gtk-offline':
            title=sql('SELECT title FROM reader_books WHERE book_key=?',(key,))[0][0]
            search(title);host.key('ctrl+e');window('Book details');field('t','GTK offline version');host.key('Return');window('Book details',False)
            host.wait(lambda s:not s['busy']);assert not dav.requests
            new=set(wires())-set(before);assert len(new)==1
            data['gtk_offline_revision']=json.loads(wires()[new.pop()])
            assert data['gtk_offline_revision']['parents']==data['win_offline_revision']['parents']
            record('gtk_real_ui_offline_edit_of_same_record_same_parent')
            sync(True)
            values=[json.loads(v) for v in wires().values()]
            assert data['win_offline_revision'] in values and data['gtk_offline_revision'] in values
            title=sql('SELECT title FROM reader_books WHERE book_key=?',(key,))[0][0];search(title);host.key('ctrl+e');d=window('Book details')
            command('import','-window',d,out/'gtk-conflict-details.png');host.key('Escape');window('Book details',False)
            record('gtk_receives_both_real_versions_and_displays_unresolved_conflict')
        else:
            sync();assert sql('SELECT title FROM reader_books WHERE book_key=?',(key,))==[('Explicit merged version',)]
            assert data['resolution_revision'] in [json.loads(v) for v in wires().values()]
            assert all(wires().get(k)==v for k,v in before.items())
            record('gtk_receives_explicit_resolution_and_retains_every_prior_revision')
            search('Explicit merged version');host.key('Return');host.wait(lambda s:s['reader_visible']==1 and s['book']>0)
            sdkid=host.read()['book'];command('import','-window',host.window,out/'gtk-original-restored.png')
            # A second sync is idempotent, including retained conflict revisions.
            saved=wires();sync();assert wires()==saved
            record('repeat_sync_does_not_duplicate_or_drop_any_revision')
            # Existing native collection deletion/restoration: never mutate the
            # SQLite projection or manufacture a revision in this driver.
            search('Explicit merged version');host.key('ctrl+shift+c');window('Library collections')
            host.key('alt+t','Home','Down');wait(lambda:state('collections').get('kind')=='1')
            tag=data['gtk_tag']
            def choose_tag():
                wait(lambda:tag in state('collections').get('group_ids','').split(','))
                ids=state('collections')['group_ids'].split(',');host.key('alt+g','Home')
                for _ in range(ids.index(tag)):host.key('Down')
                wait(lambda:state('collections').get('selected_id')==tag)
            choose_tag();host.key('alt+d');window('Collection details');host.key('Return');window('Collection details',False)
            wait(lambda:sql('SELECT deleted FROM reader_tags WHERE tag_id=?',(tag,))==[(1,)])
            command('import','-window',window('Library collections'),out/'gtk-tag-deleted.png')
            host.key('alt+F4');window('Library collections',False);sync()
            data['tag_delete_revisions']=[json.loads(v) for v in wires().values() if json.loads(v)['entity_kind']=='tag' and json.loads(v)['entity_key']==tag]
            record('native_tag_delete_is_synced_without_losing_original_or_conflict_history')
            search('Explicit merged version');host.key('ctrl+shift+c');window('Library collections')
            host.key('alt+t','Home','Down');wait(lambda:state('collections').get('kind')=='1')
            if state('collections').get('removed')!='1':host.key('alt+m')
            wait(lambda:state('collections').get('removed')=='1');choose_tag()
            host.key('alt+s');window('Collection details');host.key('Return');window('Collection details',False)
            wait(lambda:sql('SELECT deleted FROM reader_tags WHERE tag_id=?',(tag,))==[(0,)])
            command('import','-window',window('Library collections'),out/'gtk-tag-restored.png')
            host.key('alt+F4');window('Library collections',False);sync()
            data['tag_final_revisions']=[json.loads(v) for v in wires().values() if json.loads(v)['entity_kind']=='tag' and json.loads(v)['entity_key']==tag]
            assert {r['operation'] for r in data['tag_final_revisions']}>={'put','delete','restore'}
            assert all(wires().get(k)==v for k,v in saved.items())
            record('native_explicit_tag_restore_sync_retains_delete_and_unresolved_ancestors')
            host.close();host.launch();search('Explicit merged version');host.key('Return');host.wait(lambda s:s['reader_visible']==1 and s['book']==sdkid)
            record('new_process_reopens_resolved_original')
            host.close()
            subprocess.run([str((package/'received-sdk-inspect').resolve()),str(out/'profile/library.sqlite'),str(sdkid),str(out/'original.bin')],check=True,timeout=120)
            assert hashlib.sha256((out/'original.bin').read_bytes()).hexdigest()==data['windows_original_sha256']
            record('public_sdk_reads_identical_original_after_offline_conflict_recovery')
        if host.process and host.process.poll() is None:host.close()
        if a.phase=='gtk-offline':
            result=subprocess.run([str((package/'conflict-safety').resolve()),str(out/'profile/library.sqlite.product.sqlite'),key,str(out/'api-safety-copy')],capture_output=True,text=True,timeout=120)
            (out/'api-safety.log').write_text(result.stdout+'\n'+result.stderr)
            assert result.returncode==0,result.stderr
            record('separate_native_api_copy_rejects_ordinary_identity_and_stale_resolution_and_proves_exact_retry')
        data['checks_'+a.phase]=checks;data['program_'+a.phase]=identity
        (out/'retained-revisions.json').write_text(json.dumps(wires(),ensure_ascii=False,indent=2),encoding='utf-8')
        relay.save(dav,out,a.phase,data);dav=None
    finally:
        if host.process and host.process.poll() is None:host.process.kill();host.process.wait(timeout=15)
        if dav:
            (out/'failed-requests.json').write_text(json.dumps(dav.requests));dav.server.shutdown();dav.server.server_close();(out/'key.pem').unlink(missing_ok=True)
if __name__=='__main__':main()
