"""Seal only after native clients and all output writers have terminated."""
import hashlib,json,os,pathlib,subprocess,sys,shutil,traceback
from common import identity,sha
root=pathlib.Path.cwd();out=root/'build/d11';out.mkdir(parents=True,exist_ok=True);host=sys.argv[1];phase=sys.argv[2] if len(sys.argv)>2 else 'all';executions=[];programs={}
try:
 if phase!='seal':
  script=root/'tests/reader_dot_wave2/d11'/(host+'_actions.py')
  with (out/(host+'-actions.log')).open('w',encoding='utf-8') as log:r=subprocess.run([sys.executable,str(script)],stdout=log,stderr=subprocess.STDOUT)
  executions.append(dict(name='native-actions',returncode=r.returncode))
  (out/(host+'-command.json')).write_text(json.dumps(executions))
  print((out/(host+'-actions.log')).read_text(encoding='utf-8',errors='replace')[-35000:],flush=True)
 else:
  executions=json.loads((out/(host+'-command.json')).read_text())
 if phase=='execute':sys.exit(r.returncode)
 if host=='windows':
  source=root/'build/d11-evidence';shutil.copytree(source,out/'windows-build');binary=out/'windows-build/programs/EXReaderProduct.exe'
 else:
  source=root/'target/build/d11-package-ON';shutil.copytree(source,out/'gtk-build');binary=out/'gtk-build/EXReader-Linux/bin/exreader-linux'
  for name in ('CMakeCache.txt','compile_commands.json','build.ninja'):
   shutil.copy2(root/'target/build/d11-ON'/name,out/'gtk-build'/name)
 programs['actual']={'path':binary.relative_to(out).as_posix(),'sha256':sha(binary),'bytes':binary.stat().st_size}
except Exception:traceback.print_exc();executions.append(dict(name='harness',returncode=1))
finally:
 if phase=='execute':
  pass
 else:
  report=dict(**identity(host),programs=programs,executions=executions,accepted=bool(programs) and all(x['returncode']==0 for x in executions),keyboard_accepted=False,complete_product=False,screen_reader_accepted=False)
  report['files']={p.relative_to(out).as_posix():{'bytes':p.stat().st_size,'sha256':sha(p)} for p in out.rglob('*') if p.is_file()}
  (out/(host+'-execution.json')).write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
if phase!='execute':assert report['accepted']
