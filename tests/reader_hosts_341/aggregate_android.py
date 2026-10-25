"""Run the sealed Android130 raw-ZIP judge at its exact new common source."""
import json
import os
from pathlib import Path
import runpy
import subprocess

from guard_android import WORKFLOW,validate_source

validate_source(write=False)
repo='repos/'+os.environ['GITHUB_REPOSITORY']+'/'
record=json.loads(subprocess.check_output(['gh','api',repo+'actions/runs/'+os.environ['GITHUB_RUN_ID']]))
assert record['path']==WORKFLOW and record['head_sha']==os.environ['GITHUB_SHA']
assert record['run_attempt']==int(os.environ['GITHUB_RUN_ATTEMPT'])
runpy.run_path(str(Path(__file__).resolve().parents[1]/'reader_android_page_theme/check_evidence.py'),run_name='__main__')
