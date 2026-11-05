"""Actual current owner18 process checks, separate from frozen Android130."""
import json, os, subprocess, sys
from pathlib import Path
assert os.environ.get('GITHUB_ACTIONS')=='true'
out=Path('build/current-android/owner');out.mkdir(parents=True,exist_ok=True)
identity={key:os.environ[value] for key,value in [('source_sha','GITHUB_SHA'),('run_id','GITHUB_RUN_ID'),('attempt','GITHUB_RUN_ATTEMPT')]}
def adb(*args):
    return subprocess.check_output(['adb',*map(str,args)],stderr=subprocess.STDOUT,timeout=240)
def instrument(name,phase=None):
    args=['shell','am','instrument','-w','-r']
    for key,value in identity.items():args.extend(('-e',key,value))
    if phase:args.extend(('-e','phase',phase))
    raw=adb(*args,'org.exreader.host.test/org.exreader.host.ProductOwnerTest')
    (out/(name+'.txt')).write_bytes(raw)
    return raw
raw=instrument('owner18')
assert b'OK (18 tests)' in raw and b'INSTRUMENTATION_CODE: -1' in raw and b'FAILURES' not in raw
report=json.loads(adb('exec-out','run-as','org.exreader.host','cat','files/product-owner-report.json'))
assert report['failed']==0 and report['count']==18 and all(report.get(k)==v for k,v in identity.items())
for phase,witness in (('before',b'1,1,0'),('after',b'1,1,1')):
    assert b'Process crashed.' in instrument('seed-'+phase,'seed-'+phase)
    assert adb('exec-out','run-as','org.exreader.host','cat','files/owner-kill-'+phase+'/witness.txt')==witness
    assert ('EXR_OWNER_RECOVERED recover-'+phase).encode() in instrument('recover-'+phase,'recover-'+phase)
(out/'result.json').write_text(json.dumps(dict(**identity,accepted=True,checks=18,process_phases=2,report=report),indent=2)+'\n')
