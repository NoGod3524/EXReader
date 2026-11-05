"""New receiver ownership; every sealed Mac production file and judge is unchanged."""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[4]
BASE = '44eabdc86b3b84d986f81dbaf8cee92b1829cea8'
SDK = 'edddc463c06ed5731195cdb8f06b2df6dff7699e'
FAMILY = '56793e7ca4f8ecdc5f2d9c3394fce4e201aca275'
ANDROID = '4a04a9cc74dde67f755c87e87b278d63a254a3ac'


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    assert os.environ['GITHUB_REF_NAME'] == 'codex/reader-apple-raw3-android-receive'
    source = os.environ['GITHUB_SHA']; assert git('rev-parse', 'HEAD') == source
    subprocess.run(['git', 'merge-base', '--is-ancestor', BASE, source], cwd=ROOT, check=True)
    allowed = {'.github/workflows/reader-apple-raw3-android-receive.yml',
               'docs/READER-APPLE-RAW3-ANDROID-RECEIVE.md', 'docs/validation/reader-apple-raw3-android-receive.json'}
    changed = git('diff', '--name-only', BASE, source).splitlines()
    assert all(path in allowed or path.startswith('tests/apple_host/raw3/android_receive/') for path in changed), changed
    for path in git('ls-tree', '-r', '--name-only', BASE, '--', 'tests/apple_host/raw3').splitlines():
        assert git('rev-parse', source + ':' + path) == git('rev-parse', BASE + ':' + path)
    protected = ['src', 'include', 'cmake', 'CMakeLists.txt', 'bindings', 'tests/fixtures', 'licenses',
                 'tools/layers.json', '.github/workflows/native.yml', '.github/workflows/reliability.yml']
    assert not git('diff', '--name-only', SDK, source, '--', *protected)
    for name in ('revisions', 'reading-state', 'reading-commands', 'annotation-view', 'commands', 'sync', 'session'):
        assert git('rev-parse', source + ':apps/reader/' + name) == git('rev-parse', FAMILY + ':apps/reader/' + name)
    original = subprocess.check_output(['git', 'show', ANDROID + ':tests/reader_android_raw3/bundle.py'], cwd=ROOT)
    assert (ROOT / 'tests/apple_host/raw3/android_receive/android_bundle.py').read_bytes() == original
    sys.path.insert(0, str(ROOT / 'tools'))
    from check_parallel_integration import fetch
    peer = fetch('actions/runs/40207467982/attempts/1')
    assert peer['head_sha'] == ANDROID and peer['conclusion'] == 'success'
    jobs = fetch('actions/runs/40207467982/attempts/1/jobs?per_page=100')['jobs']
    assert {job['id'] for job in jobs if job['conclusion'] == 'success'} == {121211376063, 121211375764, 121216568574}
    result = {'source_sha': source, 'run_id': os.environ['GITHUB_RUN_ID'], 'attempt': os.environ['GITHUB_RUN_ATTEMPT'],
              'base': BASE, 'sdk_source': SDK, 'family': FAMILY, 'production_changed': False,
              'original_mac_judges_changed': False, 'android_source': ANDROID, 'actual_host_accepted': False}
    # The original native runner reads this guard path; its code is unchanged.
    target = ROOT / 'build/apple-raw3/guard.json'; target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
