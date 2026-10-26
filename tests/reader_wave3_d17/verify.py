"""Strict same-run/attempt original ZIP and every actual storage transition."""
import datetime,hashlib,io,json,os,pathlib,re,subprocess,sys,tarfile,traceback,types,urllib.request,urllib.parse,zipfile
assert os.environ.get('GITHUB_ACTIONS')=='true'
# Reuse the unchanged D11 transport/authentication helper and exact action catalog.
prior='da3ba2d1544edff6dc5004dd9d9d88aa732f9b12'
def reuse(name):
    raw=subprocess.check_output(['git','show',prior+':tests/reader_dot_wave2/d11/'+name+'.py'])
    m=types.ModuleType('d11_'+name);exec(compile(raw,name+'.py','exec'),m.__dict__);return m
request=reuse('producer').request;ACTIONS=reuse('common').ACTIONS
run=os.environ['GITHUB_RUN_ID'];attempt=os.environ['GITHUB_RUN_ATTEMPT'];source=os.environ['GITHUB_SHA'];out=pathlib.Path('build/d17-verify');out.mkdir(parents=True,exist_ok=True)
report=dict(source_sha=source,run_id=run,attempt=attempt,artifacts=[],actions={k:dict(result='pending',reason='not reached') for k in ACTIONS},transitions=[],errors=[],accepted=False,complete_product=False,keyboard_focus_accepted=False,physical_device_accepted=False)
def verify_bytes(raw,value):assert len(raw)==value['bytes'] and hashlib.sha256(raw).hexdigest()==value['sha256']
def check(before,after,action):
    bs=before['sdk']['books'];a=after['sdk']['books'];bp=before['product'];ap=after['product']
    assert before['sdk']['sdk_version']==after['sdk']['sdk_version']=='3.41.0'
    # Import attaches local source identity; it must not manufacture history/outbox.
    if action in ('import','setup.import'):
        assert len(bs)==0 and len(a)==1 and a[0]['note_count']==0
        for key in bp:
            if key in ('reader_books','reader_local_books'):assert not bp[key]['rows'] and len(ap[key]['rows'])==1
            else:assert bp[key]==ap[key],key
        mapped=dict(zip(ap['reader_books']['columns'],ap['reader_books']['rows'][0]));assert mapped['source_sha256']==a[0]['original_sha256'] and mapped['source_bytes']==a[0]['original_bytes']
        local=dict(zip(ap['reader_local_books']['columns'],ap['reader_local_books']['rows'][0]));assert local['sdk_book_id']==a[0]['id'] and local['location_kind']=='epub_chapter'
    elif action in ('next','previous','continue_after_return','setup.open'):
        assert len(bs)==len(a)==1 and bp==ap,'navigation changed product catalog/history/outbox'
        for key in bs[0]:
            if key not in ('progress','position'):assert bs[0][key]==a[0][key],key
        assert bs[0]['progress']!=a[0]['progress'],'expected actual durable progress change'
    else:assert before==after,'unexpected SDK original/progress/notes or product rows/history/outbox mutation'
try:
    state=json.loads(request('/actions/runs/'+run));assert state['head_sha']==source and str(state['run_attempt'])==attempt
    jobs=json.loads(request('/actions/runs/'+run+'/attempts/'+attempt+'/jobs?per_page=100'))['jobs'];report['jobs']=[{k:j[k] for k in ('id','name','status','conclusion')} for j in jobs]
    artifacts=json.loads(request('/actions/runs/'+run+'/artifacts?per_page=100'))['artifacts'];matches=[a for a in artifacts if a['name']=='d17-native-'+run+'-'+attempt];assert len(matches)==1
    meta=matches[0];assert not meta['expired'] and meta['workflow_run']['head_sha']==source and str(meta['workflow_run']['id'])==run
    assert datetime.datetime.fromisoformat(meta['expires_at'].replace('Z','+00:00'))>datetime.datetime.now(datetime.timezone.utc)
    raw=request('/actions/artifacts/'+str(meta['id'])+'/zip');assert len(raw)==meta['size_in_bytes'] and meta['digest']=='sha256:'+hashlib.sha256(raw).hexdigest()
    report['artifacts'].append({k:meta[k] for k in ('id','name','size_in_bytes','digest','expires_at')})
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        names=z.namelist();assert len(names)==len(set(names)) and all('..' not in pathlib.PurePosixPath(n).parts and not pathlib.PurePosixPath(n).is_absolute() for n in names)
        e=json.loads(z.read('execution.json'));report['execution']=e
        assert e['source_sha']==source and e['run_id']==run and e['attempt']==attempt
        for name,identity in e['files'].items():verify_bytes(z.read(name),identity)
        with tarfile.open(fileobj=io.BytesIO(z.read('actual-app.tar.gz')),mode='r:gz') as t:
            executable=t.getmember('EXReaderHost.app/Contents/MacOS/EXReaderHost');verify_bytes(t.extractfile(executable).read(),e['program']);assert executable.mode==e['program']['mode'] and not e['program']['is_symlink']
        report['program_verified']=True
        rows=[json.loads(line) for line in re.findall(r'\bD17_ACTION (\{[^\r\n]+\})',z.read('native-actions.log').decode(errors='replace'))]
        seen=set()
        for row in rows:
            key=(row['case'],row['action']);assert key not in seen;seen.add(key)
            b=json.loads(z.read('snapshots/'+row['before']));a=json.loads(z.read('snapshots/'+row['after']))
            for snap in (a,b):assert snap['source_sha']==source and snap['run_id']==run and snap['attempt']==attempt and snap['observed_twice_equal'] and snap['observer_sha256']==e['files']['sdk-observer']['sha256']
            try:check(b['state'],a['state'],row['action']);row['storage_result']='passed'
            except Exception as error:row['storage_result']='failed';row['storage_error']=str(error);report['errors'].append(row['action']+': '+str(error))
            row.update(before_state=b['state'],after_state=a['state']);report['transitions'].append(row)
            if row['action'] in ACTIONS:report['actions'][row['action']]={k:row[k] for k in ('result','storage_result','native_id','before','after')}
        native_actions=[r['action'] for r in rows if r['action'] in ACTIONS];assert len(native_actions)==len(set(native_actions))
        if all(r['storage_result']=='passed' for r in report['transitions']) and len(native_actions)==16:
            report['actions']['no_unexpected_revision']=dict(result='passed',storage_result='passed',input='all actual independent before/after SDK and catalog snapshots')
        report['rejection_passed']=any(r['action']=='reject_existing_broken' and r['storage_result']=='passed' for r in report['transitions'])
        report['accepted']=e['accepted'] and report['rejection_passed'] and not report['errors'] and all(r['result']=='passed' and r.get('storage_result')=='passed' for r in report['actions'].values())
        # Nontrivial negative: mutate the real after snapshot; the no-write check must refuse.
        negative=next((r for r in report['transitions'] if r['action']=='cancel'),None)
        if negative:
            altered=json.loads(json.dumps(negative['after_state']));altered['product']['reader_outbox']['rows'].append(['fabricated'])
            try:check(negative['before_state'],altered,'cancel')
            except AssertionError:report['mutation_negative_rejected']=True
            else:raise AssertionError('false no-write grant')
except Exception as error:report['errors'].append(type(error).__name__+': '+str(error));traceback.print_exc()
finally:
    (out/'verification.json').write_text(json.dumps(report,indent=2));print('D17_VERIFICATION '+json.dumps(report),flush=True)
assert report['accepted'],report['errors'] or '17 operations, native rejection, or independent no-write scope missing'
