#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actions-only organization evidence corruption refusals, restoring each original."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--evidence',type=Path,required=True);root=p.parse_args().evidence
    if os.environ.get('GITHUB_ACTIONS')!='true':raise SystemExit('Actions only')
    checks=[]
    def invoke(name,expected):
        run=subprocess.run([sys.executable,'tools/check_reader_organization_android.py','--evidence',str(root),'--all-exits'],capture_output=True,text=True)
        passed=(run.returncode==0)==expected;checks.append({'id':name,'passed':passed})
        if not passed:raise ValueError(name+': '+run.stdout[-1000:]+run.stderr[-500:])
    def alter(path,name,change):
        raw=path.read_bytes()
        try:path.write_bytes(change(raw));invoke(name,False)
        finally:path.write_bytes(raw)
    def edit(path,name,change):
        def replace(raw):value=json.loads(raw);change(value);return json.dumps(value).encode()
        alter(path,name,replace)
    report={key:os.environ[env] for key,env in (('source_sha','GITHUB_SHA'),('run_id','GITHUB_RUN_ID'),('attempt','GITHUB_RUN_ATTEMPT'))}
    report.update(accepted=False,checks=checks,problems=[])
    try:
        invoke('positive',True)
        edit(root/'device-report.json','old_native_source',lambda v:v.update(source_sha='0'*40))
        edit(root/'device-report.json','missing_native_case',lambda v:v['checks'].pop())
        edit(root/'device-report.json','failed_native_case',lambda v:v['checks'][0].update({'pass':False}))
        edit(root/'ui/validation.json','missing_ui_case',lambda v:v['cases'].pop())
        edit(root/'ui/validation.json','duplicate_ui_case',lambda v:v['cases'].append(v['cases'][0]))
        edit(root/'ui/validation.json','skipped_ui_case',lambda v:v.update(skipped=1))
        edit(root/'ui/validation.json','same_process_retry',lambda v:v['cases'][-1]['detail'].update(new_pid=v['cases'][-1]['detail']['old_pid']))
        edit(root/'phases/verified.json','changed_retry_revision',lambda v:v.update(revision='0'*32))
        edit(root/'phases/refused.json','incomplete_durable_intent',lambda v:v['intent'].pop('name'))
        shot=next((root/'ui/shots').glob('*.png'));alter(shot,'missing_ui_screenshot',lambda raw:b'')
        alter(root/'instrumentation.txt','skipped_manual_case',lambda raw:raw.replace(b'INSTRUMENTATION_STATUS_CODE: 0',b'INSTRUMENTATION_STATUS_CODE: -3',1))
        def skip(raw):tree=ET.fromstring(raw);ET.SubElement(next(tree.iter('testcase')),'skipped');return ET.tostring(tree)
        alter(next((root/'reports').rglob('*.xml')),'skipped_native_xml',skip)
        edit(Path('build/owner-android/result.json'),'original_owner_required',lambda v:v.update(accepted=False))
        invoke('restored_positive',True);report['accepted']=True
    except Exception as error:report['problems'].append(type(error).__name__+': '+str(error))
    report['script_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest();(root/'gate-review.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)
    if not report['accepted']:raise SystemExit(1)


if __name__=='__main__':main()
