"""Actions-only GTK host phases over relayed authentic DAV bytes."""
import argparse, configparser, hashlib, json, os, re, sqlite3, subprocess, sys, time, shutil
from pathlib import Path
import relay
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
from check_linux_host import Session, command

def main():
    p=argparse.ArgumentParser();p.add_argument('--phase',choices=['gtk-first','gtk-return'],required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--previous',type=Path);p.add_argument('--origin',type=Path);p.add_argument('--package',type=Path,required=True);p.add_argument('--inspect',type=Path,required=True);a=p.parse_args()
    assert os.environ.get('GITHUB_ACTIONS')=='true' and sys.platform.startswith('linux')
    a.out.mkdir(parents=True,exist_ok=False);data={}
    if a.previous:
        prior,_=relay.load(a.previous,'android');data=prior['data']['relay_data']
    program=a.package/'bin/exreader-linux';identity=hashlib.sha256(program.read_bytes()).hexdigest()
    if a.phase=='gtk-return':assert data['gtk_program_sha256']==identity
    origin=None
    if a.phase=='gtk-return':
        assert a.origin is not None
        origin,_=relay.load(a.origin/'state.json','gtk-first')
        assert origin['data']['program_sha256']==identity
        source=a.origin/'profile';assert source.is_dir()
        before={str(p.relative_to(source)):hashlib.sha256(p.read_bytes()).hexdigest() for p in source.rglob('*') if p.is_file()}
        shutil.copytree(source,a.out/'profile')
        after={str(p.relative_to(a.out/'profile')):hashlib.sha256(p.read_bytes()).hexdigest() for p in (a.out/'profile').rglob('*') if p.is_file()}
        assert before==after
        (a.out/'resumed-native-profile.json').write_text(json.dumps({'origin_state_sha256':hashlib.sha256((a.origin/'state.json').read_bytes()).hexdigest(),'files':before,'copied_unchanged':True,'no_app_database_injection':True},indent=2))
    dav,user,password=relay.start(a.out,a.previous,reuse_base=origin['server']['base'] if origin else None);host=None;checks=[]
    def sql(q,values=()):
        with sqlite3.connect(a.out/'profile/library.sqlite.product.sqlite') as db:return db.execute(q,values).fetchall()
    def state(section):
        value=configparser.ConfigParser(interpolation=None);value.read(host.observe)
        return dict(value[section]) if value.has_section(section) else {}
    def wait(predicate,timeout=180):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            assert host.process.poll() is None
            if predicate():return
            time.sleep(.1)
        raise TimeoutError(repr(state('account'))+' '+repr(state('collections')))
    def window(title,present=True):
        end=time.monotonic()+30
        while time.monotonic()<end:
            done=subprocess.run(['xdotool','search','--onlyvisible','--all','--pid',str(host.process.pid),'--name','^'+re.escape(title)+'$'],capture_output=True,text=True)
            if bool(done.stdout.strip())==present:
                if present:
                    w=done.stdout.splitlines()[-1];command('xdotool','windowactivate','--sync',w);return w
                return
            time.sleep(.1)
        raise TimeoutError(title)
    def account():
        command('xdotool','windowactivate','--sync',host.window);host.key('F2','ctrl+shift+a');window('Account and Sync')
    def setfield(key,value):host.key('alt+'+key,'ctrl+a');host.paste(value)
    def ready():return state('account').get('owner_busy')=='0' and state('account').get('preparing')=='0'
    def sync(expected_dependency=False):
        window('Account and Sync');generation=int(state('account').get('session_generation','0'));host.key('alt+s');wait(lambda:ready() and int(state('account').get('session_generation','0'))>generation and state('account').get('session_state') in ('4','5'))
        assert state('account')['session_state']=='4',state('account')
        host.key('alt+r')
        if expected_dependency:
            expected='Shelf organization: 0 conflicting or incomplete versions; 1 waiting for related items. Sync or resolve them, then retry'
            wait(lambda:ready() and state('account').get('phase')=='0' and state('account').get('notice')==expected)
            evidence=data['deleted_dependency_evidence']
            assert evidence['pending_count']==1 and evidence['outbox_count']==0
            assert sql('SELECT count(*) FROM reader_outbox')==[(0,)]
            for head in evidence['all_safe_heads']:
                assert sql('SELECT body_sha256 FROM reader_revisions WHERE revision_id=?',(head['revision'],))==[(head['body_sha256'],)]
            assert sql('SELECT deleted FROM reader_series WHERE series_id=?',(data['series'],))==[(1,)]
            assert evidence['surviving_membership']['key']=='series:'+data['series']+':'+data['book_key']
            (a.out/'expected-dependency.json').write_text(json.dumps({'account_ui':state('account'),'incoming_exact_heads':evidence},indent=2))
        else:
            wait(lambda:ready() and state('account').get('phase')=='0' and 'Sync finished. Open a book' in state('account').get('notice',''))
            assert state('account')['projection_status']=='0',state('account')
    def close_account():
        window('Account and Sync');host.key('alt+F4');window('Account and Sync',False)
        wait(lambda:state('account').get('session_present')=='0')
    def search(title):
        command('xdotool','windowactivate','--sync',host.window);queries=host.read()['shelf_queries'];host.key('ctrl+f','ctrl+a');host.paste(title)
        host.wait(lambda s:s['shelf_queries']>queries and not s['shelf_loading'] and not s['shelf_restoring'] and s['books']==1,timeout=60)
    def open_book(title,key):
        search(title);host.key('F2','Home','Return')
        wait(lambda:bool(sql('SELECT sdk_book_id FROM reader_local_books WHERE book_key=?',(key,))),180)
        identifier=sql('SELECT sdk_book_id FROM reader_local_books WHERE book_key=?',(key,))[0][0]
        host.wait(lambda s:s['book']==identifier and s['reader_visible']==1,timeout=90)
        return identifier
    def import_local(book):
        # Target only this process's actual chooser. A second Enter is sent only
        # while that same chooser is visible and no import has started.
        events=[];start=time.monotonic();chooser=None
        def visible():
            result=subprocess.run(['xdotool','search','--onlyvisible','--all','--pid',str(host.process.pid),
                '--name','^Import book$'],capture_output=True,text=True)
            return result.stdout.split()
        def capture(action):
            events.append({'elapsed':round(time.monotonic()-start,3),'action':action,
                           'choosers':visible(),'host':host.read()})
        try:
            command('xdotool','windowactivate','--sync',host.window);host.key('F1')
            chooser=window('Import book');capture('chooser-opened')
            host.key('ctrl+l');host.paste(str(book.resolve()))
            command('xdotool','key','--clearmodifiers','Return');capture('first-enter')
            second=False;deadline=time.monotonic()+60
            while time.monotonic()<deadline:
                assert host.process.poll() is None
                ids=visible();current=host.read()
                assert all(value==chooser for value in ids),('unexpected chooser',ids,chooser)
                if not ids and current.get('book',0)>0 and current.get('books')==1 and not current.get('error') and not current.get('busy'):
                    capture('chooser-closed-and-book-imported');return
                if not second and ids and time.monotonic()-start>=3 and not current.get('book') and not current.get('busy'):
                    command('xdotool','windowactivate','--sync',chooser)
                    current=host.read()
                    if chooser in visible() and not current.get('book') and not current.get('busy'):
                        command('xdotool','key','--clearmodifiers','Return');second=True;capture('second-enter')
                time.sleep(.1)
            capture('timeout')
            raise TimeoutError('Import requires both chooser closure and completed book import')
        except Exception:
            capture('failure')
            with (a.out/'selector-window-tree.txt').open('w',encoding='utf-8') as output:
                subprocess.run(['xwininfo','-root','-tree'],stdout=output,stderr=subprocess.STDOUT,check=False)
            subprocess.run(['import','-window','root',str(a.out/'selector-failure.png')],check=False)
            raise
        finally:
            (a.out/'selector-events.json').write_text(json.dumps(events,indent=2),encoding='utf-8')
    def screenshot(label):
        command('import','-window',window('Library collections'),a.out/(label+'.png'))
        (a.out/(label+'.json')).write_text(json.dumps(state('collections'),indent=2))
    def collections():
        search('Relay GTK');host.key('F2','Home','ctrl+shift+c');window('Library collections')
        wait(lambda:state('collections').get('visible')=='1')
    def kind(n):
        host.key('alt+t','Home',*(['Down']*n));wait(lambda:state('collections').get('kind')==str(n))
    def select(identifier):
        wait(lambda:identifier in state('collections').get('group_ids','').split(','))
        ids=state('collections')['group_ids'].split(',');host.key('alt+g','Home',*(['Down']*ids.index(identifier)))
        wait(lambda:state('collections').get('selected_id')==identifier)
    def create(name):
        host.key('alt+n');window('Collection details');setfield('n',name);host.key('Return');window('Collection details',False)
        wait(lambda:state('collections').get('selected_name')==name)
        return state('collections')['selected_id']
    def attach():
        host.key('alt+a');window('Book classification');host.key('Return');window('Book classification',False)
        wait(lambda:state('collections').get('member_keys')==data['book_key'])
    def close_collections():host.key('alt+F4');window('Library collections',False)
    def connected_sync(expected_dependency=False):
        account();setfield('w',dav.base+'/dav/');setfield('u',user);setfield('p',password);host.key('alt+h','alt+a')
        wait(lambda:ready() and state('account').get('bound')=='1');sync(expected_dependency);close_account()
    def capture_rows():
        return {table:sql('SELECT * FROM '+table) for table in ('reader_shelves','reader_tags','reader_series','reader_book_shelves','reader_book_tags','reader_book_series')}
    try:
        host=Session(program.resolve(),(a.package/'Reader.otf').resolve(),a.out);(a.out/'profile').mkdir(mode=0o700,exist_ok=True);host.launch()
        if a.phase=='gtk-first':
            book=a.out/'Relay GTK.txt';book.write_bytes(('GTK organization relay original.\n'*80).encode());digest=hashlib.sha256(book.read_bytes()).hexdigest()
            import_local(book);data.update(book_key='txt:'+digest,original_sha256=digest,gtk_program_sha256=identity)
            checks.append('gtk_native_chooser_imports_actual_book')
            collections();data['shelf']=create('GTK parent');attach();host.key('alt+e')
            wait(lambda:state('collections').get('parent_id')==data['shelf'])
            data['child']=create('GTK child');attach();screenshot('gtk-subshelf')
            kind(1);data['tag']=create('GTK tag');attach();screenshot('gtk-tag')
            kind(2);data['series']=create('GTK series');attach();screenshot('gtk-series')
            close_collections();checks.append('gtk_ui_authors_parent_child_tag_series_and_memberships')
            connected_sync();checks.append('gtk_application_publishes_authenticated_revisions_and_original')
        else:
            connected_sync(expected_dependency=True);checks.append("exact_deleted_group_dependency_visible_no_other_pending");collections()
            select(data['shelf']);assert state('collections')['selected_name']=='GTK parent'
            host.key('alt+e');wait(lambda:state('collections').get('parent_id')==data['shelf']);select(data['child']);screenshot('gtk-child-return')
            assert state('collections')['member_keys']==data['book_key']
            kind(1);select(data['tag']);assert state('collections')['selected_name']=='Android edited tag'
            assert state('collections')['member_count']=='0';screenshot('gtk-removed-membership')
            attach();screenshot('gtk-restored-membership');checks.append('gtk_ui_receives_android_edit_and_restores_membership')
            kind(2);host.key('alt+m');wait(lambda:state('collections').get('removed')=='1')
            select(data['series']);screenshot('gtk-removed-series');host.key('alt+s');window('Collection details');host.key('Return');window('Collection details',False)
            host.key('alt+m');wait(lambda:state('collections').get('removed')=='0');select(data['series']);screenshot('gtk-restored-series')
            checks.append('gtk_ui_receives_tombstone_and_restores_series')
            for k,name in ((0,'Android shelf'),(1,'Android tag'),(2,'Android series')):
                kind(k);select(data['android_'+str(k)]);assert state('collections')['selected_name']==name
                assert state('collections')['member_keys']==data['book_key'];screenshot('gtk-android-'+str(k))
            kind(0);select(data['android_0']);host.key('alt+e');wait(lambda:state('collections').get('parent_id')==data['android_0']);select(data['android_child']);assert state('collections')['member_keys']==data['book_key'];screenshot('gtk-android-child')
            checks.append('gtk_ui_displays_android_authored_groups_and_memberships');close_collections();connected_sync()
        before=capture_rows();connected_sync();assert capture_rows()==before;checks.append('gtk_duplicate_sync_preserves_exact_organization_rows')
        host.close();host.launch();collections();kind(1);select(data['tag']);assert state('collections')['member_keys']==data['book_key'];screenshot('gtk-restart')
        close_collections();assert capture_rows()==before;checks.append('gtk_restart_preserves_organization_ui_and_rows')
        host.close();data['passed']=True
        report={**relay.identity(),'passed':True,'checks':checks,'relay_data':data,'program_sha256':identity,'rows':before}
        (a.out/'report.json').write_text(json.dumps(report,indent=2));relay.save(dav,a.out,a.phase,report);dav=None
    finally:
        if host and host.process and host.process.poll() is None:host.process.kill();host.process.wait(timeout=15)
        if dav:
            (a.out/'failed-requests.json').write_text(json.dumps(dav.requests));dav.server.shutdown();dav.server.server_close();(a.out/'key.pem').unlink(missing_ok=True)
    print(json.dumps(report),flush=True)
if __name__=='__main__':main()
