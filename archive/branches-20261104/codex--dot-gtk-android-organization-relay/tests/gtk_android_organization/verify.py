"""Cross-stage identity, untouched revision chain and native UI result acceptance."""
import base64,hashlib,json,os,sys
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
# Exact phase-specific dependency, never a blanket allowance of pending work.
evidence=states[1][0]['data']['relay_data']['deleted_dependency_evidence']
assert evidence['pending_count']==1 and evidence['outbox_count']==0
assert evidence['deleted_group']['deleted']=='1' and evidence['surviving_membership']['deleted']=='0'
assert evidence['surviving_membership']['key']==evidence['expected_member_key']
retained={}
for value in states[1][0]['entries'].values():
    body=base64.b64decode(value['body'],validate=True)
    try:wire=json.loads(body)
    except (UnicodeDecodeError,json.JSONDecodeError):continue
    if isinstance(wire,dict) and 'id' in wire:retained[wire['id']]=value['sha256']
for head in evidence['all_safe_heads']:assert retained[head['revision']]==head['body_sha256']
profile=json.loads((out/'gtk-return/resumed-native-profile.json').read_text())
assert profile['origin_state_sha256']==states[0][1] and profile['copied_unchanged'] is True
assert profile['files']=={str(p.relative_to(out/'gtk-first/profile')):hashlib.sha256(p.read_bytes()).hexdigest() for p in (out/'gtk-first/profile').rglob('*') if p.is_file()}
assert all(s['data']['relay_data']['original_sha256']==states[0][0]['data']['relay_data']['original_sha256'] for s,_ in states)
assert 'gtk_ui_receives_tombstone_and_restores_series' in states[2][0]['data']['checks']
assert any(c['name']=='process_restart_real_ui_retains_groups_members' for c in states[3][0]['data']['checks'])
regressions=json.loads((out/'gtk-first/regression-outcomes.json').read_text());assert regressions['current_account']=='success' and regressions['same_historical_assertions_scoped_chooser_driver']=='success'
result={'gtk_regressions':regressions,**relay.identity(),'passed':True,'transport':'Authenticated HTTPS, sequential same-run service-state relay; no synthetic revision or app DB injection','phases':[{'phase':s['phase'],'state_sha256':sha,'program_sha256':s['data']['program_sha256'],'checks':s['data']['checks']} for s,sha in states],'limits':['Android API34 emulator, GTK X11 cloud runner; no physical Android or Internet-wide concurrent service claim']}
(out/'summary.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
