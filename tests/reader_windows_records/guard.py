"""Actions-only frozen SDK/module and single host-owner guard."""
import os
import subprocess

BASE='f0c272c87b2402979292d0cd973d4f5e7a9f62fd'
SDK='9854061be331fe603a1822d9b2b36ee357154927'
ALLOWED=('examples/reader.c','apps/reader/windows-account/CMakeLists.txt',
 'apps/reader/desktop/windows_records','tests/reader_windows_records/',
 'tests/windows_host/worker_review/hooks.h','.github/workflows/reader-windows-reading-records.yml',
 'docs/READER-WINDOWS-READING-RECORDS.md','docs/validation/reader-windows-reading-records.json')

def main():
 assert os.environ.get('GITHUB_ACTIONS')=='true'
 source=os.environ['GITHUB_SHA']
 assert subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()==source
 subprocess.run(['git','merge-base','--is-ancestor',BASE,source],check=True)
 subprocess.run(['git','diff','--exit-code',SDK,source,'--','src','include','cmake','CMakeLists.txt',
  'bindings','tests/fixtures','.github/workflows/native.yml','.github/workflows/reliability.yml'],check=True)
 subprocess.run(['git','diff','--exit-code',BASE,source,'--','apps/reader/store','apps/reader/revisions',
  'apps/reader/commands','apps/reader/reading-commands','apps/reader/annotation-view',
  'apps/reader/reading-state','apps/reader/search','apps/reader/navigation','extras'],check=True)
 for path in subprocess.check_output(['git','diff','--name-only',BASE,source],text=True).splitlines():
  assert any(path.startswith(p) for p in ALLOWED),path
 print('Windows records host ownership authenticated:',source,flush=True)

if __name__=='__main__':main()
