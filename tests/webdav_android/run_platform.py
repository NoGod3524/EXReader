#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Measure public Android URLConnection DAV verbs and I/O timeout behavior on Actions."""
import argparse
import json
import os
from pathlib import Path
import subprocess
from fixture import Fixture, require_actions


def main():
    require_actions();p=argparse.ArgumentParser();p.add_argument('--fixture',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=True);server=Fixture(a.fixture)
    def adb(*args):return subprocess.check_output(['adb',*map(str,args)],stderr=subprocess.STDOUT,timeout=30)
    try:
        ports=server.start()
        for port in ports.values():adb('reverse',f'tcp:{port}',f'tcp:{port}')
        app='org.exreader.webdav.platformprobe'
        root=Path('tests/webdav_android/android/platform/build/outputs/apk')
        adb('install','-r','-t',root/'debug/platform-debug.apk');adb('install','-r','-t',root/'androidTest/debug/platform-debug-androidTest.apk')
        raw=adb('shell','am','instrument','-w','-r','-e','root',f'https://127.0.0.1:{ports["trusted"]}/probe/',
                '-e','source_sha',os.environ['GITHUB_SHA'],'-e','run_id',os.environ['GITHUB_RUN_ID'],'-e','attempt',os.environ['GITHUB_RUN_ATTEMPT'],
                app+'.test/'+app+'.PlatformProbe')
        (a.output/'instrumentation.txt').write_bytes(raw)
        if b'EXR_WEBDAV_PLATFORM_PROBE_RECORDED' not in raw or b'INSTRUMENTATION_CODE: -1' not in raw:raise RuntimeError('Platform probe failed')
        report=adb('exec-out','run-as',app,'cat','files/platform-report.json');(a.output/'device-report.json').write_bytes(report);value=json.loads(report)
        expected={'source_sha':os.environ['GITHUB_SHA'],'run_id':os.environ['GITHUB_RUN_ID'],'attempt':os.environ['GITHUB_RUN_ATTEMPT']}
        assert all(value.get(k)==v for k,v in expected.items()) and value['api']==34 and value['abi']=='x86_64'
        assert value['trusted_fixture_tls_verified'] is True and value['read_timeout_observed'] is True
        assert [v['method'] for v in value['methods']]==['GET','PUT','PROPFIND','MKCOL']
        result={**expected,'platform_probe_recorded':True,'backend_accepted':False,'platform':value}
        (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
    finally:server.close()


if __name__=='__main__':main()
