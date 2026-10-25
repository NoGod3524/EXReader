"""Common caller identity only; sealed full GTK tests and judges stay exact."""
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
BASE = '090268310347428c58801ed26b28466705700e0a'
COMPOSITION_PREP = 'b5e49d1753a6b4b88811b03fa904fe9447865247'
COMMON_PRODUCTION = '49b2a7c86173181f8f79a760315ddb8ca2312bd1'
SEALED_GTK = '37e592375e365a510293c41b8716e7917a682a7a'
ORIGINAL = '07ebe8786434ef384c97ccdb451242d3c6aee6cb'
SDK = 'edddc463c06ed5731195cdb8f06b2df6dff7699e'
MODULES = 'f680aeaddfb1ecc67ead353554f5b91a5703f72f'
READER_BLOB = '2b6d3fff58c3a83bc0155d9d34bdfb32f51efd78'
WORKFLOW = '.github/workflows/reader-gtk-341-final.yml'
PROTECTED = ['src', 'include', 'cmake', 'CMakeLists.txt', 'tests/fixtures', 'bindings',
             '.github/workflows/native.yml', '.github/workflows/reliability.yml']
git = lambda *args: subprocess.check_output(['git', *args], text=True).strip()


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    source = os.environ['GITHUB_SHA'];assert git('rev-parse', 'HEAD') == source
    for parent in (BASE, COMPOSITION_PREP, COMMON_PRODUCTION, SEALED_GTK, ORIGINAL, SDK, MODULES):
        subprocess.run(['git', 'merge-base', '--is-ancestor', parent, source], check=True)
    allowed = {WORKFLOW, 'tests/reader_hosts_341/guard_gtk.py', 'tests/reader_hosts_341/aggregate_gtk.py',
               'docs/READER-GTK-341-COMMON-PREP.md'}
    changed = git('diff', '--name-only', BASE, source).splitlines();assert set(changed) <= allowed, changed
    for path in PROTECTED + ['licenses']:
        assert git('rev-parse', source + ':' + path) == git('rev-parse', SDK + ':' + path), path
    assert git('rev-parse', source + ':apps/reader/store/001_catalog.sql') == git('rev-parse', ORIGINAL + ':apps/reader/store/001_catalog.sql')
    assert git('rev-parse', source + ':examples/linux/reader.c') == READER_BLOB
    shared = ['tools/build_linux_host.py']
    for module, config in [('batch-import', 'BatchImport'), ('navigation', 'Navigation'),
                           ('reading-state', 'ReadingState'), ('search', 'Search')]:
        shared += ['apps/reader/' + module + '/CMakeLists.txt',
                   'apps/reader/' + module + '/EXReader' + config + 'Config.cmake.in']
    for path in shared:
        assert git('rev-parse', source + ':' + path) == git('rev-parse', MODULES + ':' + path), path
    import yaml
    old = yaml.load(subprocess.check_output(['git', 'show', SEALED_GTK + ':' + WORKFLOW], text=True), Loader=yaml.BaseLoader)
    new = yaml.load((ROOT / WORKFLOW).read_text(), Loader=yaml.BaseLoader)
    old_steps=old['jobs']['account']['steps'];new_steps=new['jobs']['account']['steps']
    assert len(old_steps)==len(new_steps)==31
    for before, after in zip(old_steps,new_steps):
        assert before.get('name')==after.get('name') and before.get('uses')==after.get('uses')
        if before.get('name')=='Require fixed SDK candidate and unchanged legacy tests':
            expected=before['run'].replace('python3 tests/reader_gtk_341_final/guard.py','python3 tests/reader_hosts_341/guard_gtk.py')
            expected=expected.replace('tests/reader_gtk_341_final/*.py','tests/reader_gtk_341_final/*.py tests/reader_hosts_341/guard_gtk.py tests/reader_hosts_341/aggregate_gtk.py')
            assert after['run']==expected
        else:assert before==after,before.get('name',before.get('uses'))
    assert new['jobs']['evidence']['steps'][1]['run']==old['jobs']['evidence']['steps'][1]['run'].replace(
        'python3 tests/reader_gtk_341_final/aggregate.py','python3 tests/reader_hosts_341/aggregate_gtk.py')
    spec=importlib.util.spec_from_file_location('common_gtk_cloud_source_guard',ROOT/'tests/reader_webdav_import/check_guards.py')
    cloud=importlib.util.module_from_spec(spec);spec.loader.exec_module(cloud);controls=cloud.selftest()
    sources=sorted(path for path in (ROOT/'apps/reader/cloud-import').rglob('*') if path.suffix in ('.c','.h'))
    assert len(sources)>=2;joined=''
    for path in sources:
        text=path.read_text();joined+=text
        assert not [pattern for pattern in cloud.FORBIDDEN if re.search(pattern,text) and
                    not (pattern=='Authorization' and path.suffix=='.h')],str(path)
    assert all(re.search(pattern,joined) for pattern,_ in cloud.BOUNDARY)
    assert 'EXR_SIDELOAD_STREAM_LIMIT' in joined and 'EXR_SIDELOAD_MEMORY_LIMIT' in joined
    common=dict(source_sha=source,run_id=os.environ['GITHUB_RUN_ID'],attempt=os.environ['GITHUB_RUN_ATTEMPT'])
    report=dict(**common,accepted=True,ordinary_merge_source=BASE,common_source=ORIGINAL,sdk=SDK,
                shared_version_support=MODULES,common_production=COMMON_PRODUCTION,composition_preparation=COMPOSITION_PREP,
                sealed_gtk_caller=SEALED_GTK,reader_blob=READER_BLOB,retained_original_producer_steps=31,
                production_trees={path:git('rev-parse',source+':'+path) for path in ('apps','examples','extras','tools')},
                shared_version_paths=shared,changed=changed,original_failed_run_retained=40177143143,
                cloud_adapter_source_guard=True,cloud_source_controls=controls)
    build=ROOT/'build';build.mkdir(exist_ok=True)
    (build/'gtk-341-source-guard.json').write_text(json.dumps(report,indent=2)+'\n')
    sys.path.insert(0,str(ROOT/'tests/reader_gtk_record_compatibility'))
    from run import BASE as RECORD_BASE,OLD_HOST,OLD_SDK,NEW_SDK
    assert NEW_SDK==SDK
    for path in PROTECTED:
        assert git('rev-parse',OLD_HOST+':'+path)==git('rev-parse',OLD_SDK+':'+path),path
    pair=dict(**common,accepted=True,base=RECORD_BASE,old_host=OLD_HOST,old_sdk=OLD_SDK,new_sdk=SDK,
              owner_trees={name:git('rev-parse',sha+':examples/linux') for name,sha in [('old',OLD_HOST),('new',source)]},
              protected_trees={name:{path:git('rev-parse',sha+':'+path) for path in PROTECTED}
                               for name,sha in [('old',OLD_SDK),('new',SDK)]},paths=changed,integration_guard=report)
    (build/'gtk-record-compatibility-guard.json').write_text(json.dumps(pair,indent=2)+'\n')
    print(json.dumps(report),flush=True)


if __name__=='__main__':main()
