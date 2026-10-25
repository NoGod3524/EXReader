"""Actions-only authentication of the fixed successful actual Apple raw3 sender ZIP."""
from datetime import datetime,timezone
import hashlib
import io
import json
import os
from pathlib import Path,PurePosixPath
import subprocess
import zipfile
from bundle import verify,parse
assert os.environ.get('GITHUB_ACTIONS')=='true'
PEER={'source_sha':'15dab6b2270dc296ed6239db67ced2e22d255e65','run_id':40196978163,'attempt':1,
 'native_job':121179826434,'strict_job':121186031984,'artifact_id':12600789926,'bytes':77056135,
 'digest':'sha256:92be56ffa04d7c334d4811a42821a314089b4f8ae01746f0dfdf456b5eab9bd5',
 'program_sha256':'5f59e17cf48e77b1ef8766695bf109895feac5e628bc18d9804ee625a2749913'}
repo='repos/'+os.environ['GITHUB_REPOSITORY']+'/'
def api(path):return parse(subprocess.check_output(['gh','api',repo+path]))
record=api('actions/runs/'+str(PEER['run_id'])+'/attempts/1')
assert record['head_sha']==PEER['source_sha'] and record['run_attempt']==1 and record['conclusion']=='success'
jobs=api('actions/runs/'+str(PEER['run_id'])+'/attempts/1/jobs?per_page=100')['jobs']
for job_id in (PEER['native_job'],PEER['strict_job']):
    actual,=[j for j in jobs if j['id']==job_id]
    assert actual['head_sha']==PEER['source_sha'] and actual['run_attempt']==1 and actual['conclusion']=='success'
artifact=api('actions/artifacts/'+str(PEER['artifact_id']))
assert artifact['id']==PEER['artifact_id'] and artifact['size_in_bytes']==PEER['bytes'] and artifact['digest']==PEER['digest'] and not artifact['expired']
assert artifact['name']=='apple-raw3-native-40196978163-1' and artifact['workflow_run']['head_sha']==PEER['source_sha'] and artifact['workflow_run']['id']==PEER['run_id']
assert datetime.fromisoformat(artifact['expires_at'].replace('Z','+00:00'))>datetime.now(timezone.utc)
body=subprocess.check_output(['gh','api',repo+'actions/artifacts/'+str(PEER['artifact_id'])+'/zip'],timeout=240)
assert len(body)==PEER['bytes'] and 'sha256:'+hashlib.sha256(body).hexdigest()==PEER['digest']
out=Path('build/android-raw3/apple-peer');out.mkdir(parents=True,exist_ok=True)
with zipfile.ZipFile(io.BytesIO(body)) as z:
    names=z.namelist();assert len(names)==len(set(names)) and len(names)<=30000 and sum(i.file_size for i in z.infolist())<512*1024**2
    for name in names:
        path=PurePosixPath(name);assert not path.is_absolute() and '..' not in path.parts and '\\' not in name and ':' not in name
        assert (z.getinfo(name).external_attr>>16)&0o170000!=0o120000
    result=parse(z.read('result.json'));assert result['accepted'] and result['source_sha']==PEER['source_sha'] and str(result['run_id'])==str(PEER['run_id']) and str(result['attempt'])=='1'
    for name,declared in result['files'].items():
        actual=z.read(name);assert len(actual)==declared['bytes'] and hashlib.sha256(actual).hexdigest()==declared['sha256']
    declared=result['files']['sender-bundle/manifest.json']
    verified=verify(lambda name:z.read('sender-bundle/'+name));manifest=verified['manifest']
    assert verified['manifest_sha256']==declared['sha256'] and verified['originals']==4 and verified['reading_records']==11
    sender=manifest['sender'];assert sender['platform']=='macos' and sender['source_sha']==PEER['source_sha'] and str(sender['run_id'])==str(PEER['run_id']) and str(sender['attempt'])=='1'
    assert sender['program_sha256']==PEER['program_sha256']
    assert hashlib.sha256(z.read('sender-bundle/proofs/program')).hexdigest()==sender['program_sha256']
    assert hashlib.sha256(z.read('sender-bundle/proofs/sdk.dylib')).hexdigest()==sender['sdk_dso_sha256']
    pdf=next(row for row in manifest['originals'] if row['role']=='pdf')
    assert pdf['bytes']==8845 and pdf['sha256']=='5627a430fa04cbe11d38eb2682e336ef21e147d445753ed46ed11a7d5e3167cc'
    for name in verified['files']+['proofs/program','proofs/sdk.dylib']:
        target=out/'bundle'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(z.read('sender-bundle/'+name))
attestation={**PEER,'artifact':{k:artifact[k] for k in ['id','name','digest','size_in_bytes','expires_at']},
 'accepted':True,'manifest_sha256':verified['manifest_sha256'],'originals':verified['originals'],'revisions':verified['revisions'],'reading_records':verified['reading_records'],
 'complete_graph':True,'original_inventory_verified':True,'actual_native_sender':sender}
(out/'attestation.json').write_text(json.dumps(attestation,indent=2)+'\n');print(json.dumps(attestation),flush=True)
