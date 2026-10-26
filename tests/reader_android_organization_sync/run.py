"""Actions-only real Android Activity/session fixture for organization projection."""
import argparse, base64, hashlib, json, os, secrets, subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'reader_session_android'))
from run_roundtrip import Dav

assert os.environ.get('GITHUB_ACTIONS') == 'true'
p = argparse.ArgumentParser()
p.add_argument('--fixture', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
a = p.parse_args(); a.output.mkdir(parents=True, exist_ok=True)
user = 'org-' + secrets.token_hex(16); password = secrets.token_hex(32)
authorization = 'Basic ' + base64.b64encode((user + ':' + password).encode()).decode()
server = Dav(a.fixture, authorization)
identity = {'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'], 'attempt': os.environ['GITHUB_RUN_ATTEMPT']}
def revision(id, kind, key, payload, parents=(), operation='put'):
    server.retain({'version':1, 'id':id, 'entity_kind':kind, 'entity_key':key, 'operation':operation,
                   'location_kind':'none', 'parents':list(parents), 'payload':payload})
def book(body, title, rid):
    sha=hashlib.sha256(body).hexdigest(); key='txt:'+sha
    with server.lock:
        server.entries['/dav/exreader-sync-v1/objects/'+sha[:2]+'/'+sha+'.txt']=body
        server.dirs.update(['/dav/exreader-sync-v1/', '/dav/exreader-sync-v1/objects/', '/dav/exreader-sync-v1/objects/'+sha[:2]+'/', '/dav/exreader-sync-v1/revisions/'])
    revision(rid, 'book', key, {'format':'txt','source_sha256':sha,'source_bytes':len(body),'title':title,'author':'Remote author','favorite':False})
    return key

def adb(*args, input=None, timeout=180):
    return subprocess.check_output(['adb',*map(str,args)],input=input,stderr=subprocess.STDOUT,timeout=timeout)

accepted=False
try:
    key=book(b'first book without local SDK mapping\n','Remote metadata only','10000000000000000000000000000001')
    deleted=book(b'deleted book\n','Original deleted title','10000000000000000000000000000002')
    revision('10000000000000000000000000000003','book',deleted,None,['10000000000000000000000000000002'],'delete')
    conflict=book(b'conflicting book\n','Original conflict','10000000000000000000000000000004')
    sha=conflict.split(':')[1]
    for rid,title in [('10000000000000000000000000000005','Conflict A'),('10000000000000000000000000000006','Conflict B')]:
        revision(rid,'book',conflict,{'format':'txt','source_sha256':sha,'source_bytes':len(b'conflicting book\n'),'title':title,'author':'','favorite':False},['10000000000000000000000000000004'])
    shelf='20000000000000000000000000000001'; orphan='20000000000000000000000000000002'
    revision('10000000000000000000000000000007','shelf',shelf,{'name':'Cloud Shelf','parent_id':None,'ordinal':1})
    revision('10000000000000000000000000000008','shelf',orphan,{'name':'Missing parent child','parent_id':'30000000000000000000000000000000','ordinal':2})
    revision('10000000000000000000000000000009','membership','shelf:'+shelf+':'+key,{'book_key':key,'collection_kind':'shelf','collection_id':shelf,'ordinal':1})
    assert adb('shell','pm','clear','org.exreader.host').strip()==b'Success'
    adb('reverse',f'tcp:{server.server.server_port}',f'tcp:{server.server.server_port}')
    payload={'root':'https://127.0.0.1:'+str(server.server.server_port)+'/dav/','user':user,'password':password,'book_key':key,'deleted_key':deleted,'conflict_key':conflict,'shelf_id':shelf,'orphan_id':orphan}
    adb('shell',"run-as org.exreader.host sh -c 'cat > files/organization-sync-input.json'",input=json.dumps(payload).encode())
    command=['shell','am','instrument','-w','-r']
    for k,v in identity.items():command.extend(['-e',k,v])
    raw=adb(*command,'org.exreader.host.test/org.exreader.host.OrganizationSyncTest',timeout=900)
    report=json.loads(adb('exec-out','run-as','org.exreader.host','cat','files/organization-sync-report.json'))
    assert all(report.get(k)==v for k,v in identity.items())
    assert report['passed'] and report['count']==5 and all(x['pass'] for x in report['checks']),report
    assert b'ORGANIZATION_SYNC_PASS' in raw and b'INSTRUMENTATION_CODE: -1' in raw
    accepted=True
finally:
    server.server.shutdown();server.server.server_close()
    report = locals().get('report', {})
    result={**identity,'accepted':accepted,'device':report,'requests':len(server.requests)}
    (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result),flush=True)
