"""Cross-stage identity, untouched revision chain and native UI result acceptance."""
import hashlib,json,os,sys
from pathlib import Path
import relay
out=Path('build/organization-audit');phases=['gtk-first','android','gtk-return','android-final'];states=[]
for phase in phases:
    folder=out/phase
    state,sha=relay.load(folder/'state.json',phase);report=json.loads((folder/'report.json').read_text());assert state['data']==report
    assert report['checks'] and report['program_sha256'];assert list(folder.glob('*.png')),'missing actual UI images'
    requests=json.loads((folder/'requests.json').read_text());assert requests and all(r['authenticated'] for r in requests)
    if states:
        prior=states[-1];assert state['previous_sha256']==prior[1]
        assert all(state['entries'].get(p)==v for p,v in prior[0]['entries'].items()),'original revisions changed'
    states.append((state,sha));assert any(r['method']=='GET' and '/revisions/' in r['path'] for r in requests) or phase=='gtk-first'
assert states[0][0]['data']['program_sha256']==states[2][0]['data']['program_sha256']
assert states[1][0]['data']['program_sha256']==states[3][0]['data']['program_sha256']
assert len(states[2][0]['entries'])>len(states[1][0]['entries'])>len(states[0][0]['entries'])
regressions=json.loads((out/'gtk-first/regression-outcomes.json').read_text());assert regressions['current_account']=='success' and regressions['same_historical_assertions_scoped_chooser_driver']=='success'
result={'gtk_regressions':regressions,**relay.identity(),'passed':True,'transport':'Authenticated HTTPS, sequential same-run service-state relay; no synthetic revision or app DB injection','phases':[{'phase':s['phase'],'state_sha256':sha,'program_sha256':s['data']['program_sha256'],'checks':s['data']['checks']} for s,sha in states],'limits':['Android API34 emulator, GTK X11 cloud runner; no physical Android or Internet-wide concurrent service claim']}
(out/'summary.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
