"""Strict Actions-only authentication and adversarial rejection of actual evidence."""
import copy
import datetime
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
from check_parallel_integration import fetch, pages, download_artifact_zip, require

REQUIRED=set(json.loads(Path('tests/reader_original_export/cases.json').read_text()))
PLATFORMS=[('Linux','ubuntu-22.04'),('Windows','windows-2022'),('macOS','macos-15')]

def object_pairs(pairs):
    out={}
    for key,value in pairs:
        require(key not in out,'duplicate JSON key '+key);out[key]=value
    return out

def load(raw): return json.loads(raw,object_pairs_hook=object_pairs)

def validate(report,members,platform,source,run,attempt):
    require(type(report['run_id']) is int and type(report['attempt']) is int,'integer report run identity')
    require(report['accepted'] is True and report['source_sha']==source and report['run_id']==run and report['attempt']==attempt,'report identity/outcome')
    require(report['platform']==platform and report['system_share_ui'] is False and report['six_devices'] is False,'platform/scope')
    expected=REQUIRED|({'windows_actual_locked_cleanup_failure'} if platform=='Windows' else {'posix_real_midstream_write_failure'})
    require(set(report['checks'])==expected and len(report['checks'])==len(expected)==report['count'],'exact named cases')
    require(not report['failures'],'failures present')
    require(set(report['binary_identities'])=={'probe','c_consumer','module'},'binary identity roles')
    used=set()
    for role,identity in report['binary_identities'].items():
        member=identity['member'];require(member not in used and member in members,'missing/duplicate binary binding');used.add(member)
        data=members[member];require(len(data)==identity['bytes']>0 and hashlib.sha256(data).hexdigest()==identity['sha256'],'actual binary digest '+role)
        require(member.startswith('oe-evidence/binaries/'),'binary member scope')
        if role=='module':
            require(data.startswith(b'!<arch>\n') and data==members.get('oe-stage/lib/'+member.split('/')[-1]),'actual installed static module binding')
        else:
            require(data[:4] in ({b'\x7fELF'} if platform=='Linux' else {b'\xcf\xfa\xed\xfe',b'\xfe\xed\xfa\xcf',b'\xca\xfe\xba\xbe',b'\xbe\xba\xfe\xca'} if platform=='macOS' else {data[:4]}),'native executable format')
            if platform=='Windows':require(data[:2]==b'MZ','native PE executable')
    nine=report['cases']['nine']['items'];require(len(nine)==9 and {r['format'] for r in nine}==set(range(1,10)),'nine original modules')
    require(all(r['committed']==1 and r['created']==1 and len(r['hash'])==64 and r['bytes']>0 for r in nine),'nine real outputs')
    # Bind actual originals, final files, snapshots and report; basename is stable.
    for r in nine:
        ext=['txt','html','fb2','epub','docx','rtf','mobi','pdf','cbz'][r['format']-1]
        original=members['oe-fixtures/book.'+ext]
        frozen=['sample.txt','sample.html','sample.fb2','sample.epub','sample.docx','sample.rtf','sample.mobi','pdf-public-text.pdf','comic.cbz'][r['format']-1]
        require(original==(Path('tests/fixtures')/frozen).read_bytes(),'original bound to frozen source fixture')
        final=members['oe-evidence/nine/'+r['hash']+'.'+ext]
        require(final==original and len(final)==r['bytes'] and hashlib.sha256(final).hexdigest()==r['hash'],'actual original/final bytes')
    before={p.removeprefix('oe-evidence/before/'):v for p,v in members.items() if p.startswith('oe-evidence/before/')}
    after={p.removeprefix('oe-evidence/after/'):v for p,v in members.items() if p.startswith('oe-evidence/after/')}
    require(before==after and len(before)==14 and before.get('history.json') and before.get('outbox.txt'),'raw invariant snapshots')
    require(members.get('oe-consumer/original-export-link.map') and b'reader_original_export' in members['oe-consumer/original-export-link.map'],'original module link binding')
    require(members.get('oe-logs/source.txt',b'').decode().strip()==source,'raw source binding')
    return True

def unpack(data):
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        infos=z.infolist();names=[x.filename for x in infos]
        require(len(names)==len(set(names)),'duplicate ZIP member')
        require(all(not n.startswith('/') and '..' not in n.split('/') and '\\' not in n for n in names),'unsafe ZIP path')
        require(sum(x.file_size for x in infos)<512*1024*1024,'unbounded ZIP')
        members={x.filename:z.read(x) for x in infos if not x.is_dir()}
    require('oe-evidence/result.json' in members,'missing report')
    return load(members['oe-evidence/result.json']),members

def rejections(report,members,platform,source,run,attempt):
    passed=[]
    changes=[('wrong_source',lambda r:r.update(source_sha='0'*40)),('wrong_attempt',lambda r:r.update(attempt=attempt+1)),('missing_case',lambda r:r['checks'].pop()),('duplicate_case',lambda r:r['checks'].append(r['checks'][0])),('false_success',lambda r:r.update(accepted=False)),('wrong_platform',lambda r:r.update(platform='other')),('missing_module',lambda r:r['binary_identities'].pop('module'))]
    for name,mutate in changes:
        altered=copy.deepcopy(report);mutate(altered)
        try: validate(altered,members,platform,source,run,attempt)
        except (ValueError,KeyError): passed.append(name)
        else: raise ValueError('verifier accepted '+name)
    for name,member in [('tampered_binary',report['binary_identities']['probe']['member']),('tampered_module',report['binary_identities']['module']['member']),('tampered_original','oe-fixtures/book.txt'),('changed_history','oe-evidence/after/history.json')]:
        altered=dict(members);altered[member]=altered[member]+b'!'
        try: validate(report,altered,platform,source,run,attempt)
        except (ValueError,KeyError): passed.append(name)
        else: raise ValueError('verifier accepted '+name)
    try: load('{"source_sha":"a","source_sha":"b"}')
    except ValueError: passed.append('duplicate_json_key')
    else: raise ValueError('duplicate JSON accepted')
    for name,entries in [('duplicate_zip',[('oe-evidence/result.json',b'{}')]*2),('missing_report',[('x',b'1')]),('unsafe_zip',[('../evil',b'1'),('oe-evidence/result.json',b'{}')])]:
        data=io.BytesIO()
        with zipfile.ZipFile(data,'w') as z:
            for path,value in entries:z.writestr(path,value)
        try: unpack(data.getvalue())
        except ValueError:passed.append(name)
        else:raise ValueError('verifier accepted '+name)
    return passed

def main():
    require(os.environ.get('GITHUB_ACTIONS')=='true','Actions only')
    source=os.environ['GITHUB_SHA'];run=int(os.environ['GITHUB_RUN_ID']);attempt=int(os.environ['GITHUB_RUN_ATTEMPT']);out=Path(sys.argv[1]);out.mkdir(parents=True)
    summary={'accepted':False,'source_sha':source,'run_id':run,'attempt':attempt,'artifacts':[],'jobs':[],'rejections':{},'binaries':{},'failures':[],'system_share_ui':False,'six_devices':False}
    try:
        run_data=fetch(f'actions/runs/{run}');require(run_data['head_sha']==source and run_data['run_attempt']==attempt and run_data['path']=='.github/workflows/reader-original-export.yml','run identity')
        jobs=pages(f'actions/runs/{run}/attempts/{attempt}/jobs','jobs');artifacts=pages(f'actions/runs/{run}/artifacts','artifacts')
        require(len({a['name'] for a in artifacts})==len(artifacts)==len({a['id'] for a in artifacts}),'duplicate artifacts')
        for platform,runner in PLATFORMS:
            name=f'reader-original-export-{platform}-{run}-{attempt}';matching=[a for a in artifacts if a['name']==name];require(len(matching)==1,'unique artifact '+name);a=matching[0]
            matching=[j for j in jobs if j['name']==f'original export ({runner})'];require(len(matching)==1,'unique completed job');j=matching[0]
            require(j['head_sha']==source and j['run_attempt']==attempt and j['status']=='completed' and j['conclusion']=='success','same-source successful producer')
            require(a['workflow_run']['id']==run and a['workflow_run']['head_sha']==source and a['size_in_bytes']>0 and not a['expired'],'artifact source/bytes')
            require(datetime.datetime.fromisoformat(a['expires_at'].replace('Z','+00:00'))>datetime.datetime.now(datetime.timezone.utc),'artifact expiry')
            with tempfile.TemporaryFile() as stream:
                download_artifact_zip(a['id'],stream);stream.seek(0);data=stream.read()
            digest=hashlib.sha256(data).hexdigest();require(len(data)==a['size_in_bytes'] and a['digest']=='sha256:'+digest,'actual ZIP bytes/digest')
            report,members=unpack(data);validate(report,members,platform,source,run,attempt)
            summary['rejections'][platform]=rejections(report,members,platform,source,run,attempt)
            summary['binaries'][platform]=report['binary_identities']
            summary['jobs'].append({k:j[k] for k in ('id','name','status','conclusion','head_sha','run_attempt')})
            summary['artifacts'].append({k:a[k] for k in ('id','name','size_in_bytes','digest','expires_at')})
        summary['accepted']=True
    except Exception as e:summary['failures'].append(repr(e))
    (out/'result.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary),flush=True)
    raise SystemExit(0 if summary['accepted'] else 1)
if __name__=='__main__':main()
