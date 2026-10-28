"""Actions-only real GTK stale-preview rejection, cancel and explicit retry."""
import argparse, configparser, hashlib, json, os, re, shutil, sqlite3, subprocess, sys, time
from pathlib import Path
import pyatspi
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'));sys.path.insert(0,str(ROOT/'tests/reader_d23_relay'));sys.path.insert(0,str(ROOT/'tests/windows_gtk_conflict_recovery'))
from check_linux_host import Session,command
import relay,service

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser()
    for name in ('previous','profile','seed','package','out'):p.add_argument('--'+name,required=True)
    a=p.parse_args();out=Path(a.out);out.mkdir(parents=True,exist_ok=False)
    assert os.environ.get('GITHUB_ACTIONS')=='true' and sys.platform.startswith('linux')
    data=json.loads(Path(a.previous).read_text())['data'];key=data['windows_book'];checks=[]
    package=Path(a.package);program=package/'bin/exreader-linux';writer=package/'gtk-preview-writer'
    assert digest(program)==data['gtk_program_sha256']
    shutil.copytree(a.profile,out/'profile');(out/'profile').chmod(0o700)
    modes=[]
    for path in (out/'profile').rglob('*'):
        assert not path.is_symlink()
        if path.is_dir():path.chmod(0o700)
        else:
            old=digest(path);path.chmod(0o600);assert digest(path)==old
            modes.append({'path':str(path.relative_to(out/'profile')),'sha256':old,'mode':'0600'})
    (out/'profile-permissions.json').write_text(json.dumps(modes,indent=2))
    dav,user,password=service.start(out,a.previous)
    host=Session(program.resolve(),(package/'Reader.otf').resolve(),out)
    catalog=out/'profile/library.sqlite.product.sqlite';pending=Path(str(catalog)+'.commands.pending')
    def sql(q,args=()):
        with sqlite3.connect('file:'+str(catalog.resolve())+'?mode=ro',uri=True) as db:return db.execute(q,args).fetchall()
    def wires():return dict(sql('SELECT revision_id,body_json FROM reader_revisions'))
    def heads():
        records=[json.loads(v) for v in wires().values()];books=[r for r in records if r['entity_kind']=='book' and r['entity_key']==key]
        return sorted({r['id'] for r in books}-{p for r in books for p in r['parents']})
    def retain(before):assert all(wires().get(k)==v for k,v in before.items())
    def record(name):checks.append(name);print(json.dumps({'check':name,'pass':True}),flush=True)
    def wait(fn,timeout=30):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            assert host.process.poll() is None
            result=fn()
            if result:return result
            time.sleep(.1)
        raise TimeoutError(str(host.read()))
    def state(section):
        c=configparser.ConfigParser(interpolation=None);c.read(host.observe);return dict(c[section]) if c.has_section(section) else {}
    def visible_ids(title):
        r=subprocess.run(['xdotool','search','--onlyvisible','--all','--pid',str(host.process.pid),'--name','^'+re.escape(title)+'$'],capture_output=True,text=True,timeout=5)
        return r.stdout.split()
    def window(title,present=True):
        def found():
            values=visible_ids(title)
            if not present:return not values
            if values:
                assert len(values)==1,(title,values)
                command('xdotool','windowactivate','--sync',values[0]);return values[0]
        return wait(found)
    def descendants(node):
        result=[];queue=[node]
        while queue:
            n=queue.pop(0);result.append(n);assert len(result)<3000
            try:queue.extend(n[i] for i in range(n.childCount))
            except (LookupError,RuntimeError):pass
        return result
    def app_tree():
        desktop=pyatspi.Registry.getDesktop(0)
        apps=[desktop[i] for i in range(desktop.childCount)]
        owned=[x for x in apps if x.get_process_id()==host.process.pid]
        return descendants(owned[0]) if len(owned)==1 else []
    def find(name):
        def locate():
            found=[n for n in app_tree() if n.name==name and n.getState().contains(pyatspi.STATE_SHOWING)]
            return found[0] if len(found)==1 else None
        return wait(locate)
    def enabled(name):return find(name).getState().contains(pyatspi.STATE_SENSITIVE)
    def click(name):
        n=find(name);assert n.getState().contains(pyatspi.STATE_SENSITIVE),name
        action=n.queryAction();assert action.nActions==1,(name,action.nActions);assert action.doAction(0),name
    def snapshot(name,title):
        nodes=[]
        for n in app_tree():
            if n.getState().contains(pyatspi.STATE_SHOWING):nodes.append({'name':n.name,'role':n.getRoleName(),'sensitive':n.getState().contains(pyatspi.STATE_SENSITIVE)})
        (out/(name+'.json')).write_text(json.dumps(nodes,ensure_ascii=False,indent=2));command('import','-window',window(title),out/(name+'.png'))
        return nodes
    def search():
        title=sql('SELECT title FROM reader_books WHERE book_key=?',(key,))[0][0]
        command('xdotool','windowactivate','--sync',host.window);count=host.read()['shelf_queries'];host.key('F2','ctrl+f','ctrl+a');host.paste(title)
        host.wait(lambda s:s['shelf_queries']>count and not s['shelf_loading'] and not s['shelf_restoring'] and s['books']==1,timeout=60);host.key('F2','Home')
    def details():search();host.key('ctrl+e');window('Book details')
    def explicit(title):
        assert not enabled('Save') and enabled('Resolve versions')
        click('Resolve versions');click('Yes');wait(lambda:enabled('Save'))
        assert find('Book title').queryEditableText().setTextContents(title)
        assert find('Book title').queryText().getText(0,-1)==title
    def ready():return state('account').get('owner_busy')=='0' and state('account').get('preparing')=='0'
    def sync():
        command('xdotool','windowactivate','--sync',host.window);host.key('F2','ctrl+shift+a');window('Account and Sync');wait(ready,180)
        for mnemonic,value in (('w',dav.base+'/dav/'),('u',user),('p',password)):
            host.key('alt+'+mnemonic,'ctrl+a');host.paste(value)
        host.key('alt+h','alt+a');wait(lambda:ready() and state('account').get('bound')=='1',180)
        generation=int(state('account').get('session_generation','0'));host.key('alt+s')
        wait(lambda:ready() and int(state('account').get('session_generation','0'))>generation and state('account').get('session_state') in ('4','5'),180)
        assert state('account')['session_state']=='4',state('account')
        host.key('alt+r');wait(lambda:ready() and state('account').get('phase')=='0' and state('account').get('notice','')=="Sync finished. Open a book to add it to this device's reading library",180)
        host.key('alt+F4');window('Account and Sync',False);wait(lambda:state('account').get('session_present')=='0',180)
    try:
        host.launch();initial=wires();original_heads=sorted([data['win_offline_revision']['id'],data['gtk_offline_revision']['id']]);assert heads()==original_heads
        details();nodes=snapshot('01-real-two-head-conflict','Book details')
        assert any('2 heads:' in n['name'] and all(h in n['name'] for h in original_heads) for n in nodes)
        explicit('Canceled two-head merge');snapshot('02-cancel-preview','Book details');click('Cancel');window('Book details',False)
        assert wires()==initial and not pending.exists();record('real_gtk_conflict_display_and_cancel_before_save_preserve_graph')
        details();explicit('Stale two-head merge');snapshot('03-open-two-head-preview','Book details')
        run=subprocess.run([str(writer.resolve()),str(Path(a.seed).resolve()),str(catalog.resolve()),key,str((out/'writer').resolve())],capture_output=True,text=True,timeout=120)
        (out/'writer-runtime.log').write_text(run.stdout+'\n'+run.stderr);assert run.returncode==0,run.stderr
        authored=json.loads(run.stdout);three=heads();assert len(three)==3 and set(original_heads)<set(three)
        assert authored['parent']==data['gtk_offline_revision']['parents'][0]
        assert authored['revision'] in three;retain(initial)
        third=json.loads(wires()[authored['revision']]);assert third['parents']==data['gtk_offline_revision']['parents']
        before_stale=wires();assert not pending.exists();window('Book details');click('Save');window('Recover book edit')
        nodes=snapshot('04-stale-save-rejected','Recover book edit')
        assert any('Pending typed metadata command was refused; original intent retained' in n['name'] for n in nodes)
        assert wires()==before_stale and heads()==three and pending.exists();pending_hash=digest(pending)
        record('second_native_api_writer_changes_real_heads_and_gtk_stale_save_explicitly_rejects')
        old_recovery=window('Recover book edit');sequence=host.read()['sequence'];click('Retry')
        def retry_completed():
            visible=visible_ids('Recover book edit');current=host.read()
            return len(visible)==1 and visible[0]!=old_recovery and current['sequence']>sequence and not current['busy']
        wait(retry_completed)
        nodes=snapshot('05-stale-retry-rejected','Recover book edit')
        assert any('Pending typed metadata command was refused; original intent retained' in n['name'] for n in nodes)
        assert wires()==before_stale and heads()==three and digest(pending)==pending_hash
        click('Close');window('Recover book edit',False);assert digest(pending)==pending_hash
        host.close();host.launch();search();host.key('ctrl+e');window('Recover book edit')
        assert wires()==before_stale and digest(pending)==pending_hash
        snapshot('06-reopened-pending-intent','Recover book edit')
        record('stale_retry_and_close_reopen_preserve_exact_intent_and_every_revision')
        click('Discard uncommitted');window('Recover book edit',False);host.wait(lambda s:not s['busy'])
        assert not pending.exists() and wires()==before_stale and heads()==three
        details();nodes=snapshot('07-refreshed-three-head-conflict','Book details');assert any('3 heads:' in n['name'] for n in nodes)
        explicit('Canceled refreshed merge');click('Cancel');window('Book details',False)
        assert wires()==before_stale and not pending.exists();record('explicit_discard_then_refresh_cancel_preserve_all_three_heads')
        details();explicit('GTK native explicit merged version');snapshot('08-actual-explicit-resolution','Book details');click('Save');window('Book details',False);host.wait(lambda s:not s['busy'])
        added=set(wires())-set(before_stale);assert len(added)==1;resolution=json.loads(wires()[added.pop()])
        assert sorted(resolution['parents'])==three and heads()==[resolution['id']]
        assert resolution['payload']['title']=='GTK native explicit merged version';retain(before_stale);assert not pending.exists()
        data['gtk_native_resolution']=resolution;data['gtk_native_third_revision']=third;data['gtk_native_three_heads']=three
        data['gtk_native_writer']={'source_sha':os.environ['GITHUB_SHA'],'program_sha256':digest(writer),'source_sha256':digest(ROOT/'tests/gtk_native_conflict_resolution_sdk342/writer/main.cpp'),'runtime':authored,'api':'Installed DesktopMetadata 0.1.0 and Revisions 0.3.0; not a second GTK UI process'}
        record('actual_gtk_explicit_resolution_parents_all_current_heads_without_history_loss')
        sync();after_sync=wires();sync();assert wires()==after_sync;retain(before_stale)
        host.close();host.launch();search();host.key('Return');host.wait(lambda s:s['reader_visible']==1 and s['book']>0);sdkid=host.read()['book']
        snapshot('09-original-reopened','EXReader Linux');host.close()
        subprocess.run([str((package/'received-sdk-inspect').resolve()),str((out/'profile/library.sqlite').resolve()),str(sdkid),str((out/'original.bin').resolve())],check=True,timeout=120)
        assert digest(out/'original.bin')==data['windows_original_sha256'];retain(before_stale)
        record('repeated_sync_fresh_process_reopen_and_public_sdk_original_readback')
        data['checks_gtk-native']=checks;data['program_gtk-native']=digest(program)
        (out/'retained-revisions.json').write_text(json.dumps(wires(),ensure_ascii=False,indent=2))
        (out/'revision-evidence.json').write_text(json.dumps({'initial':initial,'before_stale':before_stale,'after':wires(),'initial_heads':original_heads,'current_heads_at_resolution':three,'pending_sha256':pending_hash,'resolution':resolution},ensure_ascii=False,indent=2))
        relay.save(dav,out,'gtk-native',data);dav=None
    finally:
        if host.process and host.process.poll() is None:
            try:command('import','-window','root',out/'failure-screen.png')
            except Exception:pass
            host.process.kill();host.process.wait(timeout=15)
        if dav:
            (out/'failed-requests.json').write_text(json.dumps(dav.requests));dav.server.shutdown();dav.server.server_close();(out/'key.pem').unlink(missing_ok=True)
if __name__=='__main__':main()
