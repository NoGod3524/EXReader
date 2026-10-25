"""Authenticate original ZIP bytes, same-run identity and exact upstream jobs in Actions."""
import copy,datetime,hashlib,io,json,os,plistlib,re,subprocess,sys,zipfile,urllib.request,urllib.parse
from pathlib import Path
assert os.environ.get('GITHUB_ACTIONS')=='true'
repo=os.environ['GITHUB_REPOSITORY'];run=os.environ['GITHUB_RUN_ID'];attempt=os.environ['GITHUB_RUN_ATTEMPT'];source=os.environ['GITHUB_SHA']
out=Path('build/verification');out.mkdir(parents=True,exist_ok=True)
TARGETS={'macos':'15dab6b2270dc296ed6239db67ced2e22d255e65','iphone':'5ac5e1fa4cf6dcbfe81ea14b9f64b6288470164a','ipad':'5ac5e1fa4cf6dcbfe81ea14b9f64b6288470164a'}
class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        redirected=super().redirect_request(req,fp,code,msg,headers,newurl)
        assert urllib.parse.urlsplit(newurl).scheme=='https'
        if urllib.parse.urlsplit(req.full_url).netloc!=urllib.parse.urlsplit(newurl).netloc:
            redirected.remove_header('Authorization')
        return redirected
def download(artifact_id):
    request=urllib.request.Request(f'https://api.github.com/repos/{repo}/actions/artifacts/{artifact_id}/zip',headers={'Authorization':'Bearer '+os.environ['GH_TOKEN'],'Accept':'application/vnd.github+json'})
    try:
        with urllib.request.build_opener(SafeRedirect()).open(request,timeout=180) as response: return response.read()
    except Exception as error:
        raise RuntimeError('artifact transport failed: '+type(error).__name__) from None
def api(path):return json.loads(subprocess.check_output(['gh','api',f'repos/{repo}/'+path]))
arts=api(f'actions/runs/{run}/artifacts?per_page=100')['artifacts']
jobs=api(f'actions/runs/{run}/attempts/{attempt}/jobs?per_page=100')['jobs']
def validate(a,body,p):
    assert a['name']==f'd10-{p}-{run}-{attempt}'
    assert a['expired'] is False
    assert datetime.datetime.fromisoformat(a['expires_at'].replace('Z','+00:00'))>datetime.datetime.now(datetime.timezone.utc)
    assert a['workflow_run']['id']==int(run) and a['workflow_run']['head_sha']==source
    assert len(body)==a['size_in_bytes']
    assert a['digest']=='sha256:'+hashlib.sha256(body).hexdigest()
from contract import negative_checks, measured_state
results=[];negatives=negative_checks()
def default_configuration(report,project,logs):
    conditions='\n'.join(line for line in project.splitlines() if 'SWIFT_ACTIVE_COMPILATION_CONDITIONS' in line)
    assert conditions.strip(), 'missing actual build configuration'
    actual=sorted(set(re.findall(r'EXR_[A-Z_]+',conditions)))
    compile_flags=sorted(set(re.findall(r'-D\s*(EXR_[A-Z_]+)',logs)))
    assert report['review_macros']==actual==[], 'actual project/report review macro mismatch'
    assert compile_flags==[], 'actual compiler review macro leakage'
for p in ('macos','iphone','ipad'):
    match=[a for a in arts if a['name']==f'd10-{p}-{run}-{attempt}'];assert len(match)==1,(p,'unique artifact required')
    a=match[0];body=download(a['id'])
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
            if f['path'].endswith(('.log','.json','.txt','.pbxproj')):
                assert not re.search(rb'(gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{60,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)',b), 'credential pattern in retained text evidence'
        assert r['harness_sha']==source and r['run_id']==run and r['attempt']==attempt and r['platform']==p
        assert r['target_sha']==TARGETS[p] and r['sdk_sha']==os.environ['SDK_SHA']
        project=z.read('project.pbxproj').decode()
        logs='\n'.join(z.read(n).decode(errors='replace') for n in z.namelist() if n.endswith('.log'))
        default_configuration(r,project,logs)
        assert hashlib.sha256(z.read('EXReaderHost-executable')).hexdigest()==r['program']['executable_sha256']
        plist_bytes=z.read('EXReaderHost-Info.plist')
        assert hashlib.sha256(plist_bytes).hexdigest()==r['program']['info_sha256']
        plist=plistlib.loads(plist_bytes)
        assert plist['EXRSourceSHA']==r['target_sha'] and plist['EXRSDKVersion']=='3.41.0' and plist['EXRPageThemeEnabled'] is False
        for kind,badproject,badlogs in [('missing-configuration','',logs),('project-review-leak',project+'\nSWIFT_ACTIVE_COMPILATION_CONDITIONS = EXR_APPLE_HOST_REVIEW;',logs),('compiler-review-leak',project,logs+'\nswiftc -DEXR_APPLE_HOST_REVIEW')]:
            try:default_configuration(r,badproject,badlogs)
            except AssertionError:negatives.append(p+'/'+kind)
            else:raise AssertionError('review leakage accepted')
        for group in r['records'].values():
            for state in group.get('states',{}).values():
                measured_state(state)
        actual_states=[state for group in r['records'].values() for state in group.get('states',{}).values()]
        if actual_states:
            baseline=actual_states[0]
            for kind in ('stale-node','coordinate-only'):
                bad=copy.deepcopy(baseline)
                if kind=='stale-node':bad['elements'][0]['snapshot_id']='stale'
                else:bad['elements']=[]
                try:measured_state(bad)
                except AssertionError:negatives.append(p+'/actual-'+kind)
                else:raise AssertionError('accepted corrupted real observation')
            visible=next((st for st in actual_states if any(n.get('hit_test_observation')=='live-current-window' for n in st['elements'])),None)
            if visible:
                bad=copy.deepcopy(visible)
                next(n for n in bad['elements'] if n.get('hit_test_observation')=='live-current-window')['current_window']=False
                try:measured_state(bad)
                except AssertionError:negatives.append(p+'/actual-foreign-window')
                else:raise AssertionError('accepted foreign-window observation')
        try:
            assert hashlib.sha256(z.read('EXReaderHost-executable')+b'wrong').hexdigest()==r['program']['executable_sha256']
        except AssertionError:negatives.append(p+'/actual-wrong-program')
        else:raise AssertionError('accepted wrong program')
        candidates=[j for j in jobs if j['name']==f'D10 audit {p}'];assert len(candidates)==1
        j=candidates[0];assert j['status']=='completed' and j['head_sha']==source
        results.append({'platform':p,'job':{'id':j['id'],'name':j['name'],'conclusion':j['conclusion']},'artifact':{k:a[k] for k in ('id','name','size_in_bytes','digest','expires_at')},'zip_sha256':hashlib.sha256(body).hexdigest(),'program':r['program'],'checks':r['checks'],'audit_completed':r['audit_completed'],'problems':r['problems'],'findings':[f for f in r['geometry_and_name_findings'] if f.get('verdict')=='fail'],'default_ui_accepted':False,'ax_semantics_accepted':False,'dynamic_type_accepted':False,'voiceover_accepted':False,'physical_device_execution':False})
report={'harness_sha':source,'target_shas':TARGETS,'sdk_sha':os.environ['SDK_SHA'],'run_id':run,'attempt':attempt,'artifact_authentication':True,'negative_rejections':negatives,'targets':results,'accepted':False,'complete_product':False}
(out/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print('D10_VERIFIED '+json.dumps(report,ensure_ascii=False))
assert all(r['audit_completed'] and r['job']['conclusion']=='success' for r in results),'real target audit incomplete; acceptance remains false'
