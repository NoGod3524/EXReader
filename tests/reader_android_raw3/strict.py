"""Actions-only same-attempt original ZIP identity and real host/capture evidence."""
from datetime import datetime,timezone
import base64
import hashlib
import io
import json
import os
from pathlib import Path,PurePosixPath
import subprocess
import zipfile
from bundle import verify,parse
assert os.environ.get('GITHUB_ACTIONS')=='true'
identity={k:os.environ[v] for k,v in [('source_sha','GITHUB_SHA'),('run_id','GITHUB_RUN_ID'),('attempt','GITHUB_RUN_ATTEMPT')]}
source,run,attempt=identity.values();repo='repos/'+os.environ['GITHUB_REPOSITORY']+'/'
def api(path):return parse(subprocess.check_output(['gh','api',repo+path]))
record=api('actions/runs/'+run+'/attempts/'+attempt);assert record['head_sha']==source and record['run_attempt']==int(attempt)
jobs=api('actions/runs/'+run+'/attempts/'+attempt+'/jobs?per_page=100')['jobs']
for name in ('android','protocol'):
    found=[j for j in jobs if j['name']==name];assert len(found)==1 and found[0]['head_sha']==source and found[0]['conclusion']=='success'
artifacts=api('actions/runs/'+run+'/artifacts?per_page=100')['artifacts']
selected=[]
def archive(prefix):
    found=[a for a in artifacts if a['name']==prefix+'-'+run+'-'+attempt];assert len(found)==1
    a=found[0];assert not a['expired'] and a['workflow_run']['head_sha']==source and a['workflow_run']['id']==int(run)
    assert datetime.fromisoformat(a['expires_at'].replace('Z','+00:00'))>datetime.now(timezone.utc)
    raw=subprocess.check_output(['gh','api',repo+'actions/artifacts/'+str(a['id'])+'/zip'],timeout=240)
    assert len(raw)==a['size_in_bytes'] and 'sha256:'+hashlib.sha256(raw).hexdigest()==a['digest']
    selected.append({k:a[k] for k in ['id','name','digest','size_in_bytes','expires_at']})
    z=zipfile.ZipFile(io.BytesIO(raw));names=z.namelist();assert len(names)==len(set(names))
    for name in names:
        path=PurePosixPath(name);assert not path.is_absolute() and '..' not in path.parts and '\\' not in name and ':' not in name and not name.endswith('.key')
    def read(suffix):
        found=[n for n in names if n==suffix or n.endswith('/'+suffix)];assert len(found)==1,(suffix,found)
        return z.read(found[0])
    return z,read
old=json.loads(Path('build/android-record-interop-summary/summary.json').read_text())
assert old['inherited_130_accepted'] and old['checks']==138 and all(old[k]==v for k,v in identity.items())
with archive('reader-android-raw3-bundle')[0] as packet:
    verified=verify(packet.read);manifest=verified['manifest']
    assert verified['originals']==4 and verified['reading_records']==11 and verified['revisions']==19
    assert manifest['sender']['raw_selector_candidate'] and all(manifest['sender'][k]==v for k,v in identity.items())
    pdf=next(r for r in manifest['originals'] if r['role']=='pdf')
    assert pdf['bytes']==8845 and pdf['sha256']=='5627a430fa04cbe11d38eb2682e336ef21e147d445753ed46ed11a7d5e3167cc'
    for row in manifest['reading_records']:
        assert row['anchor_version']==(3 if row['mode']==3 else 2)
        if row['role']=='pdf':
            decoded=[None if x is None else base64.b64decode(x,validate=True) for x in row['capture']['selectors']]
            assert decoded[0] is not None and (b'\0' in decoded[0] if row['kind']=='highlight' else b'\0' in decoded[2])
with archive('reader-android-raw3')[0] as package:
    names=package.namelist()
    def read(suffix):
        found=[n for n in names if n==suffix or n.endswith('/'+suffix)];assert len(found)==1,(suffix,found);return package.read(found[0])
    result=parse(read('ui/result.json'));native=parse(read('native/result.json'));guard=parse(read('guard.json'))
    assert result['accepted'] and not result['adopted'] and result['checks']==14 and result['actual_tls']
    assert all(result[k]==v and native[k]==v for k,v in identity.items()) and native['accepted'] and guard['accepted']
    assert guard['seven_modules_unchanged'] and guard['legacy_suites_unchanged'] and guard['sdk_boundaries_unchanged']
    assert len(native['archives'])==7 and native['legacy_anchor_max_version']==2 and native['one_product_sqlite'] and native['single_shared_sdk'] and not native['default_enabled']
    assert result['incoming_apple_status']=='pending' and not result['bidirectional_interoperability_accepted']
    assert len(result['phases'])==8 and len({p['pid'] for p in result['phases']})==8
    for p in result['phases']:
        assert p==parse(read('ui/'+p['phase']+'-raw-report.json')) and p['passed'] and p['count']==len(p['checks']) and all(c['pass'] for c in p['checks'])
    by_phase={p['phase']:p for p in result['phases']}
    assert [by_phase[x]['count'] for x in ['sender','session-push','session-receive','session-reopen','missing-parent','legacy-pending','raw-contract','reopen-ui']]==[6,1,1,1,2,1,1,1]
    for name in ['session-push','session-receive']:assert by_phase[name]['raw3']['session']['shards']==256
    assert by_phase['session-push']['raw3']['session']['pushed']==19 and by_phase['session-receive']['raw3']['session']['pulled']==19
    assert by_phase['session-reopen']['raw3']['network_reopen_records']==11 and len(by_phase['session-reopen']['resolutions'])==11
    assert by_phase['raw-contract']['raw3']['null_exact_protocol_only'] and by_phase['raw-contract']['raw3']['restores']==[{'source_version':1,'restored_version':1},{'source_version':2,'restored_version':2}]
    boundary,=result['boundaries'];assert boundary['real_process_stopped'] and str(boundary['pid']) in boundary['pid_before'] and not boundary['pid_after']
    assert boundary=={**parse(read('ui/kill-ui-boundary.json')),'pid_before':boundary['pid_before'],'pid_after':'','real_process_stopped':True}
    pending=read('ui/kill-ui-original-pending.json');assert hashlib.sha256(pending).hexdigest()==boundary['pending_sha256'] and base64.b64decode(boundary['pending_base64'],validate=True)==pending
    saved=parse(pending);assert saved['version']==2 and saved['anchor_version']==3 and len(saved)==14
    assert by_phase['reopen-ui']['pid']!=boundary['pid'] and by_phase['reopen-ui']['raw3']['original_pending_sha256']==boundary['pending_sha256']
    runtime=manifest['sender'];raw_apk=read('apks/host-debug.apk');assert hashlib.sha256(raw_apk).hexdigest()==runtime['apk_sha256']
    with zipfile.ZipFile(io.BytesIO(raw_apk)) as apk:assert hashlib.sha256(apk.read('lib/x86_64/libexreader.so')).hexdigest()==runtime['sdk_dso_sha256']
    assert native['checks'][0]['apk_sha256']==runtime['apk_sha256'] and native['checks'][0]['sdk_dso_sha256']==runtime['sdk_dso_sha256']
    requests=parse(read('ui/native-https-requests.json'));assert requests and not any(r['path'].endswith(('.sqlite','.db')) for r in requests)
with archive('reader-android-raw3-protocol')[0] as protocol:
    report=parse(protocol.read('result.json'));assert report['accepted'] and all(report[k]==v for k,v in identity.items())
    assert len(report['phases'])==18 and len(set(report['java_policy_cases']))==20 and report['original_suite_cases_per_sdk']==19
    for name,declared in report['files'].items():
        body=protocol.read(name);assert len(body)==declared['bytes'] and hashlib.sha256(body).hexdigest()==declared['sha256']
output={**identity,'accepted':True,'adopted':False,'scope':'API34 default x86_64 independent Android raw3 native host candidate',
 'inherited_business_checks':130,'retained_default_sender_checks':8,'original_protocol_phases':18,'java_policy_cases':20,
 'raw_checks':14,'real_process_boundaries':1,'reading_records':11,'revisions':19,'originals':4,'manifest_sha256':verified['manifest_sha256'],
 'artifacts':selected,'jobs':[{k:j[k] for k in ['id','name','head_sha','conclusion']} for j in jobs if j['name'] in ('android','protocol')],
 'incoming_apple_status':'pending','bidirectional_interoperability_accepted':False,'physical_device':False,'complete_product':False}
out=Path('build/android-raw3-summary');out.mkdir(parents=True,exist_ok=True)
(out/'summary.json').write_text(json.dumps(output,indent=2)+'\n');print(json.dumps(output),flush=True)
