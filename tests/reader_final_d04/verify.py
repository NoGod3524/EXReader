"""Authenticate original ZIP bytes, same-run identity and exact upstream jobs in Actions."""
import copy,datetime,hashlib,io,json,os,subprocess,sys,zipfile
from pathlib import Path
assert os.environ.get('GITHUB_ACTIONS')=='true'
repo=os.environ['GITHUB_REPOSITORY'];run=os.environ['GITHUB_RUN_ID'];attempt=os.environ['GITHUB_RUN_ATTEMPT'];source=os.environ['GITHUB_SHA']
out=Path('build/verification');out.mkdir(parents=True,exist_ok=True)
def api(path):return json.loads(subprocess.check_output(['gh','api',f'repos/{repo}/'+path]))
arts=api(f'actions/runs/{run}/artifacts?per_page=100')['artifacts']
jobs=api(f'actions/runs/{run}/attempts/{attempt}/jobs?per_page=100')['jobs']
def validate(a,body,p):
    assert a['name']==f'd04-{p}-{run}-{attempt}'
    assert a['expired'] is False
    assert datetime.datetime.fromisoformat(a['expires_at'].replace('Z','+00:00'))>datetime.datetime.now(datetime.timezone.utc)
    assert a['workflow_run']['id']==int(run) and a['workflow_run']['head_sha']==source
    assert len(body)==a['size_in_bytes']
    assert a['digest']=='sha256:'+hashlib.sha256(body).hexdigest()
results=[];negatives=[]
for p in ('macos','iphone','ipad'):
    match=[a for a in arts if a['name']==f'd04-{p}-{run}-{attempt}'];assert len(match)==1,(p,'unique artifact required')
    a=match[0];body=subprocess.check_output(['gh','api',f'repos/{repo}/actions/artifacts/{a["id"]}/zip'])
    validate(a,body,p)
    for key,val in [('expired',True),('size_in_bytes',len(body)+1),('digest','sha256:'+'0'*64),('name','wrong'),('expires_at','2000-01-01T00:00:00Z')]:
        bad=copy.deepcopy(a);bad[key]=val
        try:validate(bad,body,p)
        except AssertionError:negatives.append(p+'/'+key)
        else:raise AssertionError('negative accepted: '+key)
    with zipfile.ZipFile(io.BytesIO(body)) as z:
        assert len(z.namelist())==len(set(z.namelist()))
        assert all(not n.startswith('/') and '..' not in n.split('/') for n in z.namelist())
        r=json.loads(z.read('report.json'));files=json.loads(z.read('files.json'))
        for f in files:
            b=z.read(f['path']);assert len(b)==f['bytes'] and hashlib.sha256(b).hexdigest()==f['sha256']
        assert r['harness_sha']==source and r['run_id']==run and r['attempt']==attempt and r['platform']==p
        assert r['target_sha']==os.environ['TARGET_SHA'] and r['sdk_sha']==os.environ['SDK_SHA']
        candidates=[j for j in jobs if j['name']==f'D04 audit {p}'];assert len(candidates)==1
        j=candidates[0];assert j['status']=='completed' and j['head_sha']==source
        results.append({'platform':p,'job':{'id':j['id'],'name':j['name'],'conclusion':j['conclusion']},'artifact':{k:a[k] for k in ('id','name','size_in_bytes','digest','expires_at')},'zip_sha256':hashlib.sha256(body).hexdigest(),'program':r['program'],'checks':r['checks'],'audit_completed':r['audit_completed'],'problems':r['problems'],'findings':[f for f in r['geometry_and_name_findings'] if f.get('verdict')=='fail'],'default_ui_accepted':False,'ax_semantics_accepted':False,'dynamic_type_accepted':False,'voiceover_accepted':False,'physical_device_execution':False})
report={'harness_sha':source,'target_sha':os.environ['TARGET_SHA'],'sdk_sha':os.environ['SDK_SHA'],'run_id':run,'attempt':attempt,'artifact_authentication':True,'negative_rejections':negatives,'targets':results,'accepted':False,'complete_product':False}
(out/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print('D04_VERIFIED '+json.dumps(report,ensure_ascii=False))
assert all(r['audit_completed'] and r['job']['conclusion']=='success' for r in results),'real target audit incomplete; acceptance remains false'
