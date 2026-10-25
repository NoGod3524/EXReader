"""Actions-only T01 source, merge dependency and frozen-tree ownership gate."""
import os
import subprocess

BASE='e4356a6e13223469fdf3b2f3d5171a6e99ab10a6'
SDK='9854061be331fe603a1822d9b2b36ee357154927'
DEPENDENCIES={
 '0d07d23bf53cd288de7a0af152d48553c18be241':('apps/reader/cloud-import/','tests/reader_webdav_import/','.github/workflows/reader-webdav-import.yml','docs/READER-WEBDAV-IMPORT.md','docs/validation/reader-webdav-import.json'),
 '757249aaed9a1dc6be981354f6af97e813233f04':('apps/reader/bulk-organization/','tests/reader_bulk_organization/','.github/workflows/reader-bulk-organization.yml','docs/READER-BULK-ORGANIZATION.md','docs/validation/reader-bulk-organization.json')}
ALLOWED=('examples/reader.c','apps/reader/windows-account/','apps/reader/desktop/windows_',
 'tests/reader_windows_import_organize/','.github/workflows/reader-windows-import-organize.yml',
 'docs/READER-WINDOWS-IMPORT-ORGANIZE.md','docs/validation/reader-windows-import-organize.json')

def main():
 assert os.environ.get('GITHUB_ACTIONS')=='true'
 source=os.environ['GITHUB_SHA']
 assert subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()==source
 for ancestor in (BASE,*DEPENDENCIES):subprocess.run(['git','merge-base','--is-ancestor',ancestor,source],check=True)
 subprocess.run(['git','diff','--exit-code',SDK,source,'--','src','include','cmake','CMakeLists.txt','bindings','tests/fixtures','.github/workflows/native.yml','.github/workflows/reliability.yml'],check=True)
 for sha,paths in DEPENDENCIES.items():subprocess.run(['git','diff','--exit-code',sha,source,'--',*paths],check=True)
 immutable=('apps/reader/store','apps/reader/desktop/CMakeLists.txt','examples/android','examples/linux','tests/windows_host','tests/reader_windows_account','tests/reader_windows_search','tests/reader_windows_navigation','tests/reader_windows_records')
 subprocess.run(['git','diff','--exit-code',BASE,source,'--',*immutable],check=True)
 dependency_paths=tuple(p for paths in DEPENDENCIES.values() for p in paths)
 for path in subprocess.check_output(['git','diff','--name-only',BASE,source],text=True).splitlines():
  assert any(path.startswith(p) for p in ALLOWED+dependency_paths),path
 print('T01 exact source, fixed merge ancestry, unchanged dependencies, frozen trees and ownership authenticated:',source,flush=True)

if __name__=='__main__':main()
