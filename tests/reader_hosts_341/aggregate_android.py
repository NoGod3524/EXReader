"""Run the sealed Android130 raw-ZIP judge at its exact new common source."""
import json
import os
from pathlib import Path
import runpy
import subprocess

from guard_android import WORKFLOW,validate_source
import android_candidate

validate_source(write=False)
repo='repos/'+os.environ['GITHUB_REPOSITORY']+'/'
record=json.loads(subprocess.check_output(['gh','api',repo+'actions/runs/'+os.environ['GITHUB_RUN_ID']]))
assert record['path']==WORKFLOW and record['head_sha']==os.environ['GITHUB_SHA']
assert record['run_attempt']==int(os.environ['GITHUB_RUN_ATTEMPT'])
result=runpy.run_path(str(Path(__file__).resolve().parents[1]/'reader_android_page_theme/check_evidence.py'),run_name='__main__')
if android_candidate.active():
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
        reading=read('reading/result.json');sync=read('sync/result.json');owner=read('owner/result.json')
        identity={'source_sha':os.environ['GITHUB_SHA'],'run_id':os.environ['GITHUB_RUN_ID'],'attempt':os.environ['GITHUB_RUN_ATTEMPT']}
        for report in (reading,sync,owner):
            assert all(report.get(k)==v for k,v in identity.items()) and report['accepted'] is True
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
    path.write_text(json.dumps(report,indent=2)+'\n')
