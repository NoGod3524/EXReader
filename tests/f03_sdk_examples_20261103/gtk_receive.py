"""Fresh GTK example receives authentic native-authored wire, then restarts."""
import configparser
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import time
from run import ROOT,setup,admission,require

def receive(phase):
    m=setup();stamp=admission();sys.path.insert(0,str(ROOT/'tools'))
    from check_linux_host import Session,command
    spec=importlib.util.spec_from_file_location('sdk_f03_relay',ROOT/'tests/reader_windows_gtk_interop/relay.py')
    relay=importlib.util.module_from_spec(spec);spec.loader.exec_module(relay)
    author=ROOT/'build/f03-author'/phase;expected=json.loads((author/'projection.json').read_bytes())
    m.same_identity(expected,stamp)
    out=ROOT/'build/f03-sdk-receipts/gtk'/phase;out.mkdir(parents=True,exist_ok=False)
    (out/'profile').mkdir(mode=0o700)
    program=ROOT/'build/package/EXReader-Linux/bin/exreader-linux'
    host=Session(program,ROOT/'build/package/EXReader-Linux/Reader.otf',out)
    database=out/'profile/library.sqlite.product.sqlite';dav=None
    def state(section):
        p=configparser.ConfigParser(interpolation=None);p.read(host.observe)
        return dict(p[section]) if p.has_section(section) else {}
    def wait(test,seconds=120):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            require(host.process.poll() is None,'GTK example exited')
            if test():return
            time.sleep(.1)
        raise TimeoutError('GTK receive did not settle: '+str(state('account'))+' '+str(state('collections')))
    def window(title,present=True):
        ids=[]
        def ready():
            result=subprocess.run(['xdotool','search','--onlyvisible','--all','--pid',str(host.process.pid),
                '--name','^'+re.escape(title)+'$'],capture_output=True,text=True,timeout=10)
            ids[:]=result.stdout.split();return bool(ids)==present
        wait(ready,40)
        if present:command('xdotool','windowactivate','--sync',ids[-1]);return ids[-1]
    def field(key,value):host.key('alt+'+key,'ctrl+a');host.paste(value)
    try:
        dav,user,password=relay.start(out/'wire',author/'wire/state.json')
        host.launch();host.key('F2','ctrl+shift+a');window('Account and Sync')
        field('w',dav.base+'/dav/');field('u',user);field('p',password);host.key('alt+h','alt+a')
        wait(lambda:state('account').get('bound')=='1' and state('account').get('owner_busy')=='0')
        generation=int(state('account').get('session_generation','0'));host.key('alt+s')
        wait(lambda:int(state('account').get('session_generation','0'))>generation and
             state('account').get('session_state') in ('4','5'),180)
        require(state('account')['session_state']=='4','native GTK synchronization failed')
        host.key('alt+r')
        wait(lambda:state('account').get('owner_busy')=='0' and state('account').get('phase')=='0' and
             'Sync finished. Open a book' in state('account').get('notice',''),180)
        require(state('account')['projection_status']=='0','native GTK organization projection incomplete')
        host.key('alt+F4');window('Account and Sync',False)
        wait(lambda:state('account').get('session_present')=='0' and state('account').get('owner_busy')=='0')
        actual=m.read_snapshot(database)
        for table in m.TABLES:require(actual[table]==expected['snapshot'][table],'GTK projection differs: '+table)
        wanted={r['id']:r['body'] for r in expected['snapshot']['revisions']}
        received={r['id']:r['body'] for r in actual['revisions']}
        require(all(received.get(k)==v for k,v in wanted.items()),'GTK revision body differs')
        host.key('F2','Home','ctrl+shift+c');window('Library collections')
        wait(lambda:state('collections').get('visible')=='1')
        command('import','-window',window('Library collections'),out/'received.png')
        host.key('alt+F4');window('Library collections',False);host.close()
        host.launch();host.key('F2');host.wait(lambda s:not s.get('shelf_loading') and not s.get('shelf_restoring'),timeout=60)
        require(m.read_snapshot(database)==actual,'GTK organization changed on process restart')
        command('import','-window',host.window,out/'restarted.png');host.close()
        m.retain_database(database,out/'native-catalog',actual)
        require(any(r['authenticated'] and r['method']=='GET' and '/revisions/' in r['path'] for r in dav.requests),
                'no actual GTK revision download')
        m.write_json(out/'projection.json',{**stamp,'host':'gtk','sdk_version':'3.42.0',
            'program_sha256':m.digest(program),'native_sync_completed':True,'restart_verified':True,
            'snapshot':actual,'snapshot_sha256':hashlib.sha256(m.canonical(actual)).hexdigest()})
        relay.save(dav,out/'wire','f03-sdk-gtk-receive',{'phase':phase});dav=None
    finally:
        if host.process and host.process.poll() is None:host.process.kill();host.process.wait(timeout=20)
        if dav:
            m.write_json(out/'failed-requests.json',dav.requests)
            dav.server.shutdown();dav.server.server_close();(out/'wire/key.pem').unlink(missing_ok=True)
