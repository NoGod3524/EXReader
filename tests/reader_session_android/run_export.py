#!/usr/bin/env python3
"""Record actual public SDK export behavior in the Android app-private filesystem."""
import argparse
import json
import os
from pathlib import Path
import subprocess


def main():
    assert os.environ.get('GITHUB_ACTIONS')=='true'
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    def adb(*args):return subprocess.check_output(['adb',*map(str,args)],stderr=subprocess.STDOUT,timeout=90)
    package='org.exreader.sessionprobe';apks=Path('tests/reader_session_android/android/session/build/outputs/apk')
    adb('install','-r','-t',apks/'debug/session-debug.apk');adb('install','-r','-t',apks/'androidTest/debug/session-debug-androidTest.apk')
    command=['shell','am','instrument','-w','-r']
    identity={key:os.environ[value] for key,value in [('source_sha','GITHUB_SHA'),('run_id','GITHUB_RUN_ID'),('attempt','GITHUB_RUN_ATTEMPT')]}
    for key,value in identity.items():command.extend(['-e',key,value])
    raw=adb(*command,package+'.test/'+package+'.SessionProbe');(a.output/'instrumentation.txt').write_bytes(raw)
    if b'EXR_SESSION_EXPORT_RECORDED' not in raw:raise RuntimeError(raw.decode(errors='replace'))
    report=json.loads(adb('exec-out','run-as',package,'cat','files/export-report.json'))
    (a.output/'device-report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)
    assert all(report.get(key)==value for key,value in identity.items()) and report['api']==34 and report['abi']=='x86_64'
    assert report['ok'] is True,'Public SDK original export did not satisfy its contract'


if __name__=='__main__':main()
