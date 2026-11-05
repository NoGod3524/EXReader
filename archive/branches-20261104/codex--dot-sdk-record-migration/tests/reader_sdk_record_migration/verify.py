"""Authenticate the exact terminal upstream jobs and their actual ZIP bytes.
All positive and negative verifier cases execute in this Actions-only job.
"""
import copy
import datetime as dt
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback
import zipfile
from contract import OLD, NEW, LABELS, NEGATIVES, DIRECTIONS

REQUIRED_REJECTIONS = {'wrong-source','wrong-run','wrong-attempt','failed-job','running-job',
    'wrong-job-name','wrong-artifact-id','empty-zip','expired-artifact','expired-date',
    'wrong-api-digest','wrong-api-size','duplicate-zip-member','duplicate-json-key',
    'missing-report','missing-case','duplicate-case','binary-tamper','wrong-module-source',
    'wrong-original-report','false-migration-acceptance',
    'backslash-manifest-path','absolute-manifest-path','parent-manifest-path',
    'backslash-zip-member','parent-zip-member','absolute-zip-member','original-tamper'}
def sha(data):return hashlib.sha256(data).hexdigest()
def pairs(values):
    result={}
    for key,value in values:
        assert key not in result, 'duplicate JSON key'
        result[key]=value
    return result
def parse(raw):return json.loads(raw,object_pairs_hook=pairs)
def member_path(path):
    # Producer serializes OS paths with as_posix(). Never silently repair a
    # malformed incoming name: that could alias two members or hide traversal.
    assert isinstance(path,str) and path and '\\' not in path and ':' not in path
    assert all(part not in ('', '.', '..') for part in path.split('/'))
    assert not any(ord(c)<32 for c in path)
    return path
def read_member(archive,path):return archive.read(member_path(path))
def api(path,binary=False):
    for retry in range(4):
        result=subprocess.run(['gh','api',path],capture_output=True)
        if result.returncode==0:return result.stdout if binary else parse(result.stdout)
        if retry==3 or not any(code in result.stderr for code in (b'HTTP 500',b'HTTP 502',b'HTTP 503',b'HTTP 504')):
            raise RuntimeError(result.stderr.decode('utf-8','replace'))
        time.sleep(10*(retry+1))
def verify(bundle,expected):
    a,j,raw=bundle['artifact'],bundle['job'],bundle['raw']
    source,run,attempt,system=expected
    assert j['name']=='migration ('+system+')'
    assert j['status']=='completed' and j['conclusion']=='success'
    assert j['head_sha']==source and str(j['run_id'])==run and str(j['run_attempt'])==attempt
    assert a['id']>0 and a['name']==f'reader-sdk-record-migration-{system}-{run}-{attempt}'
    assert a['workflow_run']['head_sha']==source and str(a['workflow_run']['id'])==run
    assert a['expired'] is False and dt.datetime.fromisoformat(a['expires_at'].replace('Z','+00:00'))>dt.datetime.now(dt.timezone.utc)
    assert raw and len(raw)==a['size_in_bytes'] and a['digest']=='sha256:'+sha(raw)
    archive=zipfile.ZipFile(io.BytesIO(raw))
    names=archive.namelist();assert len(names)==len(set(names))
    for name in names:member_path(name)
    result_names=[n for n in names if n=='result.json'];assert len(result_names)==1
    result=parse(archive.read('result.json'))
    assert result['source_sha']==source and result['run_id']==run and result['attempt']==attempt and result['system']==system
    assert result['verification_accepted'] is True and result['migration_accepted'] is False
    assert result['cross_device_sync'] is False and result['complete_product'] is False
    assert set(result['matrices'])==DIRECTIONS
    assert result['module_sources']==bundle['module_sources']
    assert set(result['originals'])=={'book.txt','book-edited.txt','book.epub','missing-spine.epub',
                                    'pages.pdf','pages.cbz','spacer.txt','manifest.json'}
    for relative,digest in result['originals'].items():
        assert sha(read_member(archive,'originals/'+relative))==digest
    assert set(result['versions'])=={'3.40.0','3.41.0'}
    for version,sdk_source in (('3.40.0',OLD),('3.41.0',NEW)):
        identity=result['versions'][version]
        assert identity['sdk_source']==sdk_source and identity['sdk_version']==version
        assert sha(read_member(archive,identity['probe_path']))==identity['probe_sha256']
        for relative,digest in identity['installed_files'].items():
            member_path(relative)
            assert sha(read_member(archive,'installed-'+version+'/'+relative))==digest
        original=parse(archive.read('original-'+version+'/summary.json'))
        assert original['identity']['GITHUB_SHA']==source and original['identity']['GITHUB_RUN_ID']==run and original['identity']['GITHUB_RUN_ATTEMPT']==attempt
        assert original['reading_commands_accepted'] is True and original['checks_failed']==0
        assert original['sdk_version']==version
        assert original['probe_sha256']==sha(read_member(archive,'original-'+version+'/'+identity['original_probe_name']))
        assert original['c_consumer_sha256']==sha(read_member(archive,'original-'+version+'/'+identity['original_c_name']))
        assert original['report_sha256']==identity['original_report_sha256']==sha(archive.read('original-'+version+'/report.json'))
        assert original['checks_total']==identity['original_checks'] and identity['original_failures']==0
    for direction,summary in result['matrices'].items():
        report_raw=read_member(archive,summary['report']);assert sha(report_raw)==summary['report_sha256']
        report=parse(report_raw);producer,consumer=direction.split('-to-')
        assert report['mode']=='consume' and report['sdk_version']==consumer and report['failures']==0
        assert len(report['checks'])==summary['checks'] and all(c['pass'] is True for c in report['checks'])
        assert NEGATIVES<={c['name'] for c in report['checks']}
        if producer!=consumer:assert 'parser-mismatch-produces-no-navigation-target' in {c['name'] for c in report['checks']}
        rows=report['records'];assert len(rows)==len(LABELS)==summary['records']
        assert {row['label'] for row in rows}==LABELS
        assert summary['database_and_wire_bytes_unchanged'] is True
        for row in rows:
            original=read_member(archive,'records-'+producer+'/'+row['revision']+'.wire')
            assert original==bytes.fromhex(row['wire_hex']) and sha(original)==row['wire_sha256']
            assert row['producer_parser']=='exreader-sdk-'+producer and row['consumer_parser']=='exreader-sdk-'+consumer
            if row['has_location']:
                assert row['record_parser']=='exreader-sdk-'+producer
                assert row['match']==('AMBIGUOUS' if row['label']=='txt-ambiguous' else 'FOUND')
                if row['match']=='FOUND':assert row['actual_text']==row['exact']
    return result

def rewrite(bundle,member,transform):
    b=copy.deepcopy(bundle)
    old=zipfile.ZipFile(io.BytesIO(b['raw']));stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as new:
        for item in old.infolist():
            value=old.read(item.filename)
            if item.filename==member:value=transform(value)
            new.writestr(item.filename,value)
    b['raw']=stream.getvalue();b['artifact']['size_in_bytes']=len(b['raw']);b['artifact']['digest']='sha256:'+sha(b['raw'])
    return b
def negative_tests(bundle,expected):
    rejected=[]
    def reject(name,b,exp=expected):
        try:verify(b,exp)
        except (AssertionError,KeyError,ValueError,zipfile.BadZipFile):rejected.append(name)
        else:raise AssertionError('verifier accepted '+name)
    for name,part,key,value in (
        ('wrong-source','job','head_sha','0'*40),('wrong-run','job','run_id',0),
        ('wrong-attempt','job','run_attempt',0),('failed-job','job','conclusion','failure'),
        ('running-job','job','status','in_progress'),('wrong-job-name','job','name','not migration'),
        ('wrong-artifact-id','artifact','id',0),('expired-artifact','artifact','expired',True),
        ('expired-date','artifact','expires_at','2000-01-01T00:00:00Z'),
        ('wrong-api-digest','artifact','digest','sha256:'+'0'*64),('wrong-api-size','artifact','size_in_bytes',1)):
        b=copy.deepcopy(bundle);b[part][key]=value;reject(name,b)
    b=copy.deepcopy(bundle);b['raw']=b'';reject('empty-zip',b)
    b=copy.deepcopy(bundle);stream=io.BytesIO(b['raw'])
    with zipfile.ZipFile(stream,'a') as z:z.writestr('result.json',b'{}')
    b['raw']=stream.getvalue();b['artifact']['size_in_bytes']=len(b['raw']);b['artifact']['digest']='sha256:'+sha(b['raw']);reject('duplicate-zip-member',b)
    reject('duplicate-json-key',rewrite(bundle,'result.json',lambda raw:raw.replace(b'"source_sha":',b'"source_sha":"duplicate","source_sha":',1)))
    result=verify(bundle,expected)
    def change_result(fn):
        def transform(raw):
            r=parse(raw);fn(r);return json.dumps(r).encode()
        return rewrite(bundle,'result.json',transform)
    reject('missing-report',change_result(lambda r:r['matrices']['3.40.0-to-3.41.0'].update(report='absent.json')))
    reject('wrong-module-source',change_result(lambda r:r['module_sources'].update({'apps/reader/reading-state':'0'*40})))
    reject('wrong-original-report',change_result(lambda r:r['versions']['3.40.0'].update(original_report_sha256='0'*64)))
    reject('false-migration-acceptance',change_result(lambda r:r.update(migration_accepted=True)))
    for name,path in (('backslash-manifest-path','installed-3.40.0\\modules\\bin\\migration-probe'),
                      ('absolute-manifest-path','/installed-3.40.0/modules/bin/migration-probe'),
                      ('parent-manifest-path','installed-3.40.0/../result.json')):
        reject(name,change_result(lambda r:r['versions']['3.40.0'].update(probe_path=path)))
    for name,path in (('backslash-zip-member','unsafe\\member'),
                      ('parent-zip-member','unsafe/../member'),('absolute-zip-member','/unsafe/member')):
        b=copy.deepcopy(bundle);stream=io.BytesIO(b['raw'])
        with zipfile.ZipFile(stream,'a') as z:z.writestr(path,b'unsafe')
        b['raw']=stream.getvalue();b['artifact']['size_in_bytes']=len(b['raw']);b['artifact']['digest']='sha256:'+sha(b['raw'])
        reject(name,b)
    binary=result['versions']['3.40.0']['probe_path'];reject('binary-tamper',rewrite(bundle,binary,lambda raw:raw+b'tamper'))
    reject('original-tamper',rewrite(bundle,'originals/book.txt',lambda raw:raw+b'tamper'))
    # Rehash the mutated report in result.json so the named-case gate itself is tested.
    for name,edit in (('missing-case',lambda r:r['records'].pop()),('duplicate-case',lambda r:r['records'].append(r['records'][0]))):
        path=result['matrices']['3.40.0-to-3.41.0']['report']
        def transform(raw):
            r=parse(raw);edit(r);return json.dumps(r).encode()
        b=rewrite(bundle,path,transform)
        def update(raw):
            r=parse(raw)
            with zipfile.ZipFile(io.BytesIO(b['raw'])) as z:r['matrices']['3.40.0-to-3.41.0']['report_sha256']=sha(z.read(path))
            return json.dumps(r).encode()
        b=rewrite(b,'result.json',update);reject(name,b)
    assert set(rejected)==REQUIRED_REJECTIONS
    return rejected

def write_failure(out,error):
    out.mkdir(parents=True,exist_ok=True)
    failure={k:os.environ.get(k) for k in ('GITHUB_SHA','GITHUB_RUN_ID','GITHUB_RUN_ATTEMPT')}
    failure.update(verification_accepted=False,migration_accepted=False,
        error_type=type(error).__name__,error=str(error),traceback=traceback.format_exc())
    (out/'failure.json').write_text(json.dumps(failure,indent=2)+'\n',encoding='utf-8')
    return failure

def main():
    assert os.environ.get('GITHUB_ACTIONS')=='true'
    source,run,attempt,repo=(os.environ[k] for k in ('GITHUB_SHA','GITHUB_RUN_ID','GITHUB_RUN_ATTEMPT','GITHUB_REPOSITORY'))
    out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=True)
    jobs=api(f'repos/{repo}/actions/runs/{run}/attempts/{attempt}/jobs?per_page=100')['jobs']
    artifacts=api(f'repos/{repo}/actions/runs/{run}/artifacts?per_page=100')['artifacts']
    module_sources={p:subprocess.check_output(['git','rev-parse','HEAD:'+p],text=True).strip()
        for p in ('apps/reader/reading-state','apps/reader/reading-commands','apps/reader/revisions','apps/reader/navigation')}
    records=[];originals=[]
    for system in ('Linux','Windows'):
        named=[a for a in artifacts if a['name']==f'reader-sdk-record-migration-{system}-{run}-{attempt}'];assert len(named)==1
        matched=[j for j in jobs if j['name']=='migration ('+system+')'];assert len(matched)==1
        artifact,job=named[0],matched[0]
        raw=api(f'repos/{repo}/actions/artifacts/{artifact["id"]}/zip',True)
        bundle={'artifact':artifact,'job':job,'raw':raw,'module_sources':module_sources}
        result=verify(bundle,(source,run,attempt,system))
        rejected=negative_tests(bundle,(source,run,attempt,system))
        try:raise RuntimeError('intentional verifier failure-evidence self-test')
        except RuntimeError as error:
            failure=write_failure(out/('failure-selftest-'+system),error)
        assert parse((out/('failure-selftest-'+system)/'failure.json').read_bytes())==failure
        assert failure['GITHUB_SHA']==source and failure['verification_accepted'] is False
        assert failure['error_type']=='RuntimeError' and 'self-test' in failure['traceback']
        originals.append(result['originals'])
        records.append({'system':system,'job_id':job['id'],'job_status':job['status'],'job_conclusion':job['conclusion'],
            'artifact_id':artifact['id'],'name':artifact['name'],'bytes':len(raw),'api_digest':artifact['digest'],
            'recomputed_sha256':sha(raw),'expires_at':artifact['expires_at'],'result_sha256':sha(zipfile.ZipFile(io.BytesIO(raw)).read('result.json')),
            'matrices':result['matrices'],'programs':{v:{k:d[k] for k in ('sdk_source','probe_sha256','c_sha256','original_checks','original_failures')} for v,d in result['versions'].items()},
            'verifier_rejections':rejected,'unexpected_exception_evidence_preserved':True})
        (out/'verified-platforms.json').write_text(json.dumps(records,indent=2)+'\n',encoding='utf-8')
    assert len({r['artifact_id'] for r in records})==2 and originals[0]==originals[1]
    result={'source_sha':source,'run_id':run,'attempt':attempt,'verification_accepted':True,
        'migration_accepted':False,'cross_device_sync':False,'complete_product':False,'artifacts':records}
    (out/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2),flush=True)
if __name__=='__main__':
    assert os.environ.get('GITHUB_ACTIONS')=='true'
    output=Path(sys.argv[1]);output.mkdir(parents=True,exist_ok=True)
    (output/'started.json').write_text(json.dumps({k:os.environ[k] for k in
        ('GITHUB_SHA','GITHUB_RUN_ID','GITHUB_RUN_ATTEMPT')})+'\n',encoding='utf-8')
    try:main()
    except Exception as error:
        write_failure(output,error)
        raise
