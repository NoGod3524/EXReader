"""Actions-only retained-profile diagnostic, not a replacement acceptance gate.

Compare the unchanged key driver with per-action busy completion on the exact
failed-run executable. Neither path changes old suite assertions or budgets.
"""
import configparser
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
import traceback

import pyatspi

assert os.environ.get('GITHUB_ACTIONS') == 'true'
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from check_linux_host import Session, command

RUN = '40794101352'
SOURCE = '2f252dd6369211d130ed376c3829974b53da4466'
EXPECTED = {
    'windows-gtk-gtk-first-' + RUN + '-1': (12863458197, 'sha256:33c3db7eb383d7c03cff7fbba2ab0044a9177701d938b21e83380edb2223795b'),
    'sdk342-gtk-identity-' + RUN + '-1': (12863382477, 'sha256:9bc6ba3fc67597e557b97e8d7c1dcc2599c8e9dd8c8044898f3b6354ad6c92bc'),
    'gtk-windows-package-' + RUN + '-1': (12863313796, 'sha256:a9245eb8b887d9f67f8ca590e36b5c8df7a802b64d79bc005118e0684d368345'),
}
folder = ROOT / 'build/collections-diagnostic'
api = json.loads(subprocess.check_output(['gh', 'api', 'repos/' + os.environ['GITHUB_REPOSITORY'] + '/actions/runs/' + RUN + '/artifacts?per_page=100'], text=True))
for name, (artifact_id, digest) in EXPECTED.items():
    matches = [x for x in api['artifacts'] if x['name'] == name]
    assert len(matches) == 1
    value = matches[0]
    assert value['id'] == artifact_id and value['digest'] == digest
    assert value['workflow_run']['head_sha'] == SOURCE and not value['expired']

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def state(path):
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(path)
    return {name: dict(parser[name]) for name in ('host', 'collections') if parser.has_section(name)}

identity = json.loads((folder / 'identity/report.json').read_text())
package = folder / 'package'
program = package / 'bin/exreader-linux'
assert identity['source_sha'] == SOURCE and identity['run_id'] == RUN and identity['attempt'] == '1'
assert identity['program_sha256'] == sha(program) == 'a871a81e22cd32fb2bda041783183998499312979ad9ac63c562f31f05763a0a'
assert subprocess.check_output([str(program), '--version'], text=True).strip() == '3.42.0 1'
archived = folder / 'evidence/current-account'
report = json.loads((archived / 'result.json').read_text())
assert report['source_sha'] == SOURCE and report['run_id'] == RUN and report['attempt'] == '1'
assert report['program_sha256'] == identity['program_sha256'] and not report['accepted']
archived_state = state(archived / 'primary/state.ini')
print('GTK_COLLECTIONS_ARCHIVED ' + json.dumps({'result': report, 'last_state': archived_state}), flush=True)
profile = archived / 'primary/profile'
assert all(not p.is_symlink() for p in profile.rglob('*'))
original_hashes = {str(p.relative_to(profile)): sha(p) for p in profile.rglob('*') if p.is_file()}

def accessibility(pid, rows):
    desktop = pyatspi.Registry.getDesktop(0)
    queue = [desktop[i] for i in range(desktop.childCount) if desktop[i].get_process_id() == pid]
    assert len(queue) == 1, 'Expected one owned AT-SPI application'
    visited = 0
    while queue:
        node = queue.pop(0)
        visited += 1
        assert visited < 3000
        try:
            flags = node.getState()
            if flags.contains(pyatspi.STATE_SHOWING):
                rows.append({'name': node.name, 'role': node.getRoleName(), 'focused': flags.contains(pyatspi.STATE_FOCUSED), 'sensitive': flags.contains(pyatspi.STATE_SENSITIVE)})
            queue.extend(node[i] for i in range(node.childCount))
        except (LookupError, RuntimeError):
            rows.append({'inspection_error': traceback.format_exc()})
            raise

results = []
for trial, mode in enumerate(('original', 'completion', 'completion', 'original', 'original', 'completion')):
    out = folder / ('trial-' + str(trial) + '-' + mode)
    out.mkdir()
    shutil.copytree(profile, out / 'profile')
    (out / 'profile').chmod(0o700)
    for path in (out / 'profile').rglob('*'):
        assert not path.is_symlink()
        path.chmod(0o700 if path.is_dir() else 0o600)
    host = Session(program.resolve(), (package / 'Reader.otf').resolve(), out)
    stop = threading.Event()
    thread = None
    samples = []
    sampler_errors = []
    inputs = []
    result = {'trial': trial, 'mode': mode, 'complete': False, 'inputs': inputs}
    started = time.monotonic()
    try:
        host.launch()
        host.key('F2', 'ctrl+shift+c')
        host.wait(lambda s: state(host.observe).get('collections', {}).get('visible') == '1', timeout=60)
        windows = subprocess.check_output(['xdotool', 'search', '--onlyvisible', '--all', '--pid', str(host.process.pid), '--name', '^Library collections$'], text=True).split()
        assert len(windows) == 1
        command('xdotool', 'windowactivate', '--sync', windows[0])
        # Establish the genuine Tags view using native controls only.
        for key in ('alt+t', 'Home', 'Down'):
            host.key(key)
            host.wait(lambda s: True, timeout=30)
        host.wait(lambda s: state(host.observe)['collections']['kind'] == '1', timeout=60)
        host.key('alt+g', 'Home')
        host.wait(lambda s: state(host.observe)['collections']['selected_name'] == 'Cloud tag', timeout=60)
        started = time.monotonic()
        def sample():
            previous = None
            try:
                while not stop.is_set():
                    value = state(host.observe)
                    if value != previous:
                        samples.append({'elapsed': time.monotonic() - started, 'state': value})
                        previous = value
                    stop.wait(.01)
            except Exception:
                sampler_errors.append(traceback.format_exc())
                stop.set()
        thread = threading.Thread(target=sample, daemon=True)
        thread.start()
        # The original path uses the exact retained driver's 150 ms/key pacing.
        for key in ('alt+t', 'Home', 'Down', 'Down'):
            inputs.append({'key': key, 'elapsed': time.monotonic() - started, 'before': state(host.observe)})
            host.key(key)
            if mode == 'completion':
                host.wait(lambda s: True, timeout=30)
            inputs[-1]['after'] = state(host.observe)
        reached = True
        try:
            host.wait(lambda s: state(host.observe)['collections']['kind'] == '2', timeout=60)
        except TimeoutError:
            reached = False
        result.update(reached_series=reached, elapsed=time.monotonic() - started, final_state=state(host.observe))
        result['accessibility'] = []
        accessibility(host.process.pid, result['accessibility'])
        command('import', '-window', windows[0], out / 'final.png')
        assert not sampler_errors, sampler_errors
        result['complete'] = True
    except Exception:
        result['error'] = traceback.format_exc()
        raise
    finally:
        stop.set()
        if thread:
            thread.join(timeout=5)
            if thread.is_alive():
                sampler_errors.append('Observer thread did not stop within 5 seconds')
        result['sampler_errors'] = sampler_errors
        result['complete'] = result['complete'] and not sampler_errors
        (out / 'result.json').write_text(json.dumps(result, indent=2))
        (out / 'observations.json').write_text(json.dumps(samples, indent=2))
        print('GTK_COLLECTIONS_TRIAL ' + json.dumps(result), flush=True)
        if host.process and host.process.poll() is None:
            host.process.kill()
            host.process.wait(timeout=15)
        if host.log and not host.log.closed:
            host.log.close()
    assert result['complete'], result
    results.append(result)

assert original_hashes == {str(p.relative_to(profile)): sha(p) for p in profile.rglob('*') if p.is_file()}
summary = {'diagnostic_only': True, 'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'], 'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'pinned_source_sha': SOURCE, 'pinned_run': RUN, 'program_sha256': identity['program_sha256'], 'artifact_identities': EXPECTED, 'archived_state': archived_state, 'trials': results}
(folder / 'summary.json').write_text(json.dumps(summary, indent=2))
print('GTK_COLLECTIONS_DIAGNOSTIC_RESULT ' + json.dumps(summary), flush=True)
