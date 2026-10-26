"""Same-run original ZIP authentication reusing the unchanged D08 downloader."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import traceback
from contract import *
from reuse import module


def main():
    assert os.environ.get('GITHUB_ACTIONS')=='true'
    out=Path('build/d20-summary');out.mkdir(parents=True,exist_ok=True)
    result=dict(verified=False,accepted=False,problems=[])
    try:
        a=module('artifacts')
        run=int(os.environ['GITHUB_RUN_ID']);attempt=int(os.environ['GITHUB_RUN_ATTEMPT']);source=os.environ['GITHUB_SHA']
        current=a.api(f'actions/runs/{run}');assert current['head_sha']==source and current['run_attempt']==attempt
        jobs=a.api(f'actions/runs/{run}/attempts/{attempt}/jobs')['jobs']
        native=[j for j in jobs if j['name']=='d20-native'];assert len(native)==1
        result['jobs']=[{k:j[k] for k in ('id','name','conclusion','status')} for j in jobs]
        proof=a.download(int(os.environ['ARTIFACT_ID']),out/'raw',run,source,os.environ['UPLOAD_DIGEST'].removeprefix('sha256:'))
        result['artifact']=proof
        name=f'reader-wave3-d20-raw-{run}-{attempt}'
        matches=[x for x in a.api(f'actions/runs/{run}/artifacts?per_page=100')['artifacts'] if x['name']==name]
        assert len(matches)==1 and matches[0]['id']==proof['id'] and proof['name']==name
        root=out/'raw';r=json.loads((root/'report.json').read_text(encoding='utf-8'))
        validate(r,source,run,attempt)
        indexed=set()
        for item in r['files']:
            path=item['path'];assert path not in indexed and not Path(path).is_absolute() and '..' not in Path(path).parts
            indexed.add(path);p=root/path
            assert p.stat().st_size==item['bytes'] and a.sha(p)==item['sha256'],path
        assert indexed=={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() and p.name!='report.json'}
        for c in r['configurations']:
            for filename in c['screenshots']:
                assert 'observations/'+filename in indexed and (root/'observations'/filename).read_bytes()[:2]==b'BM'
        negatives=json.loads((root/'negative-controls.json').read_text())
        assert {n['case'] for n in negatives}=={'requested-not-actual','fake-probe','unexecuted-pass','main-window-modal-focus','missing-baseline','missing-more','unrestored-hc','missing-screenshot'}
        assert all(n['rejected'] is True for n in negatives)
        old=json.loads((root/'d08-negative-controls.json').read_text())
        assert len(old)==4 and all(n['rejected'] is True for n in old)
        for label in ('build','prior_driver','audit'):
            reuse=json.loads((root/('reuse-'+label+'.json')).read_text())
            original=subprocess.check_output(['git','show',D08+':'+reuse['historical_path']])
            assert hashlib.sha256(original).hexdigest()==reuse['original_sha256'] and reuse['historical_source']==D08
            adapted=original.decode()
            for before,after in reuse['substitutions']:
                assert adapted.count(before)==1;adapted=adapted.replace(before,after,1)
            assert hashlib.sha256(adapted.encode()).hexdigest()==reuse['adapted_sha256'] and reuse['reverse_projection_exact'] and reuse['old_acceptance_reused'] is False
        identity=json.loads((root/'build-identity.json').read_text())
        assert identity['target_sha']==source and identity['harness_sha']==source and identity['sdk_source']==SDK
        assert identity['installed_libraries'] and identity['actual_product_compilation']
        assert all('EXR_HOST_WORKER_REVIEW' not in c['command'] and 'EXR_READER_PREFS_COMMIT_REVIEW' not in c['command'] for c in identity['actual_product_compilation'])
        cache=(root/'build-identity/host/CMakeCache.txt').read_text()
        assert all('EXR_READER_WINDOWS_'+flag+':BOOL=ON' in cache for flag in ('COMPACT','SEARCH','NAVIGATION','RECORDS','PREFERENCES','IMPORT_ORGANIZE'))
        assert 'EXR_READER_WINDOWS_RAW3:BOOL=OFF' in cache and 'EXR_READER_PREFS_COMMIT_REVIEW_BUILD:BOOL=OFF' in cache
        assert (root/'build-identity/host/windows-host.map').stat().st_size>0
        assert r['program_sha256']==identity['program_sha256']==a.sha(root/'programs/EXReaderProduct.exe')
        result.update(report=r,program_sha256=r['program_sha256'],credential_scan=a.credential_scan(root,a.api('actions/jobs/'+str(native[0]['id'])+'/logs',True)))
        assert native[0]['conclusion']=='success' and os.environ['NATIVE_RESULT']=='success'
        assert r['restoration']['scale_restored']
        assert not any(c.get('driver_exception') for c in r['configurations'])
        assert not any(v['status']=='error' for c in r['configurations'] for v in c['checks'].values())
        result['verified']=True
    except Exception:result['problems'].append(traceback.format_exc())
    (out/'validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('D20_AUTHENTICATION',json.dumps({k:v for k,v in result.items() if k!='report'},ensure_ascii=True),flush=True)
    if 'report' in result:
        r=result['report'];print('ACTUAL_COVERAGE',json.dumps(r['coverage']),flush=True)
        for c in r['configurations']:
            summary=dict(configuration=c['configuration'],execution=c['execution'],checks={k:v['status'] for k,v in c['checks'].items()},
                target_dpi={k:c['checks']['dpi']['actual'].get(k) for k in ('window_dpi','system_dpi','monitor_scale','awareness')},
                capability_reason=c['capability'].get('reason') or c['capability']['request']['reason'],
                contrast_readback=c.get('contrast_readback'),failures={k:v['actual'] for k,v in c['checks'].items() if v['status'] in ('fail','error')},
                actual_transport=c.get('actual_transport'),loaded_modules=len(c.get('loaded_modules',[])),screenshots=len(c['screenshots']))
            samples=c['checks']['contrast']['actual'].get('samples',[])
            summary['contrast_samples']=len(samples);summary['measured_pairs']=sum(s.get('measured_pair_ratio') is not None for s in samples)
            print('CONFIGURATION',json.dumps(summary,ensure_ascii=True),flush=True)
    assert result['verified'],result['problems']


if __name__=='__main__':main()
