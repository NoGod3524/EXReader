"""Actions-only audit of unmodified original relay + new native conflict phases."""
import base64,hashlib,json,os,subprocess
from pathlib import Path
assert os.environ.get('GITHUB_ACTIONS')=='true'
root=Path('build/conflict-audit');out=Path('build/conflict-summary');out.mkdir(parents=True,exist_ok=True)
phases=['windows-offline','gtk-offline','windows-resolve','gtk-final','windows-final']
required={
 'windows-offline':{'windows_real_ui_offline_edit_retains_original_parent'},
 'gtk-offline':{'gtk_real_ui_offline_edit_of_same_record_same_parent','gtk_receives_both_real_versions_and_displays_unresolved_conflict','separate_native_api_copy_rejects_ordinary_identity_and_stale_resolution_and_proves_exact_retry'},
 'windows-resolve':{'windows_cancel_retains_local_revisions_and_allows_retry','windows_received_both_actual_offline_revisions_and_displays_conflict','explicit_native_resolution_parents_both_heads_without_deleting_history','original_still_opens_after_cancel_conflict_and_resolution'},
 'gtk-final':{'gtk_receives_explicit_resolution_and_retains_every_prior_revision','repeat_sync_does_not_duplicate_or_drop_any_revision','native_tag_delete_is_synced_without_losing_original_or_conflict_history','native_explicit_tag_restore_sync_retains_delete_and_unresolved_ancestors','new_process_reopens_resolved_original','public_sdk_reads_identical_original_after_offline_conflict_recovery'},
 'windows-final':{'windows_receives_tag_delete_restore_history_and_reopens_same_original'},
}
previous=Path('build/baseline-final/gtk-return/state.json').read_bytes();prior=json.loads(previous);rows=[]
for phase in phases:
    folder=root/('conflict-'+phase+'-'+os.environ['GITHUB_RUN_ID']+'-'+os.environ['GITHUB_RUN_ATTEMPT'])
    raw=(folder/'state.json').read_bytes();state=json.loads(raw)
    assert state['phase']==phase and state['source_sha']==os.environ['GITHUB_SHA']
    assert state['run_id']==os.environ['GITHUB_RUN_ID'] and state['attempt']==os.environ['GITHUB_RUN_ATTEMPT']
    assert state['previous_sha256']==hashlib.sha256(previous).hexdigest()
    assert all(state['entries'].get(k)==v for k,v in prior['entries'].items())
    for value in state['entries'].values():assert hashlib.sha256(base64.b64decode(value['body'],validate=True)).hexdigest()==value['sha256']
    requests=json.loads((folder/'requests.json').read_text());assert requests and all(r['authenticated'] for r in requests)
    assert state['server']['base'].startswith('https://127.0.0.1:')
    assert state['server']['certificate_sha256']==hashlib.sha256((folder/'cert.pem').read_bytes()).hexdigest()
    checks=state['data']['checks_'+phase];assert set(checks)==required[phase] and len(checks)==len(set(checks))
    rows.append({'phase':phase,'state_sha256':hashlib.sha256(raw).hexdigest(),'checks':checks,'program_sha256':state['data']['program_'+phase]})
    previous=raw;prior=state
s=prior['data'];w,g,m=s['win_offline_revision'],s['gtk_offline_revision'],s['resolution_revision']
assert w['entity_key']==g['entity_key']==m['entity_key']==s['windows_book']
assert w['parents']==g['parents'] and w['id']!=g['id'] and set(m['parents'])=={w['id'],g['id']}
assert {r['operation'] for r in s['tag_final_revisions']}>={'put','delete','restore'}
api=json.loads(subprocess.check_output(['gh','api','repos/'+os.environ['GITHUB_REPOSITORY']+'/actions/runs/'+os.environ['GITHUB_RUN_ID']+'/artifacts'],text=True))
artifacts=[{k:a[k] for k in ('id','name','size_in_bytes','digest')} for a in api['artifacts'] if a['name'].startswith(('conflict-','windows-gtk-','gtk-windows-'))]
assert len(artifacts)>=12 and all(a['size_in_bytes']>0 and a['digest'].startswith('sha256:') for a in artifacts)
report=dict(accepted=True,source_sha=os.environ['GITHUB_SHA'],run_id=os.environ['GITHUB_RUN_ID'],attempt=os.environ['GITHUB_RUN_ATTEMPT'],phases=rows,artifacts=artifacts,book_original_sha256=s['windows_original_sha256'],conflict_heads=[w['id'],g['id']],resolution=m['id'],transport='Authenticated sequential HTTPS DAV snapshots, not a continuous remote service',delete_restore_scope='Actual GTK tag deletion and explicit restoration received by Windows; not book deletion',original_checks='Unmodified D23 relay and verifier prerequisite in the same run',platform='GitHub-hosted real Windows and GTK applications, UI automation, no physical device or screen-reader claim')
(out/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report,ensure_ascii=False))
