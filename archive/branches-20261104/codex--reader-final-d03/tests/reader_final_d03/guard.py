"""Actions-only source identity and exclusive-path guard."""
import os, subprocess
from pathlib import Path
BASE='0889f7d1e9a537c6c1b05456547e016b26e1cd85'
TARGET='9fc407a5cce5a0bfe644a60bd8dc29f84dea6d0e'
SDK='edddc463c06ed5731195cdb8f06b2df6dff7699e'
def git(*a): return subprocess.check_output(['git',*a],text=True).strip()
assert os.environ['GITHUB_ACTIONS']=='true'
assert git('rev-parse','HEAD')==os.environ['GITHUB_SHA']
subprocess.run(['git','merge-base','--is-ancestor',BASE,'HEAD'],check=True)
for p in git('diff','--name-only',BASE,'HEAD').splitlines():
    assert p.startswith(('tests/reader_final_d03/','docs/reader-final-d03/')) or p in ('.github/workflows/reader-final-d03.yml','docs/validation/reader-final-d03.json','HANDOFF-RESULT.md'),p
subprocess.run(['git','diff','--exit-code',BASE,'HEAD','--','apps','examples','src','include','extras','tools','cmake','CMakeLists.txt'],check=True)
assert git('-C','target','rev-parse','HEAD')==TARGET
for p in ('src','include','cmake','CMakeLists.txt','licenses'):
    assert git('-C','target','rev-parse',TARGET+':'+p)==git('-C','target','rev-parse',SDK+':'+p),p
print('SOURCE GUARD PASS',os.environ['GITHUB_SHA'],TARGET,SDK)
