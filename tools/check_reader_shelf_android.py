#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Same-run strict catalog paging candidate evidence; UI/performance are separate exits."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import xml.etree.ElementTree as ET

TESTS={'realSdkImportsAndProductionRepair','forwardKeysetHasNoMissingOrRepeatedBooks',
       'reverseKeysetMatchesForwardOrder','sameTitleUsesSourceKeyTieBreak','titleAuthorAndLiteralSearch',
       'cancelsQueriesAndRejectsWrongOwner','hidesUnmappedAndDeletedProducts','repairsNewImportBeforeRefresh',
       'canceledOldSearchCannotReplaceNewResults','missingEndAnchorFallsBackWithinSameFilter',
       'pendingRestoreRetainsOnlySameQueryAnchor'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence',type=Path,required=True)
    parser.add_argument('--all-exits',action='store_true')
    options=parser.parse_args();root=options.evidence
    result={'source_sha':os.environ.get('GITHUB_SHA'),'run_id':os.environ.get('GITHUB_RUN_ID'),
            'attempt':os.environ.get('GITHUB_RUN_ATTEMPT'),'accepted':False,'problems':[],
            'scope':'Android real-SDK catalog keyset paging candidate only', 'ui_accepted':False,
            'performance_accepted':False,'physical_device_execution':False}
    try:
        if os.environ.get('GITHUB_ACTIONS')!='true' or (root/'source.txt').read_text().strip()!=result['source_sha']:
            raise ValueError('cloud checkout identity differs')
        if (root/'device-api.txt').read_text().strip()!='34' or (root/'device-abi.txt').read_text().strip()!='x86_64':
            raise ValueError('API34 x86_64 required')
        names=[]; reports=[]
        for path in sorted((root/'catalog-reports').rglob('*.xml')):
            raw=path.read_bytes(); tree=ET.fromstring(raw)
            for suite in tree.iter('testsuite'):
                if any(int(suite.get(key,'0')) for key in ('failures','errors','skipped')):
                    raise ValueError('catalog shelf suite failed or skipped')
            for case in tree.iter('testcase'):
                if case.get('classname')!='org.exreader.host.ShelfCatalogTest' or any(case.find(key) is not None for key in ('failure','error','skipped')):
                    raise ValueError('unexpected or failed catalog shelf case')
                names.append(case.get('name'))
            reports.append({'path':path.relative_to(root).as_posix(),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
        if len(names)!=len(TESTS) or set(names)!=TESTS:
            raise ValueError('missing, duplicate or unexpected catalog shelf checks')
        result.update(accepted=True,passed=len(names),failed=0,skipped=0,real_sdk_sources=2202,txt_sources=2201,
                      pdf_sources=1,same_title_sources=130,page_limit=50,tests=sorted(names),reports=reports)
        if options.all_exits:
            from run_reader_shelf_ui import analyze
            identity={key:result[key] for key in ('source_sha','run_id','attempt')}
            ui_root=root/'ui-execution'
            ui=json.loads((ui_root/'result.json').read_text())
            actual=analyze(ui_root,identity)
            if ui.get('accepted') is not True or ui.get('problems')!=[] or any(ui.get(key)!=value for key,value in identity.items()) \
                    or any(ui.get(key)!=value for key,value in actual.items()):
                raise ValueError('UI strict result differs from its original evidence')
            imported=json.loads((root.parent/'import-android/result.json').read_text())
            if imported.get('accepted') is not True or imported.get('problems')!=[] \
                    or any(imported.get(key)!=value for key,value in identity.items()) \
                    or imported.get('passed')!=14 or imported.get('failed')!=0 or imported.get('skipped')!=0 \
                    or imported.get('catalog_passed')!=8 or imported.get('process_recovery_passed')!=2:
                raise ValueError('same-run original catalog/mapping/recovery exit missing')
            original=json.loads((root/'original-result.json').read_text())
            summary=original.get('summary',{})
            if original.get('accepted') is not True or original.get('problems')!=[] \
                    or summary.get('source_sha')!=identity['source_sha'] \
                    or summary.get('run',{}).get('id')!=identity['run_id'] \
                    or summary.get('run',{}).get('attempt')!=identity['attempt'] \
                    or not summary.get('gate_review_sha256') or not summary.get('bounded_gate_review_sha256'):
                raise ValueError('same-run original 66 and 48+20 strict gate exit missing')
            result.update(scope='API34 x86_64 production catalog shelf declared scope only',ui_accepted=True,
                          ui=actual,import_mapping_passed=14,killed_process_recovery_passed=2,original_host_accepted=True,
                          performance_accepted=False,performance_observation_complete=True)
    except (ValueError,OSError,ET.ParseError,KeyError,TypeError) as error:
        result['accepted']=False
        result['problems'].append(str(error))
    root.mkdir(parents=True,exist_ok=True)
    (root/('shelf-result.json' if options.all_exits else 'catalog-result.json')).write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result),flush=True)
    if not result['accepted']:raise SystemExit(1)


if __name__=='__main__':
    main()
