"""Actions-only actual Android raw3 sender, HTTPS worker and real process boundaries."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
import uuid
from bundle import folder,null_folder,parse,safe
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'reader_session_android'))
from run_roundtrip import Dav

def main():
    assert os.environ.get('GITHUB_ACTIONS')=='true'
    p=argparse.ArgumentParser()
    for key in ('fixtures','fixture','output'):p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--apple-peer',type=Path)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    identity={key:os.environ[value] for key,value in [('source_sha','GITHUB_SHA'),('run_id','GITHUB_RUN_ID'),('attempt','GITHUB_RUN_ATTEMPT')]}
    package='org.exreader.host';reports=[];boundaries=[];accepted=False;apple_accepted=False;null_accepted=False;apple_attestation=None
    authorization='Basic '+base64.b64encode(('raw3:'+secrets.token_hex(32)).encode()).decode()
    server=Dav(a.fixture,authorization);port=server.server.server_port
    def adb(*args,input=None,timeout=120):return subprocess.check_output(['adb',*map(str,args)],input=input,stderr=subprocess.STDOUT,timeout=timeout)
    def private(name):return adb('exec-out','run-as',package,'cat','files/'+name)
    def save(name,data):
        assert authorization.encode() not in data,'generated fixture authorization in evidence'
        path=a.output/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    def reset():
        adb('shell','am','force-stop',package);assert adb('shell','pm','clear',package).strip()==b'Success'
        adb('shell','am','start','-W','-n',package+'/.MainActivity');adb('shell','am','force-stop',package)
    def push(file,relative):
        name=safe(relative);temporary='/data/local/tmp/raw3-'+hashlib.sha256(name.encode()).hexdigest()
        adb('push',file,temporary);adb('exec-out','run-as',package,'mkdir','-p','files/'+str(Path(name).parent));adb('exec-out','run-as',package,'cp',temporary,'files/'+name)
    def write(name,body):
        local=a.output/'private-inputs'/name;local.parent.mkdir(parents=True,exist_ok=True);local.write_bytes(body)
        push(local,name);local.unlink() # Generated authorization never enters uploaded evidence.
    def seed():
        manifest=parse((a.fixtures/'manifest.json').read_bytes())
        for row in manifest['books']:push(a.fixtures/row['file'],'preferences-fixtures/'+row['file'])
        write('preferences-input.json',json.dumps(manifest,ensure_ascii=False).encode())
    def phase(name,expected,kill=False):
        adb('shell','am','force-stop',package);adb('logcat','-c')
        command=['adb','shell','am','instrument','-w','-r','-e','phase',name]
        for key,value in identity.items():command.extend(('-e',key,value))
        command.append(package+'.test/'+package+'.Raw3InteropTest')
        if kill:
            process=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
            try:
                deadline=time.monotonic()+180;marker=None
                while time.monotonic()<deadline:
                    test=subprocess.run(['adb','exec-out','run-as',package,'cat','files/raw3-kill-boundary.json'],capture_output=True,timeout=10)
                    # exec-out can return zero while Android cat reports ENOENT.
                    # The app publishes this marker atomically, so a JSON object
                    # must parse strictly; only an absent marker is retried.
                    if test.returncode==0 and test.stdout.lstrip().startswith(b'{'):
                        marker=parse(test.stdout);save('kill-ui-boundary.json',test.stdout);break
                    noise=test.stdout+test.stderr
                    assert not noise or b'No such file or directory' in noise,noise.decode(errors='replace')
                    if process.poll() is not None:raise AssertionError(('UI kill boundary exited early',process.communicate()[0].decode(errors='replace')))
                    time.sleep(.1)
                assert marker and marker['control_gate_arrived'] and all(marker[k]==v for k,v in identity.items())
                before=adb('shell','pidof',package).decode().strip().split();assert str(marker['pid']) in before
                pending=private('reading-request.json');assert hashlib.sha256(pending).hexdigest()==marker['pending_sha256']
                save('kill-ui-original-pending.json',pending)
                adb('shell','am','force-stop',package)
                after=subprocess.run(['adb','shell','pidof',package],capture_output=True,timeout=10).stdout.decode().strip()
                assert not after and private('reading-request.json')==pending
                stdout,_=process.communicate(timeout=30);save('kill-ui-instrumentation.txt',stdout)
                boundaries.append({**marker,'pid_before':before,'pid_after':after,'real_process_stopped':True})
                return
            finally:
                if process.poll() is None:process.kill();process.wait(timeout=20)
        done=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=1500,check=False)
        save(name+'-instrumentation.txt',done.stdout)
        body=private('raw3-interop-'+name+'.json');save(name+'-raw-report.json',body);report=parse(body)
        save(name+'-logcat.txt',adb('logcat','-d','-v','threadtime','-t','5000'))
        if not report['passed']:print(json.dumps(report,ensure_ascii=False),flush=True)
        assert done.returncode==0 and b'RECORD_INTEROP_SENDER_PASS' in done.stdout and b'INSTRUMENTATION_CODE: -1' in done.stdout
        assert all(report.get(k)==v for k,v in identity.items()) and report['phase']==name and report['passed'] is True
        assert [x['name'] for x in report['checks']]==expected and report['count']==len(expected) and all(x['pass'] for x in report['checks'])
        for observation in report['observations']:save('captures/'+name+'-'+observation['name']+'.png',private('preferences-captures/'+observation['name']+'.png'))
        reports.append(report);print(json.dumps({'phase':name,'passed':True,'count':report['count'],'pid':report['pid']}),flush=True)
        return report
    def peer(selected=None):
        selected=selected or a.output/'bundle';push(selected/'manifest.json','raw3-peer-manifest.json')
        for row in parse((selected/'manifest.json').read_bytes())['revisions']:push(selected/row['file'],'interop-incoming/'+row['file'])
    def session_input():
        write('raw3-session-input.json',json.dumps({'root':f'https://127.0.0.1:{port}/dav/','account':str(uuid.uuid4()),'authorization':authorization}).encode())
    def serve_packet(selected,manifest):
        entries={}
        for row in manifest['originals']:
            sha=row['sha256'];entries['/dav/exreader-sync-v1/objects/'+sha[:2]+'/'+sha+'.'+row['format']]=(selected/row['file']).read_bytes()
        for row in manifest['revisions']:entries['/dav/exreader-sync-v1/revisions/'+row['id'][:2]+'/'+row['id']+'-'+row['sha256']+'.json']=(selected/row['file']).read_bytes()
        with server.lock:
            server.entries=entries;server.dirs={'/dav/'}
            for path in entries:
                parts=path.strip('/').split('/')[:-1]
                for n in range(1,len(parts)+1):server.dirs.add('/'+'/'.join(parts[:n])+'/')
    try:
        adb('reverse',f'tcp:{port}',f'tcp:{port}');adb('shell','cmd','uimode','night','no')
        reset();seed()
        sender=phase('sender',['txt_actual_owner_point_range_commands_retained_and_read_only_resolve','epub_actual_owner_point_range_commands_retained_and_read_only_resolve','pdf_actual_owner_point_range_commands_retained_and_read_only_resolve','cbz_actual_owner_point_range_commands_retained_and_read_only_resolve','unknown_prefix_future_parser_different_original_refused','complete_actual_book_and_reading_wire_ancestor_export'])
        raw=private('interop-outgoing/manifest.json');save('bundle/manifest.json',raw);manifest=parse(raw)
        for row in manifest['originals']+manifest['revisions']:save('bundle/'+safe(row['file']),private('interop-outgoing/'+row['file']))
        verified=folder(a.output/'bundle');assert verified['originals']==4 and verified['reading_records']==11 and verified['revisions']==19 and verified['manifest_sha256']==sender['manifest_sha256']
        assert manifest['sender']['raw_selector_candidate'] and all(manifest['sender'][k]==v for k,v in identity.items())
        pdf=next(row for row in manifest['originals'] if row['role']=='pdf')
        assert pdf['bytes']==8845 and pdf['sha256']=='5627a430fa04cbe11d38eb2682e336ef21e147d445753ed46ed11a7d5e3167cc'
        pdf_records=[r for r in manifest['reading_records'] if r['role']=='pdf']
        for row in pdf_records:
            assert row['anchor_version']==3
            selected=[None if v is None else base64.b64decode(v,validate=True) for v in row['capture']['selectors']]
            assert selected[0] is not None and (b'\0' in selected[0] if row['kind']=='highlight' else b'\0' in selected[2])
        peer();session_input();phase('session-push',['actual_android_raw_session_push_ack_close_256_shards'])
        expected={}
        for row in manifest['originals']:
            sha=row['sha256'];expected['/dav/exreader-sync-v1/objects/'+sha[:2]+'/'+sha+'.'+row['format']]=(a.output/'bundle'/row['file']).read_bytes()
        for row in manifest['revisions']:expected['/dav/exreader-sync-v1/revisions/'+row['id'][:2]+'/'+row['id']+'-'+row['sha256']+'.json']=(a.output/'bundle'/row['file']).read_bytes()
        assert server.entries==expected
        for path,body in expected.items():
            put=next(i for i,r in enumerate(server.requests) if r['method']=='PUT' and r['path']==path)
            assert any(r['method']=='GET' and r['path']==path for r in server.requests[put+1:])
        reset();peer();session_input();phase('session-receive',['actual_android_raw_session_fresh_network_receive_256_shards'])
        phase('session-reopen',['fresh_android_owner_imports_downloaded_originals_and_resolves_11_exact_records'])
        if a.apple_peer:
            verified_peer=folder(a.apple_peer);apple_attestation=parse((a.apple_peer.parent/'attestation.json').read_bytes());assert apple_attestation['accepted'] and apple_attestation['manifest_sha256']==verified_peer['manifest_sha256']
            actual_peer=verified_peer['manifest'];assert actual_peer['sender']['platform']=='macos' and verified_peer['reading_records']==11 and verified_peer['originals']==4
            serve_packet(a.apple_peer,actual_peer)
            reset();peer(a.apple_peer);session_input();phase('apple-receive',['actual_apple_raw_bundle_native_android_https_session_receive'])
            phase('apple-reopen',['fresh_android_owner_resolves_11_actual_apple_records_from_downloaded_originals'])
            apple_accepted=True
            negative=a.apple_peer.parent/'null-bundle';null_verified=null_folder(negative)
            assert null_verified['manifest_sha256']==apple_attestation['null_negative']['manifest_sha256']
            serve_packet(negative,null_verified['manifest']);reset();peer(negative);session_input()
            phase('apple-null-receive',['authentic_mac_null_wire_received_by_actual_native_https_session'])
            phase('apple-null-reopen',['fresh_actual_sdk_owner_keeps_mac_null_wire_and_ui_refuses_navigation'])
            phase('apple-null-reopen-again',['second_fresh_android_process_keeps_actual_mac_null_bytes_and_ui_refusal'])
            null_accepted=True
        reset()
        for file in (a.output/'bundle').rglob('*'):
            if file.is_file():push(file,'interop-incoming/'+file.relative_to(a.output/'bundle').as_posix())
        phase('missing-parent',['actual_received_child_without_ancestor_is_pending_and_unreadable','exact_original_ancestors_complete_graph_and_found_without_outbox_write'])
        reset();seed();phase('legacy-pending',['actual_private_v1_replay_stays_writer2_and_genuine_nul_failure_keeps_exact_bytes'])
        reset();seed();phase('raw-contract',['actual_source_v1_v2_restore_note_and_null_location_owner_contract'])
        reset();seed();phase('kill-ui',[],True);phase('reopen-ui',['actual_ui_private_v2_survives_real_kill_and_exact_owner_retry'])
        assert len(boundaries)==1 and len({r['pid'] for r in reports})==len(reports)
        assert all(r['authorization_sha256']==hashlib.sha256(authorization.encode()).hexdigest() for r in server.requests)
        save('native-https-requests.json',(json.dumps(server.requests,indent=2)+'\n').encode())
        assert not any(r['path'].endswith(('.db','.sqlite')) for r in server.requests)
        save('bundle-validation.json',(json.dumps({k:v for k,v in verified.items() if k!='manifest'},indent=2)+'\n').encode())
        accepted=True
    finally:
        server.release.set();server.server.shutdown();server.server.server_close()
        adb('shell','am','force-stop',package)
        result={**identity,'accepted':accepted,'adopted':False,'scope':'explicit API34 x86_64 Android raw3 native host candidate','checks':sum(r['count'] for r in reports),'phases':reports,'boundaries':boundaries,'actual_tls':True,'incoming_apple_status':'passed' if apple_accepted else 'pending','authentic_apple_null_status':'passed' if null_accepted else 'pending','actual_apple_attestation':apple_attestation,'bidirectional_interoperability_accepted':False,'physical_device':False,'api':34,'abi':'x86_64','complete_product':False}
        save('result.json',(json.dumps(result,ensure_ascii=False,indent=2)+'\n').encode())
        print(json.dumps({**identity,'accepted':accepted,'checks':result['checks']}),flush=True)

if __name__=='__main__':main()
