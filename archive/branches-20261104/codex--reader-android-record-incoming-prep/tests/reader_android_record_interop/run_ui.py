"""Actions-only actual Android writer and unchanged-wire parent-negative receiver."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
from bundle import folder,parse,safe

assert os.environ.get('GITHUB_ACTIONS')=='true'
p=argparse.ArgumentParser();p.add_argument('--fixtures',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--incoming',type=Path);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
identity={key:os.environ[value] for key,value in [('source_sha','GITHUB_SHA'),('run_id','GITHUB_RUN_ID'),('attempt','GITHUB_RUN_ATTEMPT')]};package='org.exreader.host'
expected={'sender':['txt_actual_owner_point_range_commands_retained_and_read_only_resolve','epub_actual_owner_point_range_commands_retained_and_read_only_resolve','pdf_actual_owner_point_range_commands_retained_and_read_only_resolve','cbz_actual_owner_point_range_commands_retained_and_read_only_resolve','unknown_prefix_future_parser_different_original_refused','complete_actual_book_and_reading_wire_ancestor_export'],'missing-parent':['actual_received_child_without_ancestor_is_pending_and_unreadable','exact_original_ancestors_complete_graph_and_found_without_outbox_write']}
incoming_ready=bool(a.incoming and (a.incoming/'status.json').is_file() and parse((a.incoming/'status.json').read_bytes())['ready'])
if incoming_ready:expected['incoming']=['actual_apple_complete_original_wires_public_receive_and_sdk_found']
def adb(*args,input=None):return subprocess.check_output(['adb',*map(str,args)],input=input,stderr=subprocess.STDOUT,timeout=120)
def private(name):return adb('exec-out','run-as',package,'cat','files/'+name)
def save(name,data):
 file=a.output/name;file.parent.mkdir(parents=True,exist_ok=True);file.write_bytes(data)
def reset():
 assert adb('shell','pm','clear',package).strip()==b'Success';adb('shell','am','start','-W','-n',package+'/.MainActivity');adb('shell','am','force-stop',package)
def push_private(file,relative):
 name=safe(relative);temporary='/data/local/tmp/record-interop-'+hashlib.sha256(name.encode()).hexdigest();adb('push',file,temporary);adb('exec-out','run-as',package,'mkdir','-p','files/'+str(Path(name).parent));adb('exec-out','run-as',package,'cp',temporary,'files/'+name)
manifest=parse((a.fixtures/'manifest.json').read_bytes());manifest['books']=[row for row in manifest['books'] if row['role'] in ('txt','epub','pdf','cbz')];reports=[];accepted=False
try:
 adb('shell','cmd','uimode','night','no')
 for phase,names in expected.items():
  reset();adb('logcat','-c')
  if phase=='sender':
   for row in manifest['books']:
    data=(a.fixtures/row['file']).read_bytes();assert len(data)==row['bytes'] and hashlib.sha256(data).hexdigest()==row['sha256'];push_private(a.fixtures/row['file'],'preferences-fixtures/'+row['file'])
   adb('shell',f"run-as {package} sh -c 'cat > files/preferences-input.json'",input=json.dumps(manifest,ensure_ascii=False).encode())
  elif phase=='missing-parent':
   for file in (a.output/'bundle').rglob('*'):
    if file.is_file():push_private(file,'interop-incoming/'+file.relative_to(a.output/'bundle').as_posix())
  else:
   peer=folder(a.incoming/'bundle');assert peer['manifest']['sender']['platform']=='macos'
   for name in peer['files']:
    if not name.startswith('proofs/'):push_private(a.incoming/'bundle'/name,'interop-incoming/'+name)
   push_private(a.incoming/'attestation.json','interop-incoming-attestation.json')
  command=['adb','shell','am','instrument','-w','-r','-e','phase',phase]
  for key,value in identity.items():command.extend(('-e',key,value))
  command.append(package+'.test/'+package+'.RecordInteropTest');process=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=1500,check=False);save(phase+'-instrumentation.txt',process.stdout)
  raw=private('record-interop-'+phase+'.json');save(phase+'-raw-report.json',raw);report=parse(raw);print(json.dumps(report,ensure_ascii=False),flush=True);save(phase+'-logcat.txt',adb('logcat','-d','-v','threadtime','-t','5000'))
  for observation in report['observations']:save('captures/'+phase+'-'+observation['name']+'.png',private('preferences-captures/'+observation['name']+'.png'))
  assert process.returncode==0 and all(report.get(key)==value for key,value in identity.items()) and report['phase']==phase and report['passed'] is True and report['count']==len(names)
  assert [row['name'] for row in report['checks']]==names and all(row['pass'] is True for row in report['checks'])
  assert b'RECORD_INTEROP_SENDER_PASS' in process.stdout and b'INSTRUMENTATION_CODE: -1' in process.stdout
  if phase=='sender':
   raw_manifest=private('interop-outgoing/manifest.json');save('bundle/manifest.json',raw_manifest);bundle=parse(raw_manifest)
   for row in bundle['originals']+bundle['revisions']:
    data=private('interop-outgoing/'+safe(row['file']));save('bundle/'+row['file'],data);assert len(data)==row['bytes'] and hashlib.sha256(data).hexdigest()==row['sha256']
   verified=folder(a.output/'bundle');assert verified['manifest_sha256']==report['manifest_sha256'];assert all(bundle['sender'][key]==value for key,value in identity.items())
   save('bundle-validation.json',(json.dumps({key:value for key,value in verified.items() if key!='manifest'},indent=2)+'\n').encode())
  reports.append(report);adb('shell','am','force-stop',package)
 assert len({row['pid'] for row in reports})==len(expected) and sum(row['count'] for row in reports)==(9 if incoming_ready else 8);accepted=True
finally:
 result={**identity,'sender_export_accepted':accepted,'checks':sum(row['count'] for row in reports),'phases':reports,'incoming_apple_status':('passed' if accepted else 'failed') if incoming_ready else 'pending','incoming_apple_accepted':incoming_ready and accepted,'bidirectional_interoperability_accepted':False,'physical_device':False,'api':34,'abi':'x86_64','complete_product':False}
 save('result.json',(json.dumps(result,ensure_ascii=False,indent=2)+'\n').encode());print(json.dumps({**identity,'sender_export_accepted':accepted,'checks':result['checks']}),flush=True)
