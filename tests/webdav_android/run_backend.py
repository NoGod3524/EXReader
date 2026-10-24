#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actions-only API34 acceptance through an installed C archive and Java AAR."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import time
from fixture import Fixture,require_actions


def cases(root,ports):
    rows=[]
    def add(name,expected=0,**values):rows.append(dict(name=name,expected=expected,**values))
    add('list_root',action='list',resource='',count=3,first_resource='book.bin',title='书 & Book 📖')
    for path,count in (('folder/',1),('alias/',3),('default/',3),('redirected/',1)):
        add('list_'+path[:-1],action='list',resource=path,count=count)
    add('download')
    add('attached_java_worker',attached=True)
    add('unicode_uri',resource='%E4%B9%A6.bin')
    add('percent_uri',resource='100%25.bin')
    add('chunked',resource='chunked.bin')
    add('same_origin_redirect',resource='same.bin')
    for path in ('loop','outside','foreign','downgrade'):add('redirect_'+path,10,resource=path+'.bin')
    for name in ('untrusted','wrong_host'):add('tls_'+name,4,root=f'https://127.0.0.1:{ports[name]}/dav/')
    add('missing_credentials',6,no_auth=True)
    for code in (401,403,404,500,507):add('http_'+str(code),6 if code==401 else 5,resource='error'+str(code),http=code)
    for name,field,value in (('download','maximum',128*1024*1024+1),('listing','listing_bytes',4*1024*1024+1),('entry','entries',2001),('timeout','timeout',120001)):
        add(name+'_ceiling_argument',1,**{field:value})
    add('declared_length_limit',8,maximum=65536)
    add('chunked_limit',8,resource='chunked.bin',maximum=65536)
    add('transfer_128m_ceiling',8,resource='ceiling.bin')
    add('listing_4m_ceiling',8,action='list',resource='listing-ceiling/')
    add('cancel_before_connect',7,cancel=0)
    add('cancel_stream',7,resource='slow.bin',cancel=65536)
    add('header_deadline',3,resource='header-timeout.bin',timeout=150,max_elapsed=3000)
    add('trickle_total_deadline',3,resource='trickle.bin',timeout=150,max_elapsed=3000)
    add('truncated_transfer',3,resource='broken.bin')
    add('no_overwrite_local',11,existing=True)
    add('listing_byte_limit',8,action='list',resource='',listing_bytes=128)
    add('listing_cancel',7,action='list',resource='',cancel=128)
    for path,status in (('invalid-escape',10),('invalid-origin',10),('invalid-traversal',1),('invalid-depth',9),('invalid-duplicate',9),
                        ('invalid-xml',9),('invalid-dtd',9),('external-entity',9),('internal-entity',9),('unknown-entity',9),
                        ('invalid-namespace',9),('missing-href',9),('namespace-limit',8),('response-flood',8),('outside-flood',8),('deep',8),('invalid-utf8',1)):
        add('xml_'+path,status,action='list',resource=path+'/')
    add('names_once_decoded',action='list',resource='names/',count=2,title='a b.txt')
    add('unicode_percent_fallback',action='list',resource='unicode/',count=1,title='书 +%.txt')
    add('percent_root',action='list',root=root+'root%25/',resource='',count=1,title='child.txt')
    add('full_2000_two_propstats',action='list',resource='ceiling/',count=2000,timeout=15000)
    add('refuse_2001_entries',8,action='list',resource='overflow/')
    add('lowered_entry_budget',8,action='list',resource='ceiling/',entries=2)
    for n,path in enumerate(('a%252e.txt','a%25%32%65.txt','a%252F.txt','a%2F.txt','%2e%2e/a.txt','a//b.txt','a\\b.txt','a?x','/absolute')):
        add(f'uri_argument_{n}',1,resource=path)
    add('worker_owner_refusal',action='owner',resource='',wrong_owner=1,count=3)
    add('callback_reentry_refusal',action='reentry',reentry=1)
    add('same_client_error_recovery',action='recover',first_status=5)
    add('mkcol_create',action='mkcol',resource='immutable/')
    add('mkcol_existing',action='mkcol',resource='immutable/')
    add('mkcol_redirect_refused',10,action='mkcol',resource='write-redirect/')
    add('immutable_put',action='put',resource='immutable/item.bin',source_bytes=524288)
    add('immutable_duplicate',11,action='put',resource='immutable/item.bin',source_bytes=524288,http=412)
    add('immutable_get_verify',resource='immutable/item.bin')
    add('put_redirect_refused',10,action='put',resource='write-redirect.bin',source_bytes=524288)
    add('put_cancel_before_connect',7,action='put',resource='cancel-before.bin',source_bytes=524288,cancel=0)
    add('put_cancel_stream',7,action='put',resource='cancel-stream.bin',source_bytes=524288,cancel=65536)
    add('put_total_deadline',3,action='put',resource='write-block.bin',source_bytes=32*1024*1024,timeout=150,max_elapsed=5000)
    for n in range(4):add(f'cleanup_cycle_{n}',resource='book.bin')
    return rows


def main():
    require_actions();p=argparse.ArgumentParser();p.add_argument('--fixture',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=True);auth='Bearer '+secrets.token_hex(32);server=Fixture(a.fixture,auth);app='org.exreader.webdav.probe'
    def adb(*args,input=None,timeout=120):return subprocess.check_output(['adb',*map(str,args)],input=input,stderr=subprocess.STDOUT,timeout=timeout)
    identity={key:os.environ[value] for key,value in [('source_sha','GITHUB_SHA'),('run_id','GITHUB_RUN_ID'),('attempt','GITHUB_RUN_ATTEMPT')]}
    def private_input(value):
        # stdin goes directly into app-private storage; credentials are never shell arguments.
        adb('shell','run-as',app,'mkdir','-p','files')
        adb('shell',f"run-as {app} sh -c 'cat > files/input.json'",input=json.dumps(value).encode())
    def instrument(name):
        args=['shell','am','instrument','-w','-r']
        for key,value in identity.items():args.extend(['-e',key,value])
        raw=adb(*args,app+'.test/'+app+'.BackendProbe');(a.output/(name+'-instrumentation.txt')).write_bytes(raw)
        if b'EXR_ANDROID_DAV_ACCEPTED' not in raw or b'INSTRUMENTATION_CODE: -1' not in raw:raise RuntimeError(raw.decode(errors='replace'))
        report=json.loads(adb('exec-out','run-as',app,'cat','files/backend-report.json'))
        assert all(report.get(key)==value for key,value in identity.items()) and report['api']==34 and report['abi']=='x86_64' and report['accepted'] is True
        (a.output/(name+'-device.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');return report
    try:
        ports=server.start();root=f'https://127.0.0.1:{ports["trusted"]}/dav/'
        for port in ports.values():adb('reverse',f'tcp:{port}',f'tcp:{port}')
        apks=Path('tests/webdav_android/android/backend/build/outputs/apk')
        adb('install','-r','-t',apks/'debug/backend-debug.apk');adb('install','-r','-t',apks/'androidTest/debug/backend-debug-androidTest.apk')
        tests=cases(root,ports);private_input({'root':root,'authorization':auth,'cases':tests,'activity_exit':True});first=instrument('backend')
        assert first['count']==len(tests)+3 # uninitialized, UI-thread guard, Activity exit
        assert not any(row['port']==ports['foreign'] for row in server.requests)
        assert all(dict((k.lower(),v) for k,v in row['headers']).get('depth')=='1' for row in server.requests if row['request_line'].startswith('PROPFIND '))
        assert all(not any(name in row['request_line'] for name in ('%252e','%252F','%2F','?x')) for row in server.requests)
        private_input({'root':root,'authorization':auth,'cases':[]})
        adb('shell','am','force-stop',app);adb('shell','am','start','-W','-n',app+'/'+app+'.ExitActivity')
        assert server.committed.wait(20),'Process fixture never committed immutable PUT'
        pid_before=adb('shell','pidof',app).decode().strip();assert pid_before
        adb('shell','am','force-stop',app)
        assert not adb('shell',f'pidof {app} || true').strip()
        retry=[dict(name='process_exact_retry',action='put',resource='process.bin',source_bytes=524288,expected=11,http=412),dict(name='process_get_verify',resource='process.bin')]
        private_input({'root':root,'authorization':auth,'cases':retry});second=instrument('process-restart')
        assert server.objects['/dav/process.bin']==server.payload and second['count']==4
        request_bytes=json.dumps(server.requests).encode();assert auth.encode() not in request_bytes
        summary={**identity,'accepted':True,'api':34,'abi':'x86_64','backend_cases':first['count'],'restart_cases':second['count'],
                 'process_killed_after_server_commit':True,'force_stop_pid':pid_before,'immutable_payload_sha256':hashlib.sha256(server.payload).hexdigest(),
                 'authorization_sha256':hashlib.sha256(auth.encode()).hexdigest(),'foreign_requests':0,'secret_scan':True,'android_sync_ui_complete':False}
        for path in a.output.rglob('*'):
            if path.is_file():assert auth.encode() not in path.read_bytes()
        (a.output/'result.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary),flush=True)
    finally:
        try:adb('shell','run-as',app,'rm','-f','files/input.json')
        except subprocess.CalledProcessError:pass
        server.close()


if __name__=='__main__':main()
