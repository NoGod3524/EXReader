#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Reject altered copies of the same-run shelf exits; runs in CI after a real positive run."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--evidence',type=Path,required=True)
    root=parser.parse_args().evidence
    if os.environ.get('GITHUB_ACTIONS')!='true':raise SystemExit('cloud-only evidence regression')
    checks=[]
    def invoke(name,accepted):
        call=subprocess.run([sys.executable,'tools/check_reader_shelf_android.py','--evidence',str(root),'--all-exits'],capture_output=True,timeout=120)
        value=json.loads((root/'shelf-result.json').read_text())
        passed=(call.returncode==0)==accepted and value.get('accepted') is accepted
        checks.append({'name':name,'passed':passed,'expected_accepted':accepted})
        if not passed:raise ValueError('shelf evidence gate regression: '+name)
    def alter(path,change,name):
        original=path.read_bytes()
        try:path.write_bytes(change(original));invoke(name,False)
        finally:path.write_bytes(original)
    def edit(path,name,change):
        def replacement(raw):
            value=json.loads(raw);change(value);return (json.dumps(value)+'\n').encode()
        alter(path,replacement,name)
    result={'source_sha':os.environ['GITHUB_SHA'],'run_id':os.environ['GITHUB_RUN_ID'],'attempt':os.environ['GITHUB_RUN_ATTEMPT'],
            'accepted':False,'checks':checks,'problems':[],'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    try:
        invoke('positive',True)
        ui=root/'ui-execution/result.json';mapping=root.parent/'import-android/result.json';original=root/'original-result.json'
        edit(ui,'ui_rejected',lambda value:value.update(accepted=False))
        edit(ui,'ui_old_source',lambda value:value.update(source_sha='0'*40))
        edit(root/'ui-execution/ui/validation.json','ui_skipped_case',lambda value:value['cases'][0].update(status='skip'))
        shot=next((root/'ui-execution/ui/shots').glob('*.png'));alter(shot,lambda raw:b'','missing_ui_screenshot')
        trace=next((root/'ui-execution/windows').glob('*.jsonl'));alter(trace,lambda raw:raw+b'{','truncated_window_trace')
        edit(root/'ui-execution/pss-sampling.json','pss_sampler_error',lambda value:value['errors'].append('controlled refusal probe'))
        edit(mapping,'mapping_rejected',lambda value:value.update(accepted=False))
        edit(mapping,'mapping_old_source',lambda value:value.update(source_sha='0'*40))
        edit(mapping,'missing_process_recovery',lambda value:value.update(process_recovery_passed=1))
        edit(original,'original_host_rejected',lambda value:value.update(accepted=False))
        edit(original,'original_old_source',lambda value:value['summary'].update(source_sha='0'*40))
        edit(original,'missing_original_gate',lambda value:value['summary'].pop('gate_review_sha256',None))
        edit(original,'missing_bounded_gate',lambda value:value['summary'].pop('bounded_gate_review_sha256',None))
        alter(root/'source.txt',lambda raw:b'0'*40+b'\n','wrong_checkout')
        report=next((root/'catalog-reports').rglob('*.xml'));alter(report,lambda raw:b'','missing_catalog_cases')
        invoke('restored_positive',True)
        result['accepted']=True
    except Exception as error:result['problems'].append(type(error).__name__+': '+str(error))
    (root/'shelf-gate-review.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result),flush=True)
    if not result['accepted']:raise SystemExit(1)


if __name__=='__main__':main()
