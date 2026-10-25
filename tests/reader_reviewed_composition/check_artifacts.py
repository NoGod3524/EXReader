# SPDX-License-Identifier: MIT
"""Strict same-source/run/attempt identity plus raw ZIP and binary evidence."""
import argparse
import copy
from datetime import datetime,timezone
import io
import json
import os
import re
from pathlib import Path
import sys
import tempfile
import zipfile
from contract import BINARIES,REPORTS,RAW,SANITIZER,digest,identity,require,validate,validate_files
from check_prefix import PACKAGES
from g1 import REPORT_TAILS as G1_REPORT_TAILS, load as load_g1
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
from check_parallel_integration import download_artifact_zip,fetch,pages
WORKFLOW='.github/workflows/reader-reviewed-composition.yml'
PLATFORMS=[('linux','Linux'),('windows','Windows'),('macos','macOS')]
def authenticate_run(run,jobs,source,run_id,attempt):
 require((str(run.get('id')),run.get('head_sha'),str(run.get('run_attempt')),run.get('path','').split('@')[0])==(str(run_id),source,str(attempt),WORKFLOW),'run identity differs')
 expected={'one-prefix composition ('+key+')' for key,_ in PLATFORMS}
 producers=[j for j in jobs if j.get('name') in expected]
 require(len(producers)==3 and {j['name'] for j in producers}==expected,'missing/duplicate upstream jobs')
 require(all(j.get('id',0)>0 for j in producers) and len({j['id'] for j in producers})==3,'missing/duplicate upstream job IDs')
 for job in producers:
  require((job.get('head_sha'),str(job.get('run_id')),str(job.get('run_attempt')),job.get('status'),job.get('conclusion'))==(source,str(run_id),str(attempt),'completed','success'),'upstream not completed/success on this source/run/attempt')
 return producers
def authenticate_artifact(artifacts,name,source,run_id):
 require(len({a.get('id') for a in artifacts})==len(artifacts),'duplicate artifact IDs')
 matches=[a for a in artifacts if a.get('name')==name];require(len(matches)==1,'missing/duplicate artifact '+name);a=matches[0]
 require(type(a.get('id')) is int and a['id']>0 and type(a.get('size_in_bytes')) is int and a['size_in_bytes']>0 and a.get('expired') is False,'empty/expired artifact')
 require(datetime.fromisoformat(a['expires_at'].replace('Z','+00:00'))>datetime.now(timezone.utc),'expired artifact timestamp')
 require(a.get('workflow_run',{}).get('head_sha')==source and str(a['workflow_run'].get('id'))==str(run_id),'artifact source/run differs')
 require(re.fullmatch(r'sha256:[0-9a-f]{64}',a.get('digest') or '') is not None,'API digest absent or malformed')
 return a
def check_zip_bytes(data,artifact):require(len(data)==artifact['size_in_bytes'] and 'sha256:'+digest(data)==artifact['digest'],'downloaded ZIP size/digest differs')
def archive_root(names):
 require(len(names)==len(set(names)),'duplicate ZIP members')
 require(all(not n.startswith('/') and '\\' not in n and '..' not in n.split('/') for n in names),'unsafe ZIP member')
 roots=[n[:-len('bundle.json')] for n in names if n=='bundle.json' or n.endswith('/bundle.json')]
 require(len(roots)==1,'missing/duplicate bundle report');prefix=roots[0]
 for relative in REPORTS+RAW+['binaries/'+n for n in BINARIES]:
  matches=[n for n in names if n==relative or n.endswith('/'+relative)]
  require(matches==[prefix+relative],'missing/duplicate report or binary '+relative)
 return prefix
def self_test():
 load_g1('reader_g1_integration','aggregate.py').self_test()
 run=dict(id=1,head_sha='source',run_attempt=2,path=WORKFLOW)
 jobs=[dict(id=i,name='one-prefix composition ('+key+')',head_sha='source',run_id=1,run_attempt=2,status='completed',conclusion='success') for i,(key,_) in enumerate(PLATFORMS,1)]
 authenticate_run(run,jobs,'source',1,2)
 count=0
 def rejected(fn):
  nonlocal count
  try:fn()
  except (ValueError,KeyError):count+=1;return
  raise AssertionError('tampered control accepted')
 for field,value in [('head_sha','foreign'),('run_attempt',3),('path','other.yml')]:
  changed=dict(run);changed[field]=value;rejected(lambda:authenticate_run(changed,jobs,'source',1,2))
 for field,value in [('id',2),('head_sha','foreign'),('run_id',7),('run_attempt',3),('status','in_progress'),('conclusion','failure')]:
  changed=copy.deepcopy(jobs);changed[0][field]=value;rejected(lambda:authenticate_run(run,changed,'source',1,2))
 rejected(lambda:authenticate_run(run,jobs[:-1],'source',1,2));rejected(lambda:authenticate_run(run,jobs+[jobs[0]],'source',1,2))
 names=['bundle.json']+REPORTS+RAW+['binaries/'+n for n in BINARIES];archive_root(names)
 rejected(lambda:archive_root(names+[names[1]]));rejected(lambda:archive_root(names+['other/bundle.json']));rejected(lambda:archive_root(names+['other/evidence/result.json']));rejected(lambda:archive_root(names[:-1]));rejected(lambda:archive_root(names+['../evil']))
 artifact=dict(id=1,name='a',size_in_bytes=3,expired=False,expires_at='2099-01-01T00:00:00Z',workflow_run=dict(id=1,head_sha='source'),digest='sha256:'+digest(b'zip'))
 authenticate_artifact([artifact],'a','source',1);check_zip_bytes(b'zip',artifact)
 for field,value in [('expired',True),('expired',None),('id',True),('size_in_bytes',0),('digest',None),('digest','sha256:'+'z'*64),('expires_at','2000-01-01T00:00:00Z')]:
  changed=dict(artifact);changed[field]=value;rejected(lambda:authenticate_artifact([changed],'a','source',1))
 rejected(lambda:authenticate_artifact([artifact,artifact],'a','source',1));rejected(lambda:check_zip_bytes(b'bad',artifact))
 rejected(lambda:authenticate_artifact([artifact,dict(artifact,name='other')],'a','source',1))
 records={p:b'{}' for p in REPORTS+RAW};records['original/history/summary.json']=json.dumps(dict(report_sha256=digest(b'{}'))).encode();records.update({'binaries/'+n:b'bin' for n in BINARIES})
 for phase in ('fresh','relocated'):
  records['g1/'+phase+'/phase.json']=json.dumps(dict(reports={name:digest(records['g1/'+phase+'/'+name]) for name in G1_REPORT_TAILS if name!='phase.json'})).encode()
 manifest=dict(files={p:dict(bytes=len(v),sha256=digest(v)) for p,v in records.items()})
 validate_files(manifest,records.__getitem__)
 changed=copy.deepcopy(manifest);changed['files'].pop(REPORTS[0]);rejected(lambda:validate_files(changed,records.__getitem__))
 records[REPORTS[0]]=b'{"accepted":true}';rejected(lambda:validate_files(manifest,records.__getitem__))
 records[REPORTS[0]]=b'{}';records['binaries/'+BINARIES[0]]=b'evil';rejected(lambda:validate_files(manifest,records.__getitem__))
 records['binaries/'+BINARIES[0]]=b'bin'
 for tail in ('thumbnails/result.json','reading-commands/summary.json','annotation-view/summary.json','annotation-export/result.json','local-downloads/report.json','result.json'):
  changed=copy.deepcopy(manifest);changed['files'].pop('g1/relocated/'+tail);rejected(lambda:validate_files(changed,records.__getitem__))
 changed=copy.deepcopy(manifest);changed['files'].pop('g1/fresh/binaries/g1-chain');rejected(lambda:validate_files(changed,records.__getitem__))
 changed=copy.deepcopy(manifest);changed['files']['g1/relocated/binaries/ld-probe']['sha256']='0'*64;rejected(lambda:validate_files(changed,records.__getitem__))
 altered=dict(records);altered['g1/relocated/phase.json']=b'{"reports":{}}';changed=copy.deepcopy(manifest);changed['files']['g1/relocated/phase.json']=dict(bytes=len(altered['g1/relocated/phase.json']),sha256=digest(altered['g1/relocated/phase.json']));rejected(lambda:validate_files(changed,altered.__getitem__))
 for field,value in [('source_sha','wrong'),('run_id','wrong'),('attempt','wrong')]:
  report=dict(source_sha='source',run_id='1',attempt='2');report[field]=value;rejected(lambda:identity(report,'source','1','2'))
 print('strict protocol negative controls passed:',count)
 return count

def main():
 require(os.environ.get('GITHUB_ACTIONS')=='true','Actions only')
 p=argparse.ArgumentParser();p.add_argument('--self-test',action='store_true');p.add_argument('--downloads',type=Path);p.add_argument('--output',type=Path);a=p.parse_args()
 if a.self_test:self_test();return 0
 a.output.mkdir(parents=True,exist_ok=True);a.downloads.mkdir(parents=True,exist_ok=True)
 source=os.environ['GITHUB_SHA'];run_id=os.environ['GITHUB_RUN_ID'];attempt=os.environ['GITHUB_RUN_ATTEMPT']
 result=dict(accepted=False,source_sha=source,run_id=run_id,attempt=attempt,jobs=[],artifacts=[],platforms={},problems=[],host_ui_accepted=False,performance_accepted=False,android_accepted=False,ios_accepted=False,complete_product=False)
 result.update(acceptance_scope='fixed-source 26 optional packages plus SDK: 27 installed package configs',packages=sorted(PACKAGES),task_wide_accepted=False,task_gap='Pending the complete current-source 18 optional package baseline plus eight reviewed additions.')
 try:
  result['negative_controls']=self_test()
  run=fetch('actions/runs/'+run_id);jobs=pages('actions/runs/'+run_id+'/attempts/'+attempt+'/jobs','jobs');result['jobs']=authenticate_run(run,jobs,source,run_id,attempt)
  artifacts=pages('actions/runs/'+run_id+'/artifacts','artifacts');case_sets={};keyboard_sets={};original_sets={};history_stable={};g1_sets={}
  for key,platform in PLATFORMS:
   name='reader-reviewed-composition-'+key+'-'+run_id+'-'+attempt;a_meta=authenticate_artifact(artifacts,name,source,run_id)
   with tempfile.TemporaryFile() as stream:download_artifact_zip(a_meta['id'],stream);stream.seek(0);data=stream.read()
   check_zip_bytes(data,a_meta);(a.downloads/(name+'.zip')).write_bytes(data)
   with zipfile.ZipFile(io.BytesIO(data)) as archive:
    prefix=archive_root(archive.namelist());manifest=json.loads(archive.read(prefix+'bundle.json'));identity(manifest,source,run_id,attempt)
    require(manifest.get('accepted') is True and manifest.get('runner_os')==platform and not manifest.get('problems'),'producer bundle refused or wrong platform')
    docs,binary_hashes=validate_files(manifest,lambda path:archive.read(prefix+path))
    named_results=validate(docs,binary_hashes,source,run_id,attempt,platform)
    case_sets[key]=[r['name'] for r in docs['reviewed/run0/report.json']['checks']]
    keyboard_sets[key]={(c['suite'],c['name']):c['status'] for c in docs['original/keyboard/result.json']['cases']}
    original_sets[key]={name:sorted(r[field] for r in docs[path][rows]) for name,path,rows,field in [('cloud','original/cloud/result.json','checks','id'),('bulk','original/bulk/report.json','checks','name'),('link','original/link/report.json','checks','name'),('history','original/history/report.json','checks','name'),('information','original/information/report.json','checks','name'),('profiles','original/profiles/result.json','cases','name')]}
    original_sets[key]['status']=docs['original/status/result.json']['checks']
    g1_sets[key]={}
    for phase in ('fresh','relocated'):
     base='g1/'+phase+'/'
     g1_sets[key][phase]={name:sorted(row['name'] for row in docs[base+path]['checks']) for name,path in [('chain','chain.json'),('commands','reading-commands/report.json'),('view','annotation-view/work/report.json'),('local','local-downloads/report.json')]}
     tr=docs[base+'thumbnails/result.json']
     export_gate=load_g1('reader_annotation_export','check_artifacts.py');er=docs[base+'annotation-export/result.json']
     g1_sets[key][phase].update(thumbnails=sorted(n for n in tr['check_names'] if not n.startswith('threads:')),thumbnail_regressions=sorted(tr['regress_check_names']),thumbnail_faults=sorted(tr['fault_check_names']),export=sorted(set(er['checks'])-export_gate.OPTIONS),export_outcomes={'cases':{c['id']:c for c in er['cases'] if c['id'].startswith('export-')},'digests':er['digests']},local_regressions=sorted(docs[base+'local-regressions/regressions.json']['cases']))
    hs=docs['original/history/summary.json'];history_stable[key]=dict(originals=hs['originals'],cases=sorted(c['id'] for c in hs['cases']),steps=sorted(s['step'] for s in hs['lifecycle']),no_write={k:hs['no_write'][k] for k in ('revision_rows','outbox_rows','sdk_progress_records','sdk_notes','sdk_fixed_notes','sdk_epub_notes','databases_unchanged','control_write_changed')})
   result['platforms'][key]=dict(named_results=named_results,binaries=binary_hashes)
   result['artifacts'].append({f:a_meta[f] for f in ('id','name','size_in_bytes','digest','expires_at')})
  require(case_sets['linux']==case_sets['windows']==case_sets['macos'],'cross-platform shared-flow case identity differs')
  require(original_sets['linux']==original_sets['windows']==original_sets['macos'],'cross-platform original case identity differs')
  require(history_stable['linux']==history_stable['windows']==history_stable['macos'],'cross-platform original history proof differs')
  require(g1_sets['linux']==g1_sets['windows']==g1_sets['macos'],'cross-platform retained G1 check identities differ')
  require(all(value['fresh']==value['relocated'] for value in g1_sets.values()),'retained G1 phase check identities differ')
  require(set(keyboard_sets['linux'])==set(keyboard_sets['windows'])==set(keyboard_sets['macos']),'keyboard case identity differs across platforms')
  skipped_everywhere=[]
  for suite,name in keyboard_sets['linux']:
   values=[keyboard_sets[key][suite,name] for key,_ in PLATFORMS]
   if suite!='probe':require(values==['PASS']*3,'installed keyboard case skipped')
   elif values.count('PASS')<2:
    require(name in ('ime-composing-passthrough','reader-repeat-bounded','deactivate-cancels') and all(v in ('PASS','SKIP') for v in values),'undocumented native probe gap: '+name)
    if values.count('PASS')==0:skipped_everywhere.append(name)
  require(len(skipped_everywhere)<=2,'too many native keyboard cases skipped everywhere')
  result['keyboard_skipped_everywhere']=skipped_everywhere
  result['accepted']=True
  result['task_wide_accepted']=True
  result['task_gap']=None
 except Exception as e:result['problems'].append(str(e))
 (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));return 0 if result['accepted'] else 1
if __name__=='__main__':raise SystemExit(main())
