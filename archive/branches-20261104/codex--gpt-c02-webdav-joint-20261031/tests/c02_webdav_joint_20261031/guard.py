import json,os,subprocess
from common import *
def git(*a):return subprocess.check_output(['git',*a],cwd=ROOT,text=True).strip()
def main():
 actions();head=git('rev-parse','HEAD')
 assert head==os.environ['GITHUB_SHA'] and os.environ['GITHUB_RUN_ATTEMPT']=='1'
 assert os.environ.get('GITHUB_EVENT_NAME')=='push' and os.environ['GITHUB_REF']=='refs/heads/'+M['branch']
 for ref in (M['base'],M['c02'],M['webdav'],M['sdk'],M['c02_audit']):revision(ref)
 git('merge-base','--is-ancestor',M['base'],head)
 expected=set(M['owned'])
 for row in M['imports']:
  actual=git('rev-parse',head+':'+row['path']);assert actual==row['blob'],row['path']
  p=subprocess.run(['git','rev-parse',M['base']+':'+row['path']],cwd=ROOT,capture_output=True,text=True)
  if p.returncode or p.stdout.strip()!=row['blob']:expected.add(row['path'])
  if row['policy']=='exact':assert git('rev-parse',row['source']+':'+row['path'])==actual,row
  else:
   raw=subprocess.check_output(['git','show',M['webdav']+':'+row['path']],cwd=ROOT).decode()
   assert raw.count(row['old_line'])==1
   assert raw.replace(row['old_line'],row['new_line'])==(ROOT/row['path']).read_text()
   assert row['new_line'] in subprocess.check_output(['git','show',M['c02']+':'+row['path']],cwd=ROOT).decode()
 for row in M['runtime_test_blobs']:
  assert row['source'] in (M['c02'],M['c02_audit']) and row['path'].startswith('tests/migration/')
  assert git('rev-parse',row['source']+':'+row['path'])==row['blob'],row['path']
 changed=set(git('diff','--name-only',M['base'],head).splitlines())
 assert changed==expected,dict(extra=sorted(changed-expected),missing=sorted(expected-changed))
 for path in ('src','include','cmake','CMakeLists.txt','bindings','examples/apple','examples/android','examples/reader.c',
              'apps/reader/desktop/windows_catalog.inc','docs/reader-total-progress/catalog.json'):
  git('diff','--exit-code',M['base'],head,'--',path)
 runs=json.loads(subprocess.check_output(['gh','api','repos/NoGod3524/EXReader/actions/runs?branch='+M['branch']+'&per_page=100'],text=True))['workflow_runs']
 owned=[r for r in runs if r.get('path')=='.github/workflows/gpt-c02-webdav-joint-20261031.yml']
 assert len(owned)<=2,[(r['id'],r['head_sha']) for r in owned]
 save(OUT/'admission.json',dict(source=head,imports=M['imports'],changed=sorted(changed),rounds=len(owned),scope=M['scope'],budget=M['budgets']))
 print('JOINT-ADMITTED '+head+' paths='+str(len(changed)),flush=True)
if __name__=='__main__':main()
