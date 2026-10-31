# SPDX-License-Identifier: MIT
"""Independent deterministic interpretation of raw observations, Actions only."""
import argparse,copy,hashlib,json,os,sys
from pathlib import Path
NAMES=['normal','close-join','eacces-cleanup','kill-and-restart','target-created-during-download','existing-same-hash','existing-different-hash','link-refusal-directory']
def evaluate(index,rows,program):
    errors=[]
    if list(index['cases'])!=NAMES: errors.append('exact eight cases')
    if index['source']!=os.environ['GITHUB_SHA'] or str(index['run'])!=os.environ['GITHUB_RUN_ID'] or str(index['attempt'])!=os.environ['GITHUB_RUN_ATTEMPT']:errors.append('source/run/attempt')
    if hashlib.sha256(program).hexdigest()!=index['program_sha256']: errors.append('actual consumer digest')
    for name,row in zip(NAMES,rows):
        if row.get('name')!=name or not row.get('observation_complete'):errors.append(name+': incomplete')
        if any(str(row.get(k))!=str(index[k]) for k in ['source','run','attempt','program_sha256']):errors.append(name+': identity')
        if row.get('euid')==0:errors.append(name+': root')
        if row.get('original_before')!=row.get('original_after'):errors.append(name+': original changed')
        if row.get('synthetic_secret_leaks'):errors.append(name+': synthetic secret leaked')
        if not row.get('requests') or not all(x['authenticated'] for x in row['requests']):errors.append(name+': authenticated native requests')
    normal,closed,eacces,killed,race=rows[:5]
    if normal.get('exit_code')!=0 or not normal.get('result') or normal['result'][-1]['status']!=0 or normal['result'][-1]['pushed']!=1:errors.append('normal baseline')
    if not closed.get('close_join_passed') or not any(x.get('state')==7 for x in closed.get('views',[])):errors.append('close before destroy')
    if eacces.get('canary_errno')!=13:errors.append('real EACCES')
    if killed.get('exit_code')!=-9 or not killed.get('killed_residual') or killed.get('restart',{}).get('exit_code')!=0:errors.append('real death/restart')
    if not race.get('concurrent_target') or not race.get('target_after'):errors.append('concurrent target evidence')
    for row in rows[5:]:
        if not row.get('concurrent_target') or not row.get('target_after') or not row.get('result'):errors.append(row['name']+': target evidence')
    return errors
def main():
    a=argparse.ArgumentParser();a.add_argument('--input',type=Path,required=True);a.add_argument('--output',type=Path,required=True);args=a.parse_args()
    assert os.environ.get('GITHUB_ACTIONS')=='true'
    root=args.input;out=args.output;out.mkdir(parents=True,exist_ok=True)
    required=[root/'evidence/index.json',root/'probe/f10-probe']+[root/'evidence'/n/'observation.json' for n in NAMES]
    missing=[str(p.relative_to(root)) for p in required if not p.is_file()]
    if missing:
        result={'source':os.environ['GITHUB_SHA'],'run':os.environ['GITHUB_RUN_ID'],'attempt':os.environ['GITHUB_RUN_ATTEMPT'],'evidence_consistent':False,'safety_passed':False,'full_f10_complete':False,'errors':['producer evidence missing'],'missing':missing,'negative_controls':[]}
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result));return 1
    index=json.loads((root/'evidence/index.json').read_text())
    rows=[json.loads((root/'evidence'/n/'observation.json').read_text()) for n in NAMES]
    program=(root/'probe/f10-probe').read_bytes()
    errors=evaluate(index,rows,program)
    controls=[]
    variants=[('source','source/run/attempt',lambda i,r:i.update(source='0'*40)),('consumer','actual consumer digest',lambda i,r:i.update(program_sha256='0'*64)),
              ('permission','real EACCES',lambda i,r:r[2].update(canary_errno=0)),('kill','real death/restart',lambda i,r:r[3].update(exit_code=0)),
              ('join','close before destroy',lambda i,r:r[1].update(close_join_passed=False)),('original','normal: original changed',lambda i,r:r[0].update(original_after='0'*64))]
    for name,expected_reason,mutate in variants:
        i=copy.deepcopy(index);r=copy.deepcopy(rows);mutate(i,r)
        reasons=evaluate(i,r,program);controls.append({'name':name,'rejected':expected_reason in reasons and expected_reason not in errors,'expected_reason':expected_reason,'reasons':reasons})
    if not all(x['rejected'] for x in controls):errors.append('negative control accepted')
    temps=lambda r:[x for x in r.get('after',[]) if x['name'].endswith('.tmp')]
    findings=[
        {'requirement':'normal successful operation removes its temporaries','passed':not temps(rows[0]),'observed':temps(rows[0])},
        {'requirement':'close waits for worker release before destroy','passed':rows[1].get('close_join_passed',False)},
        {'requirement':'EACCES cleanup observation: no temporary residue at operation return','passed':not temps(rows[2]),'observed':temps(rows[2]),'note':'Residue is an observed gap, not proof all retained files are unsafe. Public result has no cleanup-owner/status field; owner policy/recovery still requires implementation and verification.'},
        {'requirement':'process-death leftovers handled by next operation','passed':not temps(rows[3]),'observed':temps(rows[3])},
        {'requirement':'concurrently appeared target not overwritten','passed':rows[4].get('concurrent_target')==rows[4].get('target_after'),'observed':{'before':rows[4].get('concurrent_target'),'after':rows[4].get('target_after')}}
    ]
    no_replace=[]
    for row in rows[4:]:
        status=row.get('result',[{}])[-1].get('status')
        expected_status=0 if row['name']=='existing-same-hash' else 5
        no_replace.append({'name':row['name'],'passed':row.get('concurrent_target')==row.get('target_after') and status==expected_status and not temps(row),'status':status,'expected_status':expected_status,'temporary_residue':temps(row)})
    result={'source':index['source'],'run':index['run'],'attempt':index['attempt'],'evidence_consistent':not errors,'errors':errors,
            'no_replace_passed':not errors and all(x['passed'] for x in no_replace),'no_replace_cases':no_replace,'findings':findings,'negative_controls':controls,'safety_passed':not errors and all(x['passed'] for x in findings) and all(x['passed'] for x in no_replace),
            'full_f10_complete':False,'scope':index['scope'],
            'limits':['No reading SDK imported or real host UI operated','No OS secure storage failure or lock-screen tests','No managed transport integration in this baseline','SIGKILL is not hardware power loss','Only high-level cache no-replace production change; original assertions retained','Stable private directory contract, not adversarial same-UID race protection','Windows native identity branch not runtime tested in this Linux round']}
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))
    # A reproducible defect deliberately remains a failed safety gate.
    return 0 if result['safety_passed'] else 1
if __name__=='__main__':sys.exit(main())
