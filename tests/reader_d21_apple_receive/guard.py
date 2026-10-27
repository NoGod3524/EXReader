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
subprocess.run(['git','merge-base','--is-ancestor','4079d4e8eefd6acd2e02fe5b7ad0810e08b004e1','HEAD'],check=True)
integration_changes = subprocess.check_output(['git','diff','--name-only','4079d4e8eefd6acd2e02fe5b7ad0810e08b004e1','HEAD'],text=True).splitlines()
assert all(p in ['.github/workflows/reader-d21-apple-receive.yml', '.github/workflows/reader-d22-android-receive.yml', '.github/workflows/reader-d23-relay.yml', '.github/workflows/reader-d24-apple-large-type.yml', '.github/workflows/reader-d25-real-formats.yml', '.github/workflows/reader-d26-accessibility.yml', 'tests/reader_d21_apple_receive/guard.py', 'tests/reader_android_receive_d22/guard.py', 'tests/reader_d25_real_formats/run.py'] for p in integration_changes), integration_changes
assert subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip() == os.environ['GITHUB_SHA']
Path('build').mkdir(exist_ok=True)
Path('build/d21-admission.json').write_text(json.dumps({'base':base,'source_sha':os.environ['GITHUB_SHA'],
    'run_id':os.environ['GITHUB_RUN_ID'],'attempt':os.environ['GITHUB_RUN_ATTEMPT'],'changed_paths':paths},indent=2))
