"""Actions-only public-types C/C++ unit checks; no SDK or host execution grant."""
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys

assert os.environ.get('GITHUB_ACTIONS')=='true'
BASE='0889f7d1e9a537c6c1b05456547e016b26e1cd85'
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'build/private-capture';OUT.mkdir(parents=True,exist_ok=True)
identity={k:os.environ[v] for k,v in [('source_sha','GITHUB_SHA'),('run_id','GITHUB_RUN_ID'),('attempt','GITHUB_RUN_ATTEMPT')]}
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT,text=True).strip()
assert git('rev-parse','HEAD')==identity['source_sha']
subprocess.run(['git','merge-base','--is-ancestor',BASE,'HEAD'],cwd=ROOT,check=True)
allowed={'apps/reader/desktop/reading_capture_bytes.h','.github/workflows/reader-private-capture.yml','docs/READER-PRIVATE-CAPTURE.md','docs/validation/reader-private-capture.json'}
changed=git('diff','--name-only',BASE,'HEAD').splitlines()
assert all(p in allowed or p.startswith('tests/reader_private_capture/') for p in changed),changed
pins={p:git('rev-parse','HEAD:'+p) for p in ('src','include','cmake','apps/reader/revisions','apps/reader/reading-state','apps/reader/reading-commands','apps/reader/annotation-view','apps/reader/commands','apps/reader/sync','apps/reader/session')}
assert all(value==git('rev-parse',BASE+':'+path) for path,value in pins.items())

# Independent format model, not the C helpers or a stored output of the codec.
def golden(mode,writer,part,page,start,end,fields):
    result=struct.pack('<8sIIIIQQQQ',b'EXRPCAP\0',1,writer,mode,0,part,page,start,end)
    for value in fields:result+=struct.pack('<BI',int(value is not None),0 if value is None else len(value))+(value or b'')
    return result
fixed=[None,None,b'p7',b'A\0B\xff',b'',None]
expected={f'fixed{w}':golden(3,w,3,7,11,15,fixed) for w in (1,2,3)}
expected['null-exact']=golden(3,2,3,7,0,0,[None,None,b'p7',None,b'',b'\0'])
for w in (1,2):expected['reflow'+str(w)]=golden(1,w,0,0,2,5,[b'chapter1',None,None,b'abc',None,b''])
expected['epub2']=golden(2,2,9,0,1,8,[b'ch.xhtml',b'spine/ch.xhtml',None,'汉😀'.encode(),None,b''])
(OUT/'golden').mkdir(exist_ok=True)
for name,body in expected.items():(OUT/'golden'/ (name+'.bin')).write_bytes(body)

includes=[ROOT/'include',ROOT/'apps/reader/revisions/include',ROOT/'apps/reader/reading-state/include',ROOT/'apps/reader/desktop']
variants=[('c','c11',[]),('cpp','c++17',[])]
if sys.platform!='win32':variants += [('c-asan','c11',['-fsanitize=address,undefined','-fno-omit-frame-pointer']),('cpp-asan','c++17',['-fsanitize=address,undefined','-fno-omit-frame-pointer']),('c-32','c11',['-m32']),('cpp-32','c++17',['-m32'])]
reports=[]
for name,standard,extra in variants:
    directory=OUT/name;directory.mkdir(exist_ok=True);executable=directory/('consumer.exe' if sys.platform=='win32' else 'consumer')
    cpp=standard=='c++17';source=ROOT/'tests/reader_private_capture/check.c'
    if sys.platform=='win32':
        command=['cl','/nologo','/TP' if cpp else '/TC','/std:'+standard,'/W4','/WX','/utf-8','/DEXR_STATIC',*['/I'+str(p) for p in includes],str(source),'/Fe:'+str(executable),'/Fo:'+str(directory/'consumer.obj')]
    else:
        command=['c++' if cpp else 'cc','-x','c++' if cpp else 'c','-std='+standard,'-Wall','-Wextra','-Werror','-pedantic','-DEXR_STATIC',*extra,*['-I'+str(p) for p in includes],str(source),'-o',str(executable)]
    compiled=subprocess.run(command,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    (directory/'compile.log').write_text(compiled.stdout);print(compiled.stdout,flush=True);assert compiled.returncode==0,command
    environment=dict(os.environ,ASAN_OPTIONS='detect_leaks=1:halt_on_error=1',UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1')
    executed=subprocess.run([str(executable),str(directory)],cwd=ROOT,env=environment,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=60)
    (directory/'run.log').write_text(executed.stdout);print(executed.stdout,flush=True);assert executed.returncode==0
    cases=[line[5:] for line in executed.stdout.splitlines() if line.startswith('PASS ')]
    assert len(cases)==len(set(cases))==10 and 'PRIVATE_CAPTURE_OK size_t='+('4' if name.endswith('-32') else '8') in executed.stdout
    files={}
    for key,body in expected.items():
        actual=(directory/(key+'.bin')).read_bytes();assert actual==body,(name,key)
        files[key]={'bytes':len(actual),'sha256':hashlib.sha256(actual).hexdigest()}
    reports.append({'name':name,'language':standard,'size_t':4 if name.endswith('-32') else 8,'cases':cases,'vectors':files,'program_sha256':hashlib.sha256(executable.read_bytes()).hexdigest()})
report={**identity,'accepted':True,'base':BASE,'platform':sys.platform,'scope':'private header codec public-types unit tests only','sdk_accepted':False,'host_accepted':False,'public_wire_accepted':False,'pins':pins,'changed':changed,'consumers':reports}
report['files']={p.relative_to(OUT).as_posix():{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in OUT.rglob('*') if p.is_file()}
(OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)
