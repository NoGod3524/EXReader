#!/usr/bin/env python3
"""Compiler-produced minimal fixtures, not EXReader product deployments."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('f11', ROOT/'tools/reader_f11_mobile_identity_20261031/verify.py')
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
SOURCE = os.environ['GITHUB_SHA']
SDK = '3.42.0'
def sha(b): return hashlib.sha256(b).hexdigest()
def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    output = ROOT/'build/f11'
    output.mkdir(parents=True, exist_ok=True)
    records = []
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        apple = work/'apple'
        (apple/'EXReader.app/Frameworks').mkdir(parents=True)
        src = work/'minimal.c'
        src.write_text('int main(void) { return 0; }\n')
        sdk = subprocess.check_output(['xcrun','--sdk','iphonesimulator','--show-sdk-path'],text=True).strip()
        common = ['xcrun','clang','-target','arm64-apple-ios15.0-simulator','-isysroot',sdk]
        subprocess.run(common+[str(src),'-o',str(apple/'EXReader.app/EXReader')],check=True)
        subprocess.run(common+['-dynamiclib',str(src),'-o',str(apple/'EXReader.app/Frameworks/libexreader.dylib')],check=True)
        def apple_producer(folder):
            return {'source_sha':SOURCE,'sdk_version':SDK,'platform':'simulator',
                    'target':'arm64-apple-ios15.0-simulator',
                    'files':{str(p.relative_to(folder/'EXReader.app')):sha(p.read_bytes())
                             for p in (folder/'EXReader.app').rglob('*') if p.is_file()}}
        (apple/'build.json').write_text(json.dumps(apple_producer(apple)))
        android = work/'android'
        (android/'artifacts').mkdir(parents=True)
        with zipfile.ZipFile(android/'artifacts/app-debug.apk','w') as z:
            for lib in ('product','','jni','host'):
                z.writestr('lib/x86_64/libexreader'+('_'+lib if lib else '')+'.so',
                           (ROOT/'build/f11-elf/libfixture.so').read_bytes())
        (android/'build.json').write_text(json.dumps({'source_sha':SOURCE,'sdk_version':SDK,'abi':'x86_64',
            'artifacts':{'app-debug.apk':{'sha256':sha((android/'artifacts/app-debug.apk').read_bytes())}}}))
        def seal(folder,target):
            files={str(p.relative_to(folder)):{'sha256':sha(p.read_bytes()),'bytes':p.stat().st_size}
                   for p in folder.rglob('*') if p.is_file()}
            manifest={'target':target,'source_sha':SOURCE,'sdk_version':SDK,'files':files}
            archive=work/'resealed.zip'
            with zipfile.ZipFile(archive,'w') as z:
                for name in files: z.write(folder/name,name)
                z.writestr('manifest.json',json.dumps(manifest))
            manifest['archive']={'sha256':sha(archive.read_bytes()),'bytes':archive.stat().st_size}
            return manifest
        def case(name,target,mutation=None,expected=None):
            folder=work/name
            shutil.copytree(android if target=='android' else apple,folder)
            producer=json.loads((folder/'build.json').read_text())
            if mutation: mutation(folder,producer)
            if producer is not None and (folder/'build.json').exists():
                (folder/'build.json').write_text(json.dumps(producer))
            manifest=seal(folder,target) # negatives are rehashed/repacked, not trivial stale outer hashes
            if name == 'undeclared-dylib':
                shutil.copyfile(folder/'EXReader.app/Frameworks/libexreader.dylib',
                                folder/'EXReader.app/Frameworks/extra.dylib')
            if name == 'symlink-file':
                (folder/'EXReader.app/linked').symlink_to('EXReader')
            try:
                result=gate.verify(folder,manifest,target,SOURCE,SDK)
                assert expected is None, name+' unexpectedly accepted'
                records.append({'name':name,'accepted':True,'binary':result['observations']})
            except ValueError as e:
                assert expected == str(e), (name,expected,str(e))
                records.append({'name':name,'accepted':False,'reason':str(e)})
        for target in ('android','iphone','ipad'): case('positive-'+target,target)
        case('wrong-source','iphone',lambda f,p:p.update(source_sha='0'*40),'producer-source')
        case('wrong-sdk','iphone',lambda f,p:p.update(sdk_version='3.40.0'),'producer-sdk')
        case('missing-producer','iphone',lambda f,p:(f/'build.json').unlink(),'missing-producer')
        case('missing-file','iphone',lambda f,p:(f/'EXReader.app/EXReader').unlink(),'producer-inventory')
        case('producer-hash','iphone',lambda f,p:p['files'].update(EXReader='0'*64),'producer-hash')
        case('device-platform','iphone',lambda f,p:p.update(platform='iphoneos'),'producer-platform')
        case('wrong-target','iphone',lambda f,p:p.update(target='arm64-apple-ios15.0'),'producer-target')
        def mutate_macho(folder,p,relative,field,value):
            path=folder/'EXReader.app'/relative
            b=bytearray(path.read_bytes())
            if field=='cpu': struct.pack_into('<I',b,4,value)
            elif field=='kind': struct.pack_into('<I',b,12,value)
            else:
                pos=32
                for _ in range(struct.unpack_from('<I',b,16)[0]):
                    cmd,size=struct.unpack_from('<II',b,pos)
                    if cmd==0x32:
                        struct.pack_into('<I',b,pos+8,value)
                        break
                    pos+=size
                else: raise AssertionError('compiler did not emit LC_BUILD_VERSION')
            path.write_bytes(b)
            p['files'][relative]=sha(b) # also reseal producer: binary parser must catch this
        case('binary-device','iphone',lambda f,p:mutate_macho(f,p,'EXReader','platform',2),'macho-platform')
        case('binary-cpu','iphone',lambda f,p:mutate_macho(f,p,'EXReader','cpu',0x1000007),'macho-cpu')
        case('sdk-device','iphone',lambda f,p:mutate_macho(f,p,'Frameworks/libexreader.dylib','platform',2),'macho-platform')
        case('android-abi','android',lambda f,p:p.update(abi='arm64-v8a'),'producer-abi')
        def wrong_elf(f,p):
            path=f/'artifacts/app-debug.apk'
            with zipfile.ZipFile(path) as z: entries={n:z.read(n) for n in z.namelist()}
            n='lib/x86_64/libexreader.so'
            b=bytearray(entries[n]); struct.pack_into('<H',b,18,183); entries[n]=b
            with zipfile.ZipFile(path,'w') as z:
                for n,b in entries.items(): z.writestr(n,b)
            p['artifacts']['app-debug.apk']['sha256']=sha(path.read_bytes())
        case('android-machine','android',wrong_elf,'elf-machine')
        case('undeclared-dylib','iphone',expected='actual-inventory')
        case('symlink-file','iphone',expected='symlink')
        case('entry-kind','iphone',lambda f,p:mutate_macho(f,p,'EXReader','kind',6),'macho-kind')
        case('dylib-kind','iphone',lambda f,p:mutate_macho(f,p,'Frameworks/libexreader.dylib','kind',2),'macho-kind')
    assert len(records)==19
    assert sum(r['accepted'] for r in records)==3
    receipt={'source_sha':SOURCE,'run_id':os.environ['GITHUB_RUN_ID'],
             'attempt':os.environ['GITHUB_RUN_ATTEMPT'],'positive':3,'negative':16,
             'fixture_scope':'compiler-built minimal binaries, not deployed product',
             'cases':records}
    (output/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt))
if __name__=='__main__': main()
