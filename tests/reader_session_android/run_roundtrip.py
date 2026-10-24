#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actions-only Android SDK -> product/session -> TLS DAV -> SDK acceptance."""
import argparse
import base64
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import sqlite3
import ssl
import subprocess
import sys
import threading
import time
import unicodedata
import uuid
from xml.sax.saxutils import escape


class Dav:
    def __init__(self, fixture, authorization):
        self.auth=authorization;self.entries={};self.dirs={f'/{name}/' for name in ('dav','cancel','auth','other')}
        self.requests=[];self.lock=threading.Lock();self.blocked=threading.Event();self.release=threading.Event();self.gate=None
        owner=self
        class Handler(BaseHTTPRequestHandler):
            protocol_version='HTTP/1.1'
            def log_message(self,*unused):pass
            def send(self,code,data=b''):
                self.trace['response']=code;self.send_response(code);self.send_header('Content-Length',str(len(data)))
                self.send_header('Connection','close');self.end_headers();self.close_connection=True
                try:self.wfile.write(data)
                except (OSError,ssl.SSLError):pass
            def authorized(self):
                value=self.headers.get('Authorization','')
                self.trace={'method':self.command,'path':self.path,'authorization_sha256':hashlib.sha256(value.encode()).hexdigest(),
                            'if_none_match':self.headers.get('If-None-Match'),'depth':self.headers.get('Depth')}
                with owner.lock:owner.requests.append(self.trace)
                if value!=owner.auth:self.send(401);return False
                return True
            def do_MKCOL(self):
                if not self.authorized():return
                with owner.lock:
                    exists=self.path in owner.dirs;parent=self.path.rstrip('/').rsplit('/',1)[0]+'/'
                    code=405 if exists else 201 if parent in owner.dirs else 409
                    if code==201:owner.dirs.add(self.path)
                self.send(code)
            def do_PUT(self):
                body=self.rfile.read(int(self.headers.get('Content-Length','0')))
                if not self.authorized():return
                self.trace['body_sha256']=hashlib.sha256(body).hexdigest();self.trace['body_bytes']=len(body)
                if self.headers.get('If-None-Match')!='*':self.send(400);return
                with owner.lock:
                    gate=owner.gate
                    if gate and self.path.startswith(gate[0]) and '/objects/' in self.path:owner.gate=None
                    else:gate=None
                if gate and gate[1]=='before':owner.blocked.set();owner.release.wait(60)
                with owner.lock:
                    exists=self.path in owner.entries
                    if not exists:owner.entries[self.path]=body
                self.trace['stored']=not exists
                if gate and gate[1]=='after':owner.blocked.set();owner.release.wait(60)
                self.send(412 if exists else 201)
            def do_GET(self):
                if not self.authorized():return
                with owner.lock:body=owner.entries.get(self.path)
                self.send(404 if body is None else 200,body or b'')
            def do_PROPFIND(self):
                self.rfile.read(int(self.headers.get('Content-Length','0')))
                if not self.authorized():return
                if self.headers.get('Depth')!='1':self.send(400);return
                with owner.lock:
                    exists=self.path in owner.dirs
                    children=[(p,True,0) for p in owner.dirs if p.startswith(self.path) and (p==self.path or '/' not in p[len(self.path):].rstrip('/'))]
                    children.extend((p,False,len(b)) for p,b in owner.entries.items() if p.startswith(self.path) and '/' not in p[len(self.path):])
                if not exists:self.send(404);return
                rows=['<d:response><d:href>'+escape(p)+'</d:href><d:propstat><d:prop><d:resourcetype>'+('<d:collection/>' if folder else '')+'</d:resourcetype><d:getcontentlength>'+str(size)+'</d:getcontentlength></d:prop><d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>' for p,folder,size in children]
                self.send(207,('<d:multistatus xmlns:d="DAV:">'+''.join(rows)+'</d:multistatus>').encode())
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);self.server.daemon_threads=True
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(fixture/'public/server.crt',fixture/'private/server.key')
        self.server.socket=context.wrap_socket(self.server.socket,server_side=True)
        threading.Thread(target=self.server.serve_forever,daemon=True).start()
    def arm(self,root,when):self.blocked.clear();self.release.clear();self.gate=(root,when)
    def retain(self,value):
        body=json.dumps(value,ensure_ascii=False,separators=(',',':')).encode();rid=value['id']
        path='/dav/exreader-sync-v1/revisions/'+rid[:2]+'/'+rid+'-'+hashlib.sha256(body).hexdigest()+'.json'
        with self.lock:self.entries[path]=body;self.dirs.add(path.rsplit('/',1)[0]+'/')
        return path


def main():
    assert os.environ.get('GITHUB_ACTIONS')=='true'
    p=argparse.ArgumentParser();p.add_argument('--fixture',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    identity={key:os.environ[value] for key,value in [('source_sha','GITHUB_SHA'),('run_id','GITHUB_RUN_ID'),('attempt','GITHUB_RUN_ATTEMPT')]}
    authorization='Basic '+base64.b64encode(('android:'+secrets.token_hex(32)).encode()).decode();server=Dav(a.fixture,authorization)
    package='org.exreader.sessionprobe';account=str(uuid.uuid4());port=server.server.server_port;root=f'https://127.0.0.1:{port}'
    checks=[];controls=[];request_id=0;accepted=False;failure=None
    def adb(*args,input=None,timeout=90):return subprocess.check_output(['adb',*map(str,args)],input=input,stderr=subprocess.STDOUT,timeout=timeout)
    def record(name,**details):checks.append({'name':name,'passed':True,**details});print('PASS '+name,flush=True)
    def control(action,profile='A',**values):
        nonlocal request_id
        request_id+=1;number=request_id
        body=json.dumps(dict(action=action,profile=profile,**values),ensure_ascii=False).encode()
        adb('shell',f"run-as {package} sh -c 'cat > files/request-{number}.json'",input=body)
        adb('shell','am','broadcast','-n',package+'/.ControlReceiver','--ei','request_id',number)
        deadline=time.monotonic()+30
        while True:
            result=subprocess.run(['adb','exec-out','run-as',package,'cat',f'files/reply-{number}.json'],capture_output=True,timeout=10)
            if result.returncode==0:reply=json.loads(result.stdout);break
            if time.monotonic()>deadline:raise AssertionError(('control timeout',action,profile))
            time.sleep(.05)
        assert authorization.encode() not in result.stdout
        controls.append({'id':number,'action':action,'profile':profile,'reply':reply})
        assert reply.get('ok') is True,(action,profile,reply)
        return reply
    def create(profile='A',namespace='dav',credential=authorization,identifier=account):
        return control('create',profile,account=identifier,root=root+'/'+namespace+'/',authorization=credential,timeout=15000)
    def wait(profile,state,seconds=180):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            view=control('observe',profile)
            if view['state']==state:return view
            assert view['state'] not in (5,7),(state,view)
            time.sleep(.1)
        raise AssertionError(('session timeout',profile,state,view))
    def close(profile):
        assert control('close',profile)['code']==0;wait(profile,7,30)
        destroyed=control('destroy',profile);assert destroyed['code']==0 and not destroyed['alive']
    def instrument(name,phase=None):
        command=['shell','am','instrument','-w','-r']
        for key,value in identity.items():command.extend(('-e',key,value))
        if phase:command.extend(('-e','phase',phase))
        result=subprocess.run(['adb',*command,'org.exreader.host.test/org.exreader.host.ProductOwnerTest'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=240)
        raw=result.stdout
        (a.output/(name+'.txt')).write_bytes(raw)
        if result.returncode:
            raise RuntimeError(raw.decode(errors='replace'))
        return raw
    def snapshot(profile):
        for name in ('sdk.sqlite','product.sqlite'):
            data=adb('exec-out','run-as',package,'cat',f'files/{profile}/{name}')
            assert authorization.encode() not in data
            (a.output/(profile+'-'+name)).write_bytes(data)
        with sqlite3.connect(a.output/(profile+'-sdk.sqlite')) as db:
            sdk_tables={row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")};sdk_version=db.execute('PRAGMA user_version').fetchone()[0]
        with sqlite3.connect(a.output/(profile+'-product.sqlite')) as db:
            product_tables={row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")};product_version=db.execute('PRAGMA user_version').fetchone()[0]
        assert 'reader_revisions' not in sdk_tables and 'reader_revisions' in product_tables and 'reader_local_books' in product_tables
        return {'sdk_version':sdk_version,'product_version':product_version,'sdk_tables':sorted(sdk_tables),'product_tables':sorted(product_tables)}
    try:
        adb('reverse',f'tcp:{port}',f'tcp:{port}');adb('shell','am','start','-n',package+'/.ControlActivity')
        title='同步书名😀E\u0301';author='远端作者📚'
        original=control('prepare',title=title,author=author);key=original['key']
        assert original['metadata_committed']==1 and original['pending']==0 and original['sdk_id']>0
        assert original['sdk']['title']!=title and original['sdk']['favorite']==0
        assert control('outbox')['count']==2
        record('sdk_owner_public_import_export_verified_then_typed_metadata_commit',original=original)
        provider=control('provider');assert provider['version']=='3.54.0' and provider['runtime_source']==provider['header_source'] and Path(provider['library']).name=='libsession-product-owner.so'
        assert {'THREADSAFE=1','DQS=0','OMIT_LOAD_EXTENSION','MAX_LENGTH=2147483647'}<=set(provider['options'].split(';'))
        record('actual_runtime_product_sqlite_provider',provider=provider)
        create();assert not server.requests and control('observe')['state']==0
        assert control('destroy')['code']==2
        server.arm('/dav/','after');assert control('start')['code']==0;assert server.blocked.wait(30)
        object_path='/dav/exreader-sync-v1/objects/'+original['sha'][:2]+'/'+original['sha']+'.epub'
        with server.lock:stored=server.entries[object_path]
        assert len(stored)==original['bytes'] and hashlib.sha256(stored).hexdigest()==original['sha']
        assert control('outbox')['count']==2
        old_pid=control('observe')['pid'];adb('shell','am','force-stop',package);server.release.set()
        adb('shell','am','start','-n',package+'/.ControlActivity');pending=control('outbox');assert pending['pid']!=old_pid and pending['count']==2
        assert control('state')['sha']==original['sha'];retry_start=len(server.requests)
        create();assert control('start')['code']==0;finished=wait('A',4);assert finished['completed_shards']==256 and finished['full_library_complete']==0 and control('outbox')['count']==0
        retried=server.requests[retry_start:];put=next(i for i,r in enumerate(retried) if r['method']=='PUT' and r['path']==object_path and r.get('response')==412)
        assert any(r['method']=='GET' and r['path']==object_path and r.get('response')==200 for r in retried[put+1:])
        record('force_stop_after_server_commit_retries_412_get_before_outbox_ack',old_pid=old_pid,new_pid=pending['pid'],finished=finished)
        close('A')
        create('B');assert control('start','B')['code']==0;received=wait('B',4)
        selected=control('inspect','B',key=key);assert selected['selection']==4 and selected['heads']==1 and selected['head']==original['head'] and selected['selected_title']==title and selected['catalog']['present']==0
        assert control('project','B',key=key,head=selected['head'],title=selected['selected_title'])['status']==0
        projected=control('inspect','B',key=key)['catalog'];assert projected['title']==title and projected['author']==author and projected['favorite']==1 and projected['sdk_id']==0 and projected['sort_title']==unicodedata.normalize('NFC',title)
        record('receiver_explicit_safe_unique_projection_precedes_sdk_import',received=received,catalog=projected)
        restored=control('restore','B',sha=original['sha'],bytes=original['bytes']);mapped=control('inspect','B',key=key)['catalog']
        assert restored['sdk_id']>0 and restored['sdk']['title']!=title and mapped['sdk_id']==restored['sdk_id']
        assert all(mapped[field]==projected[field] for field in ('title','author','favorite','sort_title'))
        duplicate=control('restore','B',sha=original['sha'],bytes=original['bytes']);assert duplicate['created']==0 and duplicate['sdk_id']==restored['sdk_id'] and duplicate['sdk']['books']==1
        record('verified_remote_cache_sdk_owner_import_and_mapping_preserve_remote_metadata',restored=restored,catalog=mapped)
        peer={'version':1,'id':'fe'+'0'*29+'1','entity_kind':'book','entity_key':key,'operation':'put','location_kind':'none','parents':[original['bootstrap']],
              'payload':{'format':'epub','source_sha256':original['sha'],'source_bytes':original['bytes'],'title':'Concurrent peer','author':'Peer','favorite':False}}
        server.retain(peer);assert control('start','B')['code']==0;wait('B',4)
        conflict=control('inspect','B',key=key);assert conflict['selection']==2 and conflict['heads']==2 and not conflict['head'] and conflict['catalog']==mapped
        assert control('project','B',key=key,head=original['head'],title=title)['status']!=0
        assert control('inspect','B',key=key)['catalog']==mapped
        record('multihead_retained_without_auto_selection_or_local_mapping_change',selection=conflict)
        close('B')
        for namespace,identifier in (('dav',str(uuid.uuid4())),('other',account)):
            n=len(server.requests);create(namespace=namespace,identifier=identifier);control('start');view=wait('A',5)
            assert view['status']==4 and len(server.requests)==n;close('A')
        record('wrong_account_and_root_refused_before_network')
        create('Auth','auth','Basic wrong');control('start','Auth');auth_failure=wait('Auth',5)
        assert auth_failure['dav_code']==6 and auth_failure['http_status']==401;close('Auth')
        create('Auth','auth');control('start','Auth');wait('Auth',4);close('Auth')
        record('auth_failure_corrected_by_closed_session_recreation',failure=auth_failure)
        control('prepare','C',title='Cancellation retry',author='Test');create('C','cancel');server.arm('/cancel/','before');control('start','C');assert server.blocked.wait(30)
        started=time.monotonic();cancel=control('cancel','C');elapsed=time.monotonic()-started
        assert cancel['code']==0 and elapsed<2 and control('destroy','C')['code']==2
        server.release.set();cancelled=wait('C',3);assert control('outbox','C')['count']==2
        assert control('start','C')['code']==0;retried=wait('C',4);assert control('outbox','C')['count']==0
        close('C');record('cancel_nonblocking_destroy_busy_then_retry_close_destroy',cancel_seconds=elapsed,cancelled=cancelled,retried=retried)
        stats=control('stats');assert stats['clients']==stats['uploads']==0 and stats['attaches']==stats['detaches'] and stats['attaches']>0
        schemas={profile:snapshot(profile) for profile in ('A','B')};record('sdk_and_product_files_distinct_and_native_lifecycle_balanced',stats=stats,schemas=schemas)
        # Execute the original host's unchanged owner suite against this source
        # and installed product packages, including its real process kills.
        apks=Path('examples/android/app/build/outputs/apk');adb('install','-r','-t',apks/'debug/app-debug.apk');adb('install','-r','-t',apks/'androidTest/debug/app-debug-androidTest.apk')
        raw=instrument('original-owner');assert b'OK (17 tests)' in raw and b'INSTRUMENTATION_CODE: -1' in raw and b'FAILURES' not in raw
        report=json.loads(adb('exec-out','run-as','org.exreader.host','cat','files/product-owner-report.json'));assert report['failed']==0 and report['count']==17 and all(report.get(k)==v for k,v in identity.items())
        (a.output/'original-owner-device.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        for phase,witness in (('before',b'1,1,0'),('after',b'1,1,1')):
            killed=instrument('original-seed-'+phase,'seed-'+phase);assert b'Process crashed.' in killed
            assert adb('exec-out','run-as','org.exreader.host','cat','files/owner-kill-'+phase+'/witness.txt')==witness
            recovered=instrument('original-recover-'+phase,'recover-'+phase);assert ('EXR_OWNER_RECOVERED recover-'+phase).encode() in recovered and b'INSTRUMENTATION_CODE: -1' in recovered
        record('unchanged_original_product_owner_17_and_two_process_phases',provider=report['provider'])
        accepted=True
    except BaseException as error:
        failure={'type':type(error).__name__,'message':str(error)};raise
    finally:
        server.release.set();server.server.shutdown();server.server.server_close()
        report={**identity,'accepted':accepted,'checks':checks,'failure':failure,'active_document_or_pager_in_harness':False,'reader_ui_accepted':False,'physical_device':False}
        for name,value in (('result.json',report),('controls.json',controls),('requests.json',server.requests)):
            data=(json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode();assert authorization.encode() not in data;(a.output/name).write_bytes(data)
        print(json.dumps(report,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
