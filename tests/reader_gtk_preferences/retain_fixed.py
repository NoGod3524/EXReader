# SPDX-License-Identifier: MIT
"""Run the unchanged fixed UI verifier, retaining real keys/state on refusal."""
from collections import deque
import json
from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'tests/linux_host'))
from check_linux_host import Session

original = Session.key
trace = deque(maxlen=45)
instances = []


def key(self, *values):
    if self not in instances: instances.append(self)
    for value in values:
        trace.append({'key': value, 'before': self.read()})
        original(self, value)
        trace[-1]['after'] = self.read()


Session.key = key
try:
    runpy.run_path(str(ROOT / 'tests/linux_host/check_fixed_ui.py'), run_name='__main__')
except BaseException:
    print(json.dumps({'original_fixed_ui_key_trace': list(trace)}), flush=True)
    for instance in instances:
        path = instance.folder / 'application.log'
        if path.exists(): print(path.read_text(errors='replace')[-16000:], flush=True)
    raise
