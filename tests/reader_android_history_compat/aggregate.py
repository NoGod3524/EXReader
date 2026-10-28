"""Run the sealed Android130 raw-ZIP judge at its exact new common source."""
import json
import os
from pathlib import Path
import runpy
import subprocess

import sys
sys.path.insert(0,'tests/reader_hosts_341')
import android_candidate
runpy.run_path('tests/reader_android_history_compat/guard.py',run_name='__main__')
WORKFLOW='.github/workflows/reader-android-history-compat.yml' 
repo='repos/'+os.environ['GITHUB_REPOSITORY']+'/'
record=json.loads(subprocess.check_output(['gh','api',repo+'actions/runs/'+os.environ['GITHUB_RUN_ID']]))
assert record['path']==WORKFLOW and record['head_sha']==os.environ['GITHUB_SHA']
assert record['run_attempt']==int(os.environ['GITHUB_RUN_ATTEMPT'])
result=runpy.run_path(str(Path('tests/reader_android_page_theme/check_evidence.py')),run_name='__main__')
if True:
    evidence=android_candidate.verify_zip(result['body'])
    import hashlib, io, zipfile
    jobs=json.loads(subprocess.check_output(['gh','api',repo+'actions/runs/'+os.environ['GITHUB_RUN_ID']+'/attempts/'+os.environ['GITHUB_RUN_ATTEMPT']+'/jobs?per_page=100']))['jobs']
    current,=[job for job in jobs if job['name']=='Android current 19 reading, 16 sync and 18 owner checks']
    assert current['head_sha']==os.environ['GITHUB_SHA'] and current['status']=='completed' and current['conclusion']=='success'
    items=json.loads(subprocess.check_output(['gh','api',repo+'actions/runs/'+os.environ['GITHUB_RUN_ID']+'/artifacts?per_page=100']))['artifacts']
    expected='android-current-130-'+os.environ['GITHUB_RUN_ID']+'-'+os.environ['GITHUB_RUN_ATTEMPT']
    artifact,=[item for item in items if item['name']==expected]
    assert artifact['workflow_run']['id']==int(os.environ['GITHUB_RUN_ID']) and artifact['workflow_run']['head_sha']==os.environ['GITHUB_SHA']
    from datetime import datetime,timezone
    assert artifact['expired'] is False and 0<artifact['size_in_bytes']<=512*1024**2
    assert datetime.fromisoformat(artifact['expires_at'].replace('Z','+00:00'))>datetime.now(timezone.utc)
    data=subprocess.check_output(['gh','api',repo+'actions/artifacts/'+str(artifact['id'])+'/zip'])
    assert len(data)==artifact['size_in_bytes'] and 'sha256:'+hashlib.sha256(data).hexdigest()==artifact['digest']
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names=archive.namelist();assert len(names)==len(set(names))
        def read(suffix):
            name,=[name for name in names if name.endswith(suffix)]
            return json.loads(archive.read(name))
        reading=read('reading/result.json');sync=read('sync/result.json');owner=read('owner/result.json');compat=read('history-compat/result.json')
        identity={'source_sha':os.environ['GITHUB_SHA'],'run_id':os.environ['GITHUB_RUN_ID'],'attempt':os.environ['GITHUB_RUN_ATTEMPT']}
        for report in (reading,sync,owner,compat):
            assert all(report.get(k)==v for k,v in identity.items()) and report['accepted'] is True
        assert compat['checks']==8 and compat['report']['passed'] is True
        raw_name,=[name for name in names if name.endswith('history-compat/raw-report.json')]
        raw=archive.read(raw_name)
        assert hashlib.sha256(raw).hexdigest()==compat['report_sha256'] and json.loads(raw)==compat['report']
        assert len(compat['report']['observations'])==8 and all(row['pass'] is True for row in compat['report']['observations'])
        apk_identity=read('apks/identity.json')
        assert all(apk_identity[k]==v for k,v in identity.items())
        assert len(apk_identity['apks'])==5 and len({row['signer_sha256'] for row in apk_identity['apks']})==1
        for row in apk_identity['apks']:
            entry,=[name for name in names if name.endswith('apks/'+row['name'])]
            assert hashlib.sha256(archive.read(entry)).hexdigest()==row['sha256']
        assert reading['checks']==19 and sync['checks']==16 and owner['checks']==18 and owner['process_phases']==2
        added={'saved_bookmark_survives_cancelled_refresh','saved_bookmark_survives_failed_refresh','conflict_remains_reachable_with_saved_bookmarks'}
        observed={row['name'] for phase in reading['phases'] for row in phase['checks'] if row['pass'] is True}
        assert added <= observed
        assert all(phase.get('expected_sdk_version')=='3.41.0' for phase in sync['phases'])
    evidence['current_checks']=dict(reading=19,sync=16,owner=18,process_phases=2,job=current['id'],
        artifact={key:artifact[key] for key in ('id','name','size_in_bytes','digest','expires_at')})
    path=Path('build/android-page-theme-summary/summary.json')
    report=json.loads(path.read_text())
    report['candidate_build_identity']=evidence
    report['history_compatibility']=compat
    path.write_text(json.dumps(report,indent=2)+'\n')
