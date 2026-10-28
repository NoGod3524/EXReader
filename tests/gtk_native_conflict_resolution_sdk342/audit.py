"""Actions-only complete-chain audit; never accept a smoke as full validation."""
import base64,hashlib,json,os,subprocess
from pathlib import Path
import identity
admitted=identity.guard();root=Path('build/native-audit');out=Path('build/native-summary');out.mkdir(parents=True,exist_ok=True)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def bound(report):identity.retained.bound(report)
suffix=os.environ['GITHUB_RUN_ID']+'-'+os.environ['GITHUB_RUN_ATTEMPT']
base=read(root/'conflict-summary'/ 'sdk342-result.json');bound(base)
assert base['baseline_checks']==15 and base['conflict_checks']==15 and base['retained_gtk_checks']=={'current':48,'original':46}
writer=read(root/'gtk-package/writer-identity.json');bound(writer)
assert writer['program_sha256']==sha(root/'gtk-package/gtk-preview-writer')
assert writer['source_sha256']==sha(Path(__file__).parent/'writer/main.cpp')
gtk_identity=read(root/'gtk-identity/report.json');bound(gtk_identity)
for path,value in writer['linked_files'].items():assert gtk_identity['installed']['product']['files'][path]['sha256']==value
previous=(root/'gtk-offline/state.json').read_bytes();initial=read(root/'gtk-offline/retained-revisions.json');rows=[]
required={
'gtk-native':{'real_gtk_conflict_display_and_cancel_before_save_preserve_graph','second_native_api_writer_changes_real_heads_and_gtk_stale_save_explicitly_rejects','stale_retry_and_close_reopen_preserve_exact_intent_and_every_revision','explicit_discard_then_refresh_cancel_preserve_all_three_heads','actual_gtk_explicit_resolution_parents_all_current_heads_without_history_loss','repeated_sync_fresh_process_reopen_and_public_sdk_original_readback'},
'windows-native':{'windows_receives_gtk_three_head_resolution_and_retains_all_original_revisions','windows_repeat_sync_native_original_reopen_and_public_sdk_bytes_match'}}
for phase in ('gtk-native','windows-native'):
    folder=root/phase;raw=(folder/'state.json').read_bytes();state=json.loads(raw);prior=json.loads(previous)
    assert state['phase']==phase and all(str(state[k])==v for k,v in identity.retained.identity().items())
    assert state['previous_sha256']==hashlib.sha256(previous).hexdigest()
    assert all(state['entries'].get(k)==v for k,v in prior['entries'].items())
    for v in state['entries'].values():assert hashlib.sha256(base64.b64decode(v['body'],validate=True)).hexdigest()==v['sha256']
    assert state['server']['certificate_sha256']==sha(folder/'cert.pem')
    assert state['server']['implementation_sha256']==sha(identity.ROOT/'tests/reader_d23_relay/relay.py')
    requests=read(folder/'requests.json');assert requests and all(r['authenticated'] for r in requests)
    program=base['gtk_program_sha256' if phase=='gtk-native' else 'windows_program_sha256'];assert state['data']['program_'+phase]==program
    checks=state['data']['checks_'+phase];assert len(checks)==len(set(checks)) and set(checks)==required[phase]
    retained=read(folder/'retained-revisions.json');assert all(retained.get(k)==v for k,v in initial.items())
    initial=retained;rows.append({'phase':phase,'program_sha256':program,'state_sha256':hashlib.sha256(raw).hexdigest(),'checks':checks});previous=raw
s=state['data'];evidence=read(root/'gtk-native/revision-evidence.json')
assert sorted(s['gtk_native_resolution']['parents'])==s['gtk_native_three_heads']==evidence['current_heads_at_resolution']
assert set(s['gtk_native_three_heads'])=={s['win_offline_revision']['id'],s['gtk_offline_revision']['id'],s['gtk_native_third_revision']['id']}
assert s['gtk_native_third_revision']['parents']==s['gtk_offline_revision']['parents']==s['win_offline_revision']['parents']
assert s['gtk_native_writer']['program_sha256']==writer['program_sha256']
assert s['gtk_native_writer']['source_sha']==os.environ['GITHUB_SHA']
runtime=s['gtk_native_writer']['runtime'];assert runtime['metadata_version']=='0.1.0' and runtime['commands_version']=='0.1.0' and runtime['revisions_version']=='0.3.0'
assert sha(root/'gtk-native/original.bin')==s['windows_original_sha256']==base['original_sha256']
for name in ('01-real-two-head-conflict','02-cancel-preview','03-open-two-head-preview','04-stale-save-rejected','05-stale-retry-rejected','06-reopened-pending-intent','07-refreshed-three-head-conflict','08-actual-explicit-resolution','09-original-reopened'):
    assert (root/'gtk-native'/(name+'.png')).read_bytes().startswith(b'\x89PNG')
    assert read(root/'gtk-native'/(name+'.json'))
api=json.loads(subprocess.check_output(['gh','api','repos/'+os.environ['GITHUB_REPOSITORY']+'/actions/runs/'+os.environ['GITHUB_RUN_ID']+'/artifacts?per_page=100'],text=True));artifacts=[]
for prefix in ('gtk-native-smoke-','gtk-native-gtk-','gtk-native-windows-','conflict-summary-','sdk342-gtk-identity-','gtk-windows-package-'):
    found=[x for x in api['artifacts'] if x['name']==prefix+suffix and not x['expired']];assert len(found)==1
    a=found[0];assert a['workflow_run']['head_sha']==os.environ['GITHUB_SHA'] and a['size_in_bytes']>0 and a['digest'].startswith('sha256:')
    artifacts.append({k:a[k] for k in ('id','name','size_in_bytes','digest')})
result=dict(identity.retained.identity(),accepted=True,sdk_version='3.42.0',abi=1,phases=rows,artifacts=artifacts,retained_baseline_checks=base['baseline_checks'],retained_conflict_checks=base['conflict_checks'],retained_gtk_checks=base['retained_gtk_checks'],original_sha256=s['windows_original_sha256'],three_heads=s['gtk_native_three_heads'],resolution=s['gtk_native_resolution'],writer=writer,gtk_program_sha256=base['gtk_program_sha256'],windows_program_sha256=base['windows_program_sha256'],scope='Real GTK UI conflict/cancel/stale rejection/recovery/three-head resolution; installed native API controlled second writer; real Windows peer receive; sequential HTTPS DAV snapshots')
(out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print('GTK_NATIVE_FINAL_AUDIT '+json.dumps(result,ensure_ascii=False),flush=True)
