"""Authenticate the real accepted Mac packet; preserve its exact wire bytes."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tests/reader_hosts_integration'))
from final import Bundle,fetch,require
SOURCE='15dab6b2270dc296ed6239db67ced2e22d255e65'
RUN=40196978163
ARTIFACT=12600789926
DIGEST='sha256:92be56ffa04d7c334d4811a42821a314089b4f8ae01746f0dfdf456b5eab9bd5'


def load(out):
    require(os.environ.get('GITHUB_ACTIONS')=='true','Actions only')
    metadata=fetch('actions/runs/'+str(RUN));require(metadata['head_sha']==SOURCE and metadata['run_attempt']==1 and metadata['conclusion']=='success','Mac source/run not accepted')
    jobs=fetch('actions/runs/%d/attempts/1/jobs?per_page=100'%RUN)['jobs']
    require({row['id'] for row in jobs if row['conclusion']=='success'}=={121179826434,121186031984},'Mac original job set differs')
    meta=fetch('actions/artifacts/'+str(ARTIFACT));require(meta['digest']==DIGEST and meta['size_in_bytes']==77056135 and
      meta['workflow_run']['head_sha']==SOURCE and meta['workflow_run']['id']==RUN,'Mac artifact identity differs')
    bundle=Bundle(meta);out.mkdir(parents=True,exist_ok=False)
    try:
        report=bundle.report('result.json');require(report['accepted'] and report['source_sha']==SOURCE and str(report['run_id'])==str(RUN) and str(report['attempt'])=='1','foreign Mac report')
        for path,entry in report['files'].items():
            data=bundle.bytes(path,128*1024**2)
            require(len(data)==entry['bytes'] and hashlib.sha256(data).hexdigest()==entry['sha256'],'Mac inventoried member differs')
        raw=bundle.bytes('sender-bundle/manifest.json',2*1024**2)
        require(hashlib.sha256(raw).hexdigest()=='f0960b35374e12827a8966f7022dc3f632e44c87419ca1482288386fb8031566','Mac manifest differs')
        manifest=json.loads(raw);require(len(manifest['reading_records'])==11 and len(manifest['originals'])==4 and len(manifest['revisions'])==15,'Mac packet scope differs')
        sender=manifest['sender'];require(sender['source_sha']==SOURCE and str(sender['run_id'])==str(RUN) and str(sender['attempt'])=='1' and
          sender['platform']=='macos' and sender['parser_version']=='3.41.0' and sender['pid']>0,'Mac actual sender identity differs')
        require(hashlib.sha256(bundle.bytes('sender-bundle/proofs/program',128*1024**2)).hexdigest()==sender['program_sha256'] and
          hashlib.sha256(bundle.bytes('sender-bundle/proofs/sdk.dylib',128*1024**2)).hexdigest()==sender['sdk_dso_sha256'],'Mac program or actual SDK differs')
        packet=out/'sender';packet.mkdir();(packet/'manifest.json').write_bytes(raw)
        wires=[];originals={}
        for row in manifest['revisions']:
            data=bundle.bytes('sender-bundle/'+row['file'],2*1024**2)
            require(len(data)==row['bytes'] and hashlib.sha256(data).hexdigest()==row['sha256'],'Mac wire differs')
            (packet/(row['id']+'.json')).write_bytes(data);wires.append((row['id'],row['sha256'],data))
        for row in manifest['originals']:
            data=bundle.bytes('sender-bundle/'+row['file'],128*1024**2)
            require(len(data)==row['bytes'] and hashlib.sha256(data).hexdigest()==row['sha256'],'Mac original differs')
            originals[row['book_key']]=(row,data);(packet/(row['sha256']+'.'+row['format'])).write_bytes(data)
        database_name='profiles/source-version-and-NULL-operations/reader-catalog.db';database=out/'original-mac-operations.db'
        database.write_bytes(bundle.bytes(database_name,64*1024**2))
        for suffix in ('-wal','-shm'):
            if database_name+suffix in report['files']:Path(str(database)+suffix).write_bytes(bundle.bytes(database_name+suffix,64*1024**2))
    finally:bundle.close()
    with tempfile.TemporaryDirectory(prefix='gtk-raw3-peer-') as temporary:
        working=Path(temporary)/database.name;shutil.copyfile(database,working)
        for suffix in ('-wal','-shm'):
            if Path(str(database)+suffix).exists():shutil.copyfile(str(database)+suffix,str(working)+suffix)
        connection=sqlite3.connect(working.resolve().as_uri()+'?mode=ro',uri=True)
        try:operations=connection.execute('SELECT revision_id,CAST(body_json AS BLOB),body_sha256 FROM reader_revisions ORDER BY revision_id').fetchall()
        finally:connection.close()
    null_ids=[]
    for revision,data,expected in operations:
        require(hashlib.sha256(data).hexdigest()==expected,'Mac operations wire differs')
        value=json.loads(data);location=(value.get('payload') or {}).get('location')
        if location and location['anchor_version']==3 and location['selector']['exact']['base64'] is None:null_ids.append(revision)
    require(null_ids==['2a490dc51d514032a2815e802c8b3f48'],'Mac NULL fixture identity differs')
    proof=dict(source_sha=SOURCE,run_id=RUN,attempt=1,artifact={key:meta[key] for key in ('id','name','size_in_bytes','digest','expires_at')},
      manifest_sha256=hashlib.sha256(raw).hexdigest(),wire_count=len(wires),original_count=len(originals),reading_records=11,
      operations_database_sha256=hashlib.sha256(database.read_bytes()).hexdigest(),null_revision_ids=null_ids)
    (out/'proof.json').write_text(json.dumps(proof,indent=2)+'\n')
    counts={key:sum(row['capture']['route'][0]==key for row in manifest['reading_records']) for key in originals}
    (packet/'books.tsv').write_text(''.join(key+' '+str(counts[key])+'\n' for key in originals))
    return proof,manifest,wires,originals,operations


def fixture(private,script):
    # Reuse the fixed authored HTTPS service; source is retained for review.
    code=subprocess.check_output(['git','show','72c6bbdd:tests/apple_host/raw3/tls_fixture.py'],cwd=ROOT)
    script.write_bytes(code);sys.path.insert(0,str(ROOT/'tests/webdav'))
    spec=importlib.util.spec_from_file_location('gtk_raw3_fixed_tls',script);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module.Fixture(private)


def populate(server,wires,originals):
    server.directories.update(['/dav/revisions/','/dav/objects/'])
    for number in range(256):server.directories.add('/dav/revisions/%02x/'%number)
    for revision,sha,data in wires:server.entries['/dav/revisions/%s/%s-%s.json'%(revision[:2],revision,sha)]=data
    for row,data in originals.values():
        digest=row['sha256'];server.directories.add('/dav/objects/'+digest[:2]+'/')
        server.entries['/dav/objects/%s/%s.%s'%(digest[:2],digest,row['format'])]=data
