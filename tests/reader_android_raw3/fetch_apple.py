"""Actions-only authentication of the fixed successful actual Apple raw3 sender ZIP."""
from datetime import datetime,timezone
import hashlib
import io
import json
import os
from pathlib import Path,PurePosixPath
import subprocess
import sqlite3
import tempfile
import zipfile
from bundle import verify,verify_null,parse
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
    # Inspect the authenticated producer database read-only; never synthesize or
    # rewrite a reading wire. The negative is separate from the 11 normal records.
    database_name='profiles/source-version-and-NULL-operations/reader-catalog.db'
    database_bytes=z.read(database_name);database_identity=result['files'][database_name]
    assert len(database_bytes)==database_identity['bytes'] and hashlib.sha256(database_bytes).hexdigest()==database_identity['sha256']
    negative_root=out/'null-bundle';negative_root.mkdir(parents=True,exist_ok=True)
    database_path=negative_root/'origin-catalog.db';database_path.write_bytes(database_bytes)
    sidecars={}
    for suffix in ('-wal','-shm'):
        name=database_name+suffix
        if name in result['files']:
            body=z.read(name);declared=result['files'][name]
            assert len(body)==declared['bytes'] and hashlib.sha256(body).hexdigest()==declared['sha256']
            (negative_root/('origin-catalog.db'+suffix)).write_bytes(body);sidecars[suffix]=declared
    with tempfile.TemporaryDirectory() as temporary:
        inspected=Path(temporary)/'catalog.db';inspected.write_bytes(database_bytes)
        for suffix in sidecars:(Path(temporary)/('catalog.db'+suffix)).write_bytes((negative_root/('origin-catalog.db'+suffix)).read_bytes())
        connection=sqlite3.connect(inspected.resolve().as_uri()+'?mode=ro',uri=True)
        try:rows=connection.execute('SELECT revision_id,entity_kind,entity_key,body_sha256,CAST(body_json AS BLOB) FROM reader_revisions').fetchall()
        finally:connection.close()
    retained={}
    for rid,kind,key,sha,body in rows:
        assert isinstance(body,bytes) and hashlib.sha256(body).hexdigest()==sha
        wire=parse(body);assert (wire['id'],wire['entity_kind'],wire['entity_key'])==(rid,kind,key)
        retained[rid]=(wire,body,sha)
    nulls=[rid for rid,(wire,body,sha) in retained.items() if wire['entity_kind']=='annotation' and wire.get('payload') and wire['payload'].get('book_key')==pdf['book_key'] and wire['payload'].get('location',{}).get('anchor_version')==3 and wire['payload']['location']['selector']['exact']=={'base64':None,'size':0}]
    null_id,=nulls;null_wire=retained[null_id][0];needed=set();visiting=set()
    def collect(rid):
        assert rid not in visiting and rid in retained
        if rid in needed:return
        visiting.add(rid)
        for parent in retained[rid][0]['parents']:collect(parent)
        visiting.remove(rid);needed.add(rid)
    collect(null_id)
    for rid,(wire,body,sha) in retained.items():
        if wire['entity_kind']=='book' and wire['entity_key']==pdf['book_key']:collect(rid)
    declarations=[]
    for rid in sorted(needed):
        wire,body,sha=retained[rid];name='revisions/'+rid+'.json';target=negative_root/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(body)
        declarations.append({k:wire[k] for k in ('id','entity_kind','entity_key','parents')}|{'file':name,'bytes':len(body),'sha256':sha,'book_key':pdf['book_key']})
    original_path=negative_root/pdf['file'];original_path.parent.mkdir(parents=True,exist_ok=True);original_path.write_bytes(z.read('sender-bundle/'+pdf['file']))
    negative={'schema':1,'purpose':'authentic-apple-null-negative','sender':sender,'origin_database':{'file':database_name,**database_identity,'sidecars':sidecars},'originals':[pdf],'revisions':declarations,'null_revision':null_id,'annotation_id':null_wire['payload']['annotation_id']}
    (negative_root/'manifest.json').write_text(json.dumps(negative,indent=2)+'\n')
    null_verified=verify_null(lambda name:(negative_root/name).read_bytes())
attestation={**PEER,'artifact':{k:artifact[k] for k in ['id','name','digest','size_in_bytes','expires_at']},
 'accepted':True,'manifest_sha256':verified['manifest_sha256'],'originals':verified['originals'],'revisions':verified['revisions'],'reading_records':verified['reading_records'],
 'complete_graph':True,'original_inventory_verified':True,'actual_native_sender':sender,
 'null_negative':{k:v for k,v in null_verified.items() if k not in ('manifest','files')}|{'origin_database':negative['origin_database']}}
(out/'attestation.json').write_text(json.dumps(attestation,indent=2)+'\n');print(json.dumps(attestation),flush=True)
