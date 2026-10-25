#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""All font material, native execution and evidence processing run only in Actions."""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time
import urllib.request
from fontTools.ttLib import TTCollection, TTFont
from cases import COMMON, POSIX, WINDOWS

COMMIT = '2823e993c53fca27c5c8749f529b56a5a7c77b6b'
INPUTS = [('TTF/SourceSerif4-Regular.ttf','font.ttf','964a2bf8934182485cf4e2348c8443091739334f',261868),
          ('OTF/SourceSerif4-Regular.otf','font.otf','fc9f84e94b2537b3cc10aaebcab08a0bc2a0e16b',241392),
          ('LICENSE.md','LICENSE.md','ebe298c6b488d68a43ec9b60155fb6b862a46bc1',4492)]

def sha(data): return hashlib.sha256(data).hexdigest()
def identity(p):
    b=p.read_bytes()
    return {'path':p.as_posix(),'bytes':len(b),'sha256':sha(b)}
def main():
    assert os.environ.get('GITHUB_ACTIONS')=='true', 'Actions only'
    base=Path('build/font-evidence').resolve();base.mkdir(parents=True,exist_ok=True)
    materials=base/'materials';materials.mkdir()
    results={'accepted':False,'source_sha':os.environ['GITHUB_SHA'],'run_id':int(os.environ['GITHUB_RUN_ID']),
      'attempt':int(os.environ['GITHUB_RUN_ATTEMPT']),'platform':platform.system(),'checks':[],
      'failures':[],'identities':[],'inputs':[],'host_ui_accepted':False,'mobile_accepted':False,
      'power_loss_accepted':False,'sdk_changed':False,'schema_changed':False,
      'gaps':['No host font picker or mobile integration','Process termination, not power-loss hardware testing',
              'No collection face enumeration; explicit face selection only']}
    log_number=0
    exe='.exe' if os.name=='nt' else ''
    probe=Path('build/font-consumer/font-probe'+exe).resolve()
    capi=Path('build/font-consumer/font-c'+exe).resolve()
    def run(args,okay=True):
        nonlocal log_number
        p=subprocess.run([str(x) for x in args],capture_output=True,text=True,encoding='utf-8',timeout=180)
        log_number+=1;(base/f'command-{log_number:02d}.log').write_text(p.stdout+'\n'+p.stderr,encoding='utf-8')
        print(p.stdout,end='');print(p.stderr,end='')
        if okay: assert p.returncode==0, (args,p.returncode)
        return p
    def listed(root):return run([probe,'list',root]).stdout.splitlines()
    try:
        for remote,name,git_hash,size in INPUTS:
            url=f'https://raw.githubusercontent.com/adobe-fonts/source-serif/{COMMIT}/{remote}'
            data=urllib.request.urlopen(url,timeout=60).read()
            assert len(data)==size and hashlib.sha1(f'blob {size}\0'.encode()+data).hexdigest()==git_hash, 'fixed material mismatch'
            (materials/name).write_bytes(data)
            results['inputs'].append({'name':name,'url':url,'commit':COMMIT,'git_blob':git_hash,'bytes':size,'sha256':sha(data),'license':'SIL Open Font License 1.1'})
        assert 'SIL OPEN FONT LICENSE Version 1.1' in (materials/'LICENSE.md').read_text(encoding='utf-8')
        collection=TTCollection();collection.fonts=[TTFont(materials/'font.ttf',recalcTimestamp=False),TTFont(materials/'font.ttf',recalcTimestamp=False)]
        collection.save(materials/'font.ttc');collection.close()
        results['inputs'].append({'name':'font.ttc','derived_from':'font.ttf twice; no glyph/name modifications','generator':'fonttools 4.58.0 TTCollection','sha256':sha((materials/'font.ttc').read_bytes()),'bytes':(materials/'font.ttc').stat().st_size,'license':'SIL Open Font License 1.1'})
        (materials/'bad.ttf').write_bytes(b'not a font\0'*20)
        (materials/'truncated.ttf').write_bytes((materials/'font.ttf').read_bytes()[:64])
        c=run([capi]);assert c.stdout.strip()=='installed-c-abi-sdk340';results['checks'].append('installed-c-abi-sdk340')
        suite_root=base/'suite';suite_root.mkdir()
        suite=run([probe,'suite',suite_root,materials]);results['checks'] += [x.removeprefix('CASE ') for x in suite.stdout.splitlines() if x.startswith('CASE ')]
        font_hash=sha((materials/'font.ttf').read_bytes());other_hash=sha((materials/'font.otf').read_bytes())
        for stage in ('copy','validated','file-published','committed'):
            root=base/('crash-'+stage);root.mkdir();run([probe,'import',root,materials/'font.ttf'])
            ready=base/('ready-'+stage)
            with (base/('child-'+stage+'.log')).open('w',encoding='utf-8') as log:
                p=subprocess.Popen([str(probe),'pause',str(root),str(materials/'font.otf'),stage,str(ready)],stdout=log,stderr=log)
                try:
                    until=time.monotonic()+90
                    while not ready.exists():
                        assert p.poll() is None, 'child ended before stage '+stage
                        assert time.monotonic()<until, 'child stage timeout'
                        time.sleep(.05)
                    assert ready.read_text()==stage
                    if stage=='copy':
                        assert run([probe,'status',root]).stdout.strip()=='STATUS 8'
                    p.kill();p.wait(timeout=30);assert p.returncode!=0
                finally:
                    if p.poll() is None:p.kill();p.wait(timeout=30)
            expected=sorted([font_hash,other_hash] if stage=='committed' else [font_hash])
            assert listed(root)==expected
            assert not list(root.glob('.rfl-tmp-*'))
            assert sorted(p.stem for p in root.glob('*.font'))==expected
            if stage!='committed':run([probe,'import',root,materials/'font.otf'])
            assert listed(root)==sorted([font_hash,other_hash])
            results['checks'].append('crash-'+stage+'-recovery')
        results['checks'].append('cross-process-lock-and-kill-release')
        root=base/'write-failure';root.mkdir();run([probe,'import',root,materials/'font.ttf']);before=(root/'manifest.rfl').read_bytes()
        if os.name!='nt':
            run([probe,'write-full',root,materials/'font.otf']);results['checks'].append('posix-real-short-write-preserves-old')
        else:
            kernel=ctypes.WinDLL('kernel32',use_last_error=True)
            kernel.CreateFileW.argtypes=[ctypes.c_wchar_p,ctypes.c_uint32,ctypes.c_uint32,ctypes.c_void_p,ctypes.c_uint32,ctypes.c_uint32,ctypes.c_void_p]
            kernel.CreateFileW.restype=ctypes.c_void_p;kernel.CloseHandle.argtypes=[ctypes.c_void_p]
            handle=kernel.CreateFileW(str(root/'manifest.rfl'),0x80000000,3,None,3,0x80,None)
            assert handle not in (None,ctypes.c_void_p(-1).value), ctypes.get_last_error()
            try:p=run([probe,'import',root,materials/'font.otf'],okay=False);assert p.returncode!=0 and '4:' in p.stderr
            finally:assert kernel.CloseHandle(handle)
            results['checks'].append('windows-locked-manifest-publish-failure-preserves-old')
            junction=base/'junction';run(['cmd','/c','mklink','/J',junction,root]);assert run([probe,'status',junction]).stdout.strip()!='STATUS 0';os.rmdir(junction)
            results['checks'].append('windows-junction-rejected')
            removal=base/'remove-uncertain';removal.mkdir();run([probe,'import',removal,materials/'font.ttf'])
            handle=kernel.CreateFileW(str(removal/(font_hash+'.font')),0x80000000,3,None,3,0x80,None)
            assert handle not in (None,ctypes.c_void_p(-1).value), ctypes.get_last_error()
            try:assert run([probe,'remove',removal,font_hash]).stdout.strip()=='STATUS 15 COUNT 15'
            finally:assert kernel.CloseHandle(handle)
            assert (removal/'manifest.rfl').read_bytes()==b'RFL1\n'
            assert listed(removal)==[] and not list(removal.glob('*.font'))
            results['checks'].append('windows-removal-commit-uncertain-recovery')
        assert (root/'manifest.rfl').read_bytes()==before and listed(root)==[font_hash]
        run([probe,'import',root,materials/'font.otf']);assert listed(root)==sorted([font_hash,other_hash])
        for entry in results['inputs']:assert sha((materials/entry['name']).read_bytes())==entry['sha256']
        assert (suite_root/'main'/f'{font_hash}.font').read_bytes()==(materials/'font.ttf').read_bytes()
        results['checks'].append('recomputed-original-font-hashes')
        # Preserve the exact installed native objects and the executables actually invoked.
        installed=Path('build/font-stage').resolve();shutil.copytree(installed,base/'installed')
        binary=base/'binary';binary.mkdir();shutil.copyfile(probe,binary/probe.name);shutil.copyfile(capi,binary/capi.name)
        linkmap=Path('build/font-consumer/font-probe.map');assert 'reader_font_library' in linkmap.read_text(errors='replace') and 'rfl_import_file' in linkmap.read_text(errors='replace')
        shutil.copyfile(linkmap,binary/'font-probe.map')
        libraries=list((base/'installed').rglob('reader_font_library.lib'))+list((base/'installed').rglob('libreader_font_library.a'))
        assert len(libraries)==1 and libraries[0].stat().st_size>0
        module_source=subprocess.check_output(['git','rev-parse',os.environ['GITHUB_SHA']+':apps/reader/font-library'],text=True).strip()
        results['module_source_tree']=module_source
        for p in sorted((base/'installed').rglob('*'))+sorted(binary.rglob('*'))+sorted(materials.rglob('*')):
            if p.is_file():
                i=identity(p);i['path']=p.relative_to(base).as_posix();results['identities'].append(i)
        results['checks'].append('installed-binary-and-package-identities')
        assert not list(Path('build/font-default-off').rglob('*reader_font_library*'))
        results['checks'].append('default-off-no-library')
        header=Path('build/reading-core/stage/include/exr/text.h').read_bytes()
        frozen=subprocess.check_output(['git','show','9854061be331fe603a1822d9b2b36ee357154927:include/exr/text.h'])
        assert header==frozen
        (base/'sdk-font-header.h').write_bytes(header);results['sdk_font_header_sha256']=sha(header)
        results['checks'].append('frozen-installed-font-header')
        expected=COMMON+(WINDOWS if os.name=='nt' else POSIX)
        assert len(results['checks'])==len(set(results['checks'])) and set(results['checks'])==set(expected), (set(expected)-set(results['checks']),set(results['checks'])-set(expected))
        results['accepted']=True
    except BaseException as error:
        results['failures'].append(repr(error));raise
    finally:
        (base/'result.json').write_text(json.dumps(results,indent=2)+'\n',encoding='utf-8');print(json.dumps(results),flush=True)
if __name__=='__main__':main()
