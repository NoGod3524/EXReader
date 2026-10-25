"""Actions-only immutable real macOS bundle + actual program/DSO proof authentication."""
from datetime import datetime,timezone
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import zipfile
from bundle import verify,safe
assert os.environ.get('GITHUB_ACTIONS')=='true'
p=argparse.ArgumentParser();p.add_argument('--artifact-id',default='');p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
if not a.artifact_id:
 (a.output/'status.json').write_text(json.dumps({'ready':False,'incoming_apple_status':'pending'})+'\n');raise SystemExit(0)
repo='repos/'+os.environ['GITHUB_REPOSITORY']+'/'
def api(path):return json.loads(subprocess.check_output(['gh','api',repo+path]))
artifact=api('actions/artifacts/'+str(int(a.artifact_id)))
assert not artifact['expired'] and 0<artifact['size_in_bytes']<=512*1024**2 and datetime.fromisoformat(artifact['expires_at'].replace('Z','+00:00'))>datetime.now(timezone.utc)
body=subprocess.check_output(['gh','api',repo+'actions/artifacts/'+str(artifact['id'])+'/zip'])
assert len(body)==artifact['size_in_bytes'] and 'sha256:'+hashlib.sha256(body).hexdigest()==artifact['digest']
with zipfile.ZipFile(io.BytesIO(body)) as archive:
 names=archive.namelist();assert len(names)==len(set(names)) and len(names)<=30000
 def find(suffix):
  if suffix in names:return suffix
  name,=[name for name in names if name==suffix or name.endswith('/'+suffix)];return name
 manifest_name=find('sender-bundle/manifest.json');prefix=manifest_name[:-len('manifest.json')]
 def read(name):
  safe(name);path=prefix+name;info=archive.getinfo(path);assert 0<info.file_size<=128*1024**2 and (info.external_attr>>16)&0o170000!=0o120000;return archive.read(path)
 verified=verify(read);peer=verified['manifest']['sender'];assert peer['platform']=='macos' and artifact['workflow_run']['head_sha']==peer['source_sha'] and str(artifact['workflow_run']['id'])==str(peer['run_id'])
 run=api('actions/runs/'+str(peer['run_id'])+'/attempts/'+str(peer['attempt']));assert run['status']=='completed' and run['conclusion']=='success' and run['head_sha']==peer['source_sha'] and run['run_attempt']==int(peer['attempt'])
 jobs=api('actions/runs/'+str(peer['run_id'])+'/attempts/'+str(peer['attempt'])+'/jobs?per_page=100')['jobs'];assert jobs and all(job['conclusion']=='success' for job in jobs)
 # Independent same-artifact program and installed-provider SDK copy, when named.
 assert hashlib.sha256(archive.read(find('record-interop'))).hexdigest()==peer['program_sha256']
 if peer.get('sdk_dso_basename'):
  basename=peer['sdk_dso_basename'];assert '/' not in basename and '\\' not in basename
  assert hashlib.sha256(archive.read(find('original-compatibility/libraries-new/'+basename))).hexdigest()==peer['sdk_dso_sha256']
 for name in verified['files']:
  target=a.output/'bundle'/safe(name);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(read(name))
 attestation={'source_sha':peer['source_sha'],'run_id':str(peer['run_id']),'attempt':str(peer['attempt']),'manifest_sha256':verified['manifest_sha256'],'artifact':{key:artifact[key] for key in ('id','name','size_in_bytes','digest','expires_at')},'program_sha256':peer['program_sha256'],'sdk_dso_sha256':peer['sdk_dso_sha256'],'actual_macho_executable_and_dylib_verified':True,'originals':verified['originals'],'revisions':verified['revisions'],'reading_records':verified['reading_records']}
 (a.output/'attestation.json').write_text(json.dumps(attestation,indent=2)+'\n');(a.output/'status.json').write_text(json.dumps({'ready':True,'incoming_apple_status':'ready-for-actual-receive'})+'\n');print(json.dumps(attestation),flush=True)
