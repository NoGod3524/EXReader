# SPDX-License-Identifier: MIT
"""Actions-only focused native diagnostic; never substitutes for the retained full round."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests/apple_host'))
from collect_evidence import load_results

def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true' and sys.platform == 'darwin'
    parser = argparse.ArgumentParser(); parser.add_argument('--platform', choices=['iphone','ipad'], required=True); args = parser.parse_args()
    out = ROOT / 'build/apple-large-type-focus' / args.platform; out.mkdir(parents=True, exist_ok=False)
    evidence = out / 'evidence'; evidence.mkdir()
    report = dict(source_sha=os.environ['GITHUB_SHA'], run_id=os.environ['GITHUB_RUN_ID'], attempt=os.environ['GITHUB_RUN_ATTEMPT'], platform=args.platform, accepted=False, diagnostic_only=True, physical_device=False, phases=[])
    def run(command, name, timeout=4800):
        with (evidence / (name+'.log')).open('w') as log:
            result = subprocess.run(list(map(str,command)), stdout=log, stderr=subprocess.STDOUT, timeout=timeout)
        lines = (evidence / (name+'.log')).read_text(errors='replace').splitlines()
        print('\n'.join(line for line in lines if 'error:' in line or 'Test Case ' in line or "identifier: 'organization." in line or 'Window (Main)' in line), flush=True)
        if result.returncode: print('\n'.join(lines[-180:]), flush=True)
        return result.returncode
    udid = None
    try:
        roots = list((ROOT/'sdk-input').glob('apple-large-type-focus-sdk-*')); assert len(roots)==1
        identity = json.loads((roots[0]/'wave3-packages.json').read_text())
        assert tuple(identity[k] for k in ('source_sha','run_id','attempt')) == tuple(report[k] for k in ('source_sha','run_id','attempt'))
        sdk=roots[0]/'sdk'; products=roots[0]/'raw-products'; resources=out/'resources'; project=out/'project'; derived=out/'derived'
        assert run([sys.executable,'tests/apple_host/prepare_fixtures.py','--resources',resources],'fixtures') == 0
        assert run(['ruby','tests/reader_team24_apple/make_project.rb',project,resources,ROOT/'tests/apple_large_type_drivers/ui','base'],'project') == 0
        data=json.loads(subprocess.check_output(['xcrun','simctl','list','devices','available','--json']))
        prefix='iPhone' if args.platform=='iphone' else 'iPad'
        runtime,name,udid=max((r,d['name'],d['udid']) for r,ds in data['devices'].items() for d in ds if d.get('isAvailable') and d['name'].startswith(prefix))
        if args.platform=='iphone':
            udid=subprocess.check_output(['xcrun','simctl','create','Large type iPhone SE','com.apple.CoreSimulator.SimDeviceType.iPhone-SE-3rd-generation',runtime],text=True).strip(); name='iPhone SE (3rd generation)'
        report['destination']=dict(runtime=runtime,name=name,udid=udid)
        subprocess.run(['xcrun','simctl','shutdown',udid],capture_output=True)
        for action in ('erase','boot'): assert run(['xcrun','simctl',action,udid],action)==0
        assert run(['xcrun','simctl','bootstatus',udid,'-b'],'boot-ready')==0
        for phase,size,selector,expected in [('setup','large','-only-testing',1),('maximum','accessibility-extra-extra-extra-large','-skip-testing',2)]:
            assert run(['xcrun','simctl','ui',udid,'content_size',size],phase+'-size-set')==0
            actual=subprocess.check_output(['xcrun','simctl','ui',udid,'content_size'],text=True).strip(); (evidence/(phase+'-system-size.txt')).write_text(actual+'\n'); assert actual==size,(actual,size)
            bundle=evidence/(phase+'.xcresult')
            status=run(['xcodebuild','test','-project',project/'EXReaderHost.xcodeproj','-scheme','EXReaderHost-iOS','-destination','platform=iOS Simulator,id='+udid,'-derivedDataPath',derived,'-resultBundlePath',bundle,'-parallel-testing-enabled','NO','-test-timeouts-enabled','YES','-default-test-execution-time-allowance','240','-maximum-test-execution-time-allowance','360',selector+':EXReaderHostUITests-iOS/OrganizationLargeTypeUITests/testPrepareOriginalThroughApp','EXR_SDK_DIR='+str(sdk),'EXR_PRODUCTS_DIR='+str(products),'CODE_SIGNING_ALLOWED=NO'],phase)
            cases=load_results(bundle) if bundle.exists() else []
            report['phases'].append(dict(name=phase,setup_only=phase=='setup',system_size=actual,exit=status,cases=cases,accepted=status==0 and len(cases)==expected and all(c['result']=='Passed' for c in cases)))
            if phase=='setup': assert report['phases'][-1]['accepted'],'real import setup failed'
        app=derived/'Build/Products/Debug-iphonesimulator/EXReaderHost.app'; binary=app/'EXReaderHost'
        info=plistlib.loads((app/'Info.plist').read_bytes()); assert info['EXRSourceSHA']==report['source_sha']
        report['program']=dict(source_sha=info['EXRSourceSHA'],sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),bytes=binary.stat().st_size)
        assert run(['ditto','-c','-k','--sequesterRsrc','--keepParent',app,evidence/'EXReaderHost-simulator.zip'],'package')==0
        report['accepted']=len(report['phases'])==2 and all(p['accepted'] for p in report['phases'])
    except Exception as error: report['failure']=str(error); print('FOCUS FAILURE '+str(error),flush=True)
    finally:
        if udid: subprocess.run(['xcrun','simctl','shutdown',udid],capture_output=True)
        (evidence/'result.json').write_text(json.dumps(report,indent=2)+'\n'); print(json.dumps(report),flush=True)
    assert report['accepted'],'focused maximum-type diagnostic did not pass'
if __name__=='__main__': main()
