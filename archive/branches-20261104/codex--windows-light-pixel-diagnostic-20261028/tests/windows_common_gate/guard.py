"""Exact authorized current-source route; never relax a historical source grant."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
BASE = 'aefe6107f8f073847f0ed590f0ad9602fa720f3d'
SDK = '5b7a34ee4f1ce38cf3bcd7cf0220575f4ecf7da9'
BRANCH = 'codex/dot-windows-common-gate'
WORKFLOW = '.github/workflows/reader-raw3-common-windows.yml'
MODIFIED = {WORKFLOW, 'tests/reader_raw3_common_runtime/guard.py',
            'tests/reader_raw3_common_runtime/windows_verify.py'}
ADDED = {'tests/windows_common_gate/' + name for name in
         ('guard.py', 'identity.py', 'verify_341.py', 'verify.py', 'authenticate.py', 'diagnose.py')}
ADDED.add('docs/windows-common-gate/README.md')


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def tree(ref):
    return dict((row.split(b'\t', 1)[1].decode(), row.split(b'\t', 1)[0].decode())
                for row in git('ls-tree', '-rz', ref).split(b'\0') if row)


def validate_tree(old, new):
    for path, identity in old.items():
        if path not in MODIFIED and new.get(path) != identity:
            raise RuntimeError('Unauthorized existing source change: ' + path)
    if set(new) - set(old) != ADDED or set(old) - set(new):
        raise RuntimeError('Unexpected current-source wrapper file set')
    for path in MODIFIED | ADDED:
        if new[path].split()[0] != '100644':
            raise RuntimeError('Non-regular wrapper: ' + path)


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only'
    source = git('rev-parse', 'HEAD').decode().strip()
    assert source == os.environ['GITHUB_SHA']
    assert os.environ['GITHUB_REF_NAME'] == BRANCH, 'Explicit current-source route only'
    subprocess.run(['git', 'merge-base', '--is-ancestor', BASE, source], cwd=ROOT, check=True)
    validate_tree(tree(BASE), tree(source))
    assert not git('diff', '--name-only', 'HEAD'), 'Dirty tracked source'
    assert not git('diff', '--name-only', SDK, source, '--', 'src', 'include', 'cmake', 'CMakeLists.txt'), 'Unauthorized SDK'
    assert git('rev-parse', source + ':src/opentype.c').decode().strip() == '8cab9b949b29c73ff54c6f9e5385edd351edf460'
    import yaml
    current_workflow = yaml.safe_load((ROOT / WORKFLOW).read_text(encoding='utf-8'))
    for job, file, old_job in (
        ('current_native', '.github/workflows/windows-txt-forward-scan.yml', 'native'),
        ('current_fonts', '.github/workflows/windows-font-lifecycle.yml', 'windows')):
        original = yaml.safe_load(git('show', BASE + ':' + file))['jobs'][old_job]
        current = current_workflow['jobs'][job]
        for key in ('runs-on', 'timeout-minutes', 'env'):
            assert current[key] == original[key], 'Original runner/budget/environment drift: ' + job
        assert current['steps'][:-1] == original['steps'][:-1], 'Original current-host assertions changed: ' + job
        assert current['if'] == "github.ref_name == 'codex/dot-windows-common-gate'"
        assert current['needs'] == 'preflight'
        assert current['defaults'] == {'run': {'shell': 'pwsh'}}
    if True:  # Refusal controls run before every expensive producer.
        old = tree(BASE); good = tree(source)
        for path in ('src/opentype.c', 'apps/reader/windows-account/main.c', 'tests/reader_windows_account/check_account_ui.py'):
            bad = dict(good); bad[path] = '100644 blob foreign'
            try: validate_tree(old, bad)
            except RuntimeError: pass
            else: raise AssertionError('Source mutation admitted: ' + path)
        print('Current-source production/SDK/original-judge refusal controls passed')
    proof = dict(source_sha=source, run_id=os.environ['GITHUB_RUN_ID'], attempt=os.environ['GITHUB_RUN_ATTEMPT'],
        authorized_common_base=BASE, authorized_sdk_source=SDK, sdk_tree=git('rev-parse', source + ':src').decode().strip(),
        host_tree=git('rev-parse', source + ':apps').decode().strip(), workflow=WORKFLOW,
        all_production_and_original_judges_unchanged=True, accepted=False, complete_product=False)
    out = ROOT / 'build/windows-341-guard'; out.mkdir(parents=True, exist_ok=True)
    (out / 'current-source.json').write_text(json.dumps(proof, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(proof), flush=True)
    if os.name == 'nt':
        # Historical compact judge requires a real >=1060x660 work area.
        # Use the existing supported-mode setup; never alter its UI assertion.
        import sys
        subprocess.run([sys.executable, str(ROOT / 'tests/reader_native_owner_repairs/display.py')], cwd=ROOT, check=True)
        display = ROOT / 'build/native-owner-preflight/display.json'
        (out / 'display.json').write_bytes(display.read_bytes())


if __name__ == '__main__': main()
