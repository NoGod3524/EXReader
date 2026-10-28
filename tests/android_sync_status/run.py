"""Actions-only real Activity/Keystore/session/Receive fixture orchestration."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import threading
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'reader_session_android'))
from run_roundtrip import Dav

def main():
    assert os.environ.get('GITHUB_ACTIONS')=='true'
    p=argparse.ArgumentParser()
    for name in ('fixture','reading-fixtures','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--sdk-version',choices=('3.40.0','3.41.0'),default='3.40.0')
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    identity={key:os.environ[value] for key,value in [('source_sha','GITHUB_SHA'),('run_id','GITHUB_RUN_ID'),('attempt','GITHUB_RUN_ATTEMPT')]}
    user='host-'+secrets.token_hex(16);password=secrets.token_hex(32);authorization='Basic '+base64.b64encode((user+':'+password).encode()).decode();sensitive=[value.encode() for value in (user,password,authorization)]
    server=Dav(a.fixture,authorization);package='org.exreader.host';phases=[];scans=[];boundaries=[];captures=[];accepted=False
    def adb(*args,input=None,timeout=90):return subprocess.check_output(['adb',*map(str,args)],input=input,stderr=subprocess.STDOUT,timeout=timeout)
    def write_private(name,body):adb('shell',f"run-as {package} sh -c 'cat > files/{name}'",input=body)
    def private_exists(name):return subprocess.run(['adb','shell','run-as',package,'test','-f','files/'+name],capture_output=True,timeout=10).returncode==0
    def save(name,data):
        leaked=any(value in data for value in sensitive)
        if leaked:
            for value in sensitive:data=data.replace(value,b'<redacted-generated-fixture-secret>')
        (a.output/name).write_bytes(data)
        assert not leaked,'generated credential appeared in saved evidence'
    def scan_private():
        names=adb('exec-out','run-as',package,'find','files','shared_prefs','no_backup','-type','f').decode().splitlines()
        for name in names:
            assert name.startswith(('files/','shared_prefs/','no_backup/')) and '\n' not in name
            data=adb('exec-out','run-as',package,'cat',name)
            assert not any(secret in data for secret in sensitive),'plaintext generated credential in app storage'
            scans.append({'phase':len(phases),'path':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'secret_absent':True})
    manifest=json.loads((a.reading_fixtures/'manifest.json').read_text());remote=(a.reading_fixtures/'book.epub').read_bytes();sha=hashlib.sha256(remote).hexdigest();assert sha==manifest['epub']['sha256']
    remote_title='UI remote EPUB 😀';remote_author='远端作者📚';rid='e1'+'0'*30
    server.retain({'version':1,'id':rid,'entity_kind':'book','entity_key':'epub:'+sha,'operation':'put','location_kind':'none','parents':[],
                   'payload':{'format':'epub','source_sha256':sha,'source_bytes':len(remote),'title':remote_title,'author':remote_author,'favorite':True}})
    root='https://127.0.0.1:'+str(server.server.server_port)+'/dav/'
    with server.lock:
        server.entries['/dav/exreader-sync-v1/objects/'+sha[:2]+'/'+sha+'.epub']=remote
        server.dirs.update(('/dav/exreader-sync-v1/','/dav/exreader-sync-v1/objects/','/dav/exreader-sync-v1/objects/'+sha[:2]+'/', '/dav/exreader-sync-v1/revisions/'))
    payload={'root':root,'user':user,'password':password,'local_text':'abcdefghijk retained UI reading anchor.\n'+'Safe original paragraph.\n'*200,'remote_sha':sha,'remote_title':remote_title,'remote_author':remote_author}
    listing_blocked=threading.Event();listing_release=threading.Event();listing_armed=threading.Event();base=server.server.RequestHandlerClass
    class ListingGate(base):
        def do_GET(self):
            if self.path.endswith('/'+sha+'.epub'):
                assert not private_exists('d22-offline'), 'offline reopening attempted network'
                mode=subprocess.run(['adb','shell','run-as',package,'cat','files/d22-get-mode'],capture_output=True,timeout=10)
                if mode.returncode==0:
                    adb('shell','run-as',package,'rm','files/d22-get-mode')
                    value=mode.stdout.decode().strip()
                    if value=='block':
                        write_private('d22-get-blocked',b'1');deadline=time.monotonic()+30
                        while time.monotonic()<deadline and not private_exists('d22-get-release'):time.sleep(.05)
                        assert private_exists('d22-get-release'),'receive cancel not observed'
                    elif value in ('corrupt','truncate'):
                        if not self.authorized():return
                        if value=='corrupt':self.send(200,bytes([remote[0]^1])+remote[1:]);return
                        self.trace['response']=200;self.send_response(200);self.send_header('Content-Length',str(len(remote)));self.send_header('Connection','close');self.end_headers();self.wfile.write(remote[:len(remote)//2]);self.wfile.flush();self.close_connection=True;return
            super().do_GET()

        def do_PROPFIND(self):
            if listing_armed.is_set() and self.headers.get('Authorization','')==authorization and self.path.startswith('/dav/'):
                listing_armed.clear();listing_blocked.set();listing_release.wait(60)
            super().do_PROPFIND()
    server.server.RequestHandlerClass=ListingGate
    expected={'first':['initial_read_only_status','authentication_failure_visible','correct_credentials_cancel_and_retry','forget_keeps_binding']}
    try:
        # The original owner suite ran against this APK first; isolate UI fixture data.
        assert adb('shell','pm','clear',package).strip()==b'Success'
        adb('shell','am','start','-W','-n',package+'/.MainActivity')
        adb('reverse',f'tcp:{server.server.server_port}',f'tcp:{server.server.server_port}')
        for phase in expected:
            adb('shell','am','force-stop',package)
            before_requests=len(server.requests);write_private('host-ui-input.json',json.dumps(payload,ensure_ascii=False).encode())
            if phase=='first':server.arm('/dav/','before')
            if phase=='secure-reopen':listing_blocked.clear();listing_release.clear();listing_armed.set()
            stop=threading.Event();monitor_failure=[]
            def monitor():
                try:
                    blocked=server.blocked if phase=='first' else listing_blocked
                    marker='host-ui-put-blocked' if phase=='first' else 'host-ui-listing-blocked'
                    reply='host-ui-cancel-clicked' if phase=='first' else 'host-ui-background-requested'
                    if phase in ('session-reopen','semantics'):return
                    deadline=time.monotonic()+90
                    while not stop.is_set() and time.monotonic()<deadline and not blocked.wait(.1):pass
                    if stop.is_set():return
                    if not blocked.is_set():raise AssertionError('real native request did not reach fixture boundary')
                    write_private(marker,b'1');deadline=time.monotonic()+60
                    while not stop.is_set() and time.monotonic()<deadline:
                        if private_exists(reply):
                            boundaries.append({'phase':phase,'real_request_blocked':True,'ui_action_observed':True});return
                        time.sleep(.1)
                    raise AssertionError('UI cancellation/background action not observed')
                except BaseException as error:monitor_failure.append(type(error).__name__+': '+str(error))
                finally:server.release.set();listing_release.set()
            thread=threading.Thread(target=monitor,daemon=True);thread.start()
            command=['shell','am','instrument','-w','-r','-e','phase',phase,'-e','sdk_version',a.sdk_version]
            for key,value in identity.items():command.extend(('-e',key,value))
            raw=adb(*command,package+'.test/'+package+'.SyncStatusTest',timeout=300);save(phase+'-instrumentation.txt',raw)
            print(raw.decode(errors='replace'),flush=True)
            logcat=adb('logcat','-d','-v','threadtime','-t','2500');save(phase+'-early-logcat.txt',logcat)
            if b'Process crashed' in raw:
                print('::error title=D22 process crash::'+phase+' instrumentation process crashed; see early-logcat evidence',flush=True)
                for line in logcat.decode(errors='replace').splitlines():
                    if any(marker in line for marker in ('JNI DETECTED','Abort message','Fatal signal','FATAL EXCEPTION','backtrace:','libexreader_host','HostTask')):print(line,flush=True)
                raise AssertionError('D22 actual host process crashed')
            report=json.loads(adb('exec-out','run-as',package,'cat','files/host-ui-'+phase+'.json'));save(phase+'-report.json',(json.dumps(report,ensure_ascii=False,indent=2)+'\n').encode())
            print(json.dumps({'phase':phase,'passed':report.get('passed'),'expected_checks':expected[phase],'actual_checks':report.get('checks'),'failed_check':report.get('failed_check'),'failure_class':report.get('failure_class'),'failure':report.get('failure'),'observations':report.get('observations',[])},ensure_ascii=False),flush=True)
            if report.get('passed') is not True:
                detail='D22 '+phase+' / '+str(report.get('failed_check'))+' / '+str(report.get('failure_class'))+': '+str(report.get('failure'))
                print('::error title=D22 receive failure::'+detail.replace('%','%25').replace('\r','%0D').replace('\n','%0A'),flush=True)
            stop.set();thread.join(10);assert not thread.is_alive() and not monitor_failure,monitor_failure
            assert all(report.get(key)==value for key,value in identity.items()) and report['expected_sdk_version']==a.sdk_version and report['phase']==phase and report['passed'] is True
            assert [row['name'] for row in report['checks']]==expected[phase] and all(row['pass'] is True for row in report['checks'])
            assert ('HOST_SYNC_UI_PASS '+phase).encode() in raw and b'INSTRUMENTATION_CODE: -1' in raw
            assert report['count']==len(expected[phase]);phases.append(report)
            if phase=='semantics':
                def nodes(tree):
                    yield tree
                    for child in tree.get('children',[]):yield from nodes(child)
                observations=report['observations'];assert [row['name'] for row in observations]==['shelf-status','organizer','reader-before','reader-after-forward','reader-toolbar','large-font-organizer']
                observed={row['name']:list(nodes(row['tree'])) for row in observations}
                def named(rows,key):return [row for row in rows if row.get('id','').endswith('/'+key)]
                assert named(observed['shelf-status'],'status_text')[0]['live_region']==1
                assert all(not named(observed[name],key) for name in ('organizer','large-font-organizer') for key in ('import_button','more_button','shelf_search'))
                before=named(observed['reader-before'],'reader_view')[0];after=named(observed['reader-after-forward'],'reader_view')[0]
                assert before['actions']&4096 and before['actions']&8192 and before['description']!=after['description']
                before_frame=json.loads(before['frame']);after_frame=json.loads(after['frame'])
                assert before_frame['book']==after_frame['book'] and after_frame['index']==before_frame['index']+1 and after_frame['start']>before_frame['start']
                assert named(observed['reader-toolbar'],'font_up')[0]['state'] and named(observed['reader-toolbar'],'reader_status')[0]['live_region']==1
                assert observations[-1]['font_scale']>=1.9
                (a.output/'captures').mkdir(exist_ok=True)
                for row in observations:
                    image=adb('exec-out','run-as',package,'cat','files/host-ui-captures/'+row['name']+'.png');assert image.startswith(b'\x89PNG\r\n\x1a\n') and len(image)>1000
                    save('captures/'+row['name']+'.png',image);captures.append({'name':row['name'],'bytes':len(image),'sha256':hashlib.sha256(image).hexdigest(),'nodes':row['nodes'],'font_scale':row['font_scale']})
            scan_private();save(phase+'-logcat.txt',adb('logcat','-d','-v','threadtime','-t','2500'))
            save(phase+'-screen.png',adb('exec-out','screencap','-p'))
            if phase in ('session-reopen','semantics'):assert len(server.requests)==before_requests,'session-only secret unexpectedly reused after kill'
        assert len(phases)==1 and len(boundaries)==1
        assert any(request['response']==401 for request in server.requests) and any(request['authorization_sha256']==hashlib.sha256(authorization.encode()).hexdigest() for request in server.requests)
        assert all(request['path'].startswith('/dav/') for request in server.requests)
        accepted=True
    finally:
        server.release.set();listing_release.set();server.server.shutdown();server.server.server_close()
        report={**identity,'accepted':accepted,'phases':phases,'checks':sum(phase['count'] for phase in phases),'boundaries':boundaries,'storage_scan':scans,
                'requests':server.requests,'captures':captures,'same_shared_sdk_runtime_asserted':accepted,'product_provider_isolated':accepted,'host_account_receive_ui_accepted':False,'targeted_semantics_accepted':False,'accessibility_accepted':False,
                'reading_state_ui_accepted':False,'physical_device':False,'api':34,'abi':'x86_64'}
        save('result.json',(json.dumps(report,ensure_ascii=False,indent=2)+'\n').encode());print(json.dumps({**identity,'accepted':accepted,'checks':report['checks'],'phases':len(phases)}),flush=True)

if __name__=='__main__':main()
