#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Additional bounded-suite rejection checks; the original 48 remain separate."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parent))
import check_evidence_gate as original


def expected_names():
    return ['positive'] + ['bounded:' + name for name in original.SUITE_MUTATIONS] + [
        'missing_bounded_report', 'missing_bounded_log', 'changed_bounded_log']


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence',type=Path,required=True)
    parser.add_argument('--build',type=Path,required=True)
    parser.add_argument('--stage',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    identity=original.cloud_identity(); checks=[]
    upstream={'build':'success','static':'success','emulator':'success'}
    report={**identity,'schema':1,'accepted':False,'script_sha256':original.sha256(__file__),'checks':checks}
    try:
        original.check_evidence(args.evidence,args.build,args.stage,upstream,identity)
        checks.append({'name':'positive','passed':True})
        for name in expected_names()[1:]:
            with tempfile.TemporaryDirectory(prefix='bounded-android-gate-') as temporary:
                root=Path(temporary); evidence=root/'evidence'; build=root/'build.json'
                shutil.copytree(args.evidence,evidence,copy_function=os.link)
                shutil.copytree(args.build.parent/'fixtures',root/'fixtures',copy_function=os.link)
                os.link(args.build,build)
                if name.startswith('bounded:'):
                    original.mutate(name,evidence,build)
                elif name=='missing_bounded_report': (evidence/'bounded/validation.json').unlink()
                elif name=='missing_bounded_log': (evidence/'bounded-logcat.txt').unlink()
                else:
                    path=evidence/'bounded-logcat.txt'; original.write(path,path.read_bytes()+b'\naltered raw log\n')
                try: original.check_evidence(evidence,build,args.stage,upstream,identity)
                except Exception: checks.append({'name':name,'passed':True})
                else: checks.append({'name':name,'passed':False})
        report['accepted']=[item['name'] for item in checks]==expected_names() and all(item['passed'] for item in checks)
    except Exception as error: report['problem']=type(error).__name__+': '+str(error)[:500]
    args.output.parent.mkdir(parents=True,exist_ok=True); original.write(args.output,report)
    print(json.dumps({'bounded_gate_accepted':report['accepted'],'checks':len(checks),'expected':len(expected_names())}))
    return 0 if report['accepted'] else 1


if __name__=='__main__': raise SystemExit(main())
