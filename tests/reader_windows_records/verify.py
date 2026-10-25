"""Same-run native records proof, retaining every original F1/F2/host gate."""
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
import verify as search_verify
from check_parallel_integration import fetch,download_artifact_zip,require

def module(name,path):
 spec=importlib.util.spec_from_file_location(name,path);value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value

def validate(report,source,run,attempt,product,review,capture,revision):
 names=search_verify.names_from_source(Path(__file__).with_name('check_ui.py'),'REQUIRED')
 search_verify.bound(report,names,source,run,attempt)
 require(report['consumer_sha256']==product and report['review_sha256']==review and
  report['capture_probe_sha256']==capture and report['revision_consumer_sha256']==revision,'different records binary')
 require(report['transport']=='SendInput+UIAutomation+Win32' and report['complete_product'] is False and
  report['performance_accepted'] is False and report['screen_reader_accepted'] is False,'invalid records scope')
 require(report['public_resolutions'] and all(r['decoded'] is True and r['status']=='OK' and r['state']=='FOUND'
  for r in report['public_resolutions']),'missing public SDK resolution proof')
 require({r['mode'] for r in report['public_resolutions']}=={'reflow_global','epub_chapter','fixed_page'},'missing reading mode')
 require(all(r['anchor_version']==2 for r in report['public_resolutions']),'new records lost anchor v2')
 require(report['screenshots'] and report['inputs'],'missing native inputs and screenshots')
 return len(names)

def selftest():
 names=search_verify.names_from_source(Path(__file__).with_name('check_ui.py'),'REQUIRED')
 source=os.environ['GITHUB_SHA'];run=os.environ['GITHUB_RUN_ID'];attempt=os.environ['GITHUB_RUN_ATTEMPT']
 good=dict(accepted=True,source_sha=source,run_id=run,attempt=attempt,checks=names,count=len(names),problems=[],
  consumer_sha256='p',review_sha256='r',capture_probe_sha256='c',revision_consumer_sha256='v',
  transport='SendInput+UIAutomation+Win32',complete_product=False,performance_accepted=False,screen_reader_accepted=False,
  public_resolutions=[dict(decoded=True,status='OK',state='FOUND',anchor_version=2,mode=mode)
   for mode in ('reflow_global','epub_chapter','fixed_page')],screenshots=['one'],inputs={'one':'sha'})
 validate(good,source,run,attempt,'p','r','c','v')
 mutations=[dict(accepted=False),dict(source_sha='0'*40),dict(run_id='0'),dict(attempt='0'),dict(count=0),
  dict(checks=names[:-1],count=len(names)-1),dict(checks=names[:-1]+names[:1]),dict(problems=['failure']),
  dict(consumer_sha256='other'),dict(review_sha256='other'),dict(capture_probe_sha256='other'),dict(revision_consumer_sha256='other'),
  dict(complete_product=True),dict(performance_accepted=True),dict(screen_reader_accepted=True),dict(transport='synthetic'),
  dict(public_resolutions=[]),dict(public_resolutions=good['public_resolutions'][:1]),dict(screenshots=[]),dict(inputs={})]
 for field,value in [('state','AMBIGUOUS'),('status','UNRESOLVED'),('anchor_version',1),('decoded',False)]:
  bad=copy.deepcopy(good['public_resolutions']);bad[0][field]=value;mutations.append(dict(public_resolutions=bad))
 for change in mutations:
  try:validate(good|change,source,run,attempt,'p','r','c','v')
  except ValueError:continue
  raise ValueError('records validator accepted a rejected mutation')
 return len(mutations)

def main():
 require(os.environ.get('GITHUB_ACTIONS')=='true','Actions only')
 if sys.argv[1:]==['--protocol-selftest']:
  print(json.dumps({'records_protocol_rejections':selftest()}));return
 source=os.environ['GITHUB_SHA'];run=int(os.environ['GITHUB_RUN_ID']);attempt=int(os.environ['GITHUB_RUN_ATTEMPT'])
 nav=module('original_navigation_verifier',ROOT/'tests/reader_windows_navigation/verify.py')
 nav.main('.github/workflows/reader-windows-reading-records.yml')
 out=Path('build/winrecords-summary');out.mkdir(parents=True,exist_ok=False)
 result=dict(accepted=False,source_sha=source,run_id=run,attempt=attempt,problems=[],complete_product=False,
  performance_accepted=False,screen_reader_accepted=False)
 try:
  identity=int(os.environ['ARTIFACT_ID']);meta=fetch('actions/artifacts/%d'%identity)
  require(meta['workflow_run']['id']==run and meta['workflow_run']['head_sha']==source and not meta['expired'] and
   datetime.fromisoformat(meta['expires_at'].replace('Z','+00:00'))>datetime.now(timezone.utc),'records ZIP identity')
  with tempfile.TemporaryFile() as stream:download_artifact_zip(identity,stream);stream.seek(0);raw=stream.read()
  require(len(raw)==meta['size_in_bytes'] and 'sha256:'+hashlib.sha256(raw).hexdigest()==meta['digest'],'records ZIP digest')
  with zipfile.ZipFile(io.BytesIO(raw)) as z:
   require(len(z.namelist())==len(set(z.namelist())),'duplicate ZIP members')
   def sha(path):return hashlib.sha256(z.read(path)).hexdigest()
   report=json.loads(z.read('ws-records-ui/records-ui.json').decode('utf-8'))
   product=sha('ws-package/EXReader/EXReader.exe');review=sha('ws-host/EXReaderShelfReview.exe')
   capture=sha('account-capture/reading-capture-probe.exe');revision=sha('account-revisions-consumer/revision-consumer.exe')
   count=validate(report,source,run,attempt,product,review,capture,revision)
   for path in report['screenshots']:require(z.read('ws-records-ui/'+path).startswith(b'BM'),'missing screenshot')
   mapping=z.read('ws-host/windows-host.map').decode('utf-8',errors='replace')
   require(all(name in mapping for name in ('reader_rc_apply','reader_av_page_get','reader_rs_resolve_fixed')),'installed records modules missing')
  result.update(accepted=True,records_ui_checks=count,protocol_rejections=selftest(),original_navigation_and_search_strict_preserved=True,
   consumer_sha256=product,review_sha256=review,artifact={k:meta[k] for k in ('id','name','size_in_bytes','digest','expires_at')})
 except Exception as error:result['problems'].append(type(error).__name__+': '+str(error))
 (out/'verified.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result),flush=True)
 require(result['accepted'],'Windows reading records strict proof rejected')

if __name__=='__main__':main()
