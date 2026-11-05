"""Actions-only source ownership and producer equivalence guard."""
import os
import subprocess as sp
from pathlib import Path
from contract import *
assert os.environ.get('GITHUB_ACTIONS')=='true'
def git(*args):return sp.check_output(['git',*args],text=True).strip()
sp.check_call(['git','merge-base','--is-ancestor',BASE,'HEAD'])
allowed=('tests/reader_final_d02/','docs/reader-final-d02/','docs/validation/reader-final-d02.json','.github/workflows/reader-final-d02.yml','HANDOFF-RESULT.md')
changed=git('diff','--name-only',BASE,'HEAD').splitlines()
assert changed and all(any(p==a or (a.endswith('/') and p.startswith(a)) for a in allowed) for p in changed),changed
for path in ('apps','examples','src','include','CMakeLists.txt','CMakePresets.json','extras','bindings','cmake','tools'):
    assert git('rev-parse','HEAD:'+path)==git('rev-parse',BASE+':'+path),path
for p in git('diff','--name-only',PRODUCER,TARGET).splitlines():assert p.startswith('docs/'),p
for p in ('src','include','CMakeLists.txt','CMakePresets.json','cmake'):
    assert git('rev-parse',TARGET+':'+p)==git('rev-parse',SDK+':'+p),p
print('D02 exclusive paths, base ancestor, immutable SDK trees and producer/target production equivalence authenticated')
