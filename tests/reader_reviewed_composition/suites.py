# SPDX-License-Identifier: MIT
"""Execute unchanged upstream consumers/judges with one installed prefix.
No expected failure is rewritten; independent suites continue after a failure
so the artifact retains all available results instead of hiding later suites.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
assert os.environ.get('GITHUB_ACTIONS')=='true','Actions only'
p=argparse.ArgumentParser();p.add_argument('--prefix',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
root=Path.cwd();prefix=Path(a.prefix).resolve().as_posix();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
build=root/'build/reviewed-original-build';build.mkdir(parents=True,exist_ok=True)
exe='.exe' if os.name=='nt' else '';platform=os.environ['RUNNER_OS'];records=[]
current='';binaries={}
def run(args,log):
 args=[str(x) for x in args];print('$ '+' '.join(args),flush=True)
 proc=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace')
 (out/(current+'-'+log+'.log')).write_text(proc.stdout,encoding='utf-8');print(proc.stdout[-7000:],flush=True)
 if proc.returncode:raise RuntimeError('command failed '+str(proc.returncode)+': '+' '.join(args))
def configure(name,source,options=()):
 path=build/name
 run(['cmake','-S',root/source,'-B',path,'-G','Ninja','-DCMAKE_BUILD_TYPE=Release','-DCMAKE_PREFIX_PATH='+prefix,'-DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded$<$<CONFIG:Debug>:Debug>',*options],name+'-configure')
 run(['cmake','--build',path,'--parallel','4','--verbose'],name+'-build')
 return path
def binary(directory,name):
 path=directory/(name+exe);binaries[name]=str(path);return path
def judge(path,*args):run([sys.executable,root/path,*args],'judge')
def suite(name,action):
 global current
 current=name;record={'name':name,'accepted':False,'binaries':{}}
 before=set(binaries)
 try:action();record['accepted']=True
 except Exception as e:record['failure']=str(e);print(str(e),flush=True)
 record['binaries']={n:p for n,p in binaries.items() if n not in before};records.append(record)
 (out/'suites.json').write_text(json.dumps(dict(source_sha=os.environ['GITHUB_SHA'],run_id=os.environ['GITHUB_RUN_ID'],attempt=os.environ['GITHUB_RUN_ATTEMPT'],accepted=all(r['accepted'] for r in records),suites=records),indent=2)+'\n')
def cloud():
 b=configure('cloud','tests/reader_reviewed_composition/cloud_consumer')
 judge('tests/reader_webdav_import/check_cloud_import.py','--probe',binary(b,'cloud-probe'),'--cxx',binary(b,'cloud-cpp-consumer'),'--review-probe',binary(b,'cloud-review-probe'),'--fixtures','tests/fixtures','--module-prefix',prefix,'--output',out/'cloud')
def bulk():
 b=configure('bulk','tests/reader_bulk_organization/consumer')
 judge('tests/reader_bulk_organization/check_bulk.py','--probe',binary(b,'bulk-probe'),'--c-consumer',binary(b,'bulk-c-consumer'),'--link-map',b/'bulk-link.map','--output',out/'bulk')
def link():
 b=configure('link','tests/reader_external_link_policy/consumer',['-DEXR_LINK_POLICY_SOURCE='+(root/'apps/reader/link-policy/src').as_posix(),'-DEXR_LINK_POLICY_INCLUDE='+(root/'apps/reader/link-policy/include').as_posix()])
 control=next(p for p in b.glob('*link-unsafe-control*') if p.suffix in ('.a','.lib'))
 judge('tests/reader_external_link_policy/check_link_policy.py','--probe',binary(b,'link-probe'),'--cpp',binary(b,'link-cpp-consumer'),'--worker',binary(b,'link-worker'),'--sdk',binary(b,'link-sdk-consumer'),'--control-lib',control,'--prefix',prefix,'--epub','tests/fixtures/navigation-epub3.epub','--source','apps/reader/link-policy/src/policy.c','--source-header','apps/reader/link-policy/include/reader_link_policy.h','--installed-header',Path(prefix)/'include/reader_link_policy.h','--output',out/'link','--platform',platform)
def history():
 b=configure('history','tests/reader_jump_history/consumer')
 run([sys.executable,'tests/reader_jump_history/make_fixtures.py',build/'history-fixtures'],'fixtures')
 judge('tests/reader_jump_history/check_jump_history.py','--probe',binary(b,'jump-history-probe'),'--c-consumer',binary(b,'jump-history-c-consumer'),'--fixtures',build/'history-fixtures','--font','tests/fixtures/fonts/primary.ttf','--installed',prefix,'--platform',platform,'--output',out/'history')
def keyboard():
 b=configure('keyboard','tests/reader_keyboard_actions/consumer');n=configure('keyboard-native','tests/reader_keyboard_actions/probes')
 judge('tests/reader_keyboard_actions/check_keyboard.py','--c',binary(b,'keyboard-c-consumer'),'--cpp',binary(b,'keyboard-cpp-consumer'),'--probe',binary(n,'keyboard-probe'),'--output',out/'keyboard','--platform',platform,'--stage',prefix,'--build-log',out/'keyboard-keyboard-build.log','--cache',b/'CMakeCache.txt')
def information():
 b=configure('information','tests/reader_book_information/consumer')
 run([sys.executable,'tests/reader_book_information/make_fixtures.py','--out',build/'information-fixtures'],'fixtures')
 judge('tests/reader_book_information/check_book_information.py','--probe',binary(b,'book-info-probe'),'--compare',binary(b,'book-info-compare'),'--fixtures',build/'information-fixtures','--work',out/'work/information','--output',out/'information','--platform',platform)
def status():
 rev=configure('revisions','tests/reader_revisions/consumer');b=configure('status','tests/reader_sync_status_view/consumer')
 judge('tests/reader_sync_status_view/check_status_view.py','--consumer',binary(b,'status-view-consumer'),'--c-consumer',binary(b,'status-view-c-consumer'),'--revision-consumer',binary(rev,'revision-consumer'),'--output',out/'status')
def profiles():
 b=configure('profiles','tests/reader_account_profiles/consumer',['-DEXR_ACCOUNT_PROFILES_SOURCE='+(root/'apps/reader/account-profiles/src').as_posix(),'-DEXR_ACCOUNT_PROFILES_INCLUDE='+(root/'apps/reader/account-profiles/include').as_posix()])
 judge('tests/reader_account_profiles/check_account_profiles.py','--probe',binary(b,'profiles-probe'),'--session',binary(b,'profiles-session-consumer'),'--worker',binary(b,'profiles-worker'),'--prefix',prefix,'--work',out/'work/profiles','--output',out/'profiles','--platform',platform)
 if platform=='Linux':run(['bash','tests/reader_reviewed_composition/sanitizer.sh'],'sanitizer')
for name,action in [('cloud',cloud),('bulk',bulk),('link',link),('history',history),('keyboard',keyboard),('information',information),('status',status),('profiles',profiles)]:suite(name,action)
raise SystemExit(0 if len(records)==8 and all(r['accepted'] for r in records) else 1)
