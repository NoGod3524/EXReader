"""Actions-only three native close probes using the exact failed-run GTK binary.
Diagnostic only: no claim that this replaces the unchanged full 48/46 suites.
"""
import configparser,hashlib,json,os,re,shutil,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'));sys.path.insert(0,str(ROOT/'tests/reader_d23_relay'));sys.path.insert(0,str(ROOT/'tests/windows_gtk_conflict_recovery'))
from check_linux_host import Session,command
from scan_barrier import install
import service
assert os.environ.get('GITHUB_ACTIONS')=='true';install(Session)
folder=ROOT/'build/driver-diagnostic';package=folder/'package';program=package/'bin/exreader-linux'
assert hashlib.sha256(program.read_bytes()).hexdigest()=='a871a81e22cd32fb2bda041783183998499312979ad9ac63c562f31f05763a0a'
assert subprocess.check_output([str(program),'--version'],text=True).strip()=='3.42.0 1'
identity=json.loads((folder/'identity/report.json').read_text())
assert identity['source_sha']=='a121564303cb2844b60487b719e34742645f5cd4' and identity['run_id']=='40730797378' and identity['attempt']=='1'
assert identity['program_sha256']==hashlib.sha256(program.read_bytes()).hexdigest()
api=json.loads(subprocess.check_output(['gh','api','repos/'+os.environ['GITHUB_REPOSITORY']+'/actions/artifacts/12837015379'],text=True))
assert api['digest']=='sha256:66889783fc504c06e42fc31fdd77a1d0e5823ae9e2414f1dd0ed823d02d00680' and api['workflow_run']['head_sha']==identity['source_sha'] and not api['expired']
results=[]
for n in range(3):
    out=folder/('case-'+str(n));out.mkdir();shutil.copytree(folder/'evidence/original-account/unavailable/profile',out/'profile');(out/'profile').chmod(0o700)
    for p in (out/'profile').rglob('*'):
        assert not p.is_symlink()
        if p.is_dir():p.chmod(0o700)
        else:
            before=hashlib.sha256(p.read_bytes()).hexdigest();p.chmod(0o600);assert hashlib.sha256(p.read_bytes()).hexdigest()==before
    dav,user,password=service.start(out,None);host=Session(program,(package/'Reader.otf'),out)
    def account():
        c=configparser.ConfigParser(interpolation=None);c.read(host.observe);return dict(c['account']) if c.has_section('account') else {}
    def wait(f,seconds=30):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            assert host.process.poll() is None
            if f():return
            time.sleep(.05)
        raise TimeoutError(str(account()))
    try:
        host.launch();host.key('F2','ctrl+shift+a')
        def ready():return account().get('visible')=='1' and account().get('owner_busy')=='0' and account().get('preparing')=='0'
        wait(ready,90)
        visible=subprocess.check_output(['xdotool','search','--onlyvisible','--all','--pid',str(host.process.pid),'--name','^Account and Sync$'],text=True).split();assert len(visible)==1
        command('xdotool','windowactivate','--sync',visible[0])
        for mnemonic,value in (('w',dav.base+'/dav/'),('u',user),('p',password)):
            host.key('alt+'+mnemonic,'ctrl+a');host.paste(value)
        host.key('alt+h');dav.pause=True;host.key('alt+s');assert dav.blocked.wait(30)
        before_close=account();generation=int(before_close['session_generation']);assert generation==1 and before_close['session_present']=='1'
        command('wmctrl','-ic',hex(int(host.window)));deadline=time.monotonic()+5
        while host.process.poll() is None and account()['closing']!='1' and int(account()['closed_generation'])!=generation:
            assert time.monotonic()<deadline,'main close request was not observed';time.sleep(.05)
        dav.release.set();code=host.process.wait(timeout=35);host.log.close()
        assert code==0 and int(account()['closed_generation'])==generation and account()['session_present']=='0'
        result={'case':n,'captured_generation':generation,'before_close':before_close,'after_close':account(),'exit_code':code,'requests':len(dav.requests),'program_sha256':identity['program_sha256']};results.append(result);print('GTK_NATIVE_PINNED_CLOSE_PROBE '+json.dumps(result),flush=True)
    finally:
        dav.release.set();dav.server.shutdown();dav.server.server_close();(out/'key.pem').unlink(missing_ok=True)
        if host.process and host.process.poll() is None:host.process.kill();host.process.wait(timeout=15)
summary={'diagnostic_only':True,'accepted':True,'source_sha':os.environ['GITHUB_SHA'],'run_id':os.environ['GITHUB_RUN_ID'],'attempt':os.environ['GITHUB_RUN_ATTEMPT'],'pinned_program_source':identity['source_sha'],'pinned_program_sha256':identity['program_sha256'],'checks':results}
(folder/'result.json').write_text(json.dumps(summary,indent=2));print('GTK_NATIVE_PINNED_CLOSE_RESULT '+json.dumps(summary),flush=True)
