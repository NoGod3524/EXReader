# SPDX-License-Identifier: MIT
"""Real loopback TLS and installed consumers; private fixture trees are not uploaded."""
import base64,hashlib,http.server,json,os,queue,signal,socket,ssl,subprocess,sys,threading,time,zlib
from pathlib import Path
BODY=b'Q'*131079
def sha(b):return hashlib.sha256(b).hexdigest()
class Server:
    def __init__(self,cert,key):
        self.data={};self.requests=[];self.mode='normal';self.arrived=threading.Event();self.release=threading.Event();self.release.set()
        outer=self
        class Handler(http.server.BaseHTTPRequestHandler):
            protocol_version='HTTP/1.1'
            def log_message(self,*args):pass
            def answer(self,status,data=b'',headers=None):
                self.send_response(status);self.send_header('Content-Length',str(len(data)))
                for k,v in (headers or {}).items():self.send_header(k,v)
                self.end_headers()
                if data:self.wfile.write(data)
            def do_PUT(self):
                size=int(self.headers.get('Content-Length','0'));data=self.rfile.read(size)
                outer.requests.append({'method':'PUT','path':self.path,'bytes':len(data),'sha256':sha(data),'if_none_match':self.headers.get('If-None-Match')})
                if len(data)!=size:return
                if outer.mode=='redirect':self.answer(307,headers={'Location':'/dav/other'});return
                exists=self.path in outer.data
                if not exists:outer.data[self.path]=data
                if outer.mode in ('gate','lost') and '/objects/' in self.path:
                    outer.arrived.set()
                    if not outer.release.wait(20):return
                    if outer.mode=='lost':
                        self.close_connection=True
                        try:self.connection.shutdown(socket.SHUT_RDWR)
                        except OSError:pass
                        return
                self.answer(412 if exists else 201)
            def do_GET(self):
                outer.requests.append({'method':'GET','path':self.path})
                self.answer(200,outer.data[self.path]) if self.path in outer.data else self.answer(404)
            def do_MKCOL(self):self.answer(201)
            def do_PROPFIND(self):
                # Consume request body so the keep-alive stream stays framed.
                self.rfile.read(int(self.headers.get('Content-Length','0')))
                prefix=self.path
                entries=['<d:response><d:href>'+prefix+'</d:href><d:propstat><d:prop><d:resourcetype><d:collection/></d:resourcetype></d:prop><d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>']
                for name,data in outer.data.items():
                    if name.startswith(prefix) and '/' not in name[len(prefix):]:
                        entries.append('<d:response><d:href>'+name+'</d:href><d:propstat><d:prop><d:resourcetype/><d:getcontentlength>'+str(len(data))+'</d:getcontentlength></d:prop><d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>')
                self.answer(207,('<?xml version="1.0"?><d:multistatus xmlns:d="DAV:">'+''.join(entries)+'</d:multistatus>').encode(),{'Content-Type':'application/xml'})
        self.server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler);self.server.daemon_threads=True
        tls=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);tls.load_cert_chain(cert,key);self.server.socket=tls.wrap_socket(self.server.socket,server_side=True)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.url='https://127.0.0.1:'+str(self.server.server_port)+'/dav/'
    def close(self):self.release.set();self.server.shutdown();self.server.server_close()
class Interactive:
    def __init__(self,binary,profile,url,env=None):
        self.p=subprocess.Popen([str(binary),'interactive',str(profile),url],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=env)
        self.lines=queue.Queue();self.raw=[]
        def read():
            for line in self.p.stdout:self.raw.append(line);self.lines.put(json.loads(line))
        threading.Thread(target=read,daemon=True).start()
        self.created=self.take('create');self.enabled=self.take('enable')
    def take(self,key):
        item=self.lines.get(timeout=20);assert key in item,(key,item);return item[key]
    def cmd(self,text,key=None):
        self.p.stdin.write(text+'\n');self.p.stdin.flush();return self.take(key or text)
    def stop(self):
        if self.p.poll() is None:self.p.stdin.write('exit\n');self.p.stdin.flush()
        self.p.wait(timeout=15)
        return ''.join(self.raw)+self.p.stderr.read()
def parse(text):
    result={}
    for line in text.splitlines():
        if line.startswith('{'):result.update(json.loads(line))
    return result
def run_suite(binary,old,boundary,out):
    out.mkdir(parents=True,exist_ok=True);private=out.parent.parent/'snapshot-private';private.mkdir(mode=0o700)
    cert=private/'cert.crt';key=private/'key.pem'
    subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1','-keyout',str(key),'-out',str(cert),'-subj','/CN=127.0.0.1','-addext','subjectAltName=IP:127.0.0.1,DNS:localhost'],check=True,capture_output=True)
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'webdav'))
    from cloud_native import trust_fixture_certificates
    trust_fixture_certificates((cert,),'f10-owned-')
    trust=subprocess.run(['openssl','verify','-CAfile','/etc/ssl/certs/ca-certificates.crt',str(cert)],capture_output=True,text=True)
    print(json.dumps({'system_trust_verify':trust.returncode,'stdout':trust.stdout,'stderr':trust.stderr}),flush=True)
    if trust.returncode:raise RuntimeError('System trust verification failed; behavior cases not started')
    rows=[]
    def case(name,fn):
        work=private/name;work.mkdir(mode=0o700);server=Server(cert,key);checks={};raw=[]
        try:fn(work,server,checks,raw)
        except Exception as e:checks['exception']=type(e).__name__
        finally:server.close()
        result={'name':name,'checks':checks,'requests':server.requests,'stored':{k:sha(v) for k,v in server.data.items()},'raw':raw}
        (out/(name+'.json')).write_text(json.dumps(result,indent=2)+'\n');rows.append(result)
        print(json.dumps({'snapshot_observation':result}),flush=True)
    def callback(kind):
        def f(w,s,c,raw):
            s.mode='redirect' if kind=='redirect' else 'normal'
            if kind=='exists':s.data['/dav/body']=BODY
            p=subprocess.run([str(binary),'callback',str(w),s.url,kind],capture_output=True,text=True,timeout=20);raw.append(p.stdout+p.stderr)
            c.update(parse(p.stdout));c['exit']=p.returncode
            c['exact_body']=int(s.data.get('/dav/body')==BODY)
            c['no_redirect_request']=int(not any(x['path']=='/dav/other' for x in s.requests))
            c['conditional']=int(all(x.get('if_none_match')=='*' for x in s.requests if x['method']=='PUT'))
        return f
    # Existing callback-normal is also the same native HTTPS fail-fast preflight.
    # Its original independent audit assertions remain unchanged.
    case('callback-normal',callback('normal'))
    preflight=rows[-1]
    expected={'put':0,'exit':0,'offset':len(BODY),'exact_body':1,'conditional':1,'no_redirect_request':1}
    if any(preflight['checks'].get(k)!=v for k,v in expected.items()) or preflight['stored'].get('/dav/body')!=sha(BODY):
        raise RuntimeError('Native verified HTTPS preflight failed; remaining behavior cases not started')
    print(json.dumps({'native_https_preflight':'passed','case':'callback-normal'}),flush=True)
    for kind in ['error','short','overflow','throw','cancel','zero','limit','redirect','exists']:case('callback-'+kind,callback(kind))
    def basic(w,s,c,raw):
        h=Interactive(binary,w,s.url);c['enable']=h.enabled;c['begin']=h.cmd('begin');c['write']=h.cmd('write');c['seal']=h.cmd('seal')
        c['busy']=h.cmd('busy');c['put']=h.cmd('put');c['offset']=h.take('offset');c['close']=h.cmd('close');c['fd_closed']=h.take('fd_closed')
        c['roots']=h.cmd('observe','roots');c['pending']=h.take('pending');raw.append(h.stop());c['exact_body']=int(s.data.get('/dav/body')==BODY)
    case('managed-normal',basic)
    def replace(w,s,c,raw):
        h=Interactive(binary,w,s.url);h.cmd('begin');h.cmd('write');h.cmd('seal')
        payload=next(w.rglob('payload'));payload.rename(w/'original-held');payload.write_bytes(b'X'*len(BODY));payload.chmod(0o600)
        c['put']=h.cmd('put');c['offset']=h.take('offset');c['exact_body']=int(s.data.get('/dav/body')==BODY)
        c['close']=h.cmd('close');h.take('fd_closed');c['replacement_preserved']=int(payload.read_bytes()==b'X'*len(BODY));raw.append(h.stop())
    case('held-fd-path-replacement',replace)
    def permissions(w,s,c,raw):
        h=Interactive(binary,w,s.url);h.cmd('begin');h.cmd('write');h.cmd('seal')
        d=next(w.rglob('payload')).parent;d.chmod(0o500)
        c['close']=h.cmd('close');h.take('fd_closed');h.cmd('observe','roots');c['pending']=h.take('pending');d.chmod(0o700)
        c['retry_begin']=h.cmd('begin');h.cmd('write');h.cmd('seal');c['retry_close']=h.cmd('close');h.take('fd_closed')
        h.cmd('observe','roots');c['final_pending']=h.take('pending');raw.append(h.stop())
    case('managed-permission-retry',permissions)
    def death(sealed):
        def f(w,s,c,raw):
            h=Interactive(binary,w,s.url);h.cmd('begin');h.cmd('write')
            if sealed:h.cmd('seal')
            before=[p for p in w.rglob('payload')];c['payload_before']=len(before)
            other=subprocess.run([str(old),'recover',str(w)],capture_output=True,text=True,timeout=10);c['active_old_refused']=int(parse(other.stdout).get('recover')!=0);raw.append(other.stdout)
            h.p.kill();h.p.wait();c['signal']=-h.p.returncode;raw.append(''.join(h.raw))
            again=Interactive(binary,w,s.url);c['enable']=again.enabled;c['roots']=again.cmd('observe','roots');c['pending']=again.take('pending');c['payload_after']=len(list(w.rglob('payload')));raw.append(again.stop())
        return f
    case('managed-owned-kill',death(False));case('managed-sealed-kill',death(True))
    def upgrade(w,s,c,raw):
        s.data['/dav/body']=BODY;h=Interactive(binary,w,s.url);c['download']=h.cmd('download');raw.append(h.stop())
        reg=w/'webdav-managed-v1/registry';before=reg.read_bytes();c['v1']=int(before.startswith(b'EXReader managed registry 1\n'))
        h=Interactive(binary,w,s.url);raw.append(h.stop());c['readonly_unchanged']=int(reg.read_bytes()==before)
        h=Interactive(binary,w,s.url);c['begin']=h.cmd('begin');h.cmd('write');h.cmd('seal');h.cmd('close');h.take('fd_closed');raw.append(h.stop())
        after=reg.read_bytes();c['v2']=int(after.startswith(b'EXReader managed registry 2\n'));c['old_d_identity']=int(before.splitlines()[3]+b' D'==after.splitlines()[3])
        p=subprocess.run([str(old),'recover',str(w)],capture_output=True,text=True,timeout=10);raw.append(p.stdout);c['old_refused']=parse(p.stdout)['recover']
    case('registry-v1-upgrade',upgrade)
    def capacity_case(mixed):
        def f(w,s,c,raw):
            p=subprocess.run([str(binary),'capacity',str(w),'mixed' if mixed else 'all-d'],capture_output=True,text=True,timeout=30);raw.append(p.stdout);c['prepare']=p.returncode
            h=Interactive(binary,w,s.url);c['enable']=h.enabled
            if mixed:
                codes=[]
                for _ in range(64):
                    codes.append(h.cmd('begin'));h.cmd('write');h.cmd('seal');codes.append(h.cmd('close'));h.take('fd_closed')
                c['64_success']=int(codes==[0]*128)
            c['limit']=h.cmd('begin');c['roots']=h.cmd('observe','roots');h.take('pending');raw.append(h.stop())
        return f
    case('registry-16-download-roots',capacity_case(False));case('registry-mixed-capacity',capacity_case(True))
    def legacy_owned(w,s,c,raw):
        p=subprocess.run([str(binary),'capacity',str(w),'all-d'],capture_output=True,text=True,timeout=30);raw.append(p.stdout)
        p=subprocess.run([str(binary),'legacy-owned',str(w)],capture_output=True,text=True,timeout=10);raw.append(p.stdout);c['signal']=-p.returncode
        payload=next(w.rglob('payload'));before=payload.read_bytes()
        h=Interactive(binary,w,s.url);c['enable']=h.enabled;h.cmd('observe','roots');c['pending']=h.take('pending');raw.append(h.stop())
        c['d_payload_preserved']=int(payload.read_bytes()==before)
        c['still_v1']=int((w/'webdav-managed-v1/registry').read_bytes().startswith(b'EXReader managed registry 1\n'))
    case('legacy-download-owned-preserved',legacy_owned)
    def malformed(kind):
        def f(w,s,c,raw):
            h=Interactive(binary,w,s.url);h.cmd('begin');h.cmd('write');h.cmd('seal');h.p.kill();h.p.wait()
            reg=w/'webdav-managed-v1/registry';b=reg.read_bytes()
            if kind=='crc':reg.write_bytes(b[:-2]+(b'1' if b[-2:-1]!=b'1' else b'2')+b'\n')
            elif kind=='purpose':
                lines=b.splitlines(keepends=True);lines[3]=lines[3][:-2]+b'X\n';prefix=b''.join(lines[:-1]);reg.write_bytes(prefix+('%08x\n'%(zlib.crc32(prefix)&0xffffffff)).encode())
            else:(reg.parent/'registry.next').write_bytes(b'preserve')
            before={str(p.relative_to(w)):sha(p.read_bytes()) for p in w.rglob('*') if p.is_file()}
            p=subprocess.run([str(binary),'interactive',str(w),s.url],input='exit\n',capture_output=True,text=True,timeout=10);raw.append(p.stdout);c['enable']=parse(p.stdout)['enable']
            c['preserved']=int(before=={str(p.relative_to(w)):sha(p.read_bytes()) for p in w.rglob('*') if p.is_file()})
        return f
    for kind in ['crc','purpose','next']:case('registry-refuse-'+kind,malformed(kind))
    def migration_death(hook):
        def f(w,s,c,raw):
            h=Interactive(binary,w,s.url);raw.append(h.stop())
            reg=w/'webdav-managed-v1/registry';before=reg.read_bytes()
            env=dict(os.environ,F10_KILL_AT=hook)
            p=subprocess.run([str(boundary),'interactive',str(w),s.url],input='begin\n',env=env,capture_output=True,text=True,timeout=10);raw.append(p.stdout);c['signal']=-p.returncode
            c['v1_preserved']=int(reg.read_bytes()==before);c['v2']=int(reg.read_bytes().startswith(b'EXReader managed registry 2\n'));c['next']=int((reg.parent/'registry.next').exists())
            p=subprocess.run([str(binary),'interactive',str(w),s.url],input='begin\nexit\n',capture_output=True,text=True,timeout=10);raw.append(p.stdout)
            result=parse(p.stdout);c['refused']=int(result.get('enable',0)!=0 or result.get('begin',0)!=0)
        return f
    case('migration-kill-before-rename',migration_death('registry_next'));case('migration-kill-after-rename',migration_death('registry_committed'))
    def sync_case(kind):
        def f(w,s,c,raw):
            for leaf in ['cache','originals','managed']:(w/leaf).mkdir(mode=0o700)
            content=b'F10 actual sync original\n'*4096;digest=sha(content);(w/'originals'/(digest+'.txt')).write_bytes(content)
            rev={'version':1,'id':'10'+'0'*29+'1','entity_kind':'book','entity_key':'txt:'+digest,'operation':'put','location_kind':'none','parents':[],
                 'payload':{'format':'txt','source_sha256':digest,'source_bytes':len(content),'title':'F10','author':'Fixture','favorite':False}}
            wire=json.dumps(rev,separators=(',',':')).encode();wirefile=w/'wire.json';wirefile.write_bytes(wire)
            cmd=lambda mode:[str(binary),mode,str(w),s.url,str(wirefile)]
            p=subprocess.run(cmd('seed'),capture_output=True,text=True,timeout=10);raw.append(p.stdout);c['seed']=parse(p.stdout)['seed']
            if kind in ('permission','kill','cancel','lost'):s.mode='lost' if kind=='lost' else 'gate';s.release.clear()
            p=subprocess.Popen(cmd('step'),stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            changed=None
            if kind!='normal':
                assert s.arrived.wait(20),'actual PUT boundary missing'
                if kind=='permission':
                    changed=next((w/'managed').rglob('payload')).parent;changed.chmod(0o500)
                if kind=='cancel':(w/'cancel').write_text('cancel')
                if kind=='kill':p.kill()
                s.release.set()
            stdout,stderr=p.communicate(timeout=25);raw.append(stdout+stderr);first=parse(stdout)
            c['first_exit']=p.returncode
            if kind=='kill':c['signal']=-p.returncode
            else:c['first_status']=first['status'];c['first_outbox']=first['outbox'];c['first_pushed']=first['pushed']
            if changed:changed.chmod(0o700)
            if (w/'cancel').exists():(w/'cancel').unlink()
            s.mode='normal'
            q=subprocess.run(cmd('step'),capture_output=True,text=True,timeout=25);raw.append(q.stdout+q.stderr);last=parse(q.stdout)
            c['retry_status']=last['status'];c['retry_outbox']=last['outbox'];c['pending']=last['cleanup_pending']
            c['original_unchanged']=int(sha((w/'originals'/(digest+'.txt')).read_bytes())==digest)
            object_path='/dav/exreader-sync-v1/objects/'+digest[:2]+'/'+digest+'.txt'
            revision_path='/dav/exreader-sync-v1/revisions/10/'+rev['id']+'-'+sha(wire)+'.json'
            c['exact_original']=int(s.data.get(object_path)==content);c['exact_revision']=int(s.data.get(revision_path)==wire)
            puts=[x for x in s.requests if x['method']=='PUT' and x['path']==object_path]
            c['immutable_retry']=int(all(x['sha256']==digest for x in puts))
            c['verified_get']=int(any(x['method']=='GET' and x['path']==object_path for x in s.requests))
        return f
    for kind in ['normal','permission','kill','cancel','lost']:case('sync-'+kind,sync_case(kind))
    index={'source':os.environ['GITHUB_SHA'],'run':os.environ['GITHUB_RUN_ID'],'attempt':os.environ['GITHUB_RUN_ATTEMPT'],
           'binaries':{p.name:sha(p.read_bytes()) for p in [binary,old,boundary]},'cases':[r['name'] for r in rows],'full_f10_complete':False}
    (out/'index.json').write_text(json.dumps(index,indent=2)+'\n')
    return rows
