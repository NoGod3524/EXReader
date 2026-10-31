# SPDX-License-Identifier: MIT
"""One bounded Actions experiment, not full F10 acceptance."""
import argparse,base64,errno,hashlib,json,os,queue,signal,stat,subprocess,sys,threading,time,uuid
from pathlib import Path
from fixture import Fixture
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'webdav'))
from cloud_native import trust_fixture_certificates

def sha(b): return hashlib.sha256(b).hexdigest()
def save(p,value): p.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def observe(folder):
    rows=[]
    for p in sorted(folder.iterdir()):
        s=p.lstat()
        rows.append({'name':p.name,'dev':s.st_dev,'ino':s.st_ino,'mode':stat.S_IMODE(s.st_mode),'nlink':s.st_nlink,'size':s.st_size,
                     'sha256':sha(p.read_bytes()) if p.is_file() and not p.is_symlink() else None})
    return rows
def main():
    a=argparse.ArgumentParser();a.add_argument('--probe',type=Path,required=True);a.add_argument('--output',type=Path,required=True);args=a.parse_args()
    assert os.environ.get('GITHUB_ACTIONS')=='true'
    assert os.geteuid()!=0, 'real non-root permission failure required'
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    private=out.parent/'private-fixture';private.mkdir(exist_ok=True,mode=0o700)
    key=private/'server.key';cert=private/'server.crt'
    subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1','-keyout',str(key),'-out',str(cert),'-subj','/CN=127.0.0.1','-addext','subjectAltName=IP:127.0.0.1,DNS:localhost'],check=True,capture_output=True)
    trust_fixture_certificates((cert,),'f10-safety-')
    secret='f10-'+uuid.uuid4().hex
    authorization='Basic '+base64.b64encode(('fixture:'+secret).encode()).decode()
    env=dict(os.environ,F10_AUTH=authorization)
    probe=args.probe.resolve()
    source=('F10 original fixture not a user book\n'*4096).encode()
    source_sha=sha(source);book_key='txt:'+source_sha
    rev={'version':1,'id':'10'+'0'*29+'1','entity_kind':'book','entity_key':book_key,'operation':'put','location_kind':'none','parents':[],
         'payload':{'format':'txt','source_sha256':source_sha,'source_bytes':len(source),'title':'F10 fixture','author':'Test','favorite':False}}
    wire=json.dumps(rev,separators=(',',':')).encode()
    object_resource='/dav/exreader-sync-v1/objects/'+source_sha[:2]+'/'+source_sha+'.txt'
    revision_resource='/dav/exreader-sync-v1/revisions/10/'+rev['id']+'-'+sha(wire)+'.json'
    all_cases=[]
    race_cases=['target-created-during-download','existing-same-hash','existing-different-hash','link-refusal-directory']
    def run_case(name):
        case=out/name;case.mkdir()
        work=private/name;work.mkdir(mode=0o700)
        cache=work/'cache';originals=work/'originals';cache.mkdir(mode=0o700);originals.mkdir(mode=0o700)
        original=originals/(source_sha+'.txt');original.write_bytes(source)
        revfile=work/'revision.json';revfile.write_bytes(wire)
        account=str(uuid.uuid4())
        fixture=Fixture(cert,key,authorization)
        process=None
        record={'name':name,'source':os.environ['GITHUB_SHA'],'run':os.environ['GITHUB_RUN_ID'],'attempt':os.environ['GITHUB_RUN_ATTEMPT'],
                'program_sha256':sha(probe.read_bytes()),'profile_id':account,'entity_key':book_key,'original_before':sha(original.read_bytes()),'euid':os.geteuid()}
        def cmd(mode):return [str(probe),mode,str(work),fixture.url,account,'16',str(revfile)]
        def collect(p):
            stdout,stderr=p.communicate(timeout=25)
            assert secret not in stdout+stderr and authorization not in stdout+stderr
            (case/'stdout.txt').write_text(stdout);(case/'stderr.txt').write_text(stderr)
            record['exit_code']=p.returncode
            record['result']=[json.loads(x) for x in stdout.splitlines() if x.startswith('{')]
        try:
            if name in race_cases:
                fixture.add(object_resource,source);fixture.add(revision_resource,wire)
                fixture.gate_method='GET';fixture.gate_fragment='/objects/'
            else:
                seed=subprocess.run(cmd('seed'),env=env,capture_output=True,text=True,timeout=20)
                assert seed.returncode==0, seed.stdout+seed.stderr
                record['seed']=json.loads(seed.stdout)
                if name!='normal':
                    fixture.gate_method='PUT';fixture.gate_fragment='/objects/'
            process=subprocess.Popen(cmd('session' if name=='close-join' else 'step'),env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            record['pid']=process.pid
            if name=='close-join':
                lines=queue.Queue()
                def reader():
                    for line in process.stdout: lines.put(line)
                threading.Thread(target=reader,daemon=True).start()
                def request(text):
                    process.stdin.write(text+'\n');process.stdin.flush()
                    return json.loads(lines.get(timeout=20))
                created=json.loads(lines.get(timeout=20));assert created['create']==0
                started=request('start')
                assert fixture.arrived.wait(20)
                record['at_gate']=observe(cache)
                close=request('close');fixture.release.set();views=[created,started,close]
                end=time.monotonic()+20
                while time.monotonic()<end:
                    view=request('observe');views.append(view)
                    if view['state']==7:break
                    time.sleep(.02)
                assert views[-1]['state']==7,'CLOSED deadline'
                destroyed=request('destroy');views.append(destroyed)
                process.wait(timeout=5)
                record['exit_code']=process.returncode;record['views']=views
                record['result']=[]
                record['close_join_passed']=destroyed['code']==0 and destroyed['alive']==0 and process.returncode==0
            elif name=='normal':
                collect(process)
            else:
                assert fixture.arrived.wait(20),'fixture gate did not fire'
                record['at_gate']=observe(cache)
                if name=='eacces-cleanup':
                    canary=cache/'permission-canary';canary.write_bytes(b'canary')
                    cache.chmod(0o500)
                    try:
                        canary.unlink();record['canary_errno']=0
                    except OSError as e: record['canary_errno']=e.errno
                    assert record['canary_errno']==errno.EACCES
                    fixture.release.set();collect(process)
                    record['before_permission_restore']=observe(cache)
                    cache.chmod(0o700);canary.unlink()
                elif name=='kill-and-restart':
                    process.kill();collect(process)
                    assert record['exit_code']==-signal.SIGKILL
                    record['killed_residual']=observe(cache)
                    fixture.release.set()
                    restart=subprocess.run(cmd('step'),env=env,capture_output=True,text=True,timeout=25)
                    record['restart']={'exit_code':restart.returncode,'result':[json.loads(x) for x in restart.stdout.splitlines() if x.startswith('{')]}
                    assert secret not in restart.stdout+restart.stderr
                elif name in race_cases:
                    target=cache/(source_sha+'.txt')
                    if name=='link-refusal-directory':target.mkdir()
                    else:target.write_bytes(source if name=='existing-same-hash' else b'F10 concurrent target must not be overwritten')
                    record['concurrent_target']={'sha256':sha(target.read_bytes()) if target.is_file() else None,'ino':target.stat().st_ino,'directory':target.is_dir()}
                    fixture.release.set();collect(process)
                    record['target_after']={'sha256':sha(target.read_bytes()) if target.is_file() else None,'ino':target.stat().st_ino,'directory':target.is_dir()}
            record['after']=observe(cache)
            record['original_after']=sha(original.read_bytes())
            record['requests']=fixture.requests
            record['observation_complete']=True
        except Exception as e:
            record['observation_complete']=False
            record['error']=type(e).__name__+': '+str(e)
        finally:
            cache.chmod(0o700)
            fixture.release.set()
            if process is not None and process.poll() is None:
                process.kill();process.wait(timeout=5)
            fixture.close()
        # Scan actual test product database and cache bytes for only synthetic
        # credential values. No user credentials are read or exported.
        leaks=[]
        for p in work.rglob('*'):
            if p.is_file():
                b=p.read_bytes()
                if secret.encode() in b or authorization.encode() in b:leaks.append(str(p.relative_to(work)))
        record['synthetic_secret_leaks']=leaks
        record['credential_scan_scope']='test product catalog, cache and fixture original only; not OS secure storage'
        save(case/'observation.json',record);all_cases.append(record)
    for name in ['normal','close-join','eacces-cleanup','kill-and-restart']+race_cases:run_case(name)
    save(out/'index.json',{'source':os.environ['GITHUB_SHA'],'run':os.environ['GITHUB_RUN_ID'],'attempt':os.environ['GITHUB_RUN_ATTEMPT'],
                          'cases':[x['name'] for x in all_cases],'program_sha256':sha(probe.read_bytes()),
                          'scope':'installed raw sync/session modules; no reading SDK or host UI acceptance','full_f10_complete':False})
    # Evidence collection success is not safety acceptance. verifier owns that.
    if not all(x.get('observation_complete') for x in all_cases):return 2
    return 0
if __name__=='__main__':sys.exit(main())
