# SPDX-License-Identifier: MIT
"""Actions-only altered-evidence refusals after actual owner/provider execution."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET


def main():
    p=argparse.ArgumentParser();p.add_argument('--evidence',type=Path,required=True);root=p.parse_args().evidence
    if os.environ.get('GITHUB_ACTIONS')!='true':raise SystemExit('Actions only')
    checks=[]
    def invoke(name,accepted):
        call=subprocess.run([sys.executable,'tools/check_reader_owner_android.py','--evidence',str(root),'--all-exits'],capture_output=True,timeout=120)
        value=json.loads((root/'result.json').read_text());passed=(call.returncode==0)==accepted and value['accepted'] is accepted
        checks.append({'id':name,'passed':passed});assert passed,(name,call.stderr,value)
    def alter(path,change,name):
        original=path.read_bytes()
        try:path.write_bytes(change(original));invoke(name,False)
        finally:path.write_bytes(original)
    def edit(path,name,change):
        def replacement(raw):
            value=json.loads(raw);change(value);return json.dumps(value).encode()
        alter(path,replacement,name)
    report={'source_sha':os.environ['GITHUB_SHA'],'run_id':os.environ['GITHUB_RUN_ID'],'attempt':os.environ['GITHUB_RUN_ATTEMPT'],
            'accepted':False,'checks':checks,'problems':[]}
    try:
        invoke('positive',True);device=root/'device-report.json'
        edit(device,'old_device_source',lambda v:v.update(source_sha='0'*40))
        edit(device,'missing_device_case',lambda v:v['checks'].pop())
        edit(device,'duplicate_device_case',lambda v:v['checks'].append(v['checks'][0]))
        edit(device,'failed_device_case',lambda v:v['checks'][0].update({'pass':False}))
        edit(device,'wrong_native_runtime_provider',lambda v:v['provider'].__setitem__(3,'/system/lib64/libsqlite.so'))
        edit(device,'wrong_actual_sqlite_source',lambda v:v['provider'].__setitem__(1,'wrong'))
        edit(device,'missing_provider_option',lambda v:v['provider'].__setitem__(4,''))
        alter(root/'owner-instrumentation.txt',lambda raw:raw.replace(b'INSTRUMENTATION_STATUS_CODE: 0',b'INSTRUMENTATION_STATUS_CODE: -3',1),'skipped_manual_owner_case')
        alter(root/'apks/app-debug.apk',lambda raw:raw+b'altered APK','different_reinstalled_application')
        def skipped(raw):
            tree=ET.fromstring(raw);ET.SubElement(next(tree.iter('testcase')),'skipped');return ET.tostring(tree)
        xml=next((root/'owner-reports').rglob('*.xml'));alter(xml,skipped,'skipped_owner_xml')
        alter(root/'native/release.symbols.txt',lambda raw:raw+b'0000 T Java_org_exreader_host_ProductFixture_injected\n','fixture_in_release')
        alter(root/'native/debug.map',lambda raw:b'','missing_link_provider_proof')
        alter(root/'witness-before.txt',lambda raw:b'0,0,0','wrong_three_write_crash_boundary')
        alter(root/'recover-after.txt',lambda raw:b'','missing_successful_retry_after_kill')
        alter(root/'seed-before.txt',lambda raw:b'OK','process_not_killed')
        edit(Path('build/shelf-android/shelf-result.json'),'old_112_rejected',lambda v:v.update(accepted=False))
        edit(Path('build/shelf-android/shelf-gate-review.json'),'missing_old_gate',lambda v:v['checks'].pop())
        invoke('restored_positive',True);report['accepted']=True
    except Exception as error:report['problems'].append(type(error).__name__+': '+str(error))
    report['script_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    (root/'gate-review.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)
    if not report['accepted']:raise SystemExit(1)


if __name__=='__main__':main()
