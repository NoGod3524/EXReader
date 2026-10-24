#!/usr/bin/env python3
"""Actions-only regression evidence for the independent F4 review."""
import argparse
import base64
import json
import os
from pathlib import Path
import subprocess
from make_fixtures import make_junction


def main():
    assert os.environ.get('GITHUB_ACTIONS')=='true'
    p=argparse.ArgumentParser();p.add_argument('--probe',type=Path,required=True);p.add_argument('--original-probe',type=Path,required=True);p.add_argument('--work',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.work.mkdir(parents=True,exist_ok=True);a.output.mkdir(parents=True,exist_ok=True);checks=[]
    link=a.work/'parent-link';(link/'root/parent').mkdir(parents=True);(link/'external').mkdir()
    (link/'root/parent/book.txt').write_text('selected original\n');(link/'external/book.txt').write_text('outside replacement\n')
    before=subprocess.run([str(a.original_probe),'enumerate','--root',str(link/'root'),'--recursive','--out',str(link/'before.tsv')],capture_output=True,text=True,timeout=60)
    assert before.returncode==0 and 'parent/book.txt' in (link/'before.tsv').read_text()
    (link/'root/parent').rename(link/'root/original-parent')
    if os.name=='nt':
        # Pass the fixture command as UTF-16 rather than through cmd.exe quoting.
        quote=lambda value:"'"+str(value).replace("'","''")+"'"
        script='New-Item -ItemType Junction -Path '+quote((link/'root/parent').absolute())+' -Target '+quote((link/'external').resolve())+' -ErrorAction Stop | Out-Null'
        created=subprocess.run(['powershell','-NoProfile','-NonInteractive','-EncodedCommand',base64.b64encode(script.encode('utf-16le')).decode()],capture_output=True,text=True,timeout=30)
        supported=created.returncode==0;detail=created.stdout+created.stderr
    else:supported,detail=make_junction(str((link/'root/parent').absolute()),str((link/'external').resolve()))
    for name in ('directory-budget','parent-link','copy-change','concurrent'):
        if name=='parent-link' and not supported:
            checks.append({'name':name,'ok':False,'returncode':2,'detail':'junction fixture failed: '+detail});print(json.dumps(checks[-1]),flush=True);continue
        result=subprocess.run([str(a.probe),name,str((a.work/name).resolve())],capture_output=True,text=True,timeout=90)
        (a.output/(name+'.txt')).write_text(result.stdout+result.stderr)
        checks.append({'name':name,'ok':result.returncode==0,'returncode':result.returncode,'detail':result.stdout+result.stderr})
        print(json.dumps(checks[-1]),flush=True)
    report={'source':os.environ['GITHUB_SHA'],'run_id':os.environ['GITHUB_RUN_ID'],'attempt':os.environ['GITHUB_RUN_ATTEMPT'],'ok':all(row['ok'] for row in checks),'checks':checks}
    (a.output/'review.json').write_text(json.dumps(report,indent=2)+'\n');return 0 if report['ok'] else 1


if __name__=='__main__':raise SystemExit(main())
