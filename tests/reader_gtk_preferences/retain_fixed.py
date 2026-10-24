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
        before = self.read();trace.append({'key': value, 'before': before})
        original(self, value)
        trace[-1]['after_original_wait'] = self.read()
        if value in ('F3', 'F4', 'F5', 'F6', 'F8', 'F10'):
            trace[-1]['original_wait_saw_dispatch'] = self.read()['generation'] > before['generation']
            self.wait(lambda state: state['generation'] > before['generation'] and not state['saving'])
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
finally:
    if '--output' in sys.argv:
        folder = Path(sys.argv[sys.argv.index('--output') + 1])
        if folder.is_dir(): (folder / 'settings-original-fixed-driver.json').write_text(json.dumps(list(trace), indent=2), encoding='utf-8')
