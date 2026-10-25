"""Exact ordinary-merge production pin; original package guards stay sealed."""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
MERGED = '58eda15d886268e054f2211a837b4032e946e165'
COMMON = '07ebe8786434ef384c97ccdb451242d3c6aee6cb'
SDK = 'edddc463c06ed5731195cdb8f06b2df6dff7699e'
MODULES = 'f680aeaddfb1ecc67ead353554f5b91a5703f72f'
DELIVERIES = ['21fd7a671ed82d157b66b34c1a9dcc179b80c8a4', 'b2c798af1a0884180062ac63c017afef77d1ebf1',
              '8325f9e1f80ef12193bee0b9eca4d4bac8c4c3be', '5f836197b0facfcbafa7e9f6eacf414cf504d0f9']
PROTECTED = ['src', 'include', 'cmake', 'CMakeLists.txt', 'tests/fixtures', 'bindings',
             '.github/workflows/native.yml', '.github/workflows/reliability.yml']
git = lambda *args: subprocess.check_output(['git', *args], text=True).strip()


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    source = os.environ['GITHUB_SHA'];assert git('rev-parse', 'HEAD') == source
    for parent in [MERGED, COMMON, SDK, MODULES, *DELIVERIES]:
        subprocess.run(['git', 'merge-base', '--is-ancestor', parent, source], check=True)
    allowed = ('tests/reader_gtk_341_final/', '.github/workflows/reader-gtk-341-final.yml',
               'docs/READER-GTK-341-FINAL.md', 'docs/validation/reader-gtk-341-final.json')
    changed = git('diff', '--name-only', MERGED, source).splitlines()
    assert all(any(path.startswith(item) if item.endswith('/') else path == item for item in allowed)
               for path in changed), changed
    for path in PROTECTED + ['licenses']:
        assert git('rev-parse', source + ':' + path) == git('rev-parse', SDK + ':' + path), path
    shared = ['tools/build_linux_host.py']
    for module, config in [('batch-import', 'BatchImport'), ('navigation', 'Navigation'),
                           ('reading-state', 'ReadingState'), ('search', 'Search')]:
        shared += ['apps/reader/' + module + '/CMakeLists.txt',
                   'apps/reader/' + module + '/EXReader' + config + 'Config.cmake.in']
    for path in shared:
        assert git('rev-parse', source + ':' + path) == git('rev-parse', MODULES + ':' + path), path
    import yaml
    original_workflow = yaml.load(subprocess.check_output(['git', 'show', DELIVERIES[0] + ':.github/workflows/reader-gtk-record-compatibility.yml'], text=True), Loader=yaml.BaseLoader)
    current_workflow = yaml.load((ROOT / '.github/workflows/reader-gtk-341-final.yml').read_text(), Loader=yaml.BaseLoader)
    original_steps = original_workflow['jobs']['account']['steps'];current_steps = current_workflow['jobs']['account']['steps']
    assert len(original_steps) == len(current_steps)
    for old, new in zip(original_steps, current_steps):
        assert old.get('name') == new.get('name') and old.get('uses') == new.get('uses')
        if old.get('name') == 'Require fixed SDK candidate and unchanged legacy tests':
            assert 'python3 tests/reader_gtk_341_final/guard.py' in new['run']
        elif old.get('name') == 'Preserve source-bound evidence and original logs without credentials or TLS private keys':
            assert old['with']['if-no-files-found'] == new['with']['if-no-files-found']
            assert set(old['with']['path'].splitlines()).issubset(set(new['with']['path'].splitlines()))
        else:
            assert old == new, old.get('name', old.get('uses'))
    common = dict(source_sha=source, run_id=os.environ['GITHUB_RUN_ID'], attempt=os.environ['GITHUB_RUN_ATTEMPT'])
    report = dict(**common, accepted=True, ordinary_merge_source=MERGED, common_source=COMMON,
                  sdk=SDK, shared_version_support=MODULES, deliveries=DELIVERIES,
                  all_existing_production_tests_and_guards_unchanged_after_merge=True,
                  retained_original_producer_steps=len(original_steps),
                  production_trees={path: git('rev-parse', source + ':' + path) for path in ('apps', 'examples', 'extras', 'tools')},
                  shared_version_paths=shared, changed=changed, original_failed_run_retained=40177143143)
    build = ROOT / 'build';build.mkdir(exist_ok=True)
    (build / 'gtk-341-source-guard.json').write_text(json.dumps(report, indent=2) + '\n')
    sys.path.insert(0, str(ROOT / 'tests/reader_gtk_record_compatibility'))
    from run import BASE, OLD_HOST, OLD_SDK, NEW_SDK
    assert NEW_SDK == SDK
    for path in PROTECTED:
        assert git('rev-parse', OLD_HOST + ':' + path) == git('rev-parse', OLD_SDK + ':' + path), path
    compatibility = dict(**common, accepted=True, base=BASE, old_host=OLD_HOST, old_sdk=OLD_SDK, new_sdk=SDK,
        owner_trees={name: git('rev-parse', sha + ':examples/linux') for name, sha in [('old', OLD_HOST), ('new', source)]},
        protected_trees={name: {path: git('rev-parse', sha + ':' + path) for path in PROTECTED}
                         for name, sha in [('old', OLD_SDK), ('new', SDK)]}, paths=changed,
        integration_guard=report)
    (build / 'gtk-record-compatibility-guard.json').write_text(json.dumps(compatibility, indent=2) + '\n')
    print(json.dumps(report), flush=True)


if __name__ == '__main__':main()
