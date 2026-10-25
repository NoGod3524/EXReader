"""T01 strict same-source/run/attempt authentication; original strict gates intact."""
import copy
from datetime import datetime,timezone
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tests/reader_windows_search'))
import verify as search
from check_parallel_integration import fetch,download_artifact_zip,require

def module(name,path):
 spec=importlib.util.spec_from_file_location(name,path);result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result

def validate(report,source,run,attempt,product,probe,command,revision):
 names=search.names_from_source(Path(__file__).with_name('check_ui.py'),'REQUIRED')
 search.bound(report,names,source,run,attempt)
 require(report['consumer_sha256']==product and report['cloud_probe_sha256']==probe and report['command_consumer_sha256']==command and report['revision_consumer_sha256']==revision,'T01 used a different host or installed consumer')
 require(report['transport']=='SendInput+UIAutomation+Win32' and report['complete_product'] is False and report['performance_accepted'] is False and report['screen_reader_accepted'] is False,'invalid T01 scope')
 require(len(report['inputs'])==9 and report['screenshots'] and report['public_readback']['ok']==1 and len(report['public_readback']['books'])==9,'missing fixture or public SDK oracle')
 inputs=search.names_from_source(Path(__file__).with_name('check_ui.py'),'INPUTS')
 expected={name:hashlib.sha256((ROOT/'tests/fixtures'/fixture).read_bytes()).hexdigest() for name,fixture in inputs}
 require(report['inputs']==expected,'fixed nine-format inputs changed')
 require(all(book['read_ok']==1 for book in report['public_readback']['books']),'public SDK readback failed')
 require(any(r['method']=='PROPFIND' and r['authenticated'] for r in report['requests']) and any(r['method']=='GET' and r['authenticated'] for r in report['requests']),'no real authenticated TLS traffic')
 return len(names)

def main(workflow_path='.github/workflows/reader-windows-import-organize.yml'):
 require(os.environ.get('GITHUB_ACTIONS')=='true','Actions only')
 workflow=workflow_path
 records=module('retained_records',ROOT/'tests/reader_windows_records/verify.py');records.main(workflow)
 source=os.environ['GITHUB_SHA'];run=int(os.environ['GITHUB_RUN_ID']);attempt=int(os.environ['GITHUB_RUN_ATTEMPT'])
 out=Path('build/wio-summary');out.mkdir(parents=True,exist_ok=False)
 result=dict(accepted=False,source_sha=source,run_id=run,attempt=attempt,problems=[],complete_product=False,performance_accepted=False,screen_reader_accepted=False)
 try:
  jobs=fetch('actions/runs/%d/attempts/%d/jobs?per_page=100'%(run,attempt))['jobs']
  matching=[job for job in jobs if job['name']=='installed F1 and native Windows search controls and lifecycle']
  require(len(matching)==1 and matching[0]['status']=='completed' and matching[0]['conclusion']=='success' and matching[0]['head_sha']==source,'T01 upstream identity/status')
  steps={step['name']:step['conclusion'] for step in matching[0]['steps']}
  for name in ('Real native cloud selection and batch organization controls','Retain J01 and J10 named module regressions','Execute native reading records and real process recovery'):
   require(steps.get(name)=='success','required T01 step did not complete successfully: '+name)
  identity=int(os.environ['ARTIFACT_ID']);meta=fetch('actions/artifacts/%d'%identity)
  all_artifacts=fetch('actions/runs/%d/artifacts?per_page=100'%run)['artifacts']
  require(len([item for item in all_artifacts if item['name']==meta['name']])==1,'duplicate artifact name')
  require(meta['workflow_run']['id']==run and meta['workflow_run']['head_sha']==source and meta['expired'] is False and meta['size_in_bytes']>0 and datetime.fromisoformat(meta['expires_at'].replace('Z','+00:00'))>datetime.now(timezone.utc),'artifact source/expiry/size')
  with tempfile.TemporaryFile() as stream:download_artifact_zip(identity,stream);stream.seek(0);raw=stream.read()
  digest=hashlib.sha256(raw).hexdigest()
  require(len(raw)==meta['size_in_bytes'] and meta['digest']=='sha256:'+digest and os.environ['UPLOAD_DIGEST'].removeprefix('sha256:')==digest,'ZIP size/digest')
  with zipfile.ZipFile(io.BytesIO(raw)) as z:
   require(len(z.namelist())==len(set(z.namelist())),'duplicate ZIP member/report')
   def sha(path):return hashlib.sha256(z.read(path)).hexdigest()
   def load(path):return json.loads(z.read(path))
   product=sha('ws-package/EXReader/EXReader.exe');probe=sha('wio-reader_webdav_import/cloud-probe.exe');command=sha('account-commands-consumer/command-consumer.exe')
   revision=sha('account-revisions-consumer/revision-consumer.exe')
   report=load('wio-ui/import-organize-ui.json');count=validate(report,source,run,attempt,product,probe,command,revision)
   originals={sha('wio-ui/readback/book-%d.bin'%book['id']) for book in report['public_readback']['books']}
   require(originals==set(report['inputs'].values()),'independent original bytes differ from fixed fixtures')
   rejections=0
   for mutation in (dict(accepted=False),dict(source_sha='0'*40),dict(run_id='0'),dict(attempt='0'),dict(consumer_sha256='wrong'),dict(cloud_probe_sha256='wrong'),dict(command_consumer_sha256='wrong'),dict(inputs={}),dict(screenshots=[]),dict(requests=[]),dict(complete_product=True),dict(public_readback={'ok':0,'books':[]})):
    try:validate(report|mutation,source,run,attempt,product,probe,command,revision)
    except (ValueError,KeyError):rejections+=1
    else:raise ValueError('T01 strict verifier accepted a malformed report')
   for path in report['screenshots']:require(z.read('wio-ui/'+path).startswith(b'BM'),'missing actual Win32 screenshot')
   cloud=load('wio-cloud-module/result.json')
   require(cloud['accepted'] is True and cloud['source_sha']==source and str(cloud['run_id'])==str(run) and str(cloud['attempt'])==str(attempt) and cloud['count']==47,'J01 original named scenarios')
   require(len(cloud['checks'])==47 and len({check['id'] for check in cloud['checks']})==47 and all(check['pass'] is True for check in cloud['checks']),'J01 failures or repeated cases')
   require(cloud['probe_sha256']==probe and cloud['review_probe_sha256']==sha('wio-reader_webdav_import/cloud-review-probe.exe'),'J01 binary identity')
   bulk=load('wio-bulk-module/report.json')
   bulk_contract=module('bulk_contract',ROOT/'tests/reader_bulk_organization/check_artifacts.py');bulk_contract.require_report(bulk,source,21,str(run),str(attempt))
   require(bulk['probe_sha256']==sha('wio-reader_bulk_organization/bulk-probe.exe'),'J10 binary identity')
   mapping=z.read('ws-host/windows-host.map').decode('utf-8',errors='replace')
   for symbol in ('reader_cloud_download','reader_cloud_import','reader_bulk_run','reader_bulk_resume','reader_bulk_inspect'):
    require(symbol in mapping,'missing installed production symbol '+symbol)
   f2=load('ws-navigation-module-evidence/probe.json');require(len(f2['checks'])==130,'original F2 count changed')
  result.update(accepted=True,ui_checks=count,original_j01_checks=47,original_j10_checks=21,original_f1_checks=264,original_f2_checks=130,original_nav_ui=31,original_records_ui=32,original_ui158=158,
   original_strict_verifiers_preserved=True,protocol_rejections=rejections,consumer_sha256=product,job_id=matching[0]['id'],artifact={key:meta[key] for key in ('id','name','size_in_bytes','digest','expires_at')})
 except Exception as error:result['problems'].append(type(error).__name__+': '+str(error))
 (out/'verified.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result),flush=True)
 require(result['accepted'],'T01 strict acceptance rejected')

if __name__=='__main__':main()
