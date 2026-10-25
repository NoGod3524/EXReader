"""Fixed GTK raw production composition; all original tests remain immutable."""
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
BASE='25bc0c67971f81491f50e0a3caaaf7e509bb7e35'
COMPACT='9fc407a5cce5a0bfe644a60bd8dc29f84dea6d0e'
COMPOSITION='f2466cc34cbe1829c7f16eb66ec7b60dedf51be7'
RAW='0889f7d1e9a537c6c1b05456547e016b26e1cd85'
CODEC='4ad6f956a9ebe33f50a5f341b51b24bd538e871a'
PRODUCTION='4b189aca819d9c5d1a7e73a6c5bbe0b2e8286f6e'
WORKFLOW='.github/workflows/reader-gtk-raw3.yml'
ON_STEP='Build and verify compact ON before the complete original OFF regressions'
MODULES=('revisions','commands','reading-state','reading-commands','annotation-view','sync','session','desktop-metadata')
PRODUCTION_PATHS={'apps/reader/desktop/CMakeLists.txt','examples/linux/reading.c','examples/linux/accounts_ui.inc',
 'examples/linux/reading_records_backend.inc','examples/linux/reading_records_ui.inc'}


def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT,text=True).replace('\r\n','\n').strip('\n')


def project(source,flag):
    # Same exact conditional projection as compact; change only the flag name.
    text=(ROOT/'tests/reader_gtk_compact/guard.py').read_text(encoding='utf-8')
    begin=text.index('def off_projection(');end=text.index('\n\ndef main(',begin)
    value={'re':re};exec(compile(text[begin:end].replace('EXR_READER_GTK_COMPACT',flag),'<raw projection>','exec'),value)
    return value['off_projection'](source)


def projection(source):return project(source,'EXR_READER_GTK_RAW3')
def off_projection(source):return project(source,'EXR_READER_GTK_COMPACT')


def main():
    assert os.environ.get('GITHUB_ACTIONS')=='true';source=os.environ['GITHUB_SHA'];assert git('rev-parse','HEAD')==source
    for parent in (COMPACT,COMPOSITION,RAW,CODEC,PRODUCTION):subprocess.run(['git','merge-base','--is-ancestor',parent,source],cwd=ROOT,check=True)
    owned=PRODUCTION_PATHS|{WORKFLOW,'apps/reader/desktop/reading_capture_bytes.h','.github/workflows/reader-private-capture.yml',
      'docs/READER-PRIVATE-CAPTURE.md','docs/validation/reader-private-capture.json','docs/READER-GTK-RAW3.md','docs/validation/reader-gtk-raw3.json'}
    changed=git('diff','--name-only',COMPOSITION,source).splitlines()
    assert all(path in owned or path.startswith(('tests/reader_gtk_raw3/','tests/reader_private_capture/')) for path in changed),changed
    subprocess.run(['git','diff','--exit-code',PRODUCTION,source,'--','apps','examples','extras','tools'],cwd=ROOT,check=True)
    for module in MODULES:
        path='apps/reader/'+module;assert git('rev-parse',source+':'+path)==git('rev-parse',RAW+':'+path),path
    assert git('rev-parse',source+':apps/reader/desktop/reading_capture_bytes.h')==git('rev-parse',CODEC+':apps/reader/desktop/reading_capture_bytes.h')
    for path in PRODUCTION_PATHS-{'apps/reader/desktop/CMakeLists.txt'}:
        expected=subprocess.check_output(['git','show',COMPOSITION+':'+path],cwd=ROOT,text=True).replace('\r\n','\n')
        assert projection((ROOT/path).read_text(encoding='utf-8'))==expected,'raw OFF byte projection differs: '+path
    spec=importlib.util.spec_from_file_location('sealed_gtk_guard',ROOT/'tests/reader_gtk_341_final/guard.py');old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
    for path in old.PROTECTED+['licenses']:assert git('rev-parse',source+':'+path)==git('rev-parse',old.SDK+':'+path),path
    assert git('rev-parse',source+':apps/reader/store')==git('rev-parse',COMPOSITION+':apps/reader/store')
    assert '#define READER_REVISION_ANCHOR_MAX_VERSION 2u' in (ROOT/'apps/reader/revisions/include/reader_revisions.h').read_text()
    import yaml
    before=yaml.load(git('show',COMPACT+':.github/workflows/reader-gtk-compact.yml'),Loader=yaml.BaseLoader)
    after=yaml.load((ROOT/WORKFLOW).read_text(),Loader=yaml.BaseLoader)
    prior=before['jobs']['account']['steps'];current=after['jobs']['account']['steps'];assert len(prior)==len(current)==32
    for a,b in zip(prior,current):
        if a.get('name')=='Require fixed SDK candidate and unchanged legacy tests':
            expected=dict(a);expected['run']=a['run'].replace('tests/reader_gtk_compact/guard.py','tests/reader_gtk_raw3/guard.py');assert b==expected
        else:assert a==b,a.get('name',a.get('uses'))
    cmake=(ROOT/'apps/reader/desktop/CMakeLists.txt').read_text()
    assert 'option(EXR_READER_GTK_RAW3 "Explicit GTK raw selector host candidate; never default" OFF)' in cmake
    assert '_exr_raw_guard_target(EXReaderReadingState::reader_reading_state_codec' in cmake
    assert 'GTK raw3 family origin differs' in cmake
    spec=importlib.util.spec_from_file_location('sealed_cloud_guard',ROOT/'tests/reader_webdav_import/check_guards.py');cloud=importlib.util.module_from_spec(spec);spec.loader.exec_module(cloud);controls=cloud.selftest()
    joined=''
    for path in (ROOT/'apps/reader/cloud-import').rglob('*'):
        if path.suffix not in ('.c','.h'):continue
        text=path.read_text();joined+=text
        assert not [p for p in cloud.FORBIDDEN if re.search(p,text) and not(p=='Authorization' and path.suffix=='.h')]
    assert all(re.search(p,joined) for p,_ in cloud.BOUNDARY)
    assert 'EXR_SIDELOAD_STREAM_LIMIT' in joined and 'EXR_SIDELOAD_MEMORY_LIMIT' in joined
    common=dict(source_sha=source,run_id=os.environ['GITHUB_RUN_ID'],attempt=os.environ['GITHUB_RUN_ATTEMPT'])
    report=dict(**common,accepted=True,ordinary_merge_source=PRODUCTION,common_source=old.COMMON,sdk=old.SDK,
      shared_version_support=old.MODULES,deliveries=old.DELIVERIES,production_trees={p:git('rev-parse',source+':'+p) for p in ('apps','examples','extras','tools')},
      shared_version_paths=['tools/build_linux_host.py'],changed=changed,original_failed_run_retained=40177143143,retained_original_producer_steps=31,
      off_projection_base=COMPOSITION,off_projection_exact=True,whitespace_normalization='CRLF to LF only',cloud_adapter_source_guard=True,
      cloud_source_controls=controls,compact_ui_accepted=False,raw_host_accepted=False,raw_family_source=RAW,private_capture_source=CODEC)
    folder=ROOT/'build';folder.mkdir(exist_ok=True);(folder/'gtk-341-source-guard.json').write_text(json.dumps(report,indent=2)+'\n')
    sys.path.insert(0,str(ROOT/'tests/reader_gtk_record_compatibility'))
    from run import BASE as RECORD_BASE,OLD_HOST,OLD_SDK
    pair=dict(**common,accepted=True,base=RECORD_BASE,old_host=OLD_HOST,old_sdk=OLD_SDK,new_sdk=old.SDK,
      owner_trees={name:git('rev-parse',sha+':examples/linux') for name,sha in [('old',OLD_HOST),('new',source)]},
      protected_trees={name:{path:git('rev-parse',sha+':'+path) for path in old.PROTECTED} for name,sha in [('old',OLD_SDK),('new',old.SDK)]},
      paths=changed,integration_guard=report)
    (folder/'gtk-record-compatibility-guard.json').write_text(json.dumps(pair,indent=2)+'\n')
    print(json.dumps(report),flush=True)


if __name__=='__main__':main()
