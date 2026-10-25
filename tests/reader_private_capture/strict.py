"""Actions-only same-run original ZIP, complete unit cases and cross-OS golden bytes."""
from datetime import datetime,timezone
import hashlib,io,json,os,subprocess,zipfile
from pathlib import Path,PurePosixPath
assert os.environ.get('GITHUB_ACTIONS')=='true'
identity={k:os.environ[v] for k,v in [('source_sha','GITHUB_SHA'),('run_id','GITHUB_RUN_ID'),('attempt','GITHUB_RUN_ATTEMPT')]}
repo='repos/'+os.environ['GITHUB_REPOSITORY']+'/'
def api(path):return json.loads(subprocess.check_output(['gh','api',repo+path]))
jobs=api('actions/runs/'+identity['run_id']+'/attempts/'+identity['attempt']+'/jobs?per_page=100')['jobs']
for platform in ('linux','windows'):
    job,=[j for j in jobs if j['name']=='private-capture-'+platform]
    assert job['conclusion']=='success' and job['head_sha']==identity['source_sha'] and job['status']=='completed'
artifacts=api('actions/runs/'+identity['run_id']+'/artifacts?per_page=100')['artifacts'];proofs=[];golden=None
for platform in ('linux','windows'):
    artifact,=[a for a in artifacts if a['name']=='private-capture-'+platform+'-'+identity['run_id']+'-'+identity['attempt']]
    assert not artifact['expired'] and artifact['workflow_run']['head_sha']==identity['source_sha'] and artifact['workflow_run']['id']==int(identity['run_id'])
    assert datetime.fromisoformat(artifact['expires_at'].replace('Z','+00:00'))>datetime.now(timezone.utc)
    body=subprocess.check_output(['gh','api',repo+'actions/artifacts/'+str(artifact['id'])+'/zip']);assert len(body)==artifact['size_in_bytes'] and 'sha256:'+hashlib.sha256(body).hexdigest()==artifact['digest']
    with zipfile.ZipFile(io.BytesIO(body)) as z:
        names=z.namelist();assert len(names)==len(set(names))
        for name in names:assert not PurePosixPath(name).is_absolute() and '..' not in PurePosixPath(name).parts and '\\' not in name
        result=json.loads(z.read('report.json'));assert result['accepted'] and all(result[k]==v for k,v in identity.items()) and not any(result[k] for k in ('sdk_accepted','host_accepted','public_wire_accepted'))
        assert len(result['consumers'])==(6 if platform=='linux' else 2)
        for name,declared in result['files'].items():
            content=z.read(name);assert len(content)==declared['bytes'] and hashlib.sha256(content).hexdigest()==declared['sha256']
        for consumer in result['consumers']:
            assert len(consumer['cases'])==len(set(consumer['cases']))==10
            vectors={key:z.read(consumer['name']+'/'+key+'.bin') for key in consumer['vectors']}
            assert len(vectors)==7
            if golden is None:golden=vectors
            assert vectors==golden
    proofs.append({k:artifact[k] for k in ('id','name','digest','size_in_bytes','expires_at')})
summary={**identity,'accepted':True,'scope':'private header codec C11/C++ unit tests Windows/Linux only','artifacts':proofs,'consumers':8,'cases_per_consumer':10,'identical_golden_vectors':7,'sdk_accepted':False,'host_accepted':False,'public_wire_accepted':False}
out=Path('build/private-capture-summary');out.mkdir(parents=True,exist_ok=True);(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary),flush=True)
