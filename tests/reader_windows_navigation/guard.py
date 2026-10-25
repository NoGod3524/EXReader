"""Cloud-only source ownership and unchanged installed SDK/module identities."""
import os
from pathlib import Path
import subprocess

BASE='3917897e'
SDK='9854061be331fe603a1822d9b2b36ee357154927'
ALLOWED=('examples/reader.c','apps/reader/windows-account/CMakeLists.txt',
 'apps/reader/desktop/windows_search.inc','apps/reader/desktop/windows_source.inc',
 'apps/reader/desktop/windows_navigation.inc','apps/reader/desktop/windows_navigation_types.h',
 'tests/windows_host/worker_review/hooks.h','tests/reader_windows_search/check_ui.py',
 'tests/reader_hosts_integration/guard.py','tests/reader_windows_navigation/',
 '.github/workflows/reader-windows-navigation-ui.yml',
 'docs/READER-WINDOWS-NAVIGATION.md','docs/validation/reader-windows-navigation.json')

def main():
 assert os.environ.get('GITHUB_ACTIONS')=='true'
 source=os.environ['GITHUB_SHA']
 assert subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()==source
 subprocess.run(['git','merge-base','--is-ancestor',BASE,source],check=True)
 subprocess.run(['git','diff','--exit-code',SDK,source,'--','src','include','cmake','CMakeLists.txt',
   'bindings','tests/fixtures','.github/workflows/native.yml','.github/workflows/reliability.yml'],check=True)
 subprocess.run(['git','diff','--exit-code',BASE,source,'--','apps/reader/store/001_catalog.sql',
   'apps/reader/search','apps/reader/navigation','apps/reader/reading-state','extras'],check=True)
 for path in subprocess.check_output(['git','diff','--name-only',BASE,source],text=True).splitlines():
  assert any(path.startswith(p) if p.endswith('/') else path==p for p in ALLOWED),path
 print('Windows navigation candidate ownership authenticated:',source,flush=True)

if __name__=='__main__':main()
