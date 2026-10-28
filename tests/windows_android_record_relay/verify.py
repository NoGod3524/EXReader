"""Actions-only authenticate same-round ZIPs and actual app record relay, never borrowed green."""
import base64,hashlib,io,json,os,urllib.request,zipfile
from pathlib import Path
import relay
identity=relay.identity();root='https://api.github.com/repos/NoGod3524/EXReader/actions/runs/'+identity['run_id']
out=Path('build/records-authentication');out.mkdir(parents=True,exist_ok=True)
report={**identity,'passed':False,'artifacts':[],'checks':[]}
def fetch(url):
    req=urllib.request.Request(url,headers={'Authorization':'Bearer '+os.environ['GH_TOKEN'],'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'})
    with urllib.request.urlopen(req,timeout=90) as response:return response.read()
def api(url):return json.loads(fetch(url))
try:
    run=api(root);assert run['head_sha']==identity['source_sha'] and str(run['run_attempt'])==identity['attempt']
    jobs=api(root+'/jobs?filter=latest&per_page=100')['jobs']
    for name in ('android','retained','windows-first','Android receives resolves moves and syncs back','windows-return'):
        chosen=[j for j in jobs if j['name']==name];assert len(chosen)==1 and chosen[0]['conclusion']=='success',(name,chosen)
    artifacts=api(root+'/artifacts?per_page=100')['artifacts'];states=[]
    for phase,prefix in [('windows-first','records-windows-first'),('android','records-android'),('windows-return','records-windows-return')]:
        name=prefix+'-'+identity['run_id']+'-'+identity['attempt'];matches=[a for a in artifacts if a['name']==name];assert len(matches)==1
        a=matches[0];assert not a['expired'];raw=fetch(a['archive_download_url']);digest=hashlib.sha256(raw).hexdigest();assert a['digest']=='sha256:'+digest
        (out/(name+'.zip')).write_bytes(raw)
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            names=[n for n in z.namelist() if n=='state.json'];assert len(names)==1,z.namelist()
            data=z.read('state.json');path=out/(phase+'-state.json');path.write_bytes(data);state,_=relay.load(path,phase);states.append((state,hashlib.sha256(data).hexdigest()))
            requests=json.loads(z.read('requests.json'));assert requests and all(r['authenticated'] for r in requests)
            assert any(r['method']=='GET' for r in requests) and any(r['method']=='PUT' for r in requests)
        report['artifacts'].append({'id':a['id'],'name':name,'zip_sha256':digest,'url':'https://github.com/NoGod3524/EXReader/actions/runs/'+identity['run_id']+'/artifacts/'+str(a['id'])})
    first,middle,last=[x[0] for x in states]
    assert middle['previous_sha256']==states[0][1] and last['previous_sha256']==states[1][1]
    for state in (middle,last):
        assert state['data']['book_identity']==first['data']['book_identity']
        assert state['data']['original_sha256']==first['data']['original_sha256']
    assert first['data']['program_sha256']==last['data']['program_sha256']==middle['data']['windows_program_sha256']
    key='/dav/exreader-sync-v1/objects/'+first['data']['original_sha256'][:2]+'/'+first['data']['original_sha256']+'.epub'
    original=base64.b64decode(first['entries'][key]['body']);assert len(original)==first['data']['original_bytes']
    for state in (middle,last):assert state['entries'][key]==first['entries'][key]
    incoming=middle['data']['incoming_records'];outgoing=middle['data']['outgoing_records'];assert len(incoming)==3 and len(outgoing)==4
    by_body=lambda rows,body:next(x for x in rows if x['body']==body)
    old=by_body(incoming,'Windows note');new=by_body(outgoing,'Android edited note');assert old['id']==new['id'] and old['head']!=new['head']
    for k in ('part','path','start','end','exact','prefix','suffix'):assert old[k]==new[k]
    assert len(last['data']['actual_pages'])==3
    report['checks']=['all_required_jobs_success_same_source_attempt','artifact_zip_digests_match_GitHub','authenticated_HTTPS_requests','immutable_original_preserved_three_phases','record_edit_preserves_annotation_identity_and_anchor','native_pages_actual_resolution','ambiguous_anchor_explicit_no_jump','repeat_sync_no_duplicate_records','same_Windows_program_on_return']
    report['passed']=True
finally:
    (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False,indent=2))
