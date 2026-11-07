#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Run the original phase-a/b/c scripts offscreen, including a baseline repeat.
Usage: check_step5_legacy.py EXE BASELINE FONT BOOK OUT
No workflow is invoked. All child consoles are hidden.
"""
from pathlib import Path
import shutil
import subprocess
import sys
from check_step5 import run,dump,HIDDEN
from compare_shots import compare

def main():
    exe,baseline,font,book,out=map(lambda p:Path(p).resolve(),sys.argv[1:])
    root=Path(__file__).resolve().parents[3];out.mkdir(parents=True,exist_ok=True)
    fixtures=out/'fixtures'
    subprocess.run([sys.executable,str(root/'tests/windows_host/make_fixtures.py'),'--output',str(fixtures)],
                   capture_output=True,check=True,creationflags=HIDDEN)
    shutil.copy2(book,fixtures/'Sample.epub')
    result={}
    for label,binary in [('baseline',baseline),('control',baseline),('changed',exe)]:
        result[label]={}
        for letter in 'ABC':
            script=(root/f'tests/windows_host/phase-{letter.lower()}.txt').read_text(encoding='utf-8')
            script=script.replace('@@SAMPLE@@',str(fixtures)).replace('@@FIXTURES@@',str(fixtures))
            evidence=out/label/letter
            run(binary,font,script,out/label/'profile',evidence,allowed_failures=2)
            failed=[l for l in (evidence/'drive.log').read_text(encoding='utf-8').splitlines()
                    if l.startswith('STEP\t') and l.split('\t')[3]!='PASS']
            result[label][letter]=failed
    for label in ('control','changed'):assert result[label]==result['baseline'],result
    lines=[]
    for label in ('control','changed'):
        count,failed=compare(out/'baseline',out/label,38,lambda *args:lines.append(label+' '+' '.join(map(str,args))))
        result[label]['images']=count;result[label]['nonzero']=failed
        assert count==8 and failed==0,(label,count,failed)
    (out/'comparison.txt').write_text('\n'.join(lines),encoding='utf-8')
    dump(out/'result.json',result)
    print('\n'.join(lines))

if __name__=='__main__':main()
