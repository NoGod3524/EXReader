"""Conservative observation contract: no coordinate/foreign/stale AX grants."""
import copy,json,os
from pathlib import Path

def observation(row):
    assert row['snapshot_epoch']==row['current_epoch'], 'stale node'
    assert row['window_id']==row['current_window_id'], 'foreign window'
    assert row['ax_evidence'] and row['ax_semantics_accepted'] is False
    assert row['configuration'] and row['program_hash']==row['actual_program_hash']
    assert row['functional_reachable'] is True
    # False wrapper hittability is retained and does not grant AX semantics.
    assert row['wrapper_hittable'] is False

def targets(rows):
    assert set(rows)=={'macos','iphone','ipad'}

def negative_checks():
    row=dict(snapshot_epoch=2,current_epoch=2,window_id='window-2',current_window_id='window-2',ax_evidence=True,ax_semantics_accepted=False,configuration={'review_macros':[]},program_hash='actual',actual_program_hash='actual',functional_reachable=True,wrapper_hittable=False)
    observation(row);targets(['macos','iphone','ipad']);rejected=[]
    for name,change in [('stale-node',{'snapshot_epoch':1}),('foreign-window',{'window_id':'other'}),('coordinate-only',{'ax_evidence':False}),('missing-configuration',{'configuration':None}),('wrong-program',{'program_hash':'wrong'}),('coordinate-promoted-AX',{'ax_semantics_accepted':True})]:
        bad=copy.deepcopy(row);bad.update(change)
        try: observation(bad)
        except AssertionError: rejected.append(name)
        else: raise AssertionError('negative accepted: '+name)
    try:targets(['macos','iphone'])
    except AssertionError:rejected.append('missing-ipad')
    else:raise AssertionError('missing mobile accepted')
    return rejected
if __name__=='__main__':
    assert os.environ.get('GITHUB_ACTIONS')=='true'
    out=Path('build');out.mkdir(exist_ok=True)
    report={'contract_negatives':negative_checks(),'synthetic_only':True,'accepted':False}
    (out/'d10-contract.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))
