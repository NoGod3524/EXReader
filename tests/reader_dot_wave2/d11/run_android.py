"""Reinstall exact producer APK and reexecute existing native UI event tools."""
import hashlib,json,os,pathlib,subprocess,sys,traceback,shutil
assert os.environ.get('GITHUB_ACTIONS')=='true'
root=pathlib.Path.cwd();out=root/'build/d11';producer=out/'android-producer';target=root/'target';executions=[];programs={}
def find(suffix):
 matches=[p for p in producer.rglob(pathlib.Path(suffix).name) if p.as_posix().endswith(suffix)];assert len(matches)==1,(suffix,matches);return matches[0].resolve()
def run(name,args,cwd=target):
 with (out/(name+'.log')).open('w') as log:r=subprocess.run(list(map(str,args)),cwd=cwd,stdout=log,stderr=subprocess.STDOUT)
 executions.append(dict(name=name,returncode=r.returncode));print(json.dumps(executions[-1]),flush=True)
 if r.returncode:print('\n'.join((out/(name+'.log')).read_text(errors='replace').splitlines()[-90:]),flush=True)
 return r.returncode
try:
 host=find('apk/debug/app-debug.apk');(out/'programs').mkdir(exist_ok=True);shutil.copy2(host,out/'programs/app-debug.apk');programs['host']={'path':str(host),'sha256':hashlib.sha256(host.read_bytes()).hexdigest()}
 assert run('android-install-host',['adb','install','-r','-t',host])==0
 run('android-actual-config',[sys.executable,root/'tests/reader_dot_wave2/d11/apk_config.py',host],cwd=root)
 run('android-focus',[sys.executable,root/'tests/reader_dot_wave2/d11/android_focus.py'],cwd=root)
 # Bind installed application bytes independently to the authenticated input APK.
 installed=subprocess.check_output(['adb','shell','pm','path','org.exreader.host'],text=True).strip().removeprefix('package:')
 data=subprocess.check_output(['adb','exec-out','cat',installed]);assert hashlib.sha256(data).hexdigest()==programs['host']['sha256']
 programs['installed']={'path':installed,'sha256':hashlib.sha256(data).hexdigest()}
except Exception:
 traceback.print_exc();executions.append(dict(name='environment-or-harness',returncode=1))
finally:
 report=dict(harness_sha=os.environ['GITHUB_SHA'],target_sha=subprocess.check_output(['git','-C',str(target),'rev-parse','HEAD'],text=True).strip(),producer=json.loads((out/'android-producer-identity.json').read_text()),run_id=os.environ['GITHUB_RUN_ID'],attempt=os.environ['GITHUB_RUN_ATTEMPT'],host='android',programs=programs,executions=executions,accepted=bool(executions) and all(r['returncode']==0 for r in executions),keyboard_accepted=False,complete_product=False,screen_reader_accepted=False,device=subprocess.check_output(['adb','shell','getprop','ro.build.fingerprint'],text=True).strip())
 report['files']={p.relative_to(out).as_posix():{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in out.rglob('*') if p.is_file() and '-producer' not in str(p.relative_to(out)) and p.suffix in ('.json','.png','.log','.txt','.xml','.apk')}
 (out/'android-execution.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
assert report['accepted']
