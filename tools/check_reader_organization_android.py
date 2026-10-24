#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actions-only strict native Android organization UI and recovery evidence."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import xml.etree.ElementTree as ET

NAMES='''completeUnicodeIntentBeforeWrite staleRefusalRetainsExactRequest bootstrapKeepsCurrentUserFields partialBootstrapSurvivesMembershipRefusal legacyMetadataChangeRefusesBootstrap lateCancelPreservesCommittedOutcome groupAndRemovedKeysetsStayBounded membershipDeleteRequiresExplicitRestore'''.split()
UI='''more_create_edit_and_nested_shelves add_books_via_public_original_bootstrap remove_and_explicitly_restore_membership series_ordinal_changes_visible_order group_delete_and_full_removed_restore bounded_forward_reverse_and_removed_pages book_long_press_organize_entry refused_intent_kill_and_exact_ui_retry'''.split()


def require(value,message):
    if not value:raise ValueError(message)


def read(path):return json.loads(path.read_bytes())


def digest(path):
    raw=path.read_bytes();return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}


def identity():
    require(os.environ.get('GITHUB_ACTIONS')=='true','execution is Actions only')
    return {key:os.environ[env] for key,env in (('source_sha','GITHUB_SHA'),('run_id','GITHUB_RUN_ID'),('attempt','GITHUB_RUN_ATTEMPT'))}


def same(value,expected):require(all(value.get(k)==v for k,v in expected.items()),'source/run/attempt differs')


def inspect(root,all_exits):
    expected=identity();same(read(root/'device-report.json'),expected);device=read(root/'device-report.json')
    require(digest(root/'apks/app-debug.apk')==digest(Path('build/owner-android/apks/app-debug.apk')),'organization and original owner applications differ')
    require(device['api']==34 and device['abi']=='x86_64' and device['count']==8 and device['failed']==0,'organization device suite failed')
    require([v['id'] for v in device['checks']]==NAMES and all(v['pass'] is True for v in device['checks']),'native cases failed/missing/repeated')
    xml_cases=[];files={}
    for path in sorted((root/'reports').rglob('*.xml')):
        tree=ET.fromstring(path.read_bytes());files[str(path.relative_to(root))]=digest(path)
        for suite in tree.iter('testsuite'):require(not any(int(suite.get(k,'0')) for k in ('failures','errors','skipped')),'XML suite failed/skipped')
        for case in tree.iter('testcase'):
            require(case.get('classname')=='org.exreader.host.OrganizationTest' and not any(case.find(k) is not None for k in ('failure','error','skipped')),'XML failure or wrong class')
            xml_cases.append(case.get('name'))
    require(len(xml_cases)==8 and set(xml_cases)==set(NAMES),'XML cases missing/repeated')
    raw=(root/'instrumentation.txt').read_text();require('OK (8 tests)' in raw and 'FAILURES' not in raw and re.search(r'^INSTRUMENTATION_CODE: -1\s*$',raw,re.M),'manual instrumentation failed')
    completed=[];status={}
    for line in raw.splitlines():
        if line.startswith('INSTRUMENTATION_STATUS: '):
            key,_,value=line[len('INSTRUMENTATION_STATUS: '):].partition('=');status[key]=value
        elif line.startswith('INSTRUMENTATION_STATUS_CODE: '):
            code=int(line.split(':',1)[1]);require(code in (0,1),'manual failure/skip')
            if code==0:
                require(status.get('class')=='org.exreader.host.OrganizationTest','manual class differs');completed.append(status.get('test'))
            status={}
    require(completed==NAMES,'manual cases missing/reordered/repeated')
    ui=read(root/'ui/validation.json');same(ui,expected)
    require(ui['count']==ui['passed']==8 and ui['failed']==ui['skipped']==0 and [v['id'] for v in ui['cases']]==UI,'UI cases incomplete/failed/skipped')
    for case in ui['cases']:
        same(case,expected);require(case['status']=='pass' and read(root/'ui'/f'{case["id"]}.json')==case,'UI individual case differs')
        shot=root/'ui/shots'/f'{case["id"]}.png';require(shot.read_bytes().startswith(b'\x89PNG\r\n\x1a\n') and shot.stat().st_size>100,'UI screenshot missing/corrupt');files[str(shot.relative_to(root))]=digest(shot)
    detail=ui['cases'][-1]['detail'];require(re.fullmatch(r'[0-9]+',detail['old_pid']) and re.fullmatch(r'[0-9]+',detail['new_pid']) and detail['old_pid']!=detail['new_pid'],'real process change missing')
    seed,refused,verified=(read(root/'phases'/f'{name}.json') for name in ('seed','refused','verified'))
    for report in (seed,refused,verified):same(report,expected)
    require(seed['books']==2 and seed['shelves']==seed['removed_tags']==105,'real source/paging fixture differs')
    intent=refused['intent'];require('refused' in refused['outcome'] and intent['name']=='Killed retry' and intent['heads']==[] and len(intent)==18,'complete refused request absent')
    require(verified['exact_retry'] is True and verified['product_fields_preserved'] is True and verified['revision']==intent['revision'] and verified['entity']==intent['id'],'exact persisted retry differs')
    require(detail['verified']==verified,'UI/native retry witness differs')
    raw_ui=(root/'ui-instrumentation.txt').read_text();require('FAILURES' not in raw_ui and re.search(r'^INSTRUMENTATION_CODE: -1\s*$',raw_ui,re.M),'real UI runner failed')
    for name in ('seed-ui','fault','release-fault','verify-ui'):
        path=root/'seed-ui.txt' if name=='seed-ui' else root/'ui'/f'phase-{name}.txt'
        raw_phase=path.read_text();require('EXR_ORGANIZATION_PHASE '+name in raw_phase and re.search(r'^INSTRUMENTATION_CODE: -1\s*$',raw_phase,re.M),'UI fixture phase failed')
        files[str(path.relative_to(root))]=digest(path)
    files.update({name:digest(root/name) for name in ('device-report.json','instrumentation.txt','ui-instrumentation.txt','ui/validation.json','phases/seed.json','phases/refused.json','phases/verified.json')})
    result={**expected,'accepted':True,'problems':[],'native_checks':8,'real_ui_checks':8,'real_process_retry_checks':1,
        'full_intent_before_submission':True,'complete_observed_heads_retained':True,'page_limit':50,'metadata_history_outbox_same_native_transaction':True,
        'classification_ui_accepted':True,'complete_product':False,'physical_device_execution':False,'evidence_files':files}
    if all_exits:
        owner=read(Path('build/owner-android/result.json'));same(owner,expected)
        require(owner['accepted'] is True and owner['problems']==[] and owner['owner_checks']==17 and owner['typed_kill_checks']==2 and
            owner['original_functional_checks']==112 and owner['original_gate_checks']==87,'original owner/functional/strict gates failed')
        gate=read(Path('build/owner-android/gate-review.json'));same(gate,expected)
        require(gate['accepted'] is True and gate['problems']==[] and len(gate['checks'])==19 and all(v['passed'] for v in gate['checks']),'original owner altered-evidence19 failed')
        result.update(original_owner_checks=17,original_typed_kill_checks=2,original_functional_checks=112,original_gate_checks=87,original_owner_altered_evidence_checks=19)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--evidence',type=Path,required=True);p.add_argument('--all-exits',action='store_true');a=p.parse_args()
    result={**identity(),'accepted':False,'problems':[]}
    try:result=inspect(a.evidence,a.all_exits)
    except (ValueError,OSError,KeyError,TypeError,IndexError,ET.ParseError) as error:result['problems'].append(str(error))
    a.evidence.mkdir(parents=True,exist_ok=True);(a.evidence/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
    if not result['accepted']:raise SystemExit(1)


if __name__=='__main__':main()
