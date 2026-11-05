"""Actions-only source identity and exclusive-path guard."""
import os, subprocess
from pathlib import Path
BASE='0889f7d1e9a537c6c1b05456547e016b26e1cd85'
TARGET='803098e9df1a365a9b8e206805c2d179aca8501f'
SDK='edddc463c06ed5731195cdb8f06b2df6dff7699e'
def git(*a): return subprocess.check_output(['git',*a],text=True).strip()
assert os.environ['GITHUB_ACTIONS']=='true'
assert git('rev-parse','HEAD')==os.environ['GITHUB_SHA']
subprocess.run(['git','merge-base','--is-ancestor',BASE,'HEAD'],check=True)
for p in git('diff','--name-only',BASE,'HEAD').splitlines():
    assert p.startswith(('tests/reader_dot_wave2/d09/','docs/reader-dot-wave2/d09/')) or p in ('.github/workflows/reader-dot-d09.yml','HANDOFF-RESULT-D09.md'),p
subprocess.run(['git','diff','--exit-code',BASE,'HEAD','--','apps','examples','src','include','extras','tools','cmake','CMakeLists.txt'],check=True)
assert git('-C','target','rev-parse','HEAD')==TARGET
for p in ('src','include','cmake','CMakeLists.txt','licenses'):
    assert git('-C','target','rev-parse',TARGET+':'+p)==git('-C','target','rev-parse',SDK+':'+p),p
print('SOURCE GUARD PASS',os.environ['GITHUB_SHA'],TARGET,SDK)
