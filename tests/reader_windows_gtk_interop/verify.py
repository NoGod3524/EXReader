"""Actions-only identity and state-chain audit; the servers are sequential, not one live service."""
import base64, hashlib, json, os, subprocess
from pathlib import Path
assert os.environ.get('GITHUB_ACTIONS')=='true'
root=Path('build/audit');out=Path('build/summary');out.mkdir(parents=True,exist_ok=True)
phases=[('windows-first',root/'win1/windows-first'),('gtk-first',root/'gtk1/gtk-first'),('windows-return',root/'win2'),('gtk-return',root/'gtk2/gtk-return')]
rows=[];last=None
for phase,folder in phases:
    body=(folder/'state.json').read_bytes();s=json.loads(body)
    assert s['phase']==phase and s['source_sha']==os.environ['GITHUB_SHA'] and s['run_id']==os.environ['GITHUB_RUN_ID'] and s['attempt']==os.environ['GITHUB_RUN_ATTEMPT']
    assert s['server']['base'].startswith('https://127.0.0.1:') and s['server']['certificate_sha256']==hashlib.sha256((folder/'cert.pem').read_bytes()).hexdigest()
    assert s['server']['implementation_sha256']==hashlib.sha256((Path(__file__).parent/'relay.py').read_bytes()).hexdigest()
    assert s['previous_sha256']==(hashlib.sha256(last).hexdigest() if last else None)
    for key,value in s['entries'].items():
        data=base64.b64decode(value['body'],validate=True);assert hashlib.sha256(data).hexdigest()==value['sha256']
    if rows: assert all(s['entries'].get(k)==v for k,v in rows[-1]['state']['entries'].items())
    req=json.loads((folder/'requests.json').read_text());assert req and all(r['authenticated'] for r in req)
    rows.append({'phase':phase,'folder':folder,'state':s,'requests':req,'snapshot_sha256':hashlib.sha256(body).hexdigest()});last=body
s=rows[-1]['state'];data=s['data']
required={
 'windows-first':{'windows_imports_original_in_native_host','windows_sync_publishes_real_book_and_original'},
 'gtk-first':{'gtk_imports_original_in_native_host','gtk_opens_windows_original_from_relay','gtk_native_ui_creates_tag_and_membership','gtk_publishes_real_organization_and_original','gtk_public_sdk_reads_exact_windows_original'},
 'windows-return':{'windows_same_binary_as_first_phase','windows_public_sdk_reads_exact_gtk_original','windows_native_ui_removes_gtk_tag_membership','windows_publishes_membership_change_and_second_original'},
 'gtk-return':{'gtk_receives_windows_membership_tombstone','gtk_opens_windows_return_original','gtk_public_sdk_reads_exact_windows_original'},
}
for name,_ in phases:
    checks=data['checks_'+name];assert len(checks)==len(set(checks)) and set(checks)==required[name]
win=hashlib.sha256((root/'windows-package/EXReader.exe').read_bytes()).hexdigest()
gtk=hashlib.sha256((root/'gtk-package/bin/exreader-linux').read_bytes()).hexdigest()
assert data['windows_program_sha256']==win and data['gtk_program_sha256']==gtk and win!=gtk
for item in rows:
    phase=item['phase'];expected_program=win if phase.startswith('windows-') else gtk
    assert item['state']['data']['program_'+phase]==expected_program
build=json.loads((root/'win1/c09/report.json').read_text())
assert build['accepted'] and not build['failures'] and build['source_sha']==os.environ['GITHUB_SHA'] and str(build['run_id'])==os.environ['GITHUB_RUN_ID'] and str(build['attempt'])==os.environ['GITHUB_RUN_ATTEMPT'] and build['program_sha256']==win
for folder,count in (('current-account',48),('original-account',46)):
    report=json.loads((root/'gtk1'/folder/'result.json').read_text())
    assert report['accepted'] and report['count']==count and report['source_sha']==os.environ['GITHUB_SHA'] and report['run_id']==os.environ['GITHUB_RUN_ID'] and report['attempt']==os.environ['GITHUB_RUN_ATTEMPT'] and report['program_sha256']==data['gtk_program_sha256']
for item in rows[:3]: assert any(x['method']=='PUT' for x in item['requests'])
for item in rows[1:]: assert any(x['method']=='GET' for x in item['requests'])
for key in ('windows_original_sha256','gtk_original_sha256','return_original_sha256'):
    sha=data[key];assert any('/objects/' in p and sha in p and v['sha256']==sha for p,v in s['entries'].items())
revisions=[json.loads(base64.b64decode(v['body'])) for p,v in s['entries'].items() if '/revisions/' in p and p.endswith('.json')]
selected=[r for r in revisions if r['entity_kind']=='membership' and r['entity_key']=='tag:'+data['gtk_tag']+':'+data['windows_book']]
assert {r['operation'] for r in selected}>={'put','delete'}
assert hashlib.sha256((rows[1]['folder']/'readback.bin').read_bytes()).hexdigest()==data['windows_original_sha256']
assert hashlib.sha256((rows[3]['folder']/'readback.bin').read_bytes()).hexdigest()==data['return_original_sha256']
assert (rows[1]['folder']/'gtk-membership.png').read_bytes().startswith(b'\x89PNG')
assert (rows[2]['folder']/'windows-membership.bmp').read_bytes().startswith(b'BM')
assert (rows[3]['folder']/'gtk-return-membership.png').read_bytes().startswith(b'\x89PNG')
api=json.loads(subprocess.check_output(['gh','api','repos/%s/actions/runs/%s/artifacts'%(os.environ['GITHUB_REPOSITORY'],os.environ['GITHUB_RUN_ID'])],text=True))
expected=['windows-gtk-package-','gtk-windows-package-','windows-gtk-first-','windows-gtk-gtk-first-','windows-gtk-return-','windows-gtk-final-']
artifacts=[]
for prefix in expected:
    name=prefix+os.environ['GITHUB_RUN_ID']+'-'+os.environ['GITHUB_RUN_ATTEMPT']
    matches=[a for a in api['artifacts'] if a['name']==name and not a['expired']]
    assert len(matches)==1 and matches[0]['size_in_bytes']>0 and matches[0]['digest'].startswith('sha256:')
    artifacts.append({k:matches[0][k] for k in ('id','name','digest','size_in_bytes')})
summary={'accepted':True,'scope':'actual Windows and GTK host actions with sequential service-state relay; separate local TLS servers','same_online_service':False,'source_sha':os.environ['GITHUB_SHA'],'run_id':os.environ['GITHUB_RUN_ID'],'attempt':os.environ['GITHUB_RUN_ATTEMPT'],'windows_program_sha256':data['windows_program_sha256'],'gtk_program_sha256':data['gtk_program_sha256'],'phases':[{'phase':x['phase'],'snapshot_sha256':x['snapshot_sha256'],'checks':data['checks_'+x['phase']]} for x in rows],'artifacts':artifacts,'complete_product':False}
(out/'result.json').write_text(json.dumps(summary,indent=2),encoding='utf-8');print(json.dumps(summary),flush=True)
