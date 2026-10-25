"""Real common-source gate; sealed GTK source guards are never executed or claimed."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
BASE='1a6d98ed613c61ffea4267f01f83e2c49b1c02f6'
PRODUCTION=BASE
GTK_PIN='69c60ace09f7f995e92c55494b1bdf80e6474621'
GTK_TESTED='1cf5ab55b6a92c471af69a8e68b0e9d0c5e3fe6e'
SDK='edddc463c06ed5731195cdb8f06b2df6dff7699e'
RAW='0889f7d1e9a537c6c1b05456547e016b26e1cd85'
CODEC='4ad6f956a9ebe33f50a5f341b51b24bd538e871a'
ORIGINAL='.github/workflows/reader-gtk-raw3.yml'
WORKFLOW='.github/workflows/reader-raw3-common-gtk.yml'
GUARD_KIND='raw3-common-gtk-v1'
ON_STEP='Build and verify compact ON before the complete original OFF regressions'
NEW_FILES={WORKFLOW,*('tests/reader_raw3_common_gtk/'+name for name in
    ('guard.py','test_guard.py','retained.py','collect.py','README.md'))}
GTK_PIN_PATHS=('examples/linux','apps/reader/desktop/CMakeLists.txt',
    'apps/reader/desktop/reading_capture_bytes.h',ORIGINAL,
    'tests/reader_gtk_raw3','tests/reader_gtk_compact','tests/reader_gtk_341_final',
    'tests/reader_gtk_record_compatibility','tests/reader_gtk_page_background')
RAW_MODULES=('revisions','commands','desktop-metadata','reading-state',
    'reading-commands','annotation-view','sync','session')
SELF_TEST_STEP='''      - name: Check common GTK source projection and new guard refusal cases in Actions
        run: |
          python3 -m py_compile tests/reader_raw3_common_gtk/*.py
          python3 tests/reader_raw3_common_gtk/test_guard.py
'''


def require(condition,message):
    if not condition:raise RuntimeError(message)


def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT)


def object_id(ref,path):return git('rev-parse',ref+':'+path).decode().strip()


def tree(ref):
    result={}
    for row in git('ls-tree','-rz',ref).split(b'\0'):
        if row:
            metadata,path=row.split(b'\t',1);result[path.decode('utf-8')]=metadata.decode('ascii')
    return result


def validate_tree(baseline,current,extensions=None):
    for path,identity in baseline.items():
        require(current.get(path)==identity,'Existing common-source blob or mode changed: '+path)
    added=set(current)-set(baseline)
    allowed=NEW_FILES|set(extensions or ())
    require(added==allowed,'Common GTK wrapper file set differs: '+repr(sorted(added)))
    require(all(current[path].split()[0]=='100644' for path in added),'Common GTK wrapper mode differs')


def project_workflow(text):
    substitutions=(
      ('name: Common raw3 GTK actual host and complete retained scopes',
       'name: Explicit GTK raw3 actual host and complete retained scopes',1),
      ('branches: [codex/reader-raw3-common-integration]',
       'branches: [codex/reader-gtk-raw3-candidate]',1),
      ('python3 tests/reader_raw3_common_gtk/guard.py','python3 tests/reader_gtk_raw3/guard.py',2),
      ('python3 tests/reader_raw3_common_gtk/retained.py','python3 tests/reader_gtk_raw3/retained.py',3),
      ('python3 tests/reader_raw3_common_gtk/collect.py','python3 tests/reader_gtk_raw3/collect.py',1),
      (SELF_TEST_STEP,'',1),
    )
    for replacement,original,count in substitutions:
        require(text.count(replacement)==count,'Workflow projection substitution differs: '+replacement)
        text=text.replace(replacement,original)
    return text


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,ROOT/path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def off_projection(source):
    # Only the sealed pure conditional-projection helper is reused; no old main runs.
    return load('sealed_gtk_raw3_projection_helper','tests/reader_gtk_raw3/guard.py').off_projection(source)


def check_source(source):
    require(git('rev-parse','HEAD').decode().strip()==source,'Checkout and actual Actions source differ')
    for parent in (BASE,GTK_PIN,GTK_TESTED,SDK,RAW,CODEC):
        subprocess.run(['git','merge-base','--is-ancestor',parent,source],cwd=ROOT,check=True)
    # Read only the reviewed composition's pure constants. Do not configure its
    # historical adapters or replace this process's guard module registration.
    composition=load('common_gtk_extensions_registry','tests/reader_raw3_common_runtime/combined.py')
    require(composition.BASE==BASE,'Composition extension registry uses another baseline')
    extensions=composition.EXTENSIONS
    require(isinstance(extensions,(set,frozenset)) and all(type(path) is str for path in extensions),
            'Composition extension registry is not an exact path set')
    validate_tree(tree(BASE),tree(source),extensions=extensions)
    subprocess.run(['git','diff','--exit-code',source,'--','.'],cwd=ROOT,check=True)
    for path in GTK_PIN_PATHS:
        require(object_id(source,path)==object_id(GTK_PIN,path),'Sealed GTK leaf changed: '+path)
    sealed=load('sealed_gtk_guard_constants','tests/reader_gtk_341_final/guard.py')
    for path in sealed.PROTECTED+['licenses']:
        require(object_id(source,path)==object_id(SDK,path),'Frozen SDK source changed: '+path)
    for module in RAW_MODULES:
        path='apps/reader/'+module
        require(object_id(source,path)==object_id(RAW,path),'Sealed raw family changed: '+path)
    require(object_id(source,'apps/reader/desktop/reading_capture_bytes.h')==
            object_id(CODEC,'apps/reader/desktop/reading_capture_bytes.h'),'Sealed capture codec changed')
    original=git('show',GTK_PIN+':'+ORIGINAL)
    require(original==git('show',BASE+':'+ORIGINAL),'Common baseline changed the original GTK workflow')
    current=git('show',source+':'+WORKFLOW).decode('utf-8')
    require(project_workflow(current).encode('utf-8')==original,
            'Original GTK jobs, steps, suites, options, judges or budgets changed')
    return sealed,hashlib.sha256(original).hexdigest()


def validate_header(value,source,run,attempt):
    require(value.get('guard_kind')==GUARD_KIND and type(value.get('guard_schema')) is int and
            value.get('guard_schema')==1,'Wrong common GTK guard kind')
    require(value.get('source_sha')==source and str(value.get('run_id'))==str(run) and
            str(value.get('attempt'))==str(attempt),'Foreign common GTK guard identity')
    require(value.get('composition_source')==BASE and value.get('gtk_source_pin')==GTK_PIN and
            value.get('gtk_tested_source')==GTK_TESTED,'Wrong actual common baseline or sealed GTK leaf')
    require(value.get('workflow')==WORKFLOW and value.get('original_workflow')==ORIGINAL,'Wrong actual common GTK workflow')
    require(value.get('accepted') is True and value.get('source_guard_passed') is True and
            value.get('runtime_accepted') is False and value.get('old_guard_executed') is False,
            'Source-only gate status or old-guard claim differs')
    require(value.get('all_existing_blobs_and_modes_unchanged') is True and
            value.get('original_gtk_workflow_projection_exact') is True,'Common GTK source projection missing')
    require(value.get('allowed_new_files')==sorted(NEW_FILES),'Common GTK wrapper allowance differs')


def validate_source_report(value,source,run,attempt):
    validate_header(value,source,run,attempt)
    sealed,digest=check_source(source)
    require(value.get('baseline_tree')==git('rev-parse',BASE+'^{tree}').decode().strip() and
            value.get('original_workflow_sha256')==digest,'Common GTK Git baseline proof differs')
    require(value.get('ordinary_merge_source')==BASE and value.get('common_source')==sealed.COMMON and
            value.get('sdk')==SDK and value.get('shared_version_support')==sealed.MODULES and
            value.get('deliveries')==sealed.DELIVERIES and value.get('original_failed_run_retained')==40177143143,
            'Common GTK compatibility metadata differs')
    expected={path:object_id(source,path) for path in ('apps','examples','extras','tools')}
    require(value.get('production_trees')==expected and
            all(identity==object_id(BASE,path) for path,identity in expected.items()),'Actual common production tree differs')
    require(value.get('gtk_source_trees')=={path:object_id(GTK_PIN,path) for path in GTK_PIN_PATHS},
            'Sealed GTK leaf proof differs')
    changed=set(tree(source))-set(tree(BASE))
    require(value.get('changed')==sorted(changed) and
            value.get('composition_extensions')==sorted(changed-NEW_FILES),'Actual composition extension proof differs')
    return value


def validate_compatibility_report(value,source,run,attempt):
    validate_header(value,source,run,attempt)
    validate_source_report(value.get('integration_guard',{}),source,run,attempt)
    require(value.get('baseline_tree')==value['integration_guard']['baseline_tree'] and
            value.get('original_workflow_sha256')==value['integration_guard']['original_workflow_sha256'] and
            value.get('composition_extensions')==value['integration_guard']['composition_extensions'] and
            value.get('paths')==value['integration_guard']['changed'],
            'Compatibility gate baseline differs')
    # The unchanged original compatibility contract still verifies its fixed
    # old host/SDK, source trees, all process reports and every negative assertion.


def main():
    require(os.environ.get('GITHUB_ACTIONS')=='true','Actions only')
    source=os.environ['GITHUB_SHA'];sealed,digest=check_source(source)
    changed=sorted(set(tree(source))-set(tree(BASE)))
    header=dict(source_sha=source,run_id=os.environ['GITHUB_RUN_ID'],attempt=os.environ['GITHUB_RUN_ATTEMPT'],
      accepted=True,source_guard_passed=True,runtime_accepted=False,old_guard_executed=False,
      guard_kind=GUARD_KIND,guard_schema=1,composition_source=BASE,gtk_source_pin=GTK_PIN,
      gtk_tested_source=GTK_TESTED,workflow=WORKFLOW,original_workflow=ORIGINAL,
      baseline_tree=git('rev-parse',BASE+'^{tree}').decode().strip(),original_workflow_sha256=digest,
      all_existing_blobs_and_modes_unchanged=True,original_gtk_workflow_projection_exact=True,
      allowed_new_files=sorted(NEW_FILES),composition_extensions=sorted(set(changed)-NEW_FILES))
    report=dict(**header,ordinary_merge_source=BASE,common_source=sealed.COMMON,sdk=SDK,
      shared_version_support=sealed.MODULES,deliveries=sealed.DELIVERIES,
      production_trees={path:object_id(source,path) for path in ('apps','examples','extras','tools')},
      gtk_source_trees={path:object_id(GTK_PIN,path) for path in GTK_PIN_PATHS},
      changed=changed,original_failed_run_retained=40177143143,
      retained_original_producer_steps=31,retained_actual_producer_steps=35,
      scope='new common GTK source gate only; no runtime or old-guard acceptance')
    sys.path.insert(0,str(ROOT/'tests/reader_gtk_record_compatibility'))
    from run import BASE as RECORD_BASE,OLD_HOST,OLD_SDK,NEW_SDK
    require(NEW_SDK==SDK,'Historical new SDK constant differs')
    compatibility=dict(**header,base=RECORD_BASE,old_host=OLD_HOST,old_sdk=OLD_SDK,new_sdk=NEW_SDK,
      owner_trees={name:object_id(owner,'examples/linux') for name,owner in [('old',OLD_HOST),('new',source)]},
      protected_trees={name:{path:object_id(sdk,path) for path in sealed.PROTECTED}
                       for name,sdk in [('old',OLD_SDK),('new',NEW_SDK)]},
      paths=changed,integration_guard=report,
      scope='new common GTK compatibility-source gate; original runtime contract is still required')
    build=ROOT/'build';build.mkdir(exist_ok=True)
    for name,value in [('gtk-341-source-guard.json',report),('gtk-record-compatibility-guard.json',compatibility)]:
        (build/name).write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report),flush=True)


if __name__=='__main__':main()
