# SPDX-License-Identifier: MIT
import argparse,copy,hashlib,json,os
from pathlib import Path
def evidence_identity():
    if os.environ.get('F10_FIXED_PRODUCER_AUDIT')=='1':
        fixed=json.loads(Path(__file__).with_name('manifest.json').read_text())['fixed_producer']
        return [fixed['source'],str(fixed['run']),str(fixed['attempt'])]
    return [os.environ['GITHUB_SHA'],os.environ['GITHUB_RUN_ID'],os.environ['GITHUB_RUN_ATTEMPT']]

EXPECTED={"owned-kill":[["actual_sigkill",9],["different_process",1],["actual_snapshot_bytes",43],["abandon_status",0],["removed",1],["directory_absent",1],["receipt_state",6],["same_identity_idempotent",0],["cleaned_wrong_id_refused",4],["close",0]],"sealed-kill":[["actual_sigkill",9],["different_process",1],["actual_snapshot_bytes",43],["abandon_status",0],["removed",1],["directory_absent",1],["receipt_state",6],["same_identity_idempotent",0],["cleaned_wrong_id_refused",4],["close",0]],"active-owner":[["active_owner_busy",3],["actual_sigkill",9],["different_process",1],["actual_snapshot_bytes",43],["abandon_status",0],["removed",1],["directory_absent",1],["receipt_state",6],["same_identity_idempotent",0],["cleaned_wrong_id_refused",4],["close",0]],"historical-device":[["actual_sigkill",9],["different_process",1],["actual_snapshot_bytes",43],["abandon_status",0],["removed",1],["directory_absent",1],["receipt_state",6],["same_identity_idempotent",0],["cleaned_wrong_id_refused",4],["close",0]],"wrong-uuid":[["actual_sigkill",9],["different_process",1],["actual_snapshot_bytes",43],["open_refused",4],["payload_preserved",1]],"corrupt-receipt":[["actual_sigkill",9],["different_process",1],["actual_snapshot_bytes",43],["open_refused",4],["payload_preserved",1]],"residual-receipt-next":[["actual_sigkill",9],["different_process",1],["actual_snapshot_bytes",43],["open_refused",4],["payload_preserved",1]],"wrong-id":[["actual_sigkill",9],["different_process",1],["actual_snapshot_bytes",43],["abandon_status",4],["rejected_path_identity_preserved",1],["receipt_state",3],["close",0]],"wrong-slot":[["actual_sigkill",9],["different_process",1],["actual_snapshot_bytes",43],["abandon_status",1],["rejected_path_identity_preserved",1],["receipt_state",3],["close",0]],"wrong-inode":[["actual_sigkill",9],["different_process",1],["actual_snapshot_bytes",43],["abandon_status",4],["rejected_path_identity_preserved",1],["receipt_state",3],["close",0]],"wrong-state":[["actual_sigkill",9],["different_process",1],["actual_snapshot_bytes",43],["abandon_status",4],["rejected_path_identity_preserved",1],["receipt_state",3],["close",0]],"wrong-bytes":[["actual_sigkill",9],["different_process",1],["actual_snapshot_bytes",43],["abandon_status",4],["rejected_path_identity_preserved",1],["receipt_state",3],["close",0]],"extra-entry":[["actual_sigkill",9],["different_process",1],["actual_snapshot_bytes",43],["abandon_status",4],["rejected_path_identity_preserved",1],["receipt_state",3],["close",0]],"payload-replaced":[["actual_sigkill",9],["different_process",1],["actual_snapshot_bytes",43],["abandon_status",4],["rejected_path_identity_preserved",1],["receipt_state",3],["close",0]],"directory-replaced":[["actual_sigkill",9],["different_process",1],["actual_snapshot_bytes",43],["abandon_status",4],["rejected_path_identity_preserved",1],["receipt_state",3],["close",0]],"payload-symlink":[["actual_sigkill",9],["different_process",1],["actual_snapshot_bytes",43],["abandon_status",4],["rejected_path_identity_preserved",1],["receipt_state",3],["close",0]],"directory-symlink":[["actual_sigkill",9],["different_process",1],["actual_snapshot_bytes",43],["abandon_status",4],["rejected_path_identity_preserved",1],["receipt_state",3],["close",0]],"extra-hardlink":[["actual_sigkill",9],["different_process",1],["actual_snapshot_bytes",43],["abandon_status",4],["rejected_path_identity_preserved",1],["receipt_state",3],["close",0]],"foreign-payload-owner":[["actual_sigkill",9],["different_process",1],["actual_snapshot_bytes",43],["actual_foreign_uid",0],["abandon_status",4],["rejected_path_identity_preserved",1],["receipt_state",3],["close",0]],"payload-permissions":[["actual_sigkill",9],["different_process",1],["actual_snapshot_bytes",43],["abandon_status",4],["rejected_path_identity_preserved",1],["receipt_state",3],["close",0]],"directory-permissions":[["actual_sigkill",9],["different_process",1],["actual_snapshot_bytes",43],["abandon_status",4],["rejected_path_identity_preserved",1],["receipt_state",3],["close",0]],"sealed-size":[["actual_sigkill",9],["different_process",1],["actual_snapshot_bytes",43],["abandon_status",4],["rejected_path_identity_preserved",1],["receipt_state",3],["close",0]],"legacy-owned-pending":[["actual_sigkill",9],["different_process",1],["actual_snapshot_bytes",43],["old_recover_status",0],["old_pending",1],["payload_preserved",1],["abandon_status",0],["removed",1],["directory_absent",1],["receipt_state",6],["same_identity_idempotent",0],["cleaned_wrong_id_refused",4],["close",0]],"permission-retry":[["actual_sigkill",9],["different_process",1],["actual_snapshot_bytes",43],["permission_failure",2],["pending",1],["native_eacces",13],["payload_preserved",1],["abandon_status",0],["removed",1],["directory_absent",1],["receipt_state",6],["same_identity_idempotent",0],["cleaned_wrong_id_refused",4],["close",0]],"unregistered-residue":[["actual_sigkill",9],["different_process",1],["actual_snapshot_bytes",43],["abandon_status",0],["removed",1],["directory_absent",1],["receipt_state",6],["same_identity_idempotent",0],["cleaned_wrong_id_refused",4],["unknown_residue_preserved",1],["close",0]],"borrow":[["owned_borrow_refused",4],["failed_fd_negative",-1],["active_tx_busy",3],["sealed_borrow",0],["kernel_readonly",0],["exact_snapshot_read",1],["write_refused",-1],["write_errno",9],["root_close_busy",3],["cleanup",0],["borrow_closed_after_cleanup",-1],["closed_errno",9],["tx_close",0],["root_close",0]],"borrow-replaced":[["owned_borrow_refused",4],["failed_fd_negative",-1],["active_tx_busy",3],["replacement_borrow_refused",4],["failed_fd_negative_again",-1],["tx_close",0],["root_close",0]],"lifetime64":[["unchanged_64_slots",64],["slot65_limit",5],["old_recover_status",0],["old_inspected64",64],["old_pending0",0],["root_close",0]],"legacy-published":[["publish",0],["published_flag",1],["new_abandon_published_refused",4],["old_recover_status",0],["old_cleaned1",1],["published_preserved",1],["root_close",0]],"cleanup-kill-payload":[["actual_sigkill",9],["different_process",1],["cleanup_actual_sigkill",9],["resume_after_partial_cleanup",0],["receipt_state",6],["close",0]],"cleanup-kill-directory":[["actual_sigkill",9],["different_process",1],["cleanup_actual_sigkill",9],["resume_after_partial_cleanup",0],["receipt_state",6],["close",0]],"reserved-refused":[["actual_boundary_sigkill",9],["expected_state",1],["new_abandon_refused",4],["old_recover_status",0],["old_pending1",1],["close",0]],"intent-refused":[["actual_boundary_sigkill",9],["expected_state",4],["new_abandon_refused",4],["old_recover_status",0],["old_pending1",1],["close",0]]}
NAMES=list(EXPECTED)
BOUNDARIES=set(NAMES[-4:])
def evaluate(index,rows,binaries):
    errors=[]
    if [str(index.get(k)) for k in ['source','run','attempt']] != evidence_identity():errors.append('source/run/attempt')
    if index.get('cases')!=NAMES or len(rows)!=len(NAMES):errors.append('case set')
    if index.get('euid')==0:errors.append('nonroot')
    for name,data in binaries.items():
        if hashlib.sha256(data).hexdigest()!=index.get('binaries',{}).get(name):errors.append('binary digest')
    for name,row in zip(NAMES,rows):
        if row.get('name')!=name or row.get('exit')!=0 or row.get('timeout'):errors.append(name+': execution')
        binary='f10-stale-boundary-probe' if name in BOUNDARIES else 'f10-stale-probe'
        if row.get('binary')!=binary or row.get('binary_sha256')!=index.get('binaries',{}).get(binary):errors.append(name+': binary identity')
        records=row.get('records',[]);checks=[x for x in records if 'check' in x];summaries=[x for x in records if x.get('summary')]
        if [x.get('check') for x in checks]!=[x[0] for x in EXPECTED[name]]:errors.append(name+': exact assertions')
        for check,expected in zip(checks,EXPECTED[name]):
            if type(check.get('actual')) is not int or check.get('actual')!=expected[1] or check.get('expected')!=expected[1]:errors.append(name+': '+expected[0])
        if len(summaries)!=1 or summaries[0].get('checks')!=len(EXPECTED[name]) or summaries[0].get('failures')!=0 or not summaries[0].get('euid'):errors.append(name+': summary')
    return errors

SNAPSHOT_EXPECTED={"callback-normal":{"put":0,"exit":0,"exact_body":1,"no_redirect_request":1,"conditional":1,"offset":131079},"callback-error":{"put":3,"exit":0,"exact_body":0,"no_redirect_request":1,"conditional":1},"callback-short":{"put":3,"exit":0,"exact_body":0,"no_redirect_request":1,"conditional":1},"callback-overflow":{"put":3,"exit":0,"exact_body":0,"no_redirect_request":1,"conditional":1},"callback-throw":{"put":3,"exit":0,"exact_body":0,"no_redirect_request":1,"conditional":1},"callback-cancel":{"put":7,"exit":0,"exact_body":0,"no_redirect_request":1,"conditional":1},"callback-zero":{"put":1,"exit":0,"exact_body":0,"no_redirect_request":1,"conditional":1,"calls":0},"callback-limit":{"put":1,"exit":0,"exact_body":0,"no_redirect_request":1,"conditional":1,"calls":0},"callback-redirect":{"put":10,"exit":0,"exact_body":0,"no_redirect_request":1,"conditional":1},"callback-exists":{"put":11,"exit":0,"exact_body":1,"no_redirect_request":1,"conditional":1},"managed-normal":{"enable":0,"begin":0,"write":131079,"seal":0,"busy":3,"put":0,"offset":131079,"close":0,"fd_closed":1,"roots":1,"pending":0,"exact_body":1},"held-fd-path-replacement":{"put":0,"offset":131079,"exact_body":1,"close":3,"replacement_preserved":1},"managed-permission-retry":{"close":3,"pending":1,"retry_begin":0,"retry_close":0,"final_pending":0},"managed-owned-kill":{"payload_before":1,"active_old_refused":1,"signal":9,"enable":0,"roots":1,"pending":0,"payload_after":0},"managed-sealed-kill":{"payload_before":1,"active_old_refused":1,"signal":9,"enable":0,"roots":1,"pending":0,"payload_after":0},"registry-v1-upgrade":{"download":0,"v1":1,"readonly_unchanged":1,"begin":0,"v2":1,"old_d_identity":1,"old_refused":4},"registry-16-download-roots":{"prepare":0,"enable":0,"limit":8,"roots":16},"registry-mixed-capacity":{"prepare":0,"enable":0,"64_success":1,"limit":8,"roots":16},"legacy-download-owned-preserved":{"signal":9,"enable":0,"pending":1,"d_payload_preserved":1,"still_v1":1},"registry-refuse-crc":{"enable":3,"preserved":1},"registry-refuse-purpose":{"enable":3,"preserved":1},"registry-refuse-next":{"enable":3,"preserved":1},"migration-kill-before-rename":{"signal":9,"v1_preserved":1,"v2":0,"next":1,"refused":1},"migration-kill-after-rename":{"signal":9,"v1_preserved":0,"v2":1,"next":0,"refused":1},"sync-normal":{"seed":0,"retry_status":0,"retry_outbox":0,"pending":0,"original_unchanged":1,"exact_original":1,"exact_revision":1,"immutable_retry":1,"verified_get":1,"first_exit":0,"first_outbox":0,"first_pushed":1,"first_status":0},"sync-permission":{"seed":0,"retry_status":0,"retry_outbox":0,"pending":0,"original_unchanged":1,"exact_original":1,"exact_revision":1,"immutable_retry":1,"verified_get":1,"first_exit":0,"first_outbox":1,"first_pushed":0},"sync-kill":{"seed":0,"retry_status":0,"retry_outbox":0,"pending":0,"original_unchanged":1,"exact_original":1,"exact_revision":1,"immutable_retry":1,"verified_get":1,"first_exit":-9,"signal":9},"sync-cancel":{"seed":0,"retry_status":0,"retry_outbox":0,"pending":0,"original_unchanged":1,"exact_original":1,"exact_revision":1,"immutable_retry":1,"verified_get":1,"first_exit":0,"first_outbox":1,"first_pushed":0},"sync-lost":{"seed":0,"retry_status":0,"retry_outbox":0,"pending":0,"original_unchanged":1,"exact_original":1,"exact_revision":1,"immutable_retry":1,"verified_get":1,"first_exit":0,"first_outbox":0,"first_pushed":1,"first_status":0}}
def evaluate_snapshot(index,rows,binaries):
    errors=[]
    if [str(index.get(k)) for k in ['source','run','attempt']]!=evidence_identity():errors.append('snapshot source/run/attempt')
    if index.get('cases')!=list(SNAPSHOT_EXPECTED) or [r.get('name') for r in rows]!=list(SNAPSHOT_EXPECTED):errors.append('snapshot case set')
    for name,data in binaries.items():
        if hashlib.sha256(data).hexdigest()!=index.get('binaries',{}).get(name):errors.append('snapshot binary digest')
    for row in rows:
        name=row.get('name');actual=row.get('checks',{})
        if 'exception' in actual:errors.append(name+': exception')
        for key,value in SNAPSHOT_EXPECTED.get(name,{}).items():
            if type(actual.get(key)) is not int or actual[key]!=value:errors.append(name+': '+key)
        if name in ['sync-permission','sync-cancel'] and actual.get('first_status',0)==0:errors.append(name+': false ack')
        # Independently bind network success to server-observed bytes, not the
        # producer's exact_body flag. Callback source is fixed public fixture.
        if name in ['callback-normal','callback-exists','managed-normal','held-fd-path-replacement']:
            if row.get('stored',{}).get('/dav/body')!=hashlib.sha256(b'Q'*131079).hexdigest():errors.append(name+': server bytes')
        if name.startswith('callback-'):
            raw={}
            for text in row.get('raw',[]):
                for line in text.splitlines():
                    if line.startswith('{'):raw.update(json.loads(line))
            if raw.get('put')!=actual.get('put'):errors.append(name+': raw status')
        if name.startswith('sync-'):
            if not any(x.get('method')=='GET' and '/objects/' in x.get('path','') for x in row.get('requests',[])):errors.append(name+': no independent GET')
            if any(x.get('if_none_match')!='*' for x in row.get('requests',[]) if x.get('method')=='PUT'):errors.append(name+': conditional write')
    return errors
def snapshot_audit(root):
    index=json.loads((root/'evidence/snapshot/index.json').read_text())
    rows=[json.loads((root/'evidence/snapshot'/(name+'.json')).read_text()) for name in SNAPSHOT_EXPECTED]
    binaries={name:(root/'probe'/name).read_bytes() for name in ['f10-sync-probe','f10-old-client','f10-managed-boundary-probe']}
    errors=evaluate_snapshot(index,rows,binaries);controls=[]
    guards=[('held-fd-path-replacement','exact_body',0),('managed-permission-retry','pending',0),
      ('managed-owned-kill','signal',0),('registry-v1-upgrade','old_d_identity',0),
      ('registry-v1-upgrade','old_refused',0),('registry-16-download-roots','limit',0),
      ('registry-refuse-purpose','enable',0),('migration-kill-before-rename','v1_preserved',0),
      ('legacy-download-owned-preserved','d_payload_preserved',0),('sync-permission','first_outbox',0)]
    for name,key,value in guards:
        mutated=copy.deepcopy(rows);next(r for r in mutated if r['name']==name)['checks'][key]=value
        reason=name+': '+key;got=evaluate_snapshot(index,mutated,binaries)
        controls.append({'name':reason,'rejected':reason in got and reason not in errors})
    if not all(x['rejected'] for x in controls):errors.append('snapshot negative control accepted')
    return {'snapshot_accepted':not errors,'snapshot_errors':errors,'snapshot_cases':len(rows),
            'snapshot_assertions':sum(len(x) for x in SNAPSHOT_EXPECTED.values()),
            'snapshot_negative_controls':controls,
            'callback_accepted':not any(e.startswith('callback-') for e in errors) and not any(e.startswith('snapshot ') for e in errors),
            'managed_accepted':not any(not e.startswith('sync-') and not e.startswith('callback-') for e in errors),
            'sync_accepted':not any(e.startswith('sync-') for e in errors) and not any(e.startswith('snapshot ') for e in errors)}


GET_EXPECTED={"get-readonly":{"seed":0,"first_exit":0,"cache_empty_after_first":1,"first_get_present":1,"retry_status":0,"retry_outbox":0,"pending":0,"cache_empty_final":1,"source_identity":1,"remote_original_exact":1,"remote_revision_exact":1,"first_status":0,"first_dav":0,"first_outbox":0,"first_pushed":1,"first_wire_absent":0,"cache_mode":320},"get-missing":{"seed":0,"first_exit":0,"cache_empty_after_first":1,"first_get_present":1,"retry_status":0,"retry_outbox":0,"pending":0,"cache_empty_final":1,"source_identity":1,"remote_original_exact":1,"remote_revision_exact":1,"first_status":0,"first_dav":0,"first_outbox":0,"first_pushed":1,"first_wire_absent":0,"no_original_put":1},"get-wrong":{"seed":0,"first_exit":0,"cache_empty_after_first":1,"first_get_present":1,"retry_status":0,"retry_outbox":0,"pending":0,"cache_empty_final":1,"source_identity":1,"remote_original_exact":1,"remote_revision_exact":1,"first_status":5,"first_dav":0,"first_outbox":1,"first_pushed":0,"first_wire_absent":1},"get-short":{"seed":0,"first_exit":0,"cache_empty_after_first":1,"first_get_present":1,"retry_status":0,"retry_outbox":0,"pending":0,"cache_empty_final":1,"source_identity":1,"remote_original_exact":1,"remote_revision_exact":1,"first_status":3,"first_dav":3,"first_outbox":1,"first_pushed":0,"first_wire_absent":1},"get-over":{"seed":0,"first_exit":0,"cache_empty_after_first":1,"first_get_present":1,"retry_status":0,"retry_outbox":0,"pending":0,"cache_empty_final":1,"source_identity":1,"remote_original_exact":1,"remote_revision_exact":1,"first_status":7,"first_dav":8,"first_outbox":1,"first_pushed":0,"first_wire_absent":1},"get-cancel":{"seed":0,"first_exit":0,"cache_empty_after_first":1,"first_get_present":1,"retry_status":0,"retry_outbox":0,"pending":0,"cache_empty_final":1,"source_identity":1,"remote_original_exact":1,"remote_revision_exact":1,"first_status":6,"first_dav":7,"first_outbox":1,"first_pushed":0,"first_wire_absent":1,"get_boundary":1},"get-kill":{"seed":0,"first_exit":-9,"cache_empty_after_first":1,"first_get_present":1,"retry_status":0,"retry_outbox":0,"pending":0,"cache_empty_final":1,"source_identity":1,"remote_original_exact":1,"remote_revision_exact":1,"signal":9,"get_boundary":1,"first_wire_absent":1},"get-consumer-error":{"get":3,"calls":1,"received":0,"exit":0,"no_local_file":1}}
def evaluate_get(index,rows,binaries):
    errors=[]
    if [str(index.get(k)) for k in ['source','run','attempt']]!=evidence_identity():errors.append('get source/run/attempt')
    if index.get('get_cases')!=list(GET_EXPECTED) or [r.get('name') for r in rows]!=list(GET_EXPECTED):errors.append('get case set')
    for name,data in binaries.items():
        if hashlib.sha256(data).hexdigest()!=index.get('binaries',{}).get(name):errors.append('get binary digest')
    content=b'F10 stream verification original|'*4096
    identity=hashlib.sha256(content).hexdigest()
    for row in rows:
        name=row.get('name');actual=row.get('checks',{})
        if 'exception' in actual:errors.append(name+': exception')
        for key,value in GET_EXPECTED.get(name,{}).items():
            if type(actual.get(key)) is not int or actual[key]!=value:errors.append(name+': '+key)
        raw=[]
        for text in row.get('raw',[]):
            merged={}
            for line in text.splitlines():
                if line.startswith('{'):merged.update(json.loads(line))
            raw.append(merged)
        if name=='get-consumer-error':
            if len(raw)!=1 or any(raw[0].get(k)!=actual.get(k) for k in ['get','calls','received']):errors.append(name+': raw status')
            continue
        if len(raw)!=3:errors.append(name+': raw sequence');continue
        if name!='get-kill' and any(raw[1].get(k)!=actual.get('first_'+k) for k in ['status','outbox','pushed']):errors.append(name+': raw status')
        if raw[2].get('status')!=actual.get('retry_status') or raw[2].get('outbox')!=actual.get('retry_outbox'):errors.append(name+': raw retry')
        if actual.get('expected_bytes')!=len(content) or actual.get('expected_sha256')!=identity:errors.append(name+': trusted identity')
        resource='/dav/exreader-sync-v1/objects/'+identity[:2]+'/'+identity+'.txt'
        gets=[r for r in row.get('requests',[]) if r.get('method')=='GET' and r.get('path')==resource]
        sent= b'X'*len(content) if name=='get-wrong' else content[:-1] if name=='get-short' else content+b'X' if name=='get-over' else content
        if not gets or gets[0].get('response_bytes')!=len(sent) or gets[0].get('response_sha256')!=hashlib.sha256(sent).hexdigest():errors.append(name+': actual response')
        if row.get('stored',{}).get(resource)!=identity:errors.append(name+': server original')
        if any(r.get('if_none_match')!='*' for r in row.get('requests',[]) if r.get('method')=='PUT'):errors.append(name+': conditional write')
    return errors
def get_audit(root):
    index=json.loads((root/'evidence/snapshot/index.json').read_text())
    rows=[json.loads((root/'evidence/snapshot'/(name+'.json')).read_text()) for name in GET_EXPECTED]
    binaries={'f10-sync-probe':(root/'probe/f10-sync-probe').read_bytes()}
    errors=evaluate_get(index,rows,binaries);controls=[]
    guards=[('get-readonly','cache_empty_final',0),('get-missing','no_original_put',0),
            ('get-wrong','first_status',0),('get-short','first_status',0),('get-over','first_status',0),
            ('get-cancel','first_outbox',0),('get-kill','signal',0),('get-consumer-error','get',0)]
    for name,key,value in guards:
        changed=copy.deepcopy(rows);next(r for r in changed if r['name']==name)['checks'][key]=value
        reason=name+': '+key;observed=evaluate_get(index,changed,binaries)
        controls.append({'name':reason,'rejected':reason in observed and reason not in errors})
    if not all(c['rejected'] for c in controls):errors.append('get negative control accepted')
    return {'get_accepted':not errors,'get_errors':errors,'get_cases':len(rows),
            'get_assertions':sum(len(x) for x in GET_EXPECTED.values()),'get_negative_controls':controls}


PULL_EXPECTED={"pull-normal":{"first_exit":0,"before_retry_received":1,"cache_exists_first":1,"no_random_cache_first":1,"first_revision_get":1,"first_original_get":1,"target_preserved":1,"recover":0,"recovery_pending":0,"retry_status":0,"retry_received":1,"retry_exact_wire":1,"retry_cleanup_pending":0,"final_cache_exact":1,"no_random_cache_final":1,"no_put":1,"remote_unchanged":1,"final_payloads":0,"published_inode_preserved":1,"first_status":0,"first_dav_code":0,"first_revision_code":0,"first_pulled":1,"first_received":1,"first_exact_wire":1,"first_after_empty":1,"first_cleanup_pending":0},"pull-revision-wrong":{"first_exit":0,"before_retry_received":0,"cache_exists_first":0,"no_random_cache_first":1,"first_revision_get":1,"first_original_get":0,"target_preserved":1,"recover":0,"recovery_pending":0,"retry_status":0,"retry_received":1,"retry_exact_wire":1,"retry_cleanup_pending":0,"final_cache_exact":1,"no_random_cache_final":1,"no_put":1,"remote_unchanged":1,"final_payloads":0,"published_inode_preserved":1,"first_status":4,"first_dav_code":0,"first_revision_code":6,"first_pulled":0,"first_received":0,"first_exact_wire":0,"first_after_empty":1,"first_cleanup_pending":0},"pull-revision-over":{"first_exit":0,"before_retry_received":0,"cache_exists_first":0,"no_random_cache_first":1,"first_revision_get":0,"first_original_get":0,"target_preserved":1,"recover":0,"recovery_pending":0,"retry_status":0,"retry_received":1,"retry_exact_wire":1,"retry_cleanup_pending":0,"final_cache_exact":1,"no_random_cache_final":1,"no_put":1,"remote_unchanged":1,"final_payloads":0,"published_inode_preserved":1,"first_status":5,"first_dav_code":0,"first_revision_code":0,"first_pulled":0,"first_received":0,"first_exact_wire":0,"first_after_empty":1,"first_cleanup_pending":0},"pull-revision-cancel":{"first_exit":0,"before_retry_received":0,"cache_exists_first":0,"no_random_cache_first":1,"first_revision_get":1,"first_original_get":0,"target_preserved":1,"recover":0,"recovery_pending":0,"retry_status":0,"retry_received":1,"retry_exact_wire":1,"retry_cleanup_pending":0,"final_cache_exact":1,"no_random_cache_final":1,"no_put":1,"remote_unchanged":1,"final_payloads":0,"published_inode_preserved":1,"first_status":6,"first_dav_code":7,"first_revision_code":0,"first_pulled":0,"first_received":0,"first_exact_wire":0,"first_after_empty":1,"first_cleanup_pending":0,"get_boundary":1},"pull-revision-kill":{"first_exit":-9,"before_retry_received":0,"cache_exists_first":0,"no_random_cache_first":1,"first_revision_get":1,"first_original_get":0,"target_preserved":1,"recover":0,"recovery_pending":0,"retry_status":0,"retry_received":1,"retry_exact_wire":1,"retry_cleanup_pending":0,"final_cache_exact":1,"no_random_cache_final":1,"no_put":1,"remote_unchanged":1,"final_payloads":0,"published_inode_preserved":1,"signal":9,"get_boundary":1},"pull-original-wrong":{"first_exit":0,"before_retry_received":0,"cache_exists_first":0,"no_random_cache_first":1,"first_revision_get":1,"first_original_get":1,"target_preserved":1,"recover":0,"recovery_pending":0,"retry_status":0,"retry_received":1,"retry_exact_wire":1,"retry_cleanup_pending":0,"final_cache_exact":1,"no_random_cache_final":1,"no_put":1,"remote_unchanged":1,"final_payloads":0,"published_inode_preserved":1,"first_status":5,"first_dav_code":0,"first_revision_code":0,"first_pulled":0,"first_received":0,"first_exact_wire":0,"first_after_empty":1,"first_cleanup_pending":0},"pull-original-short":{"first_exit":0,"before_retry_received":0,"cache_exists_first":0,"no_random_cache_first":1,"first_revision_get":1,"first_original_get":1,"target_preserved":1,"recover":0,"recovery_pending":0,"retry_status":0,"retry_received":1,"retry_exact_wire":1,"retry_cleanup_pending":0,"final_cache_exact":1,"no_random_cache_final":1,"no_put":1,"remote_unchanged":1,"final_payloads":0,"published_inode_preserved":1,"first_status":3,"first_dav_code":3,"first_revision_code":0,"first_pulled":0,"first_received":0,"first_exact_wire":0,"first_after_empty":1,"first_cleanup_pending":0},"pull-original-cancel":{"first_exit":0,"before_retry_received":0,"cache_exists_first":0,"no_random_cache_first":1,"first_revision_get":1,"first_original_get":1,"target_preserved":1,"recover":0,"recovery_pending":0,"retry_status":0,"retry_received":1,"retry_exact_wire":1,"retry_cleanup_pending":0,"final_cache_exact":1,"no_random_cache_final":1,"no_put":1,"remote_unchanged":1,"final_payloads":0,"published_inode_preserved":1,"first_status":6,"first_dav_code":7,"first_revision_code":0,"first_pulled":0,"first_received":0,"first_exact_wire":0,"first_after_empty":1,"first_cleanup_pending":0,"get_boundary":1},"pull-original-kill":{"first_exit":-9,"before_retry_received":0,"cache_exists_first":0,"no_random_cache_first":1,"first_revision_get":1,"first_original_get":1,"target_preserved":1,"recover":0,"recovery_pending":0,"retry_status":0,"retry_received":1,"retry_exact_wire":1,"retry_cleanup_pending":0,"final_cache_exact":1,"no_random_cache_final":1,"no_put":1,"remote_unchanged":1,"final_payloads":0,"published_inode_preserved":1,"signal":9,"get_boundary":1},"pull-cleanup-permission":{"first_exit":0,"before_retry_received":0,"cache_exists_first":1,"no_random_cache_first":1,"first_revision_get":1,"first_original_get":1,"target_preserved":1,"recover":0,"recovery_pending":0,"retry_status":0,"retry_received":1,"retry_exact_wire":1,"retry_cleanup_pending":0,"final_cache_exact":1,"no_random_cache_final":1,"no_put":1,"remote_unchanged":1,"final_payloads":0,"published_inode_preserved":1,"first_status":3,"first_dav_code":3,"first_revision_code":0,"first_pulled":0,"first_received":0,"first_exact_wire":0,"first_after_empty":1,"first_cleanup_pending":1,"get_boundary":1},"pull-target-same":{"first_exit":0,"before_retry_received":1,"cache_exists_first":1,"no_random_cache_first":1,"first_revision_get":1,"first_original_get":1,"target_preserved":1,"recover":0,"recovery_pending":0,"retry_status":0,"retry_received":1,"retry_exact_wire":1,"retry_cleanup_pending":0,"final_cache_exact":1,"no_random_cache_final":1,"no_put":1,"remote_unchanged":1,"final_payloads":0,"published_inode_preserved":1,"first_status":0,"first_dav_code":0,"first_revision_code":0,"first_pulled":1,"first_received":1,"first_exact_wire":1,"first_after_empty":1,"first_cleanup_pending":0,"get_boundary":1},"pull-target-different":{"first_exit":0,"before_retry_received":0,"cache_exists_first":1,"no_random_cache_first":1,"first_revision_get":1,"first_original_get":1,"target_preserved":1,"recover":0,"recovery_pending":0,"retry_status":0,"retry_received":1,"retry_exact_wire":1,"retry_cleanup_pending":0,"final_cache_exact":1,"no_random_cache_final":1,"no_put":1,"remote_unchanged":1,"final_payloads":0,"published_inode_preserved":1,"first_status":5,"first_dav_code":0,"first_revision_code":0,"first_pulled":0,"first_received":0,"first_exact_wire":0,"first_after_empty":1,"first_cleanup_pending":0,"get_boundary":1}}
def evaluate_pull(index,rows,binaries):
    errors=[]
    if [str(index.get(k)) for k in ['source','run','attempt']]!=evidence_identity():errors.append('pull source/run/attempt')
    if index.get('pull_cases')!=list(PULL_EXPECTED) or [r.get('name') for r in rows]!=list(PULL_EXPECTED):errors.append('pull case set')
    for name,data in binaries.items():
        if hashlib.sha256(data).hexdigest()!=index.get('binaries',{}).get(name):errors.append('pull binary digest')
    content=b'F10 pulled original|'*4096;digest=hashlib.sha256(content).hexdigest();leaf=digest+'.txt'
    rev={'version':1,'id':'00'+'0'*29+'1','entity_kind':'book','entity_key':'txt:'+digest,'operation':'put','location_kind':'none','parents':[],
         'payload':{'format':'txt','source_sha256':digest,'source_bytes':len(content),'title':'F10 pull','author':'Fixture','favorite':False}}
    wire=json.dumps(rev,separators=(',',':')).encode();wirehash=hashlib.sha256(wire).hexdigest()
    object_path='/dav/exreader-sync-v1/objects/'+digest[:2]+'/'+leaf
    revision_path='/dav/exreader-sync-v1/revisions/00/'+rev['id']+'-'+wirehash+'.json'
    for row in rows:
        name=row.get('name');actual=row.get('checks',{})
        if 'exception' in actual:errors.append(name+': exception')
        for key,value in PULL_EXPECTED.get(name,{}).items():
            if type(actual.get(key)) is not int or actual[key]!=value:errors.append(name+': '+key)
        raw=[]
        for text in row.get('raw',[]):
            merged={}
            for line in text.splitlines():
                if line.startswith('{'):merged.update(json.loads(line))
            raw.append(merged)
        if len(raw)!=4:errors.append(name+': raw sequence');continue
        if not name.endswith('-kill'):
            for key in ['status','dav_code','revision_code','pulled','received','exact_wire','after_empty','cleanup_pending']:
                if raw[0].get(key)!=actual.get('first_'+key):errors.append(name+': raw '+key)
        if raw[1].get('received')!=actual.get('before_retry_received'):errors.append(name+': raw retained history')
        if raw[2].get('recover')!=actual.get('recover') or raw[2].get('pending')!=actual.get('recovery_pending'):errors.append(name+': raw recovery')
        for key in ['status','received','exact_wire','cleanup_pending']:
            if raw[3].get(key)!=actual.get('retry_'+key):errors.append(name+': raw retry '+key)
        first_names=[leaf] if PULL_EXPECTED[name]['cache_exists_first'] else []
        if actual.get('cache_names_first')!=first_names or actual.get('cache_names_final')!=[leaf]:errors.append(name+': cache names')
        first_hash=hashlib.sha256(b'X'*len(content)).hexdigest() if name=='pull-target-different' else digest if first_names else ''
        if actual.get('cache_sha_first')!=first_hash or actual.get('cache_sha_final')!=digest:errors.append(name+': cache bytes')
        if name in ['pull-target-same','pull-target-different'] and actual.get('target_inode_before')!=actual.get('cache_inode_first'):errors.append(name+': existing inode')
        if name=='pull-cleanup-permission' and actual.get('cache_inode_first')!=actual.get('cache_inode_final'):errors.append(name+': published inode')
        if row.get('stored',{}).get(object_path)!=digest or row.get('stored',{}).get(revision_path)!=wirehash:errors.append(name+': remote bytes')
        requests=row.get('requests',[]);n=actual.get('first_request_count')
        if type(n) is not int or n>len(requests) or (n!=0 if name=='pull-revision-over' else n<1):errors.append(name+': request boundary');continue
        first=requests[:n];revision_get=[x for x in first if x.get('method')=='GET' and x.get('path')==revision_path]
        original_get=[x for x in first if x.get('method')=='GET' and x.get('path')==object_path]
        if bool(revision_get)!=bool(PULL_EXPECTED[name]['first_revision_get']) or bool(original_get)!=bool(PULL_EXPECTED[name]['first_original_get']):errors.append(name+': request sequence')
        if revision_get:
            sent=wire.replace(b'F10 pull',b'G10 pull') if name=='pull-revision-wrong' else wire
            if revision_get[0].get('response_bytes')!=len(sent) or revision_get[0].get('response_sha256')!=hashlib.sha256(sent).hexdigest():errors.append(name+': revision response')
        if original_get:
            sent=b'X'*len(content) if name=='pull-original-wrong' else content[:-1] if name=='pull-original-short' else content
            if original_get[0].get('response_bytes')!=len(sent) or original_get[0].get('response_sha256')!=hashlib.sha256(sent).hexdigest():errors.append(name+': original response')
        if any(x.get('method')=='PUT' for x in requests):errors.append(name+': unexpected remote mutation')
    return errors
def pull_audit(root):
    index=json.loads((root/'evidence/snapshot/index.json').read_text())
    rows=[json.loads((root/'evidence/snapshot'/(name+'.json')).read_text()) for name in PULL_EXPECTED]
    binaries={'f10-sync-probe':(root/'probe/f10-sync-probe').read_bytes()}
    errors=evaluate_pull(index,rows,binaries);controls=[]
    for name in PULL_EXPECTED:
        key='signal' if name.endswith('-kill') else 'target_preserved' if name.startswith('pull-target-') else 'first_cleanup_pending' if name=='pull-cleanup-permission' else 'no_random_cache_final' if name=='pull-normal' else 'first_status'
        value=0 if PULL_EXPECTED[name][key]!=0 else 99
        mutated=copy.deepcopy(rows);next(r for r in mutated if r['name']==name)['checks'][key]=value
        reason=name+': '+key;got=evaluate_pull(index,mutated,binaries)
        controls.append({'name':reason,'rejected':reason in got and reason not in errors})
    if not all(c['rejected'] for c in controls):errors.append('pull negative control accepted')
    return {'pull_accepted':not errors,'pull_errors':errors,'pull_cases':len(rows),
            'pull_assertions':sum(len(x) for x in PULL_EXPECTED.values()),'pull_negative_controls':controls}

def main():
    a=argparse.ArgumentParser();a.add_argument('--input',type=Path,required=True);a.add_argument('--output',type=Path,required=True);args=a.parse_args()
    assert os.environ.get('GITHUB_ACTIONS')=='true'
    out=args.output;out.mkdir(parents=True,exist_ok=True);root=args.input
    source,run,attempt=evidence_identity()
    result={'source':source,'run':run,'attempt':attempt,'api_accepted':False,'full_f10_complete':False}
    if os.environ.get('F10_FIXED_PRODUCER_AUDIT')=='1':
        result.update(audit_source=os.environ['GITHUB_SHA'],audit_run=os.environ['GITHUB_RUN_ID'],audit_attempt=os.environ['GITHUB_RUN_ATTEMPT'],
                      mode='fixed original producer re-audit; no product rerun',producer_artifact=13066057477)
    try:
        index=json.loads((root/'evidence/index.json').read_text())
        rows=[json.loads((root/'evidence'/n/'observation.json').read_text()) for n in NAMES]
        binaries={n:(root/'probe'/n).read_bytes() for n in ['f10-stale-probe','f10-stale-boundary-probe']}
        errors=evaluate(index,rows,binaries)
        # Bind parsed observations to original ordinary stdout, not booleans alone.
        for name,row in zip(NAMES,rows):
            actual=[json.loads(l) for l in (root/'evidence'/name/'stdout.log').read_text().splitlines() if l.startswith('{')]
            if actual!=row['records']:errors.append(name+': raw log mismatch')
        controls=[]
        def replace(rows,name,key,value):
            row=rows[NAMES.index(name)]
            next(x for x in row['records'] if x.get('check')==key)['actual']=value
        mutations=[
          ('source','source/run/attempt',lambda i,r:i.update(source='0'*40)),
          ('consumer','binary digest',lambda i,r:i['binaries'].update({'f10-stale-probe':'0'*64})),
          ('death','owned-kill: actual_sigkill',lambda i,r:replace(r,'owned-kill','actual_sigkill',0)),
          ('permission','permission-retry: native_eacces',lambda i,r:replace(r,'permission-retry','native_eacces',0)),
          ('identity','wrong-id: abandon_status',lambda i,r:replace(r,'wrong-id','abandon_status',0)),
          ('capacity','lifetime64: slot65_limit',lambda i,r:replace(r,'lifetime64','slot65_limit',0)),
          ('readonly','borrow: kernel_readonly',lambda i,r:replace(r,'borrow','kernel_readonly',2)),
          ('ambiguous','intent-refused: new_abandon_refused',lambda i,r:replace(r,'intent-refused','new_abandon_refused',0))]
        for name,reason,mutate in mutations:
            i=copy.deepcopy(index);r=copy.deepcopy(rows);mutate(i,r);reasons=evaluate(i,r,binaries)
            controls.append({'name':name,'expected_reason':reason,'rejected':reason in reasons and reason not in errors})
        if not all(c['rejected'] for c in controls):errors.append('negative control accepted')
        result.update(api_accepted=not errors,errors=errors,cases=len(NAMES),assertions=sum(len(x) for x in EXPECTED.values()),negative_controls=controls,
                      installed_consumer_cases=len(NAMES)-len(BOUNDARIES),instrumented_boundary_cases=len(BOUNDARIES),
                      limits=['POSIX Linux only','Core API verdict alone does not grant sync; phase B has separate callback/managed/sync verdicts','No SDK or host UI acceptance','Cooperative private namespace, not malicious same-UID attacker resistance','SIGKILL not hardware power loss','Fixed 64 lifetime slots unchanged'])
    except (OSError,ValueError,KeyError,TypeError,StopIteration) as e:result.update(errors=['incomplete evidence: '+type(e).__name__])
    try:result.update(snapshot_audit(root))
    except (OSError,ValueError,KeyError,TypeError,StopIteration) as e:result.update(snapshot_accepted=False,snapshot_errors=['incomplete snapshot evidence: '+type(e).__name__])
    try:result.update(get_audit(root))
    except (OSError,ValueError,KeyError,TypeError,StopIteration) as e:result.update(get_accepted=False,get_errors=['incomplete GET evidence: '+type(e).__name__])
    try:result.update(pull_audit(root))
    except (OSError,ValueError,KeyError,TypeError,StopIteration) as e:result.update(pull_accepted=False,pull_errors=['incomplete pull evidence: '+type(e).__name__])
    result['full_f10_complete']=False
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
    return 0 if result['api_accepted'] and result.get('snapshot_accepted') and result.get('get_accepted') and result.get('pull_accepted') else 1
if __name__=='__main__':raise SystemExit(main())
