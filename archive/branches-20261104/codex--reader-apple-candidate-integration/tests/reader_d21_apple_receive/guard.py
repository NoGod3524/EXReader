# SPDX-License-Identifier: MIT
"""D21 additive owner gate. Original owner guards and tests stay unchanged."""
import json, os, subprocess
from pathlib import Path
assert os.environ.get('GITHUB_ACTIONS') == 'true'
base = '2f215f5793a7344d22db350276ba9f8a07abe86f'
allowed = {'examples/apple/HostAccount.swift', 'examples/apple/HostCatalog.swift',
           'examples/apple/HostModel.swift', 'examples/apple/HostViews.swift',
           '.github/workflows/reader-d21-apple-receive.yml'}
paths = subprocess.check_output(['git','diff','--name-only',base,'HEAD'], text=True).splitlines()
assert all(p in allowed or p.startswith(('tests/reader_d21_apple_receive/', 'docs/handoffs/d21-')) for p in paths), paths
assert subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip() == os.environ['GITHUB_SHA']
Path('build').mkdir(exist_ok=True)
Path('build/d21-admission.json').write_text(json.dumps({'base':base,'source_sha':os.environ['GITHUB_SHA'],
    'run_id':os.environ['GITHUB_RUN_ID'],'attempt':os.environ['GITHUB_RUN_ATTEMPT'],'changed_paths':paths},indent=2))
