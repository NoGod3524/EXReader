#!/usr/bin/env python3
"""Compare native contextual case conversion against the system ICU via Node Intl."""
# SPDX-License-Identifier: MIT
import argparse,json,random,subprocess
from pathlib import Path

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('binary',type=Path);p.add_argument('node');a=p.parse_args()
    alphabet=['I','J','i','j','İ','ı','Σ','σ','ς','A','a','ß','ﬃ','ǅ','中',"'",'0',
        '\u0307','\u0301','\u0323','\u0345','\u034f','\u200c','\u200d','\u02b0','\u02bc','\u0456']
    rng=random.Random(180618);cases=[]
    for language in ('und','tr-TR','az-AZ','lt-LT'):
        for mode in (0,2):
            for _ in range(250):
                text=''.join(rng.choice(alphabet) for _ in range(rng.randint(1,24)))
                cases.append([mode,language,text])
    version=subprocess.check_output([a.node,'-p','process.versions.unicode'],text=True).strip()
    scope='context alphabet predates Unicode 14'
    if int(version.split('.')[0])>=17:
        scope='includes all Unicode 17 default mapping scalars'
        for line in (Path(__file__).resolve().parents[1]/'tests/fixtures/unicode/CaseMappingTest.txt').read_text().splitlines():
            if line.startswith('#'): continue
            cp=chr(int(line.split(';')[0],16))
            for mode in (0,2): cases.append([mode,'und',cp])
    script="""let data='';process.stdin.setEncoding('utf8');process.stdin.on('data',x=>data+=x);process.stdin.on('end',()=>{let cases=JSON.parse(data);process.stdout.write(JSON.stringify({icu:process.versions.icu,unicode:process.versions.unicode,results:cases.map(([mode,lang,text])=>mode===0?text.toLocaleLowerCase(lang):text.toLocaleUpperCase(lang))}));});"""
    ref=json.loads(subprocess.check_output([a.node,'-e',script],input=json.dumps(cases).encode()))
    query=''.join(f"{mode};{language};"+' '.join(f'{ord(cp):X}' for cp in text)+'\n' for mode,language,text in cases)
    actual=subprocess.run([str(a.binary.resolve()),'--batch-map'],input=query.encode(),capture_output=True,check=True).stdout.decode().splitlines()
    assert len(actual)==len(cases)
    for case,result,expected in zip(cases,actual,ref['results']):
        result=''.join(chr(int(x,16)) for x in result.split())
        assert result==expected,(case,repr(result),repr(expected))
    print(f"{len(cases)} contextual case comparisons passed; independent ICU {ref['icu']}, Unicode {ref['unicode']}; {scope}")
if __name__=='__main__': main()
