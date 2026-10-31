# SPDX-License-Identifier: MIT
import argparse,copy,hashlib,json,os
from pathlib import Path
EXPECTED={"owned-kill":[["actual_sigkill",9],["different_process",1],["actual_snapshot_bytes",43],["abandon_status",0],["removed",1],["directory_absent",1],["receipt_state",6],["same_identity_idempotent",0],["cleaned_wrong_id_refused",4],["close",0]],"sealed-kill":[["actual_sigkill",9],["different_process",1],["actual_snapshot_bytes",43],["abandon_status",0],["removed",1],["directory_absent",1],["receipt_state",6],["same_identity_idempotent",0],["cleaned_wrong_id_refused",4],["close",0]],"active-owner":[["active_owner_busy",3],["actual_sigkill",9],["different_process",1],["actual_snapshot_bytes",43],["abandon_status",0],["removed",1],["directory_absent",1],["receipt_state",6],["same_identity_idempotent",0],["cleaned_wrong_id_refused",4],["close",0]],"historical-device":[["actual_sigkill",9],["different_process",1],["actual_snapshot_bytes",43],["abandon_status",0],["removed",1],["directory_absent",1],["receipt_state",6],["same_identity_idempotent",0],["cleaned_wrong_id_refused",4],["close",0]],"wrong-uuid":[["actual_sigkill",9],["different_process",1],["actual_snapshot_bytes",43],["open_refused",4],["payload_preserved",1]],"corrupt-receipt":[["actual_sigkill",9],["different_process",1],["actual_snapshot_bytes",43],["open_refused",4],["payload_preserved",1]],"residual-receipt-next":[["actual_sigkill",9],["different_process",1],["actual_snapshot_bytes",43],["open_refused",4],["payload_preserved",1]],"wrong-id":[["actual_sigkill",9],["different_process",1],["actual_snapshot_bytes",43],["abandon_status",4],["rejected_path_identity_preserved",1],["receipt_state",3],["close",0]],"wrong-slot":[["actual_sigkill",9],["different_process",1],["actual_snapshot_bytes",43],["abandon_status",1],["rejected_path_identity_preserved",1],["receipt_state",3],["close",0]],"wrong-inode":[["actual_sigkill",9],["different_process",1],["actual_snapshot_bytes",43],["abandon_status",4],["rejected_path_identity_preserved",1],["receipt_state",3],["close",0]],"wrong-state":[["actual_sigkill",9],["different_process",1],["actual_snapshot_bytes",43],["abandon_status",4],["rejected_path_identity_preserved",1],["receipt_state",3],["close",0]],"wrong-bytes":[["actual_sigkill",9],["different_process",1],["actual_snapshot_bytes",43],["abandon_status",4],["rejected_path_identity_preserved",1],["receipt_state",3],["close",0]],"extra-entry":[["actual_sigkill",9],["different_process",1],["actual_snapshot_bytes",43],["abandon_status",4],["rejected_path_identity_preserved",1],["receipt_state",3],["close",0]],"payload-replaced":[["actual_sigkill",9],["different_process",1],["actual_snapshot_bytes",43],["abandon_status",4],["rejected_path_identity_preserved",1],["receipt_state",3],["close",0]],"directory-replaced":[["actual_sigkill",9],["different_process",1],["actual_snapshot_bytes",43],["abandon_status",4],["rejected_path_identity_preserved",1],["receipt_state",3],["close",0]],"payload-symlink":[["actual_sigkill",9],["different_process",1],["actual_snapshot_bytes",43],["abandon_status",4],["rejected_path_identity_preserved",1],["receipt_state",3],["close",0]],"directory-symlink":[["actual_sigkill",9],["different_process",1],["actual_snapshot_bytes",43],["abandon_status",4],["rejected_path_identity_preserved",1],["receipt_state",3],["close",0]],"extra-hardlink":[["actual_sigkill",9],["different_process",1],["actual_snapshot_bytes",43],["abandon_status",4],["rejected_path_identity_preserved",1],["receipt_state",3],["close",0]],"foreign-payload-owner":[["actual_sigkill",9],["different_process",1],["actual_snapshot_bytes",43],["actual_foreign_uid",0],["abandon_status",4],["rejected_path_identity_preserved",1],["receipt_state",3],["close",0]],"payload-permissions":[["actual_sigkill",9],["different_process",1],["actual_snapshot_bytes",43],["abandon_status",4],["rejected_path_identity_preserved",1],["receipt_state",3],["close",0]],"directory-permissions":[["actual_sigkill",9],["different_process",1],["actual_snapshot_bytes",43],["abandon_status",4],["rejected_path_identity_preserved",1],["receipt_state",3],["close",0]],"sealed-size":[["actual_sigkill",9],["different_process",1],["actual_snapshot_bytes",43],["abandon_status",4],["rejected_path_identity_preserved",1],["receipt_state",3],["close",0]],"legacy-owned-pending":[["actual_sigkill",9],["different_process",1],["actual_snapshot_bytes",43],["old_recover_status",0],["old_pending",1],["payload_preserved",1],["abandon_status",0],["removed",1],["directory_absent",1],["receipt_state",6],["same_identity_idempotent",0],["cleaned_wrong_id_refused",4],["close",0]],"permission-retry":[["actual_sigkill",9],["different_process",1],["actual_snapshot_bytes",43],["permission_failure",2],["pending",1],["native_eacces",13],["payload_preserved",1],["abandon_status",0],["removed",1],["directory_absent",1],["receipt_state",6],["same_identity_idempotent",0],["cleaned_wrong_id_refused",4],["close",0]],"unregistered-residue":[["actual_sigkill",9],["different_process",1],["actual_snapshot_bytes",43],["abandon_status",0],["removed",1],["directory_absent",1],["receipt_state",6],["same_identity_idempotent",0],["cleaned_wrong_id_refused",4],["unknown_residue_preserved",1],["close",0]],"borrow":[["owned_borrow_refused",4],["failed_fd_negative",-1],["active_tx_busy",3],["sealed_borrow",0],["kernel_readonly",0],["exact_snapshot_read",1],["write_refused",-1],["write_errno",9],["root_close_busy",3],["cleanup",0],["borrow_closed_after_cleanup",-1],["closed_errno",9],["tx_close",0],["root_close",0]],"borrow-replaced":[["owned_borrow_refused",4],["failed_fd_negative",-1],["active_tx_busy",3],["replacement_borrow_refused",4],["failed_fd_negative_again",-1],["tx_close",0],["root_close",0]],"lifetime64":[["unchanged_64_slots",64],["slot65_limit",5],["old_recover_status",0],["old_inspected64",64],["old_pending0",0],["root_close",0]],"legacy-published":[["publish",0],["published_flag",1],["new_abandon_published_refused",4],["old_recover_status",0],["old_cleaned1",1],["published_preserved",1],["root_close",0]],"cleanup-kill-payload":[["actual_sigkill",9],["different_process",1],["cleanup_actual_sigkill",9],["resume_after_partial_cleanup",0],["receipt_state",6],["close",0]],"cleanup-kill-directory":[["actual_sigkill",9],["different_process",1],["cleanup_actual_sigkill",9],["resume_after_partial_cleanup",0],["receipt_state",6],["close",0]],"reserved-refused":[["actual_boundary_sigkill",9],["expected_state",1],["new_abandon_refused",4],["old_recover_status",0],["old_pending1",1],["close",0]],"intent-refused":[["actual_boundary_sigkill",9],["expected_state",4],["new_abandon_refused",4],["old_recover_status",0],["old_pending1",1],["close",0]]}
NAMES=list(EXPECTED)
BOUNDARIES=set(NAMES[-4:])
def evaluate(index,rows,binaries):
    errors=[]
    if [str(index.get(k)) for k in ['source','run','attempt']] != [os.environ['GITHUB_SHA'],os.environ['GITHUB_RUN_ID'],os.environ['GITHUB_RUN_ATTEMPT']]:errors.append('source/run/attempt')
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
def main():
    a=argparse.ArgumentParser();a.add_argument('--input',type=Path,required=True);a.add_argument('--output',type=Path,required=True);args=a.parse_args()
    assert os.environ.get('GITHUB_ACTIONS')=='true'
    out=args.output;out.mkdir(parents=True,exist_ok=True);root=args.input
    result={'source':os.environ['GITHUB_SHA'],'run':os.environ['GITHUB_RUN_ID'],'attempt':os.environ['GITHUB_RUN_ATTEMPT'],'api_accepted':False,'full_f10_complete':False}
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
                      limits=['POSIX Linux only','No sync snapshot integration','No SDK or host UI acceptance','Cooperative private namespace, not malicious same-UID attacker resistance','SIGKILL not hardware power loss','Fixed 64 lifetime slots unchanged'])
    except (OSError,ValueError,KeyError,TypeError,StopIteration) as e:result.update(errors=['incomplete evidence: '+type(e).__name__])
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
    return 0 if result['api_accepted'] else 1
if __name__=='__main__':raise SystemExit(main())
