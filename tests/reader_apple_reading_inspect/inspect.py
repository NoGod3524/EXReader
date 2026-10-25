"""Read-only cloud inspection. Never relabel or rerun an original failed test."""
import hashlib
import io
import json
import os
from pathlib import Path,PurePosixPath
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
from check_parallel_integration import fetch,download_artifact_zip,require
RUN=40195374154
SOURCE='25bc0c67971f81491f50e0a3caaaf7e509bb7e35'
CASE='testFixedCbzAndPdfRealPointRecords'


def main():
    global RUN, CASE
    target = sys.argv[1] if len(sys.argv) == 2 else 'records'
    require(target in ('records', 'fast-import', 'theme-iphone'), 'unknown diagnostic target')
    workflow = '.github/workflows/reader-apple-reading-records.yml'
    artifact_name = 'apple-reading-ui-iphone-'
    bundle_name = 'iphone.xcresult'
    if target != 'records':
        RUN = 40203445172
        workflow = '.github/workflows/reader-apple-page-theme.yml'
        artifact_name = 'apple-theme-fast-import-' if target == 'fast-import' else 'apple-theme-ui-iphone-'
        CASE = 'testFastOwnerImportPublishesWithoutBusyTransition' if target == 'fast-import' else 'test'
        bundle_name = 'ipad.xcresult' if target == 'fast-import' else 'theme.xcresult'
    require(os.environ.get('GITHUB_ACTIONS')=='true','Actions only')
    out=ROOT/'build/apple-reading-original-inspect';out.mkdir(parents=True,exist_ok=False)
    result=dict(accepted=False,diagnostic_only=True,original_source=SOURCE,original_run=RUN,original_attempt=1,
                diagnostic_source=os.environ['GITHUB_SHA'],original_failure_preserved=True,commands=[])
    run=fetch('actions/runs/'+str(RUN))
    require(run['head_sha']==SOURCE and run['run_attempt']==1 and run['status']=='completed' and run['conclusion']=='failure' and
            run['path']==workflow,'original run differs')
    rows=fetch('actions/runs/'+str(RUN)+'/artifacts?per_page=100')['artifacts']
    meta,=[row for row in rows if row['name']==artifact_name+str(RUN)+'-1']
    require(not meta['expired'] and meta['workflow_run']['head_sha']==SOURCE and meta['workflow_run']['id']==RUN and
            0<meta['size_in_bytes']<=512*1024**2,'original artifact differs')
    with tempfile.TemporaryFile() as stream:
        download_artifact_zip(meta['id'],stream);stream.seek(0);raw=stream.read()
    require(len(raw)==meta['size_in_bytes'] and 'sha256:'+hashlib.sha256(raw).hexdigest()==meta['digest'],'original ZIP differs')
    result['artifact']={key:meta[key] for key in ('id','name','size_in_bytes','digest','expires_at')}
    extracted=out/'original';extracted.mkdir()
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        require(len(archive.namelist())==len(set(archive.namelist())),'duplicate member')
        for info in archive.infolist():
            path=PurePosixPath(info.filename)
            require(not path.is_absolute() and '..' not in path.parts and '\\' not in info.filename and
                    (info.external_attr>>16)&0o170000!=0o120000,'unsafe original ZIP member')
            if not (any(part.endswith('.xcresult') for part in path.parts) or path.suffix in ('.log', '.json', '.txt')):continue
            destination=extracted.joinpath(*path.parts)
            if info.is_dir():destination.mkdir(parents=True,exist_ok=True)
            else:
                require(info.file_size<=256*1024**2,'member too large')
                destination.parent.mkdir(parents=True,exist_ok=True)
                with archive.open(info) as source,destination.open('wb') as output:shutil.copyfileobj(source,output)
    if target != 'records':
        for path in extracted.rglob('*'):
            if path.is_file() and path.suffix in ('.json', '.log', '.txt') and not any(part.endswith('.xcresult') for part in path.parts) and path.stat().st_size <= 2*1024**2:
                print('ORIGINAL-RAW-TEXT', path.relative_to(out).as_posix(), path.read_text(errors='replace')[-24000:], flush=True)
    bundles=list(extracted.rglob(bundle_name))
    if not bundles and target == 'theme-iphone':
        result['original_xcresult_absent'] = True
        (out/'report.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(result),flush=True)
        return
    require(len(bundles)==1,'original result bundle missing or ambiguous')
    bundle=bundles[0]
    def command(name,*args):
        response=subprocess.run(['xcrun','xcresulttool',*map(str,args)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=120)
        body=response.stdout.decode('utf-8',errors='replace');(out/(name+'.txt')).write_text(body,encoding='utf-8')
        result['commands'].append(dict(name=name,status=response.returncode,bytes=len(response.stdout)))
        print(name,body[:24000],flush=True)
        return body if response.returncode==0 else None
    command('summary','get','test-results','summary','--path',bundle,'--format','json')
    tests=command('tests','get','test-results','tests','--path',bundle,'--format','json')
    identifiers=[]
    def walk(value):
        if isinstance(value,dict):
            if CASE in str(value.get('name','')):
                print('FAILED-CASE-NODE',json.dumps(value),flush=True)
                identifiers.extend(str(value[key]) for key in ('nodeIdentifier','testIdentifier','identifier') if value.get(key))
            for child in value.values():walk(child)
        elif isinstance(value,list):
            for child in value:walk(child)
    if tests:walk(json.loads(tests))
    for index,identifier in enumerate(dict.fromkeys(identifiers or ['ReadingUITests/'+CASE+'()'])):
        command('activities-'+str(index),'get','test-results','activities','--path',bundle,'--test-id',identifier,'--format','json')
    attachments=out/'attachments'
    command('attachments-export','export','attachments','--path',bundle,'--output-path',attachments)
    trace=[]
    if attachments.exists():
        for path in attachments.rglob('*'):
            if path.is_file() and path.suffix in ('.txt','.json','.log') and path.stat().st_size<=2*1024**2:
                text=path.read_text(encoding='utf-8',errors='replace')
                if any(key in text for key in ('fixture-request','import-request','rejected-unready','committed','library.title')):
                    trace.append(path.relative_to(out).as_posix());print('TRACE-ATTACHMENT',str(path),text[:24000],flush=True)
    result['trace_text_attachments']=trace
    result['trace_absence_is_not_proof_of_missing_import_callback']=True
    (out/'report.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result),flush=True)


if __name__=='__main__':main()
