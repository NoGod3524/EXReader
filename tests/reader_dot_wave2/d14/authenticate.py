"""Same-attempt original ZIP authentication, independently recomputed file inventory."""
import datetime,hashlib,io,json,os,sys,traceback,zipfile
from pathlib import Path
sys.path.insert(0,str(Path('tools').resolve()))
from check_parallel_integration import fetch,pages,download_artifact_zip
from contract import TARGETS,digest,write,validate,selftest
assert os.environ.get('GITHUB_ACTIONS')=='true'
out=Path('authentication');out.mkdir(exist_ok=True)
report=dict(accepted=False,artifact_authentication=False,harness=os.environ['GITHUB_SHA'],run=os.environ['GITHUB_RUN_ID'],attempt=os.environ['GITHUB_RUN_ATTEMPT'],platforms={},failures=[])
try:
    selftest();run=fetch('actions/runs/'+report['run']);assert run['head_sha']==report['harness'] and str(run['run_attempt'])==report['attempt']
    jobs=pages('actions/runs/'+report['run']+'/attempts/'+report['attempt']+'/jobs','jobs');report['jobs']=jobs
    artifacts=pages('actions/runs/'+report['run']+'/artifacts','artifacts')
    for platform in TARGETS:
        record=dict(authenticated=False,accepted=False);report['platforms'][platform]=record
        try:
            matches=[a for a in artifacts if a['name']==f'd14-{platform}-{report["run"]}-{report["attempt"]}'];assert len(matches)==1
            a=matches[0];assert not a['expired'] and datetime.datetime.fromisoformat(a['expires_at'].replace('Z','+00:00'))>datetime.datetime.now(datetime.timezone.utc)
            assert a['workflow_run']['id']==int(report['run']) and a['workflow_run']['head_sha']==report['harness']
            raw=download_artifact_zip(a['id']);sha=hashlib.sha256(raw).hexdigest();assert len(raw)==a['size_in_bytes'] and a['digest']=='sha256:'+sha
            record.update(artifact_id=a['id'],bytes=len(raw),sha256=sha,expires_at=a['expires_at'],name=a['name'])
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                names=z.namelist();assert len(names)==len(set(names)) and all(not n.startswith('/') and '..' not in Path(n).parts for n in names)
                assert 'bundle.json' in names
                bundle=json.loads(z.read('bundle.json'));assert set(bundle)==set(n for n in names if not n.endswith('/') and n!='bundle.json')
                for name,value in bundle.items():
                    b=z.read(name);assert len(b)==value['bytes'] and hashlib.sha256(b).hexdigest()==value['sha256'],name
                identity=json.loads(z.read('build-identity.json'));v=json.loads(z.read('report.json'))
                assert all(identity[k]==report[k] for k in ('harness','run','attempt')) and identity['platform']==platform and identity['target']==TARGETS[platform]
                assert hashlib.sha256(z.read(identity['program'])).hexdigest()==identity['program_sha256']
                assert hashlib.sha256(z.read('Reader.otf')).hexdigest()==identity['font_sha256']
                record.update(authenticated=True,identity=identity,completed_cycles=v['completed_cycles'],stages=v['stages'],failed_actions=[r for r in v['actions'] if r['status']!='completed'],failures=v['failures'],resources=len(v['resources']))
                write(out/(platform+'-report.json'),v)
                validate(v,identity)
                own=[j for j in jobs if j['name']==f'lifecycle ({platform})'];assert len(own)==1 and own[0]['conclusion']=='success'
                record['accepted']=True
        except BaseException:record['error']=traceback.format_exc();report['failures'].append(platform+': '+record['error'])
    report['artifact_authentication']=all(v.get('authenticated') for v in report['platforms'].values())
    report['accepted']=all(v['accepted'] for v in report['platforms'].values())
except BaseException:report['failures'].append(traceback.format_exc())
finally:write(out/'authentication.json',report);print('D14_AUTH '+json.dumps(report),flush=True)
assert report['accepted'],'incomplete lifecycle evidence; original failures retained'
