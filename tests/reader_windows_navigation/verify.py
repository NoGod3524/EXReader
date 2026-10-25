"""Same-run F2/native navigation proof, retaining the original strict F1 verifier."""
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

def validate_ui(report,source,run,attempt,product,review):
 required=search_verify.names_from_source(Path(__file__).with_name('check_ui.py'),'REQUIRED')
 search_verify.bound(report,required,source,run,attempt)
 require(report['consumer_sha256']==product and report['review_sha256']==review,'navigation used another host')
 require(report['transport']=='SendInput+UIAutomation+Win32' and report['complete_product'] is False and
  report['performance_accepted'] is False and report['screen_reader_accepted'] is False,'invalid scope claim')
 return len(required)

def validate_standalone(link_map):
 # MSVC maps identify archive members as library:object, without a .lib suffix.
 require(all(name in link_map for name in ('reader_navigation_open_publication',
  'reader_navigation_children','reader_navigation_resolve_cfi')) and
  all(name not in link_map for name in ('reader_search_open_reflow','reader_search_next')),
  'navigation must link F2 independently of F1')

def self_test():
 source=os.environ['GITHUB_SHA'];run=os.environ['GITHUB_RUN_ID'];attempt=os.environ['GITHUB_RUN_ATTEMPT']
 names=search_verify.names_from_source(Path(__file__).with_name('check_ui.py'),'REQUIRED')
 good=dict(accepted=True,source_sha=source,run_id=run,attempt=attempt,checks=names,count=len(names),
  consumer_sha256='product',review_sha256='review',transport='SendInput+UIAutomation+Win32',
  complete_product=False,performance_accepted=False,screen_reader_accepted=False,problems=[])
 validate_ui(good,source,run,attempt,'product','review')
 bads=[dict(consumer_sha256='other'),dict(review_sha256='other'),dict(screen_reader_accepted=True),
  dict(performance_accepted=True),dict(complete_product=True),dict(checks=names[:-1],count=len(names)-1),
  dict(checks=names[:-1]+names[:1]),dict(problems=['failed'])]
 for mutation in bads:
  bad=good|mutation
  try:validate_ui(bad,source,run,attempt,'product','review')
  except ValueError:continue
  raise ValueError('accepted navigation rejection mutation '+repr(mutation))
 symbols='reader_navigation_open_publication reader_navigation_children reader_navigation_resolve_cfi'
 validate_standalone(symbols)
 for wrong in (symbols.replace('reader_navigation_children',''),symbols+' reader_search_next'):
  try:validate_standalone(wrong)
  except ValueError:continue
  raise ValueError('accepted wrong navigation-only link map')
 return search_verify.protocol_selftest(source,run,attempt)+len(bads)+2

def main(workflow_path='.github/workflows/reader-windows-navigation-ui.yml'):
 require(os.environ.get('GITHUB_ACTIONS')=='true','Actions only')
 source=os.environ['GITHUB_SHA'];run=int(os.environ['GITHUB_RUN_ID']);attempt=int(os.environ['GITHUB_RUN_ATTEMPT'])
 if sys.argv[1:]==['--protocol-selftest']:
  print(json.dumps({'protocol_rejections':self_test()}));return
 # This first authenticates all unchanged F1, 158 original UI, product, shelf,
 # metadata, account, keyboard and worker checks, including their binary hashes.
 search_verify.main(workflow_path)
 output=Path('build/winnav-summary');output.mkdir(parents=True,exist_ok=False)
 result=dict(accepted=False,source_sha=source,run_id=run,attempt=attempt,problems=[],complete_product=False,
  performance_accepted=False,screen_reader_accepted=False)
 try:
  identity=int(os.environ['ARTIFACT_ID']);meta=fetch('actions/artifacts/%d'%identity)
  require(meta['workflow_run']['id']==run and meta['workflow_run']['head_sha']==source and not meta['expired'] and
   datetime.fromisoformat(meta['expires_at'].replace('Z','+00:00'))>datetime.now(timezone.utc),'navigation ZIP identity')
  with tempfile.TemporaryFile() as stream:
   download_artifact_zip(identity,stream);stream.seek(0);raw=stream.read()
  require(len(raw)==meta['size_in_bytes'] and 'sha256:'+hashlib.sha256(raw).hexdigest()==meta['digest'],'navigation ZIP digest')
  with zipfile.ZipFile(io.BytesIO(raw)) as z:
   require(len(z.namelist())==len(set(z.namelist())),'duplicate ZIP entries')
   def load(path):return json.loads(z.read(path).decode('utf-8'))
   def sha(path):return hashlib.sha256(z.read(path)).hexdigest()
   product=sha('ws-package/EXReader/EXReader.exe');review=sha('ws-host/EXReaderShelfReview.exe')
   report=load('ws-navigation-ui/navigation-ui.json');count=validate_ui(report,source,run,attempt,product,review)
   nav=load('ws-navigation-module-evidence/result.json');probe=load('ws-navigation-module-evidence/probe.json')
   contract=module('navigation_original_contract',ROOT/'tests/reader_navigation/check_navigation.py')
   require(nav['accepted'] is True and nav['source_sha']==source and str(nav['run_id'])==str(run) and
    str(nav['attempt'])==str(attempt) and nav['probe_sha256']==sha('ws-navigation-consumer/navigation-probe.exe') and
    nav['c_consumer_sha256']==sha('ws-navigation-consumer/navigation-c-consumer.exe'),'installed F2 identity')
   checks=probe['checks'];names={c['name'] for c in checks}
   require(checks and all(c['pass'] is True for c in checks) and nav['checks']==len(checks) and
    probe['failures']==0 and set(contract.REQUIRED_CHECKS)<=names,'original F2 cases missing')
   cases=probe['cases'];require(len(cases)==len({c['id'] for c in cases}) and
    set(contract.REQUIRED_CASES)<={c['id'] for c in cases},'F2 case identity')
   for case in cases:require(case['mislocated']==0 and case['other']==0,'F2 unresolved failure')
   standalone=z.read('ws-navigation-only/windows-host.map').decode('utf-8',errors='replace').lower()
   validate_standalone(standalone)
   jobs=fetch('actions/runs/%d/attempts/%d/jobs?per_page=100'%(run,attempt))['jobs']
   job=[j for j in jobs if j['name']=='installed F1 and native Windows search controls and lifecycle']
   require(len(job)==1 and job[0]['conclusion']=='success','host job failed')
   steps={s['name']:s['conclusion'] for s in job[0]['steps']}
   require(steps.get('Execute installed F2 and real native directory controls')=='success' and
    steps.get('Compile navigation without optional search')=='success','required navigation steps failed')
  result.update(accepted=True,navigation_ui_checks=count,original_f2_checks=len(checks),
   original_f1_strict_preserved=True,protocol_rejections=self_test(),job=job[0]['id'],
   consumer_sha256=product,review_sha256=review,artifact={k:meta[k] for k in ('id','name','size_in_bytes','digest','expires_at')})
 except Exception as error:result['problems'].append(type(error).__name__+': '+str(error))
 (output/'verified.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result),flush=True)
 require(result['accepted'],'navigation strict same-run proof rejected')

if __name__=='__main__':main()
