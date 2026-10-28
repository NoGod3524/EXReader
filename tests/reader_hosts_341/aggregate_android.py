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
    path=Path('build/android-page-theme-summary/summary.json')
    report=json.loads(path.read_text())
    report['candidate_build_identity']=evidence
    path.write_text(json.dumps(report,indent=2)+'\n')
