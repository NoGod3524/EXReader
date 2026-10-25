"""Exact common source and complete sealed Android130 caller ownership."""
import json
import os
from pathlib import Path
import subprocess
from source_paths import COMMON_BASE as BASE, CALLER_PIN_PATHS

ROOT=Path(__file__).resolve().parents[2]
COMMON_PRODUCTION='49b2a7c86173181f8f79a760315ddb8ca2312bd1'
ORIGINAL='07ebe8786434ef384c97ccdb451242d3c6aee6cb'
THEME='1b3cfd1413fa5ebade31be6958f835f6de3b5290'
TESTED_THEME='57bc3966c20171f2f51e3fc6bf02f1ad1f7e5165'
PARSER='b1a7b7891cd394671842164a07a86c8e316dace3'
SDK='edddc463c06ed5731195cdb8f06b2df6dff7699e'
WORKFLOW='.github/workflows/reader-android-page-theme.yml'
MARKER='python -m py_compile tests/reader_android_page_theme/*.py'
ENTRY='python -m pip install PyYAML==6.0.3\npython -m py_compile tests/reader_hosts_341/guard_android.py tests/reader_hosts_341/aggregate_android.py\npython tests/reader_hosts_341/guard_android.py\n'
JAVA=[f'examples/android/app/src/main/java/org/exreader/host/{name}.java'
      for name in ('NativeCbz','NativeReadingSdk','ReadingParserPolicy')]
git=lambda *args:subprocess.check_output(['git',*args],text=True).strip()


def validate_source(write=False):
    assert os.environ.get('GITHUB_ACTIONS')=='true'
    source=os.environ['GITHUB_SHA'];assert git('rev-parse','HEAD')==source
    for parent in (BASE,COMMON_PRODUCTION,ORIGINAL,THEME,TESTED_THEME,PARSER,SDK):
        subprocess.run(['git','merge-base','--is-ancestor',parent,source],check=True)
    allowed={WORKFLOW,'tests/reader_hosts_341/guard_android.py','tests/reader_hosts_341/aggregate_android.py',
             'docs/READER-ANDROID-341-COMMON-PREP.md'}
    changed=git('diff','--name-only',BASE,source).splitlines();assert set(changed)<=allowed | CALLER_PIN_PATHS,changed
    subprocess.run(['git','diff','--exit-code',BASE,source,'--','apps','examples','extras','tools'],check=True)
    for path in ('src','include','cmake','CMakeLists.txt','bindings','tests/fixtures','licenses',
                 '.github/workflows/native.yml','.github/workflows/reliability.yml'):
        assert git('rev-parse',source+':'+path)==git('rev-parse',SDK+':'+path),path
    assert git('rev-parse',source+':apps/reader/store/001_catalog.sql')==git('rev-parse',ORIGINAL+':apps/reader/store/001_catalog.sql')
    android_delta=set(git('diff','--name-only',THEME,source,'--','examples/android').splitlines())
    assert android_delta<=set(JAVA),android_delta
    for path in JAVA:assert git('rev-parse',source+':'+path)==git('rev-parse',PARSER+':'+path),path
    original_tests=('reader_android_page_theme','reader_android_host_import','reader_android_fixed_pan',
                    'reader_android_cbz_reading','reader_android_reading','reader_android_preferences',
                    'reader_android_navigation','reader_android_search','reader_host_session_android',
                    'reader_session_android','webdav_android')
    for name in original_tests:
        path='tests/'+name;assert git('rev-parse',source+':'+path)==git('rev-parse',THEME+':'+path),path
    for path in ('apps/reader/revisions','apps/reader/reading-state','apps/reader/reading-commands','apps/reader/annotation-view'):
        assert git('rev-parse',source+':'+path)==git('rev-parse',THEME+':'+path),path
    header=subprocess.check_output(['git','show',source+':apps/reader/revisions/include/reader_revisions.h'],text=True)
    assert '#define READER_REVISION_ANCHOR_MAX_VERSION 2u' in header
    import yaml
    old=yaml.load(subprocess.check_output(['git','show',THEME+':'+WORKFLOW],text=True),Loader=yaml.BaseLoader)
    new=yaml.load((ROOT/WORKFLOW).read_text(),Loader=yaml.BaseLoader)
    assert set(new['jobs'])==set(old['jobs'])=={'android','summary'}
    old_steps=old['jobs']['android']['steps'];new_steps=new['jobs']['android']['steps']
    assert len(old_steps)==len(new_steps)==16
    assert {key:value for key,value in new['jobs']['android'].items() if key!='steps'}=={key:value for key,value in old['jobs']['android'].items() if key!='steps'}
    for before,after in zip(old_steps,new_steps):
        if before.get('name')=='Record identity and preserve frozen SDK schema and delivered packages':
            expected=dict(before);body=before['run'];assert body.count(MARKER)==1
            expected['run']=body[:body.index('git merge-base')]+ENTRY+body[body.index(MARKER):]
            assert after==expected
        else:assert before==after,before.get('name',before.get('uses'))
    old_summary=old['jobs']['summary'];new_summary=new['jobs']['summary']
    assert {key:value for key,value in new_summary.items() if key!='steps'}=={key:value for key,value in old_summary.items() if key!='steps'}
    expected_checkout=dict(old_summary['steps'][0]);expected_checkout['with']={'fetch-depth':'0'}
    assert new_summary['steps'][0]==expected_checkout
    expected_auth=dict(old_summary['steps'][1]);expected_auth['run']=expected_auth['run'].replace(
        'python -m pip install Pillow==11.1.0','python -m pip install Pillow==11.1.0 PyYAML==6.0.3').replace(
        'python tests/reader_android_page_theme/check_evidence.py','python tests/reader_hosts_341/aggregate_android.py')
    assert new_summary['steps'][1]==expected_auth
    assert new_summary['steps'][2:]==old_summary['steps'][2:]
    report=dict(accepted=True,scope='exact source and unchanged complete Android130 caller only',
        source_sha=source,run_id=os.environ['GITHUB_RUN_ID'],attempt=os.environ['GITHUB_RUN_ATTEMPT'],
        baseline=BASE,common_production=COMMON_PRODUCTION,sdk_source=SDK,theme_source=THEME,
        original_tested_theme_source=TESTED_THEME,parser_policy_source=PARSER,java_policy_paths=JAVA,
        revision_anchor_max_version=2,original_producer_steps=16,inherited_business_checks=120,theme_checks=10,
        all_original_semantics_fixtures_and_130_judges_unchanged=True,
        production_trees={path:git('rev-parse',source+':'+path) for path in ('apps','examples','extras','tools')},
        schema_changed=False,debug_sender138_adopted=False,raw_v3_adopted=False,
        android130_scope_accepted=False,physical_device_execution=False,complete_product=False,changed=changed)
    if write:
        folder=ROOT/'build/android-page-theme';folder.mkdir(parents=True,exist_ok=True)
        (folder/'common-source-guard.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)
    return report


if __name__=='__main__':validate_source(write=True)
