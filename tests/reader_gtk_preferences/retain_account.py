# SPDX-License-Identifier: MIT
"""Run unchanged account checks after retiring their private portal FUSE mount."""
import json
import configparser
import hashlib
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
from check_linux_host import Session, command


original = shutil.rmtree
runner_temp = Path(os.environ['RUNNER_TEMP']).resolve()
original_dialog = Session.dialog


def dialog(self, path=None):
    if path is None: return original_dialog(self, path)
    before = self.read()['generation']
    self.key('F1')
    window = command('xdotool', 'search', '--sync', '--onlyvisible', '--name', '^Import book$').splitlines()[-1]
    command('xdotool', 'windowactivate', '--sync', window)
    self.key('ctrl+l');self.paste(str(path))
    expected = hashlib.sha256(str(path).encode()).hexdigest()
    deadline = time.monotonic() + 30

    def observed():
        value = configparser.ConfigParser(interpolation=None);value.read(self.observe)
        return dict(value['native_import'])

    try:
        while time.monotonic() < deadline:
            value = observed()
            if value['visible'] == '1' and value['selected_sha256'] == expected and value['accept_sensitive'] == '1': break
            assert self.process.poll() is None, 'host exited during native selection'
            time.sleep(.05)
        else: raise TimeoutError('native selected file did not become ready: ' + repr(observed()))
        self.key('Return')
        self.wait(lambda value: value['generation'] > before and not value['saving'] and observed()['visible'] == '0',
                  timeout=max(.1, deadline - time.monotonic()))
        print(json.dumps({'single_native_import': Path(path).name, 'selected_file_verified': True,
                          'before_generation': before, 'completed_generation': self.read()['generation']}), flush=True)
    except BaseException:
        print(json.dumps({'native_import_refusal': Path(path).name, 'native': observed(), 'host': self.read()}), flush=True)
        print((self.folder / 'application.log').read_text(errors='replace')[-3000:], flush=True)
        raise


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
Session.dialog = dialog
try:
    runpy.run_path(str(Path(__file__).resolve().parents[1] / 'linux_host/check_account_ui.py'), run_name='__main__')
finally:
    shutil.rmtree = original
    Session.dialog = original_dialog
