"""Authenticate original ZIP bytes, same-run identity and exact upstream jobs in Actions."""
import copy,datetime,hashlib,io,json,os,plistlib,re,subprocess,sys,zipfile,urllib.request,urllib.parse
from pathlib import Path
assert os.environ.get('GITHUB_ACTIONS')=='true'
repo=os.environ['GITHUB_REPOSITORY'];run=os.environ['GITHUB_RUN_ID'];attempt=os.environ['GITHUB_RUN_ATTEMPT'];source=os.environ['GITHUB_SHA']
review_prior='--review-d10-final' in sys.argv
if review_prior:
    run='40229896420';attempt='1';source='d2e1b55c9cd4ded4201cbb4d1351bc490ef644df'
out=Path('build/prior-verification' if review_prior else 'build/verification');out.mkdir(parents=True,exist_ok=True)
HISTORICAL_TARGETS={'macos':'15dab6b2270dc296ed6239db67ced2e22d255e65','iphone':'5ac5e1fa4cf6dcbfe81ea14b9f64b6288470164a','ipad':'5ac5e1fa4cf6dcbfe81ea14b9f64b6288470164a'}
TARGETS=HISTORICAL_TARGETS if review_prior else {p:source for p in ('macos','iphone','ipad')}
PREFIX='d10' if review_prior else 'd16'
JOB_PREFIX='D10' if review_prior else 'D16'
WORKFLOW='.github/workflows/reader-dot-d10.yml' if review_prior else '.github/workflows/reader-wave3-d16.yml'
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
run_meta=api(f'actions/runs/{run}')
assert str(run_meta['id'])==run and run_meta['head_sha']==source and str(run_meta['run_attempt'])==attempt
assert run_meta['path'].split('@')[0]==WORKFLOW
arts=api(f'actions/runs/{run}/artifacts?per_page=100')['artifacts']
jobs=api(f'actions/runs/{run}/attempts/{attempt}/jobs?per_page=100')['jobs']
def validate(a,body,p):
    assert a['name']==f'{PREFIX}-{p}-{run}-{attempt}'
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
def complete_named_audit(report,platform):
    labels=['normal-light','normal-dark']+([] if platform=='macos' else ['large-light','large-dark'])
    expected={'import':{'test01ProductionBodyNamesAndActualEdgeTap()'},
        'original-compact' if platform=='macos' else 'original-large':{'test02CompactReaderActualTurnFontAndNotes()'}}
    expected.update({label:{'test01DefaultShelfAndAccountDismissal()','test02DefaultReaderLowFrequencyJourney()'} for label in labels})
    rows=report['checks']
    if len(rows)!=len(expected) or {row['label'] for row in rows}!=set(expected):return False
    for row in rows:
        if row['exit']!=0 or len(row['cases'])!=len(expected[row['label']]):return False
        if {case['name'] for case in row['cases']}!=expected[row['label']]:return False
        if not all(case['result']=='Passed' for case in row['cases']):return False
        if not review_prior and not any(n.get('executable_sha256')==report['program']['executable_sha256'] and n.get('source')==source and n.get('run_id')==run and n.get('attempt')==attempt and n.get('pid',0)>0 for n in row.get('native_processes',[])):return False
    for label in labels:
        states=report['records'].get(label,{}).get('states',{})
        for step in ('shelf','account-settings','reader','reader-font-settings','more-menu','records','returned-shelf'):
            if not any(key.endswith('.'+step) for key in states):return False
    return not report['problems']
for p in ('macos','iphone','ipad'):
    match=[a for a in arts if a['name']==f'{PREFIX}-{p}-{run}-{attempt}'];assert len(match)==1,(p,'unique artifact required')
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
        program_verified=False
        if {'EXReaderHost-executable','EXReaderHost-Info.plist'} <= set(z.namelist()):
            assert hashlib.sha256(z.read('EXReaderHost-executable')).hexdigest()==r['program']['executable_sha256']
            plist_bytes=z.read('EXReaderHost-Info.plist')
            assert hashlib.sha256(plist_bytes).hexdigest()==r['program']['info_sha256']
            plist=plistlib.loads(plist_bytes)
            assert plist['EXRSourceSHA']==r['target_sha'] and plist['EXRSDKVersion']=='3.41.0' and plist['EXRPageThemeEnabled'] is False
            program_verified=True
        else:
            r['problems'].append('strict actual program authentication failed: executable/plist missing')
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
        if program_verified:
            try:
                assert hashlib.sha256(z.read('EXReaderHost-executable')+b'wrong').hexdigest()==r['program']['executable_sha256']
            except AssertionError:negatives.append(p+'/actual-wrong-program')
            else:raise AssertionError('accepted wrong program')
        named_complete=complete_named_audit(r,p)
        if named_complete:
            bad=copy.deepcopy(r);bad['checks'][0]['cases']=[]
            assert complete_named_audit(bad,p) is False
            negatives.append(p+'/missing-named-XCTest')
        candidates=[j for j in jobs if j['name']==f'{JOB_PREFIX} audit {p}'];assert len(candidates)==1
        j=candidates[0];assert j['status']=='completed' and j['head_sha']==source
        results.append({'platform':p,'job':{'id':j['id'],'name':j['name'],'conclusion':j['conclusion']},'artifact':{k:a[k] for k in ('id','name','size_in_bytes','digest','expires_at')},'zip_sha256':hashlib.sha256(body).hexdigest(),'program':r['program'],'program_authentication':program_verified,'checks':r['checks'],'audit_completed':named_complete and program_verified,'producer_audit_completed':r['audit_completed'],'problems':r['problems'],'findings':[f for f in r['geometry_and_name_findings'] if f.get('verdict')=='fail'],'default_ui_accepted':False,'ax_semantics_accepted':False,'dynamic_type_accepted':False,'voiceover_accepted':False,'physical_device_execution':False})
report={'verifier_harness_sha':os.environ['GITHUB_SHA'],'review_prior':review_prior,'harness_sha':source,'target_shas':TARGETS,'sdk_sha':os.environ['SDK_SHA'],'run_id':run,'attempt':attempt,'artifact_authentication':True,'negative_rejections':negatives,'targets':results,'accepted':False,'complete_product':False}
(out/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
from contract import targets
targets([row['platform'] for row in results])
try:targets([row['platform'] for row in results if row['platform']!='ipad'])
except AssertionError:negatives.append('actual-missing-ipad')
else:raise AssertionError('accepted missing actual mobile target')
(out/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print('D16_SUMMARY '+json.dumps({k:v for k,v in report.items() if k!='targets'} | {'targets':[{k:v for k,v in row.items() if k!='findings'} for row in results]},ensure_ascii=False))
print('D16_VERIFIED '+json.dumps(report,ensure_ascii=False))
if review_prior:
    assert all(row['program_authentication'] for row in results)
    assert next(row for row in results if row['platform']=='iphone')['audit_completed'] is False
    assert all(row['audit_completed'] for row in results if row['platform']!='iphone')
    print('D16_PRIOR_AUTHENTICATED_FAILURE '+json.dumps(report,ensure_ascii=False))
else:
    assert all(r['audit_completed'] and r['program_authentication'] and r['job']['conclusion']=='success' for r in results),'real target audit incomplete; acceptance remains false'
