"""Actions-only, package-local admission. Existing Android130 guards remain sealed."""
import hashlib,json,os,subprocess,sys
from pathlib import Path
assert os.environ.get('GITHUB_ACTIONS')=='true'
BASE='9f6bc74b21b9cbd694b8c421d7097bb0c88bdef3'
ORIGINAL='9fb36c2aae690d90269df36850516cd689244962'
WORKFLOW='.github/workflows/reader-android-history-compat.yml'
ALLOWED={'examples/android/app/src/main/java/org/exreader/host/BookStore.java',
 'examples/android/app/src/androidTest/java/org/exreader/host/HistoryCompatTest.java',WORKFLOW,
 'tests/reader_hosts_341/android_candidate.py','tests/reader_hosts_341/android_current.py',
 'tests/reader_windows_341/candidate.py'}
source=os.environ['GITHUB_SHA']
assert subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()==source
subprocess.check_call(['git','merge-base','--is-ancestor',BASE,source])
changed=subprocess.check_output(['git','diff','--name-only',BASE,source],text=True).splitlines()
assert changed and all(p in ALLOWED or p.startswith('tests/reader_android_history_compat/') or p.startswith('docs/evidence/android-history-compat/') for p in changed),changed
sys.path.insert(0,'tests/reader_hosts_341')
import android_candidate
identity={key:os.environ[value] for key,value in [('source_sha','GITHUB_SHA'),('run_id','GITHUB_RUN_ID'),('attempt','GITHUB_RUN_ATTEMPT')]}
# Keep the prior Android test trees and their frozen inputs byte-identical.
subprocess.check_call(['git','diff','--exit-code',ORIGINAL,source,'--', *['tests/'+name for name in android_candidate.TEST_TREES]])
for p in android_candidate.FROZEN_TESTS:
 assert subprocess.check_output(['git','show',source+':'+p])==subprocess.check_output(['git','show',ORIGINAL+':'+p])
for p in ('tests/reader_hosts_341/android_candidate.py','tests/reader_hosts_341/android_current.py',
          'tests/reader_windows_341/candidate.py'):
 assert subprocess.check_output(['git','show',source+':'+p])==subprocess.check_output(['git','show',ORIGINAL+':'+p])
subprocess.check_call(['git','diff','--exit-code','5b7a34ee4f1ce38cf3bcd7cf0220575f4ecf7da9',source,'--',
                       'src','include','cmake','CMakeLists.txt','bindings','tests/fixtures'])
report=dict(**identity,accepted=True,base=BASE,changed=changed,original_failure_run=40630678650,
 old_tests_unchanged=True,SDK_unchanged=True,physical_device=False)
out=Path('build/android-page-theme');out.mkdir(parents=True,exist_ok=True)
(out/'common-source-guard.json').write_text(json.dumps(report,indent=2)+'\n')
if len(sys.argv)>1 and sys.argv[1]=='prepare':
 entries=[]
 for p in android_candidate.FROZEN_TESTS:
  data=subprocess.check_output(['git','show',android_candidate.THEME+':'+p]);Path(p).write_bytes(data)
  entries.append(dict(path=p,source=android_candidate.THEME,sha256=hashlib.sha256(data).hexdigest()))
 target=out/'candidate-source-evidence';target.mkdir(parents=True,exist_ok=True)
 (target/'frozen-tests.json').write_text(json.dumps(entries,indent=2)+'\n')
print(json.dumps(report),flush=True)
