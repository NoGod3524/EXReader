"""Reuse frozen D22 build commands with the explicit, fixed SDK342 input."""
import os,shutil,subprocess,sys,textwrap
from fetch_sender import *
def run(label,command,env):
 p=subprocess.run(['bash','-euo','pipefail','-c',command],cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=1800)
 (OUT/(label+'.log')).write_text(p.stdout+'\n'+p.stderr)
 print('F02_BUILD '+label+' exit='+str(p.returncode)+'\n'+p.stdout[-1800:]+p.stderr[-1800:],flush=True)
 need(p.returncode==0,'build '+label)
def block(lines,name):
 marker='      - name: '+name
 hits=[i for i,l in enumerate(lines) if l==marker];need(len(hits)==1,'frozen recipe '+name)
 i=hits[0]+1
 while i<len(lines) and not lines[i].startswith('        run:'):i+=1
 need(i<len(lines),'run block '+name)
 value=lines[i].strip()[len('run:'):].strip()
 if value!='|':return value+'\n'
 body=[];i+=1
 while i<len(lines) and (not lines[i].strip() or lines[i].startswith('          ')):
  body.append(lines[i][10:] if lines[i].strip() else '');i+=1
 return '\n'.join(body)+'\n'
def main():
 actions();OUT.mkdir(parents=True,exist_ok=True)
 env=dict(os.environ);ws=ROOT/'build/wave3';stage=ws/'stage';sdk=ws/'sdk-stage'
 android=Path(env.get('ANDROID_HOME','/usr/local/lib/android/sdk'))
 sdk_source=ROOT/'build/f02-sdk8357'
 subprocess.run(['git','worktree','add','--detach',str(sdk_source),LOCK['sdk']],cwd=ROOT,check=True)
 env.update(C11_NDK='27.0.12077973',ANDROID_HOME=str(android),ANDROID_SDK_ROOT=str(android),
  C11_TOOLCHAIN=str(android/'ndk/27.0.12077973/build/cmake/android.toolchain.cmake'),
  C11_STAGE=str(stage),C11_SDK_STAGE=str(sdk),F02_SDK_SOURCE=str(sdk_source),
  EXREADER_ORIGINAL_HASH_PREFIX=str(stage.resolve()))
 workflow=ROOT/'.github/workflows/reader-d22-android-receive.yml';lines=workflow.read_text().splitlines()
 report=dict(identity=identity(),sdk_source=LOCK['sdk'],sdk_version='3.42.0',accepted=False,
  original_recipe_sha256=file_sha(workflow),assertions_removed=False,steps=[])
 selected=[
 ('candidate','Prepare existing C11 candidate test sources'),
 ('toolchain','Install the Android platform CMake NDK and API34 image'),
 ('sdk','Build and install the frozen 3.41 SDK for x86_64'),
 ('modules','Install the raw0.2 product and reviewed wave3 packages into one prefix'),
 ('assets','Author the deterministic fixtures and the bundled font'),
 ('instrumentation','Build D22 explicit receive runner')]
 try:
  for label,name in selected:
   original=block(lines,name);command=original
   if label=='sdk':
    a='cmake -S . -B "$ws/sdk"';need(command.count(a)==1,'fixed SDK recipe insertion')
    command=command.replace(a,'cmake -S "$F02_SDK_SOURCE" -B "$ws/sdk"')
   command=command.replace('3.41.0','3.42.0')
   if label in ('host','instrumentation'):
    command=command.replace('gradle -p examples/android ','gradle -p examples/android -PexrSdkVersion=3.42.0 ')
   if label=='modules':
    a='build_module product apps/reader/store/native';need(command.count(a)==1,'hash owner staging')
    command=command.replace(a,'build_module original-hash extras/opds -DEXREADER_OPDS_HASH_ONLY=ON\n'+a)
   if label=='instrumentation':
    command='mkdir -p "$PWD/build/wave3/artifacts"\n'+command
    command=command.replace(':app:assembleDebugAndroidTest',':app:assembleDebug :app:assembleDebugAndroidTest')
    command=command.replace('tests/reader_android_receive_d22/init.gradle','tests/reader_f02_win_android_20261031/init.gradle')
    command=command.replace('org.exreader.host.D22ReceiveTest','org.exreader.host.F02ReceiveTest')
   (OUT/('recipe-'+label+'.sh')).write_text(command)
   report['steps'].append(dict(name=label,original_sha256=sha(original.encode()),derived_sha256=sha(command.encode())))
   run(label,command,env)
  artifacts=OUT/'artifacts';artifacts.mkdir()
  shutil.copyfile(ROOT/'examples/android/app/build/outputs/apk/debug/app-debug.apk',artifacts/'host.apk')
  shutil.copyfile(ws/'artifacts/d22-debug-androidTest.apk',artifacts/'test.apk')
  report['files']={p.name:dict(bytes=p.stat().st_size,sha256=file_sha(p)) for p in artifacts.iterdir()}
  report['product_blobs']=LOCK['production_result_blobs']
  report['sdk_trees']={p:subprocess.check_output(['git','rev-parse',LOCK['sdk']+':'+p],cwd=ROOT,text=True).strip() for p in ('src','include','cmake','CMakeLists.txt','bindings')}
  caches=list((ROOT/'examples/android/app/.cxx').rglob('CMakeCache.txt'))
  need(bool(caches),'actual Android host CMake caches')
  for cache in caches:
   need('EXR_HOST_SDK_VERSION:STRING=3.42.0' in cache.read_text(),'explicit host SDK342 cache')
  report['host_caches']=[dict(path=str(p.relative_to(ROOT)),sha256=file_sha(p)) for p in caches]
  report['accepted']=True
 finally:
  save(OUT/'build.json',report)
  print('F02_ANDROID_BUILD '+json.dumps(report),flush=True)
if __name__=='__main__':main()
