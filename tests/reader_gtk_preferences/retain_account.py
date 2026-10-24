# SPDX-License-Identifier: MIT
"""Run unchanged account checks after retiring their private portal FUSE mount."""
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess


original = shutil.rmtree
runner_temp = Path(os.environ['RUNNER_TEMP']).resolve()


def mounted(path):
    return str(path) in {line.split()[4] for line in Path('/proc/self/mountinfo').read_text().splitlines()}


def rmtree(path, *args, **kwargs):
    private = Path(path).resolve()
    if kwargs.get('ignore_errors') and private.parent == runner_temp and private.name.startswith('gtk-account-'):
        target = private / 'run/doc'
        if mounted(target):
            helper = shutil.which('fusermount3') or shutil.which('fusermount')
            assert helper, 'private document portal mount requires native FUSE cleanup'
            subprocess.run([helper, '-u', '-z', '--', str(target)], check=True, capture_output=True, text=True, timeout=15)
            assert not mounted(target), 'private document portal mount remains attached'
            print(json.dumps({'private_account_portal_unmounted_before_original_cleanup': True}), flush=True)
    return original(path, *args, **kwargs)


shutil.rmtree = rmtree
try:
    runpy.run_path(str(Path(__file__).resolve().parents[1] / 'linux_host/check_account_ui.py'), run_name='__main__')
finally:
    shutil.rmtree = original
