"""Compile the pinned editing model and ABI probes with the actual MSVC CRT."""
import os, subprocess, sys
from pathlib import Path
from audit import ROOT, HERE, TEMP, snapshot, save, done

VC = r'C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvarsall.bat'

def msvc_env(arch):
    p = subprocess.run(f'"{VC}" {arch} >nul && set', shell=True, capture_output=True, text=True)
    p.check_returncode()
    return dict(line.split('=',1) for line in p.stdout.splitlines() if '=' in line and not line.startswith('='))

def run(args, env, log):
    p = subprocess.run([str(a) for a in args],env=env,cwd=TEMP,capture_output=True,text=True)
    with log.open('a',encoding='utf-8') as f:
        f.write('$ '+subprocess.list2cmdline([str(a) for a in args])+'\n'+p.stdout+p.stderr+f'\nexit={p.returncode}\n')
    if p.returncode: raise RuntimeError(f'{p.returncode}: {log}')
    return p.stdout

def alignment():
    model=snapshot('6cb452da',['src/docx_edit.c','include','tests/test_docx_edit.c','tests/test_docx_edit_alloc.c'],'model')
    generated=TEMP/'generated/exr'
    generated.mkdir(parents=True,exist_ok=True)
    # Use the actual generated header from the previously built same SDK version.
    import shutil
    shutil.copyfile(Path('C:/Users/Oscar/Documents/Codex/EXReader-dxmodel-20261110/build/native/generated/include/exr/version.h'),generated/'version.h')
    for arch in ['x64','x86']:
        env=msvc_env(arch)
        cl=next(Path(d)/'cl.exe' for d in env['Path'].split(';') if (Path(d)/'cl.exe').exists())
        opts=['/nologo','/std:c11','/W4','/DEXR_STATIC','/I'+str(TEMP/'generated'),'/I'+str(model/'include')]
        log=HERE/f'01-alignment-msvc-{arch}.txt'
        log.write_text('',encoding='utf-8')
        exe=TEMP/f'alignment-{arch}.exe'
        run([cl,*opts,'/DEXR_EDIT_MODEL_SOURCE="'+(model/'src/docx_edit.c').as_posix()+'"',
             ROOT/'tests/check_orchestrator_alignment.c','/Fo'+str(TEMP/f'alignment-{arch}.obj'),'/Fe'+str(exe)],env,log)
        print(run([exe],env,log),flush=True)
        exe=TEMP/f'edit-{arch}.exe'
        run([cl,*opts,model/'src/docx_edit.c',model/'tests/test_docx_edit.c','/Fe'+str(exe),'/link','psapi.lib'],env,log)
        for group in ['insert','split','para-props','run-props','delete','transaction','rollback','history','preservation','boundaries','mixed']:
            run([exe,group],env,log)
        exe=TEMP/f'edit-alloc-{arch}.exe'
        run([cl,*opts,model/'tests/test_docx_edit_alloc.c','/Fe'+str(exe)],env,log)
        run([exe],env,log)
    done(1,'MSVC x64/x86 原始模型 11 组语义测试及分配失败测试均通过；真实类型 sizeof/alignof 和 4096 次分配见 01-alignment-msvc-*.txt。')

if __name__=='__main__':
    alignment()
