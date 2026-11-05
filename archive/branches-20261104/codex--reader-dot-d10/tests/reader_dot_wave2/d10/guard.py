"""Actions-only D10 exact base, protected tree and new-path guard."""
import os, subprocess
assert os.environ.get('GITHUB_ACTIONS') == 'true'
BASE='0889f7d1e9a537c6c1b05456547e016b26e1cd85'
SDK='edddc463c06ed5731195cdb8f06b2df6dff7699e'
def git(*args): return subprocess.check_output(['git',*args],text=True).strip()
assert git('rev-parse','HEAD') == os.environ['GITHUB_SHA']
subprocess.run(['git','merge-base','--is-ancestor',BASE,'HEAD'],check=True)
for line in git('diff','--name-status',BASE,'HEAD').splitlines():
    status,path=line.split('\t')
    assert status == 'A', ('only new files',line)
    assert path.startswith(('tests/reader_dot_wave2/d10/','docs/reader-dot-wave2/d10/')) or path in ('.github/workflows/reader-dot-d10.yml','HANDOFF-RESULT-D10.md'),path
for path in ('src','include','cmake','CMakeLists.txt','bindings'):
    assert git('rev-parse',f'HEAD:{path}') == git('rev-parse',f'{SDK}:{path}'),path
print('D10 protected trees and new-path guard passed')
