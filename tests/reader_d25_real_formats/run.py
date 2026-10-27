"""Actions-only current SDK acceptance; pinned historical inputs remain immutable."""
import hashlib, importlib.util, json, os, platform, re, shutil, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT/'build/d25'
BASE = '2f215f5793a7344d22db350276ba9f8a07abe86f'
F5 = '278d63691a4c73e7aa932d71a40a5938c5427514'
ADAPTER = '8015c576822d5284dedfea17428ecf1a240befd0'
def git(*args): return subprocess.check_output(['git',*args],cwd=ROOT)
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,data):
 p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def identity(): return {'source_sha':os.environ['GITHUB_SHA'],'run_id':os.environ['GITHUB_RUN_ID'],'attempt':os.environ['GITHUB_RUN_ATTEMPT']}
def run(args,label,required=True):
 p=WORK/'logs'/f'{label}.log';p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('wb') as f: result=subprocess.run([str(a) for a in args],cwd=ROOT,stdout=f,stderr=subprocess.STDOUT)
 print(label,result.returncode,flush=True)
 if result.returncode:
  print(p.read_text(encoding='utf-8',errors='replace')[-12000:],flush=True)
  if required: raise RuntimeError(label)
 return result.returncode

def materialize():
 assert os.environ.get('GITHUB_ACTIONS')=='true'
 assert git('rev-parse','HEAD').decode().strip()==identity()['source_sha']
 subprocess.run(['git','merge-base','--is-ancestor',BASE,'HEAD'],check=True)
 changed=git('diff','--name-only',BASE,'HEAD').decode().splitlines()
 subprocess.run(['git','merge-base','--is-ancestor','a7020b07b8515e0d4b8e2693522920e2ec78eb35','HEAD'],check=True)
 integration_changes=git('diff','--name-only','a7020b07b8515e0d4b8e2693522920e2ec78eb35','HEAD').decode().splitlines()
 font_paths = ['examples/android/app/src/main/java/org/exreader/host/MainActivity.java', '.github/workflows/reader-android-font-reader.yml', 'docs/android-font-reader/PLAN.md', 'tests/android_font_reader/README.md', 'tests/android_font_reader/device.sh', 'tests/android_font_reader/guard.py', 'tests/android_font_reader/java/org/exreader/host/FontReaderUiTest.java', 'tests/android_font_reader/retained_report.py', 'tests/android_font_reader/run_ui.py', 'tests/android_font_reader/test.init.gradle']
 subprocess.run(['git','diff','--exit-code','1550aad19234ee5f8ffad901a53583e69d02af31','HEAD','--',*font_paths],check=True)
 assert all(p in font_paths or p in ['.github/workflows/sdk-txt-anchor-resolve.yml', 'apps/reader/desktop/windows_records.inc', 'apps/reader/desktop/windows_records_owner.cpp', 'include/exr/formats.h', 'src/formats.c', 'tests/txt_anchor_resolve/CMakeLists.txt', 'tests/txt_anchor_resolve/check.c', '.github/workflows/reader-d21-apple-receive.yml', '.github/workflows/reader-d22-android-receive.yml', '.github/workflows/reader-d23-relay.yml', '.github/workflows/reader-d24-apple-large-type.yml', '.github/workflows/reader-d25-real-formats.yml', '.github/workflows/reader-d26-accessibility.yml', 'tests/reader_d21_apple_receive/guard.py', 'tests/reader_android_receive_d22/guard.py', 'tests/reader_d25_real_formats/run.py', 'examples/reader.c', 'apps/reader/desktop/windows_search.inc', 'apps/reader/desktop/windows_search_types.h', 'apps/reader/desktop/windows_txt_search.inc', 'apps/reader/desktop/windows_wave3.inc', 'apps/reader/original-export/include/reader_original_export.h', 'apps/reader/original-export/src/original_export.cpp', 'tests/reader_txt_mixed_export/CMakeLists.txt', 'tests/reader_txt_mixed_export/mixed.c', '.github/workflows/reader-txt-mixed-export.yml', 'tests/windows_host/txt/check_progress.py', 'tests/reader_wave3_c09/build.py', 'tests/reader_d26_accessibility/current_expectations.py', 'tests/reader_d26_accessibility/g13_current.py', 'docs/READER-WINDOWS-TXT-PROGRESS.md', 'tests/reader_d26_accessibility/audit_current.py', 'tests/reader_d26_accessibility/tools_current.py', 'tests/reader_d26_accessibility/account_status.py', 'docs/reader-total-progress/catalog.json', 'docs/reader-total-progress/README.md', 'docs/reader-total-progress/android-jump-d22.md', 'docs/reader-total-progress/android-annotations-d22.md', '.github/workflows/windows-wave3-txt-progress.yml'] for p in integration_changes),integration_changes
 assert not git('diff','--name-only','a7020b07b8515e0d4b8e2693522920e2ec78eb35','HEAD','--','src','include',':(exclude)src/formats.c',':(exclude)include/exr/formats.h').strip()
 for reference,paths in [('9727ca1624ee59e561fd6aad7a22bb85a0fd2632',['src/formats.c','include/exr/formats.h']),
                         ('e09b25aa02b03297dc8a7f1f6eb32c092e11d410',['apps/reader/desktop/windows_records.inc','apps/reader/desktop/windows_records_owner.cpp'])]:
  assert not git('diff','--name-only',reference,'HEAD','--',*paths).strip(),paths
 for p in ('bindings','cmake','CMakeLists.txt','tests/fixtures'):
  assert not git('diff','--name-only','a7020b07b8515e0d4b8e2693522920e2ec78eb35','HEAD','--',p).strip(),p
 sources={}
 for label,commit,prefix in [('f5',F5,'tests/reader_real_corpus/'),('adapter',ADAPTER,'tests/reader_format_candidate/')]:
  for path in git('ls-tree','-r','--name-only',commit,'--',prefix).decode().splitlines():
   dest=WORK/'vendor'/label/path[len(prefix):];dest.parent.mkdir(parents=True,exist_ok=True)
   dest.write_bytes(git('show',commit+':'+path));sources[path]={'commit':commit,'sha256':sha(dest)}
 assert git('rev-parse','HEAD:src/rtf.c').decode().strip()=='5475935199f9a0e0fbbdd17a3a74f2ef3b2952d9'
 assert git('rev-parse','HEAD:src/cbz.c').decode().strip()=='8be705007cec11d4f586d0b87b2a001ea87b4de2'
 write(WORK/'source-identity.json',{**identity(),'base':BASE,'dependencies':sources,'changed_paths':changed})
 return sources

def configure(source,build,extra):
 run(['cmake','-S',source,'-B',build,'-DCMAKE_BUILD_TYPE=Release',*extra],build.name+'-configure')
 run(['cmake','--build',build,'--config','Release','--parallel','4'],build.name+'-build')
def exe(build,name):
 for p in (build/'bin'/name,build/'bin'/(name+'.exe'),build/name,build/'Release'/(name+'.exe')):
  if p.exists(): return p.resolve()
 raise RuntimeError('missing executable '+name)
def producer():
 materialize()
 f5dir=WORK/'vendor/f5';adapter=WORK/'vendor/adapter'
 spec=importlib.util.spec_from_file_location('f5',f5dir/'run_acceptance.py');f5=importlib.util.module_from_spec(spec);spec.loader.exec_module(f5)
 v1=json.loads((f5dir/'manifest.json').read_bytes());v2=json.loads((adapter/'manifest-v2.json').read_bytes())
 assert sha(f5dir/'manifest.json')=='be300d9a54329ab227ac7060bc39e0117de722ae3c60d6c0d998418eba994bf6'
 # Reuse the existing separately versioned correction, never change the original declaration.
 expected=json.loads(json.dumps(v1));expected['dataset_id']='reader-real-corpus-v2'
 next(r for r in expected['files'] if r['id']=='rtf-crowley-policy')['query']='EH123 Rhetoric and Composition I'
 assert v2==expected
 corpus=WORK/'corpus';corpus.mkdir(parents=True,exist_ok=True)
 downloads=f5.download_manifest(v1,corpus,'collect');write(corpus/'downloads.json',downloads)
 assert len(downloads)==18 and all(r['status']=='verified' for r in downloads),downloads
 write(corpus/'license-evidence.json',f5.collect_license_evidence(v1,corpus))
 sdk=WORK/'sdk';stage=WORK/'installed'
 configure(ROOT,sdk,['-DEXR_BUILD_JNI=OFF','-DEXR_ENABLE_AAC=OFF','-DEXR_BUILD_SHARED_COMPAT=ON'])
 native=run(['ctest','--test-dir',sdk,'-C','Release','--output-on-failure','--output-junit',WORK/'logs/native.xml'],'native',False)
 run(['cmake','--install',sdk,'--config','Release','--prefix',stage],'install')
 configure(f5dir,WORK/'original',['-DEXR_SDK='+str(stage)])
 configure(adapter,WORK/'adapter',['-DEXR_SDK='+str(stage),'-DFORMAT_ORIGINAL_CONSUMER='+str(f5dir/'consumer.c')])
 run([sys.executable,adapter/'test_argv.py',WORK/'adapter/bin',WORK/'argv'],'argv')
 font=Path('C:/Windows/Fonts/arial.ttf') if os.name=='nt' else Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
 library=stage/('bin/exreader.dll' if os.name=='nt' else 'lib/libexreader.so')
 original=exe(WORK/'original','exreader-real-corpus-consumer');wrapped=exe(WORK/'adapter','format-f5-consumer')
 if os.name=='nt':
  for dll in stage.rglob('*.dll'): shutil.copy2(dll,original.parent/dll.name)
 panels={}
 for label,manifest,consumer,iswrapped in [('original-v1',v1,original,False),('utf8-v1',v1,wrapped,True),('existing-v2',v2,wrapped,True)]:
  out=WORK/'panels'/label;out.mkdir(parents=True,exist_ok=True);records=[]
  for entry in manifest['files']:
   source=corpus/entry['path'];assert source.stat().st_size==entry['source']['bytes'] and sha(source)==entry['source']['sha256']
   result=f5.run_one(dict(entry,path=str(source.resolve())),out,consumer,font,600)
   write(out/'results'/entry['id']/'process.json',result)
   if iswrapped:
    assert re.findall(r'^FORMAT_QUERY_UTF8_HEX ([0-9a-f]*)$',result['stderr'],re.M)==[entry.get('query','').encode().hex()]
    loaded=re.findall(r'^FORMAT_LOADED_SDK (.+)$',result['stderr'],re.M);assert len(loaded)==1 and sha(loaded[0].strip())==sha(library)
   result['input_sha256']=sha(source);records.append(result);print(label,entry['id'],result['status'],flush=True)
  panels[label]={'accepted':all(r['status']=='accepted' for r in records),'files':records,'consumer_sha256':sha(consumer)}
  write(out/'summary.json',{**identity(),**panels[label]})
 summary={**identity(),'platform':platform.system(),'native_exit':native,'manifest_v1_sha256':sha(f5dir/'manifest.json'),'manifest_v2_sha256':sha(adapter/'manifest-v2.json'),'sdk_sha256':sha(library),'panels':panels,'legacy_1710_count':0,'render_fidelity_accepted':False,'complete_product':False}
 write(WORK/'summary.json',summary)
 assert native==0
 assert [r['id'] for r in panels['utf8-v1']['files'] if r['status']!='accepted']==['rtf-crowley-policy']
 assert panels['existing-v2']['accepted'],'Existing v2 has compatibility gaps; see unchanged per-file results'

def aggregate():
 rows=[json.loads(p.read_bytes()) for p in (ROOT/'build/results').glob('*/summary.json')]
 assert len(rows)==2 and {r['platform'] for r in rows}=={'Windows','Linux'}
 for r in rows:
  assert all(r[k]==v for k,v in identity().items())
  assert r['native_exit']==0 and r['panels']['existing-v2']['accepted']
  assert len(r['panels']['existing-v2']['files'])==18
  assert [x['id'] for x in r['panels']['utf8-v1']['files'] if x['status']!='accepted']==['rtf-crowley-policy']
 for key in ('manifest_v1_sha256','manifest_v2_sha256'):
  assert rows[0][key]==rows[1][key]
 assert [(r['id'],r['input_sha256']) for r in rows[0]['panels']['existing-v2']['files']]==[(r['id'],r['input_sha256']) for r in rows[1]['panels']['existing-v2']['files']]
 write(ROOT/'build/aggregate.json',{**identity(),'platforms':[r['platform'] for r in rows],'current_sdk_existing_v2_18_files_accepted':True,'original_v1_accepted':False,'original_v1_gap':'rtf-crowley-policy query mismatch retained','legacy_1710_count':0,'render_fidelity_accepted':False})
 print('Same-source Windows/Linux existing v2 accepted; original v1 query failure retained.')
if __name__=='__main__':
 assert os.environ.get('GITHUB_ACTIONS')=='true'
 if sys.argv[1]=='aggregate':aggregate()
 else:producer()
