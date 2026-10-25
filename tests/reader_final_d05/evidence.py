"""Actions-only evidence identity, manifest and fail-closed audit aggregation."""
import datetime, hashlib, json, os, pathlib, re, sys, urllib.request, urllib.parse, zipfile
BASE='0889f7d1e9a537c6c1b05456547e016b26e1cd85'
SDK='edddc463c06ed5731195cdb8f06b2df6dff7699e'
LEGACY='shelf_semantics hidden_panels status_announcement import_picker shelf_row_and_search organize_panel back_navigation reader_line_nodes reader_page_turn reader_toolbar_state annotate_flow notes_panel rotation large_font display_scaling'.split()
DELTA=['default_shelf','import_cancel','import_sample','touch_page','annotation_ui']+[f'{kind}_{scale}' for scale in ('1.0','1.3','2.0') for kind in ('font','rotation','rebuild')]+['annotation_after_rebuild','dpad_back']+['default_entry_'+x for x in ('书内搜索','目录 / 按页入口','阅读记录','阅读设置')]+['default_account']
class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        redirected=super().redirect_request(req,fp,code,msg,headers,newurl)
        if urllib.parse.urlparse(req.full_url).netloc != urllib.parse.urlparse(newurl).netloc:
            redirected.remove_header('Authorization')
        return redirected
OPENER=urllib.request.build_opener(SafeRedirect())
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p): return json.loads(p.read_text())
def write(p,v): p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def manifest_check(root,manifest):
    assert set(manifest)=={str(p.relative_to(root)) for p in root.rglob('*') if p.is_file() and p.name!='manifest.json'}
    for n,v in manifest.items(): assert (root/n).stat().st_size==v['bytes'] and digest(root/n)==v['sha256'],n
def check(root):
    identity=load(root/'identity.json')
    assert identity['harness_sha']==os.environ['GITHUB_SHA']
    assert identity['run_id']==os.environ['GITHUB_RUN_ID'] and identity['attempt']==os.environ['GITHUB_RUN_ATTEMPT']
    assert identity['target_sha']==BASE and identity['sdk_source']==SDK
    assert identity['apk_sha256']==digest(root/'installed-host.apk')
    with zipfile.ZipFile(root/'installed-host.apk') as z:
        assert identity['sdk_so_sha256']==hashlib.sha256(z.read('lib/x86_64/libexreader.so')).hexdigest()
    assert '[ro.build.version.sdk]: [34]' in (root/'getprop.txt').read_text()
    assert '[ro.product.cpu.abi]: [x86_64]' in (root/'getprop.txt').read_text()
    legacy=load(root/'legacy/validation.json')
    assert legacy['source_sha']==identity['harness_sha'] and str(legacy['run_id'])==identity['run_id'] and str(legacy['attempt'])==identity['attempt']
    groups={'legacy':legacy['cases'],'delta':load(root/'delta/cases.json')}
    for group,expected in [('legacy',LEGACY),('delta',DELTA)]:
        assert [c['id'] for c in groups[group]]==expected,group+' missing/duplicate cases'
        assert 'OK (1 test)' in (root/f'{group}-instrumentation.txt').read_text(),group+' instrumentation incomplete'
        assert (root/f'{group}-exit.txt').read_text().strip()=='0'
        for c in groups[group]:
            assert c['verdict'] in ('pass','fail')
            if group=='delta':
                assert c.get('last_capture'),c
                capture=root/'delta'/c['last_capture']
                for suffix in ('.xml','.json','.png'): assert pathlib.Path(str(capture)+suffix).is_file(),str(capture)+suffix
    # Every emitted snapshot is paired with actual XML and PNG, including failed stages.
    for folder in [root/'legacy/trees',root/'delta']:
        for p in folder.glob('*.xml'):
            png=(root/'legacy/shots'/p.name).with_suffix('.png') if folder.name=='trees' else p.with_suffix('.png')
            assert png.read_bytes().startswith(b'\x89PNG\r\n\x1a\n') and png.stat().st_size>1000
            assert p.with_suffix('.json').is_file()
    assert load(root/'delta/events.json')
    failures=[dict(group=g,**c) for g,cs in groups.items() for c in cs if c['verdict']!='pass']
    passed={c['id'] for c in groups['delta'] if c['verdict']=='pass'}
    result=dict(identity,audit_completed=True,default_ui_accepted=not failures,semantics_accepted=not failures,
        font_scale_accepted=False,font_scale_tree_checks_passed=all('font_'+s in passed for s in ('1.0','1.3','2.0')),
        # Page label alone is not stable raw reading-offset/record identity.
        rotation_accepted=False,rotation_visual_checks_passed=all('rotation_'+s in passed for s in ('1.0','1.3','2.0')),
        talkback_execution='pending',talkback_accepted=False,physical_device_execution=False,complete_product=False,
        checks={g:{'pass':sum(c['verdict']=='pass' for c in cs),'fail':sum(c['verdict']=='fail' for c in cs)} for g,cs in groups.items()},findings=failures,
        unverified=['TalkBack speech and gestures','physical device and keyboard','other API/locales','glyph clipping/contrast visual review','stable raw reading offset and records across rotation','default-macro gated feature flows','release APK'])
    snapshots=[load(p) for p in (root/'delta').glob('*.json') if p.name not in ('cases.json','events.json')]
    result['font_scales_actual']=sorted({s['font_scale'] for s in snapshots})
    result['dimensions_actual']=sorted({f"{s['width']}x{s['height']}" for s in snapshots})
    result['density_actual']=sorted({s['density'].strip() for s in snapshots})
    result['image_source_properties']=(root/'image-source.properties').read_text()
    result['device_fingerprint']=[line for line in (root/'getprop.txt').read_text().splitlines() if '[ro.build.fingerprint]' in line]
    return result

def seal(root):
    b=load(pathlib.Path('build/android-host/build.json'))
    assert b['sdk_version']=='3.41.0' and b['core_version']=='3.40.0' and b['abi_version']==1
    apk=root/'installed-host.apk'
    with zipfile.ZipFile(apk) as z: native=hashlib.sha256(z.read('lib/x86_64/libexreader.so')).hexdigest()
    identity=dict(harness_sha=os.environ['GITHUB_SHA'],target_sha=BASE,sdk_source=SDK,run_id=os.environ['GITHUB_RUN_ID'],attempt=os.environ['GITHUB_RUN_ATTEMPT'],apk_sha256=digest(apk),sdk_so_sha256=native,sdk_version=b['sdk_version'],core_version=b['core_version'],abi=1,image='system-images;android-34;default;x86_64',configuration='owner app-debug; all optional feature macros default false')
    write(root/'identity.json',identity)
    result=check(root);write(root/'validation.json',result)
    # Scan serialized text evidence, not binary font/APK bytes, for common real-secret forms.
    suspicious=re.compile(r'(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|-----BEGIN (?:RSA |OPENSSH )?PRIVATE KEY-----)')
    for p in root.rglob('*'):
        if p.is_file() and p.suffix in ('.json','.txt','.xml','.log'): assert not suspicious.search(p.read_text(errors='replace')),str(p)
    write(root/'manifest.json',{str(p.relative_to(root)):dict(bytes=p.stat().st_size,sha256=digest(p)) for p in sorted(root.rglob('*')) if p.is_file() and p.name!='manifest.json'})
    print(json.dumps(result,ensure_ascii=False))

def verify():
    repo=os.environ['GITHUB_REPOSITORY'];run=os.environ['GITHUB_RUN_ID'];attempt=os.environ['GITHUB_RUN_ATTEMPT'];token=os.environ['GH_TOKEN']
    def api(path,raw=False):
        request=urllib.request.Request('https://api.github.com/repos/'+repo+path,headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json'})
        with OPENER.open(request,timeout=120) as f: b=f.read()
        return b if raw else json.loads(b)
    name=f'reader-final-d05-{run}-{attempt}'
    artifacts=api(f'/actions/runs/{run}/artifacts?per_page=100')['artifacts'];matches=[a for a in artifacts if a['name']==name];assert len(matches)==1
    a=matches[0];assert not a['expired'] and a['workflow_run']['head_sha']==os.environ['GITHUB_SHA']
    assert datetime.datetime.fromisoformat(a['expires_at'].replace('Z','+00:00'))>datetime.datetime.now(datetime.timezone.utc)
    jobs=api(f'/actions/runs/{run}/attempts/{attempt}/jobs?per_page=100')['jobs'];producer=[j for j in jobs if j['name']=='audit'];assert len(producer)==1 and producer[0]['conclusion']=='success'
    raw=api(f"/actions/artifacts/{a['id']}/zip",True);sha=hashlib.sha256(raw).hexdigest();assert len(raw)==a['size_in_bytes'] and a['digest']=='sha256:'+sha
    pathlib.Path('verified.zip').write_bytes(raw)
    with zipfile.ZipFile('verified.zip') as z:
        names=z.namelist();assert len(names)==len(set(names)) and all(not n.startswith('/') and '..' not in pathlib.PurePosixPath(n).parts for n in names);z.extractall('verified')
    root=pathlib.Path('verified');manifest=load(root/'manifest.json')
    manifest_check(root,manifest)
    mutations=[]
    for kind in ('missing','wrong_size','tampered_hash'):
        changed=json.loads(json.dumps(manifest));first=next(iter(changed))
        if kind=='missing':changed.pop(first)
        elif kind=='wrong_size':changed[first]['bytes']+=1
        else:changed[first]['sha256']='0'*64
        try:manifest_check(root,changed)
        except AssertionError:mutations.append(dict(kind=kind,rejected=True))
        else:raise AssertionError('corruption was accepted: '+kind)
    result=check(root);assert result==load(root/'validation.json')
    record=dict(artifact=a,zip_bytes=len(raw),zip_sha256=sha,producer_job=producer[0]['id'],verifier_source=os.environ['GITHUB_SHA'],corruption_checks=mutations,result=result)
    write(pathlib.Path('verified-evidence.json'),record);print(json.dumps(record,ensure_ascii=False))
def history():
    repo=os.environ['GITHUB_REPOSITORY'];token=os.environ['GH_TOKEN']
    def api(path,raw=False):
        req=urllib.request.Request('https://api.github.com/repos/'+repo+path,headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json'})
        with OPENER.open(req,timeout=120) as f:b=f.read()
        return b if raw else json.loads(b)
    a=api('/actions/artifacts/12607826896');assert not a['expired'] and a['workflow_run']['id']==40215281412 and a['workflow_run']['head_sha']=='a32a10c191e8a6d2e791f81686f8f8761515a7b5'
    assert datetime.datetime.fromisoformat(a['expires_at'].replace('Z','+00:00'))>datetime.datetime.now(datetime.timezone.utc)
    jobs=api('/actions/runs/40215281412/attempts/1/jobs')['jobs'];assert any(j['id']==121234967050 and j['conclusion']=='success' for j in jobs)
    b=api('/actions/artifacts/12607826896/zip',True);sha=hashlib.sha256(b).hexdigest();assert len(b)==a['size_in_bytes'] and a['digest']=='sha256:'+sha
    pathlib.Path('history.zip').write_bytes(b)
    with zipfile.ZipFile('history.zip') as z:
        names=z.namelist();assert len(names)==len(set(names)) and all(not n.startswith('/') and '..' not in pathlib.PurePosixPath(n).parts for n in names);z.extractall('history')
    root=pathlib.Path('history');manifest_check(root,load(root/'manifest.json'));v=load(root/'validation.json')
    assert v['harness_sha']==a['workflow_run']['head_sha'] and v['run_id']=='40215281412' and v['attempt']=='1' and v['apk_sha256']==digest(root/'installed-host.apk')
    record=dict(artifact=a,zip_bytes=len(b),zip_sha256=sha,producer_job=121234967050,producer_source=v['harness_sha'],verifier_source=os.environ['GITHUB_SHA'],historical_only=True,result=v)
    write(pathlib.Path('build/final-d05/history-authentication.json'),record)
    print('HISTORY_AUTHENTICATED '+json.dumps({k:v for k,v in record.items() if k!='result'}))
    for p in sorted((root/'delta').glob('*.xml')):
        import xml.etree.ElementTree as ET
        nodes=ET.parse(p).iter('node');print('HISTORY_TREE '+json.dumps(dict(file=p.name,nodes=[{k:n.attrib.get(k) for k in ('text','content-desc','resource-id','package','bounds')} for n in nodes if n.attrib.get('text') or n.attrib.get('content-desc')]),ensure_ascii=False))
if __name__=='__main__':
    assert os.environ.get('GITHUB_ACTIONS')=='true','Actions only'
    if sys.argv[1]=='seal':seal(pathlib.Path(sys.argv[2]))
    elif sys.argv[1]=='history':history()
    else:verify()
