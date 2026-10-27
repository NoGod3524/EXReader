"""Actions-only GTK host phases over relayed authentic DAV bytes."""
import argparse, configparser, hashlib, json, os, re, sqlite3, subprocess, sys, time
from pathlib import Path
import relay
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
from check_linux_host import Session, command

def main():
    p=argparse.ArgumentParser();p.add_argument('--phase',choices=['gtk-first','gtk-return'],required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--previous',type=Path,required=True);p.add_argument('--package',type=Path,required=True);p.add_argument('--inspect',type=Path,required=True);a=p.parse_args()
    assert os.environ.get('GITHUB_ACTIONS')=='true' and sys.platform.startswith('linux')
    a.out.mkdir(parents=True,exist_ok=False);prior=json.loads(a.previous.read_text(encoding='utf-8'));data=prior['data']
    assert prior['phase']==('windows-first' if a.phase=='gtk-first' else 'windows-return')
    program=a.package/'bin/exreader-linux';identity=hashlib.sha256(program.read_bytes()).hexdigest()
    if a.phase=='gtk-return':assert data['gtk_program_sha256']==identity
    dav,user,password=relay.start(a.out,a.previous);host=None;checks=[]
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
    def sync():
        window('Account and Sync');generation=int(state('account').get('session_generation','0'));host.key('alt+s');wait(lambda:ready() and int(state('account').get('session_generation','0'))>generation and state('account').get('session_state') in ('4','5'))
        assert state('account')['session_state']=='4',state('account')
        host.key('alt+r');wait(lambda:ready() and state('account').get('phase')=='0' and 'Sync finished. Open a book' in state('account').get('notice',''))
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
    try:
        host=Session(program.resolve(),(a.package/'Reader.otf').resolve(),a.out);(a.out/'profile').mkdir(mode=0o700);(a.out/'profile').chmod(0o700);host.launch()
        if a.phase=='gtk-first':
            book=a.out/'Relay GTK.txt';book.write_bytes(('GTK authored original.\n'*80).encode());digest=hashlib.sha256(book.read_bytes()).hexdigest()
            import_local(book)
            data.update(gtk_book='txt:'+digest,gtk_original_sha256=digest,gtk_program_sha256=identity)
            checks.append('gtk_imports_original_in_native_host')
        account();setfield('w',dav.base+'/dav/');setfield('u',user);setfield('p',password);host.key('alt+h','alt+a')
        wait(lambda:ready() and state('account').get('bound')=='1');sync();close_account()
        if a.phase=='gtk-first':
            bookid=open_book('Relay Windows',data['windows_book']);checks.append('gtk_opens_windows_original_from_relay')
            search('Relay Windows');host.key('F2','Home','ctrl+shift+c');window('Library collections')
            wait(lambda:state('collections').get('visible')=='1');host.key('alt+t','Home','Down');wait(lambda:state('collections').get('kind')=='1')
            host.key('alt+n');window('Collection details');setfield('n','GTK relay tag');host.key('Return');window('Collection details',False)
            wait(lambda:bool(state('collections').get('selected_id')) and state('collections').get('selected_name')=='GTK relay tag')
            tag=state('collections')['selected_id'];host.key('alt+a');window('Book classification');host.key('Return');window('Book classification',False)
            wait(lambda:state('collections').get('member_keys')==data['windows_book'])
            assert sql('SELECT book_key FROM reader_book_tags WHERE tag_id=?',(tag,))==[(data['windows_book'],)]
            command('import','-window',window('Library collections'),a.out/'gtk-membership.png')
            data['gtk_tag']=tag;checks.append('gtk_native_ui_creates_tag_and_membership')
            host.key('alt+F4');window('Library collections',False);account();setfield('w',dav.base+'/dav/');setfield('u',user);setfield('p',password);host.key('alt+h','alt+a');wait(lambda:ready() and state('account').get('bound')=='1');sync();close_account()
            assert any(r['method']=='PUT' and '/revisions/' in r['path'] for r in dav.requests)
            assert any(r['method']=='PUT' and '/objects/' in r['path'] and data['gtk_original_sha256'] in r['path'] for r in dav.requests)
            checks.append('gtk_publishes_real_organization_and_original')
        else:
            assert sql('SELECT count(*) FROM reader_book_tags WHERE tag_id=? AND book_key=?',(data['gtk_tag'],data['windows_book']))==[(0,)]
            assert sql('SELECT name FROM reader_tags WHERE tag_id=?',(data['gtk_tag'],))==[('GTK relay tag',)]
            search('Relay Windows');host.key('F2','Home','ctrl+shift+c');window('Library collections')
            host.key('alt+t','Home','Down');wait(lambda:state('collections').get('kind')=='1' and data['gtk_tag'] in state('collections').get('group_ids',''))
            ids=state('collections')['group_ids'].split(',');host.key('alt+g','Home')
            for _ in range(ids.index(data['gtk_tag'])):host.key('Down')
            wait(lambda:state('collections').get('selected_id')==data['gtk_tag'] and state('collections').get('member_count')=='0')
            command('import','-window',window('Library collections'),a.out/'gtk-return-membership.png')
            host.key('alt+F4');window('Library collections',False)
            checks.append('gtk_receives_windows_membership_tombstone')
            bookid=open_book('Relay return',data['return_book']);checks.append('gtk_opens_windows_return_original')
            assert any(r['method']=='GET' and '/objects/' in r['path'] and data['return_original_sha256'] in r['path'] for r in dav.requests)
        host.close();readback=a.out/'readback.bin'
        subprocess.run([str(a.inspect.resolve()),str(a.out/'profile/library.sqlite'),str(bookid),str(readback)],check=True,capture_output=True,text=True,timeout=120)
        expected=data['windows_original_sha256'] if a.phase=='gtk-first' else data['return_original_sha256']
        assert hashlib.sha256(readback.read_bytes()).hexdigest()==expected
        checks.append('gtk_public_sdk_reads_exact_windows_original')
        data['checks_'+a.phase]=checks;data['program_'+a.phase]=identity;relay.save(dav,a.out,a.phase,data);dav=None
    finally:
        if host and host.process and host.process.poll() is None:host.process.kill();host.process.wait(timeout=15)
        if dav:
            (a.out/'failed-requests.json').write_text(json.dumps(dav.requests),encoding='utf-8')
            dav.server.shutdown();dav.server.server_close();(a.out/'key.pem').unlink(missing_ok=True)
    print(json.dumps({'phase':a.phase,'source':os.environ['GITHUB_SHA'],'program_sha256':identity,'checks':checks}),flush=True)
if __name__=='__main__':main()
