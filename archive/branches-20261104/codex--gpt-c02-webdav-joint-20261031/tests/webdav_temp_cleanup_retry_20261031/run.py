# SPDX-License-Identifier: MIT
import argparse,errno,hashlib,json,os,pathlib,ssl,subprocess,sys,threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
sys.path.insert(0,str(pathlib.Path('tests/webdav').resolve()))
from cloud_native import trust_fixture_certificates
p=argparse.ArgumentParser()
p.add_argument('--probe',required=True);p.add_argument('--output',required=True)
a=p.parse_args()
assert os.environ.get('GITHUB_ACTIONS')=='true' and os.geteuid()!=0
out=pathlib.Path(a.output).resolve();out.mkdir(parents=True,exist_ok=False)
probe=str(pathlib.Path(a.probe).resolve())
payload=b'WebDAV cleanup synthetic payload\n'+bytes(range(256))*4096
expected_hash=hashlib.sha256(payload).hexdigest()
key=out/'fixture.key';cert=out/'fixture.crt'
subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1',
 '-keyout',str(key),'-out',str(cert),'-subj','/CN=localhost',
 '-addext','subjectAltName=DNS:localhost'],check=True,capture_output=True)
trust_fixture_certificates((cert,),'exr-cleanup-retry-')
requests=[]
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_GET(self):
        requests.append(self.path)
        assert self.path=='/dav/book.epub'
        self.send_response(200);self.send_header('Content-Length',str(len(payload)))
        self.end_headers();self.wfile.write(payload)
server=ThreadingHTTPServer(('localhost',0),Handler)
server.daemon_threads=True
context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(cert,key)
server.socket=context.wrap_socket(server.socket,server_side=True)
threading.Thread(target=server.serve_forever,daemon=True).start()
root='https://localhost:'+str(server.server_port)+'/dav/'
results=[]
try:
    for mode in ('normal','eio_once','eintr_once','eio_persistent','eacces_persistent','existing','late_cancel'):
        directory=out/mode;directory.mkdir(mode=0o700)
        target=directory/'book.epub'
        if mode=='existing':target.write_bytes(b'UNCHANGED EXISTING TARGET')
        before=len(requests)
        try:
            r=subprocess.run([probe,root,str(directory),mode],capture_output=True,text=True,timeout=40)
        finally:
            # Only this synthetic case directory; restore even on timeout.
            directory.chmod(0o700)
        (out/(mode+'.stdout.json')).write_text(r.stdout)
        (out/(mode+'.stderr.txt')).write_text(r.stderr)
        assert r.returncode==0,(mode,r.returncode,r.stderr)
        v=json.loads(r.stdout)
        assert v['source']==os.environ['GITHUB_SHA'] and v['uid']!=0
        assert v['restored'] and v['unrelated_unlink_ok'] and v['hook_error']==0
        assert len(requests)==before+1
        temps=list(directory.glob('.exr-webdav-*.tmp'))
        if mode=='existing':
            assert v['status']==11 and v['published']==0 and v['bytes']==0
            assert v['link_attempts']==1 and v['link_committed']==0 and v['target_unlinks']==0
            assert not temps and target.read_bytes()==b'UNCHANGED EXISTING TARGET'
        else:
            assert v['status']==0 and v['published']==1 and v['bytes']==len(payload)
            assert hashlib.sha256(target.read_bytes()).hexdigest()==expected_hash
            assert v['link_attempts']==v['link_committed']==1
            assert v['target_unlinks']==(1 if mode in ('normal','late_cancel') else 2)
            assert v['same_at_link']
            if mode in ('normal','late_cancel','eio_once','eintr_once'):
                assert not temps and not v['temp_exists'] and v['target_nlink']==1
                assert v['permission_changed']==0
                if mode in ('normal','late_cancel'):assert v['injected']==v['unlink_errno']==0
                else:assert v['injected']==1 and v['unlink_errno']==(errno.EIO if mode=='eio_once' else errno.EINTR)
            else:
                assert len(temps)==1 and temps[0].name==v['temp_name']
                st,dt=temps[0].stat(),target.stat()
                assert v['temp_exists'] and v['same_inode'] and v['target_nlink']==2
                assert (st.st_dev,st.st_ino)==(dt.st_dev,dt.st_ino)
                assert hashlib.sha256(temps[0].read_bytes()).hexdigest()==expected_hash
                if mode=='eio_persistent':
                    assert v['injected']==2 and v['unlink_errno']==errno.EIO and not v['permission_changed']
                else:
                    assert v['injected']==0 and v['unlink_errno']==errno.EACCES
                    assert v['permission_changed']==1 and v['directory_mode_before_restore']==0o500
        v.update(mode=mode,real_https_requests=1,target_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                 observed_temp_count=len(temps),retry_case_passed=True)
        # Record observation before explicit fixture cleanup, never erase the target.
        for temp in temps:temp.unlink()
        assert not list(directory.glob('.exr-webdav-*.tmp'))
        v['fixture_residue_removed']=True
        results.append(v);print('CLEANUP-RETRY-CASE '+json.dumps(v),flush=True)
    assert len(results)==7 and len(requests)==7
    receipt=dict(source=os.environ['GITHUB_SHA'],run=os.environ['GITHUB_RUN_ID'],
      attempt=os.environ['GITHUB_RUN_ATTEMPT'],validation_completed=True,transient_cleanup_passed=True,
      product_cleanup_passed=False,persistent_cleanup_unresolved=True,crash_recovery_validated=False,
      publication_contract_preserved=True,cases=results,scope='Linux installed module; synthetic private fixtures')
    (out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print('CLEANUP-RETRY-SUMMARY '+json.dumps(receipt),flush=True)
finally:
    server.shutdown();server.server_close()
    key.unlink(missing_ok=True)
    for directory in out.iterdir():
        if directory.is_dir():directory.chmod(0o700)
