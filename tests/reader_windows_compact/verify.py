"""Authenticate original OFF regressions and the independent actual compact binary."""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import zipfile
from contract import selftest,validate

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
from check_parallel_integration import fetch,download_artifact_zip,require
WORKFLOW='.github/workflows/reader-windows-compact.yml'


def main():
    assert os.environ.get('GITHUB_ACTIONS')=='true'
    controls=selftest()
    if '--self-test' in sys.argv:
        print('compact protocol refusals:',controls);return
    source,run,attempt=os.environ['GITHUB_SHA'],int(os.environ['GITHUB_RUN_ID']),int(os.environ['GITHUB_RUN_ATTEMPT'])
    result=dict(accepted=False,source_sha=source,run_id=run,attempt=attempt,problems=[],protocol_rejections=controls,
                scope='Windows independent compact native UI plus complete original default-OFF regression',
                complete_product=False,performance_accepted=False)
    out=ROOT/'build/compact-summary';out.mkdir(parents=True,exist_ok=True)
    try:
        sys.path.insert(0,str(ROOT/'tests/reader_windows_341'))
        spec=importlib.util.spec_from_file_location('original_full_windows341',ROOT/'tests/reader_windows_341/verify.py')
        original=importlib.util.module_from_spec(spec);spec.loader.exec_module(original)
        original.WORKFLOW=WORKFLOW;original.main()
        meta=fetch('actions/artifacts/'+os.environ['ARTIFACT_ID'])
        require(meta['workflow_run']['head_sha']==source and meta['workflow_run']['id']==run and not meta['expired'],'foreign compact raw artifact')
        with tempfile.TemporaryFile() as stream:
            download_artifact_zip(meta['id'],stream);stream.seek(0);raw=stream.read()
        require(len(raw)==meta['size_in_bytes'] and 'sha256:'+hashlib.sha256(raw).hexdigest()==meta['digest'],'raw ZIP differs')
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            require(len(archive.namelist())==len(set(archive.namelist())),'duplicate ZIP member')
            binary=hashlib.sha256(archive.read('compact-host/EXReaderProduct.exe')).hexdigest()
            report=json.loads(archive.read('compact-ui/report.json'));validate(report,source,run,attempt,binary)
            cache=archive.read('compact-host/CMakeCache.txt').decode('utf-8')
            require('EXR_READER_WINDOWS_COMPACT:BOOL=ON' in cache and 'EXR_SDK_VERSION:STRING=3.41.0' in cache,'wrong actual compact build')
            require(set(report['screenshots'])=={'default-library.bmp','txt-reading.bmp','epub-reading.bmp','pdf-reading.bmp','cbz-reading.bmp','small-reading.bmp'},'missing actual UI screenshots')
            for name,record in report['screenshots'].items():
                image=archive.read('compact-ui/'+name)
                require(image.startswith(b'BM') and len(image)==record['bytes'] and hashlib.sha256(image).hexdigest()==record['sha256'],'actual native screenshot differs')
            require(binary!=json.loads(archive.read('windows-341-identity.json'))['files']['production']['sha256'],'compact and original OFF host substituted')
        result.update(accepted=True,compact_checks=report['count'],compact_program_sha256=binary,
            original_OFF_full_F3_and_atomic13_accepted=True,artifact={key:meta[key] for key in ('id','name','size_in_bytes','digest','expires_at')})
    except Exception as error:result['problems'].append(type(error).__name__+': '+str(error))
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result),flush=True);require(result['accepted'],'compact candidate refused')


if __name__=='__main__':main()
