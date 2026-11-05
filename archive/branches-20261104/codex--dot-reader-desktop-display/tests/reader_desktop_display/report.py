#!/usr/bin/env python3
"""Bind exact raw results to installed library and actual fresh consumer bytes."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from cases import CASES, UNAVAILABLE

def digest(p):
    b=p.read_bytes(); return {'sha256':hashlib.sha256(b).hexdigest(),'size':len(b)}
def strict_json(text):
    def pairs(items):
        d={}
        for k,v in items:
            if k in d: raise ValueError('duplicate JSON key '+k)
            d[k]=v
        return d
    return json.loads(text, object_pairs_hook=pairs)
def validate_raw(root, platform, sha):
    cases={}
    for p in sorted((root/'raw').glob('*.jsonl')):
        for line in p.read_text().splitlines():
            r=strict_json(line); name=r['case']
            if name in cases: raise ValueError('duplicate case '+name)
            if r.get('module') != sha: raise ValueError('wrong original module stamp')
            if r['result']!='PASS' and not (r['result']=='UNAVAILABLE' and name in UNAVAILABLE[platform] and r.get('detail')): raise ValueError('failed/unapproved result '+name)
            cases[name]=r
    if set(cases)!=set(CASES[platform]): raise ValueError('missing/extra named cases: '+str(set(cases)^set(CASES[platform])))
    for p in (root/'raw').glob('*.exit'):
        if p.read_text().strip()!='0': raise ValueError('nonzero raw exit '+p.name)
    required={'native.exit','termination.exit','consumer_c.exit','consumer_cpp.exit'} | ({'real.exit','real_termination.exit'} if platform=='linux' else set())
    if not required <= {p.name for p in (root/'raw').glob('*.exit')}: raise ValueError('missing original exit')
    return cases

def main():
    if os.environ.get('GITHUB_ACTIONS')!='true': raise SystemExit('Actions only')
    platform, dest=sys.argv[1:]; root=Path(dest); sha=os.environ['GITHUB_SHA']
    cases=validate_raw(root,platform,sha)
    files={str(p.relative_to(root)).replace('\\','/'):digest(p) for p in root.rglob('*') if p.is_file() and p.name!='report.json'}
    suffix='.exe' if platform=='windows' else ''
    binary_names=['bin/display_probe'+suffix,'bin/consumer_c'+suffix,'bin/consumer_cpp'+suffix,'lib/exr_desktop_display.lib' if platform=='windows' else 'lib/libexr_desktop_display.a']
    if not all(n in files and files[n]['size']>0 for n in binary_names): raise ValueError('missing actual module/consumer bytes')
    report={'schema':1,'source_sha':sha,'run_id':int(os.environ['GITHUB_RUN_ID']),'run_attempt':int(os.environ['GITHUB_RUN_ATTEMPT']),'platform':platform,'job_name':'native ('+platform+')','module_tree':subprocess.check_output(['git','rev-parse',sha+':extras/desktop-reader-display'],text=True).strip(),'cases':cases,'files':files,'actual_binaries':binary_names,'capabilities':{'physical_screen_energy':'UNAVAILABLE','wayland':'UNAVAILABLE','linux_real_service':cases.get('real_session_service',{}).get('result','NOT_APPLICABLE'),'linux_fault_fixture':'deterministic-only' if platform=='linux' else 'NOT_APPLICABLE'}}
    (root/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'platform':platform,'source_sha':sha,'results':{r:sum(v['result']==r for v in cases.values()) for r in ['PASS','UNAVAILABLE']},'actual_binaries':{n:files[n] for n in binary_names}},indent=2))
if __name__=='__main__': main()
