"""Bounded SDK verification: real organization receive in GTK and Windows examples."""
import argparse
import importlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
LEGACY=ROOT/'tests/dot_f03_same_source_20261031'
PHASES=['create','delete','restore','member-remove','member-restore','restart']
PATHS=['src','include','cmake','CMakeLists.txt','bindings']
UNFROZEN=['apps/reader/desktop/windows_records_owner.cpp',
 'examples/android/app/src/main/java/org/exreader/host/ReadingParserPolicy.java',
 'examples/apple/HostReadingRecords.swift']

def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT,text=True).strip()
def call(*args):subprocess.run(list(map(str,args)),cwd=ROOT,check=True)
def require(ok,message):
    if not ok:raise AssertionError(message)
def admission():
    require(os.environ.get('GITHUB_ACTIONS')=='true','native execution requires Actions')
    require(os.environ['GITHUB_REF']=='refs/heads/codex/f03-six-host-20261103','dedicated integration branch required')
    source=git('rev-parse','HEAD');require(source==os.environ['GITHUB_SHA'],'checkout differs')
    message=git('log','-1','--format=%B')
    rounds=[n for n in (1,2) if '[F03-SDK-R'+str(n)+']' in message]
    require(len(rounds)==1 and os.environ['GITHUB_RUN_ATTEMPT']=='1','only two explicit rounds, no reruns')
    require(not git('diff','HEAD','--name-only'),'tracked inputs changed during execution')
    call('git','diff','--exit-code','232341db418ecd47c3b98216a3802c5ef565faf1','HEAD','--','docs/reader-total-progress/catalog.json')
    return {k:os.environ[v] for k,v in [('source_sha','GITHUB_SHA'),('run_id','GITHUB_RUN_ID'),('attempt','GITHUB_RUN_ATTEMPT')]}
def sdk_objects():return {p:git('rev-parse','HEAD:'+p) for p in PATHS}
def setup():
    sys.path.insert(0,str(LEGACY));m=importlib.import_module('identity')
    m.identity=admission;m.SCOPE={**m.SCOPE,'active_hosts':['gtk','windows'],'hosts':['gtk','windows']}
    return m
def legacy(name,args):
    setup();sys.argv=[str(LEGACY/(name+'.py')),*args];runpy.run_path(sys.argv[0],run_name='__main__')
def build(host):
    m=setup();stamp=admission()
    if host=='gtk':legacy('build',['--host','gtk','--output','build/f03-gtk-build.json'])
    elif host=='windows':
        b=importlib.import_module('build');b.prepare_hash('windows',os.environ,[])
        call(sys.executable,'tests/windows_sdk342/build.py','--organization-only')
    else:
        os.environ['EXR_APPLE_SDK_VERSION']='3.42.0'
        target='macos' if host=='macos' else 'iphonesimulator'
        call(sys.executable,'tests/apple_sdk342_host/build.py','--target',target)
        prefix=ROOT/'build/raw3-ios-sdk'/target
        call(sys.executable,'tools/build_apple_host.py','--sdk',prefix/'sdk','--product-prefix',prefix/'raw-products',
             '--platform','macos' if host=='macos' else 'simulator','--sdk-version','3.42.0',
             '--selector-bytes-candidate','--wave3','--output',ROOT/'build/f03-sdk-apple'/host)
    m.write_json(ROOT/('build/f03-sdk-'+host+'.json'),{**stamp,'host':host,'sdk_objects':sdk_objects(),
        'sdk_version':'3.42.0','build_completed':True,'build_only':host not in ('gtk','windows'),
        'builder':'tests/windows_sdk342/build.py --organization-only' if host=='windows' else 'installed example builder',
        'unfrozen_blob_ids':{p:git('rev-parse','HEAD:'+p) for p in UNFROZEN}})
def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['admit','legacy','build','receive'])
    p.add_argument('args',nargs=argparse.REMAINDER);a=p.parse_args()
    if a.action=='admit':print(json.dumps(admission()));return
    if a.action=='legacy':legacy(a.args[0],a.args[1:]);return
    if a.action=='build':build(a.args[0]);return
    host=a.args[0]
    if host=='gtk':
        from gtk_receive import receive
        for phase in PHASES:receive(phase)
    else:
        for phase in PHASES:
            author=ROOT/'build/f03-input/f03-author'/phase
            legacy('windows',['--mode','receive','--package','build/windows-sdk342/package/EXReader',
                '--previous',str(author/'wire/state.json'),'--expectations',str(author/'projection.json'),
                '--output',str(ROOT/'build/f03-sdk-receipts/windows'/phase)])
if __name__=='__main__':main()
