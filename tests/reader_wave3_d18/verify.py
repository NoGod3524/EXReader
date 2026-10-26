"""Bind raw same-attempt ZIPs, app bytes, XCTest and independent per-action reads."""
import datetime, hashlib, io, json, os, re, tarfile, traceback, zipfile
from common import OUT, ACTIONS, REJECTS, identity, hashed, write
from producer import request
info=identity();out=OUT/'verification';out.mkdir(parents=True,exist_ok=True)
report=dict(**info,accepted=False,artifacts=[],platforms={},errors=[],complete_product=False,physical_device=False,physical_keyboard=False,keyboard_focus=False)

def unique(names,suffix):
    found=[n for n in names if n==suffix or n.endswith('/'+suffix)];assert len(found)==1,(suffix,found);return found[0]
def value(z,suffix):return json.loads(z.read(unique(z.namelist(),suffix)))
def invariants(before,after):
    assert before['semantic']==after['semantic'],'failure/no-op changed SDK or catalog'

def mapping(snapshot):
    """Prove that the SDK originals are precisely the product's mapped books."""
    product=snapshot['product'];public=snapshot['public_sdk']
    def records(table):
        value=product[table]
        return [dict(zip(value['columns'],row)) for row in value['rows']]
    books=records('reader_books');locals=records('reader_local_books')
    originals={b['id']:b for b in public['originals']}
    assert len(originals)==public['book_count']==len(books)==len(locals)
    for row in locals:
        candidates=[b for b in books if b['book_key']==row['book_key']]
        assert len(candidates)==1 and candidates[0]['deleted']==0
        book=candidates[0];source=originals[row['sdk_book_id']]
        assert source['sha256']==book['source_sha256'] and source['bytes']==book['source_bytes']
        assert book['book_key']==book['format']+':'+source['sha256']
        assert book['format']=='epub' and row['location_kind']=='epub_chapter'

def validate(host,e,rows,snapshots):
    assert all(e[k]==info[k] for k in info) and e['host']==host and e['accepted']
    assert len(rows)==18 and len({r['action'] for r in rows})==18
    assert {r['action'] for r in rows}==set(ACTIONS)|{'reject.badfile'}
    assert e['configuration']['review_macros_present'] is False
    assert e['configuration']['product_manifest']['source_sha']==info['source_sha']
    assert e['program']['info_plist']['EXRSourceSHA']==info['source_sha']
    assert e['program']['installed_sha256']==e['program']['sha256']
    assert e['program']['info_plist']['UIFileSharingEnabled'] is True
    assert e['physical_device'] is False and e['physical_keyboard'] is False and e['keyboard_focus'] is False
    for r in rows:
        assert r['result']=='passed' and r['executed'] and r['exposed'] and r['input']==('independent-public-readback' if r['action']=='no_unexpected_revision' else 'native-touch')
        for phase in ['before','after']:
            s=snapshots[r[phase]]
            assert all(s[k]==info[k] for k in info) and s['host']==host
            assert s['idle']['stable'] and s['idle']['sample_count']>=2 and s['idle']['separation_seconds']>=0.5
            assert s['public_sdk']['sdk_version']=='3.41.0'
            assert s['paths']['sdk'].endswith('/library.sqlite') and s['paths']['catalog'].endswith('/reader-catalog.db')
            assert s['semantic']['product_sha256']==hashed(s['product'])
            mapping(s)
        if r['action'] in REJECTS:invariants(snapshots[r['before']],snapshots[r['after']])
    assert snapshots['import.before']['public_sdk']['book_count']==0
    assert snapshots['import.after']['public_sdk']['book_count']==1
    base=snapshots['opened.idle'];final=snapshots['final.idle']
    assert base['public_sdk']['book_count']==final['public_sdk']['book_count']==1
    assert snapshots['book.open.before']['monotonic'] < base['monotonic'] < snapshots['cancel.before']['monotonic'] < snapshots['cancel.after']['monotonic'] < snapshots['reject.badfile.before']['monotonic'] < snapshots['reject.badfile.after']['monotonic'] < final['monotonic']
    for key in ['sources_sha256','revisions_sha256']:
        assert base['semantic'][key]==final['semantic'][key],key
    for action in ['next','previous','continue_after_return']:
        assert snapshots[action+'.before']['semantic']['sdk_sha256']!=snapshots[action+'.after']['semantic']['sdk_sha256'],action+' did not independently change reading progress'
    return dict(accepted=True,passed_named_actions=len(ACTIONS),additional_badfile_rejection=True,
        ordinary_open_progress={'before':snapshots['book.open.before']['public_sdk'],'after_idle':base['public_sdk']},
        ordinary_progress_changes={a:{p:snapshots[a+'.'+p]['public_sdk'] for p in ['before','after']} for a in ['next','previous','continue_after_return']},
        rejection_comparisons={a:{p:snapshots[a+'.'+p]['semantic'] for p in ['before','after']} for a in REJECTS},
        opened_idle_baseline=base,final_idle=final,rows=rows)
try:
    run=info['run_id'];attempt=info['attempt']
    jobs=json.loads(request('/actions/runs/'+run+'/attempts/'+attempt+'/jobs?per_page=100'))['jobs']
    report['jobs']=[{k:j[k] for k in ['id','name','status','conclusion']} for j in jobs]
    artifacts=json.loads(request('/actions/runs/'+run+'/artifacts?per_page=100'))['artifacts']
    for host in ['source','iphone','ipad']:
        try:
            name='d18-'+host+'-'+run+'-'+attempt;found=[a for a in artifacts if a['name']==name];assert len(found)==1,name
            a=found[0];assert not a['expired'] and a['workflow_run']['id']==int(run) and a['workflow_run']['head_sha']==info['source_sha']
            assert datetime.datetime.fromisoformat(a['expires_at'].replace('Z','+00:00'))>datetime.datetime.now(datetime.timezone.utc)
            raw=request('/actions/artifacts/'+str(a['id'])+'/zip');sha=hashlib.sha256(raw).hexdigest()
            assert len(raw)==a['size_in_bytes'] and a['digest']=='sha256:'+sha
            item=dict(name=name,id=a['id'],bytes=len(raw),sha256=sha,expires_at=a['expires_at'],source_sha=info['source_sha'],run_id=run,attempt=attempt)
            report['artifacts'].append(item);print('D18_ORIGINAL_ZIP '+json.dumps(item),flush=True)
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                names=z.namelist();assert len(names)==len(set(names)) and all(not n.startswith('/') and '..' not in n.split('/') for n in names)
                if host=='source':
                    guard=value(z,'guard.json');assert guard['source_preflight'] and all(guard[k]==info[k] for k in info);continue
                e=value(z,host+'/execution.json')
                report['platforms'][host]=dict(native_accepted=e['accepted'],program=e['program'],executions=e['executions'],configuration=e['configuration'],test_cases=e['test_cases'])
                # Bind every raw observation, screenshot, native log and xcresult.
                for path,f in e['files'].items():
                    data=z.read(unique(names,host+'/'+path));assert len(data)==f['bytes'] and hashlib.sha256(data).hexdigest()==f['sha256'],path
                with tarfile.open(fileobj=io.BytesIO(z.read(unique(names,host+'/actual-app.tar.gz'))),mode='r:gz') as tar:
                    members=[m for m in tar.getmembers() if m.isfile() and m.name=='EXReaderHost.app/EXReaderHost'];assert len(members)==1
                    data=tar.extractfile(members[0]).read();assert hashlib.sha256(data).hexdigest()==e['program']['sha256'] and len(data)==e['program']['bytes']
                    assert members[0].mode==e['program']['mode'] and not e['program']['is_symlink']
                logs=z.read(unique(names,host+'/native-actions.log')).decode(errors='replace')
                rows=[json.loads(raw) for raw in re.findall(r'\bD18_ACTION (\{[^\r\n]+\})',logs)]
                attachments=value(z,host+'/attachments/manifest.json')
                for row in rows:
                    for kind,ext in [('screen','png'),('tree','txt')]:
                        role=row['action']+'-'+kind+'_'
                        found=[a for group in attachments for a in group['attachments'] if a.get('suggestedHumanReadableName','').startswith(role)]
                        assert len(found)==1,(role,found)
                        raw=z.read(unique(names,host+'/attachments/'+found[0]['exportedFileName']))
                        assert raw
                        if ext=='png':assert raw[:8]==b'\x89PNG\r\n\x1a\n' and int.from_bytes(raw[16:20],'big')>0 and int.from_bytes(raw[20:24],'big')>0
                snapshots={}
                for n in names:
                    prefix=host+'/observations/'
                    if prefix in n:
                        suffix=n.split(prefix,1)[1]
                        if suffix.endswith('.json') and '/' not in suffix and suffix!='picker-fixtures.json': snapshots[suffix[:-5]]=json.loads(z.read(n))
                report['platforms'][host].update(rows=rows,completed_rows=len(rows))
                accepted=validate(host,e,rows,snapshots);report['platforms'][host].update(accepted)
                matching=[j for j in jobs if j['name']=='D18 native '+host];assert len(matching)==1 and matching[0]['conclusion']=='success'
                print('D18_PLATFORM '+json.dumps(dict(host=host,program=e['program'],passed_named_actions=17,rejections=accepted['rejection_comparisons'],configuration=e['configuration'])),flush=True)
        except Exception as error:
            report['errors'].append(host+': '+type(error).__name__+': '+str(error));traceback.print_exc()
    report['accepted']=not report['errors'] and set(report['platforms'])=={'iphone','ipad'}
    # Runtime negative controls use the real accepted data, never fabricated success.
    if report['accepted']:
        import copy
        negative=[]
        assert validate('ipad',e,rows,snapshots)['accepted']
        for name,change in [('missing-action',lambda r,s:r.pop()),('wrong-store-path',lambda r,s:s['cancel.before']['paths'].update(catalog='unknown')),('missing-idle',lambda r,s:s['cancel.before']['idle'].update(stable=False)),('unexpected-mutation',lambda r,s:s['cancel.after']['semantic'].update(sdk_sha256='wrong')),('wrong-source',lambda r,s:s['cancel.before'].update(source_sha='0'*40))]:
            # Re-read the retained values from the matching original ZIP above is
            # unnecessary: snapshots/rows are still the actual last platform data.
            badrows=copy.deepcopy(rows);badsnap=copy.deepcopy(snapshots)
            try:change(badrows,badsnap);validate('ipad',e,badrows,badsnap)
            except (AssertionError,KeyError):negative.append(name)
            else:raise AssertionError('negative accepted: '+name)
        report['negative_controls']=negative
finally:
    write(out/'verification.json',report)
    print('D18_VERIFICATION '+json.dumps({k:v for k,v in report.items() if k!='platforms'}),flush=True)
assert report['accepted'],report['errors']
