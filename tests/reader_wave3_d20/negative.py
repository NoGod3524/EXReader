"""Refusal fixtures are harness tests, never product observations."""
import copy
import json
import os
from pathlib import Path
import subprocess
from contract import *


def main():
    assert os.environ.get('GITHUB_ACTIONS')=='true'
    configs=[]
    for name in CONFIGS:
        scale=int(name.split('-')[0]);high=name.split('-')[1]=='high'
        active=scale==100
        c=dict(configuration=name,requested_scale=scale,requested_contrast='high' if high else 'normal',
               execution='executed' if active else 'not-run-capability-pending',screenshots=['fake.bmp'] if active else [],
               checks={key:dict(status='pending',actual={}) for key in REQUIRED},
               capability=dict(available=active,readback={'monitors':[dict(primary=True,scale_percent=scale,probe_dpi=scale*96//100,probe_awareness=2)]}),
               contrast_readback=dict(flags=1 if high else 0),loaded_modules=['synthetic'],actual_transport='sendinput')
        configs.append(c)
    base=dict(source_sha='test',target_sha='test',run_id=1,attempt=1,seed=BASE,sdk_source=SDK,historical_source=D08,
              accepted=False,screen_reader_accepted=False,program_sha256='0'*64,files=['synthetic'],restoration=dict(high_contrast_restored=True),
              configurations=configs,coverage={'100':4,'150':0,'200':0})
    validate(base,'test',1,1)
    results=[]
    for case in ('requested-not-actual','fake-probe','unexecuted-pass','main-window-modal-focus','missing-baseline','missing-more','unrestored-hc','missing-screenshot'):
        r=copy.deepcopy(base);c=r['configurations'][0]
        if case=='requested-not-actual':c['capability']['readback']['monitors'][0]['scale_percent']=150
        if case=='fake-probe':c['capability']['readback']['monitors'][0]['probe_awareness']=0
        if case=='unexecuted-pass':r['configurations'][4]['checks']['dpi']['status']='pass'
        if case=='main-window-modal-focus':c['checks']['search']=dict(status='pass',actual=dict(focus=[dict(descendant=False,visible=True,enabled=True)]*3,after=dict(descendant=True,visible=True,enabled=True)))
        if case=='missing-baseline':r['configurations'].pop(0)
        if case=='missing-more':c['checks'].pop('more')
        if case=='unrestored-hc':r['restoration']['high_contrast_restored']=False
        if case=='missing-screenshot':c['screenshots']=[]
        try:validate(r,'test',1,1)
        except (AssertionError,KeyError):results.append(dict(case=case,rejected=True));continue
        raise AssertionError('accepted refusal control '+case)
    out=Path('build/d20-evidence');out.mkdir(parents=True,exist_ok=True)
    (out/'negative-controls.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
    # Re-run all four exact D08 refusal checks against its exact old contract.
    old=Path('build/d20-original-negative');old.mkdir(parents=True,exist_ok=True)
    for name in ('contract.py','negative.py'):
        (old/name).write_bytes(subprocess.check_output(['git','show',D08+':tests/reader_dot_wave2/d08/'+name]))
    subprocess.run([__import__('sys').executable,str(old/'negative.py')],check=True)
    (out/'d08-negative-controls.json').write_bytes(Path('build/d08-evidence/negative-controls.json').read_bytes())
    print(json.dumps(results))


if __name__=='__main__':main()
