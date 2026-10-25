# SPDX-License-Identifier: MIT
"""Strict source-bound report contract, shared by producer and ZIP verifier."""
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
REPORTS=['source-guard.json','evidence/result.json','evidence/composition-c.json','evidence/composition-c-relocated.json','evidence/composition-run1.json','evidence/composition-run2.json','gates/gates.json','install-all.json','sdk-only.json','prefix-scan.json','reviewed/result.json','reviewed/run0/report.json','reviewed/run1/report.json','original/suites.json','original/cloud/result.json','original/bulk/report.json','original/link/report.json','original/history/summary.json','original/history/report.json','original/keyboard/result.json','original/information/report.json','original/status/result.json','original/profiles/result.json']
BINARIES=['composition-c','composition-cxx','composition-c-relocated','composition-cxx-relocated','reviewed-flow','reviewed-flow-relocated','cloud-probe','cloud-cpp-consumer','cloud-review-probe','bulk-probe','bulk-c-consumer','link-probe','link-cpp-consumer','link-worker','link-sdk-consumer','jump-history-probe','jump-history-c-consumer','keyboard-c-consumer','keyboard-cpp-consumer','keyboard-probe','book-info-probe','book-info-compare','status-view-consumer','status-view-c-consumer','revision-consumer','profiles-probe','profiles-session-consumer','profiles-worker']
def require(ok,message):
 if not ok:raise ValueError(message)
def load_module(folder,filename):
 path=ROOT/'tests'/folder/filename
 sys.path.insert(0,str(path.parent))
 spec=importlib.util.spec_from_file_location(folder+'_'+path.stem,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
def identity(report,source,run,attempt):
 if 'identity' in report:
  value=report['identity'];got=(value.get('GITHUB_SHA'),str(value.get('GITHUB_RUN_ID')),str(value.get('GITHUB_RUN_ATTEMPT')))
 else:got=(report.get('source_sha',report.get('source')),str(report.get('run_id')),str(report.get('attempt')))
 require(got==(source,str(run),str(attempt)),'report source/run/attempt differs')
def named(rows,field='pass',expected=None):
 names=[r.get('name',r.get('id')) for r in rows]
 require(rows and None not in names and len(names)==len(set(names)),'missing or duplicate named checks')
 require(all(r.get(field) is True for r in rows),'failed named check')
 if expected is not None:require(set(names)==set(expected),'named check identity differs')
 return names
def validate(doc,binary_hashes,source,run,attempt,platform):
 for path in ['source-guard.json','evidence/result.json','gates/gates.json','reviewed/result.json','original/suites.json','original/cloud/result.json','original/bulk/report.json','original/link/report.json','original/history/summary.json','original/keyboard/result.json','original/information/report.json','original/status/result.json','original/profiles/result.json']:identity(doc[path],source,run,attempt)
 require(doc['source-guard.json'].get('accepted') is True,'source guard failed')
 base=load_module('reader_module_composition','check_artifacts.py')
 bundle=dict(result=doc['evidence/result.json'],gates=doc['gates/gates.json'],manifest=doc['install-all.json'])
 require(not base.verify_bundles({key:bundle for key,_ in base.PLATFORMS},source,run,attempt),'original composition criteria failed')
 original=load_module('reader_module_composition','check_composition.py')
 for name,required in [('composition-c',original.REQUIRED_C),('composition-c-relocated',original.REQUIRED_C),('composition-run1',original.REQUIRED_CXX),('composition-run2',original.REQUIRED_CXX)]:
  report=doc['evidence/'+name+'.json'];names=named(report.get('checks',[]));require(set(required).issubset(names) and report.get('failures')==0,'original named consumer criteria missing or failed')
 for name,record in doc['evidence/result.json']['consumers'].items():require(binary_hashes[name]==record['sha256'],'actual original consumer binary differs '+name)
 reviewed=doc['reviewed/result.json'];require(reviewed.get('accepted') is True and not reviewed.get('problems'),'shared flow refused')
 required=re.findall(r'need\([^;]*?,"([^"]+)"\);',(Path(__file__).parent/'consumer/reviewed_flow.cpp').read_text())
 require(len(required)>=35,'shared-flow contract incomplete')
 for i,key in enumerate(['reviewed-flow','reviewed-flow-relocated']):
  raw=doc['reviewed/run'+str(i)+'/report.json'];require(raw.get('accepted') is True,'raw shared-flow failed');named(raw.get('checks',[]),expected=required)
  require(reviewed['runs'][i]['binary_sha256']==binary_hashes[key],'actual shared-flow binary differs')
 suites=doc['original/suites.json'];require(suites.get('accepted') is True,'original suite runner failed')
 expected={'cloud','bulk','link','history','keyboard','information','status','profiles'}
 require(len(suites.get('suites',[]))==8 and {r['name'] for r in suites['suites']}==expected and all(r.get('accepted') is True for r in suites['suites']),'original suite missing or failing')
 cloud=load_module('reader_webdav_import','check_artifacts.py');cloud.require_report(doc['original/cloud/result.json'],source,str(run),str(attempt))
 bulk=load_module('reader_bulk_organization','check_artifacts.py');bulk.require_report(doc['original/bulk/report.json'],source,bulk.CHECKS,str(run),str(attempt))
 link=load_module('reader_external_link_policy','check_artifacts.py');link.require_report(doc['original/link/report.json'],source,platform)
 history=load_module('reader_jump_history','check_artifacts.py');hs=doc['original/history/summary.json'];history.authenticate_checks(doc['original/history/report.json'],hs)
 require(hs.get('jump_history_module_accepted') is True and not hs.get('problems') and hs.get('checks_failed')==0,'jump history failed')
 require(hs['probe_sha256']==binary_hashes['jump-history-probe'] and hs['c_consumer_sha256']==binary_hashes['jump-history-c-consumer'],'history binaries differ')
 keyboard=load_module('reader_keyboard_actions','check_keyboard.py');kr=doc['original/keyboard/result.json'];require(kr.get('accepted') is True and not kr.get('problems'),'keyboard failed')
 statuses={}
 for row in kr.get('cases',[]):
  key=(row['suite'],row['name']);require(key not in statuses,'duplicate keyboard case');statuses[key]=row['status']
  require(row['status'] in ('PASS','SKIP'),'keyboard failed or unknown status')
  if row['status']=='SKIP':require(row['suite']=='probe' and row['name'] in keyboard.DOCUMENTED_SKIPS,'undocumented keyboard skip')
 for suite,names in [('consumer-c',keyboard.CASE_C),('consumer-cpp',keyboard.CASE_CPP),('probe',keyboard.CASE_PROBE)]:
  require({name for s,name in statuses if s==suite}==set(names),'keyboard required cases differ')
 info=load_module('reader_book_information','check_book_information.py');ir=doc['original/information/report.json'];require(ir.get('ok') is True,'book-info failed');named(ir.get('checks',[]),'ok',info.REQUIRED_CASES)
 require(all(c.get('assertions',0)>0 and not c.get('problems') for c in ir['checks']),'book-info incomplete assertions')
 status=load_module('reader_sync_status_view','aggregate.py');sr=doc['original/status/result.json'];require(sr.get('accepted') is True and len(sr.get('checks',[]))==len(set(sr.get('checks',[]))) and set(sr.get('checks',[]))==status.REQUIRED and sr.get('metadata_wait_positive_covered') is True,'status cases failed or changed')
 require(sr['consumer_sha256']==binary_hashes['status-view-consumer'] and sr['c_consumer_sha256']==binary_hashes['status-view-c-consumer'],'status binaries differ')
 profiles=load_module('reader_account_profiles','check_artifacts.py');profiles.verify_report(doc['original/profiles/result.json'],source,str(run),str(attempt),platform)
 return dict(original_composition_items=len(doc['evidence/result.json']['items']),shared_flow_items=len(required),cloud=len(doc['original/cloud/result.json']['checks']),bulk=len(doc['original/bulk/report.json']['checks']),link=len(doc['original/link/report.json']['checks']),history=hs['checks_total'],keyboard=len(kr['cases']),keyboard_skips=kr.get('skipped',[]),information_cases=len(ir['checks']),information_assertions=ir['assertions'],status=len(sr['checks']),profiles=doc['original/profiles/result.json']['checks'])
def digest(data):return hashlib.sha256(data).hexdigest()
def validate_files(manifest,read):
 required=set(REPORTS)|{'binaries/'+name for name in BINARIES}
 require(set(manifest.get('files',{}))==required,'missing or unexpected required bundle member')
 documents={};binary_hashes={}
 for path,record in manifest['files'].items():
  data=read(path);require(len(data)>0 and len(data)==record['bytes'] and digest(data)==record['sha256'],'member bytes/digest differs '+path)
  if path in REPORTS:documents[path]=json.loads(data)
  else:binary_hashes[path.split('/')[-1]]=digest(data)
 return documents,binary_hashes
