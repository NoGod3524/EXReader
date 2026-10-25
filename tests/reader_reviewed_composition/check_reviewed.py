# SPDX-License-Identifier: MIT
"""Real shared owner/session flow, independently judged in Actions."""
import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from webdav_fixture import WebDAVFixture
assert os.environ.get('GITHUB_ACTIONS')=='true','Actions only'
p=argparse.ArgumentParser();p.add_argument('--probe',type=Path,required=True);p.add_argument('--relocated',type=Path,required=True);p.add_argument('--fixtures',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
out=a.output.resolve();out.mkdir(parents=True,exist_ok=True);problems=[];runs=[]
original=(a.fixtures/'sample.txt').resolve();data=original.read_bytes();digest=hashlib.sha256(data).hexdigest()
source=(Path(__file__).parent/'consumer/reviewed_flow.cpp').read_text()
required=re.findall(r'need\([^;]*?,"([^"]+)"\);',source)
assert len(required)>=35 and len(required)==len(set(required)), 'fixed unique source check contract'
with WebDAVFixture(out/'certificates',roots=('/reviewed/','/relocated/')) as fixture:
 for index,binary in enumerate((a.probe,a.relocated)):
  root=fixture.roots[index];fixture.entries[root+'incoming.txt']=data
  folder=out/('run'+str(index));folder.mkdir();report=folder/'report.json'
  cmd=[str(binary.resolve()),str(folder/'work'),fixture.root_url(index),str(original),digest,str(report)]
  result=subprocess.run(cmd,capture_output=True,text=True,env=dict(os.environ,READER_TEST_AUTH=fixture.authorization))
  (folder/'consumer.log').write_text(result.stdout+'\n'+result.stderr,encoding='utf-8');print(result.stdout)
  record=json.loads(report.read_text()) if report.is_file() else {}
  names=[c.get('name') for c in record.get('checks',[])]
  ok=result.returncode==0 and record.get('accepted') is True and names==required and all(c.get('pass') is True for c in record.get('checks',[]))
  if not ok:problems.append('shared-flow-'+str(index)+': '+str(record.get('failure', 'missing or incomplete report')))
  objects=fixture.objects(root);revisions=fixture.revisions(root)
  if len(objects)!=1 or list(objects.values())!=[data]:problems.append('shared-flow original bytes not independently observed in '+root)
  if len(revisions)!=2:problems.append('shared-flow expected exactly original and favorite revisions in '+root)
  journal=[r for r in fixture.requests if r['root']==root]
  if not any(r['method']=='GET' and r['path']==root+'incoming.txt' and r['status']==200 for r in journal):problems.append('no actual cloud download '+root)
  for name,body in revisions.items():
   value=json.loads(body)
   if not name.endswith(value['id']+'-'+hashlib.sha256(body).hexdigest()+'.json'):problems.append('revision identity differs '+name)
  runs.append(dict(binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),checks=names,accepted=ok,objects=len(objects),revisions=len(revisions)))
 (out/'requests.json').write_text(json.dumps(fixture.requests,indent=2)+'\n')
 fixture.assert_secret_free(out)
summary=dict(accepted=not problems,source_sha=os.environ['GITHUB_SHA'],run_id=os.environ['GITHUB_RUN_ID'],attempt=os.environ['GITHUB_RUN_ATTEMPT'],runs=runs,problems=problems,host_ui_accepted=False,performance_accepted=False)
(out/'result.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary));raise SystemExit(1 if problems else 0)
