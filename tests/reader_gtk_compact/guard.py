"""Actions-only reviewed compact production pin and byte-exact OFF projection."""
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
BASE='25bc0c67971f81491f50e0a3caaaf7e509bb7e35'
PRODUCTION='a7bcf0483fb52ecf9cd3cdf7dda07a4aa742f174'
WORKFLOW='.github/workflows/reader-gtk-compact.yml'
OLD_WORKFLOW='.github/workflows/reader-gtk-341-final.yml'
PRODUCTION_PATHS={'examples/linux/reader.c','examples/linux/CMakeLists.txt'}
ON_STEP='Build and verify compact ON before the complete original OFF regressions'
CMAKE_BLOCK='''option(EXR_READER_GTK_COMPACT "Use optional compact native library and reading views" OFF)
if(EXR_READER_GTK_COMPACT)
  target_compile_definitions(exreader-linux PRIVATE EXR_READER_GTK_COMPACT=1)
endif()
'''


def git(*args):return subprocess.check_output(['git',*args],text=True).replace('\r\n','\n')


def off_projection(source):
    output=[];frames=[];active=True
    for line in source.replace('\r\n','\n').splitlines(keepends=True):
        text=line.strip()
        if re.match(r'#\s*(?:if|ifdef|ifndef)\b',text):
            target=text in ('#ifdef EXR_READER_GTK_COMPACT','#ifndef EXR_READER_GTK_COMPACT')
            frames.append((target,active,text=='#ifndef EXR_READER_GTK_COMPACT'))
            if target:active=active and frames[-1][2];continue
        elif text=='#else':
            assert frames,'unmatched else'
            target,parent,condition=frames[-1]
            if target:active=parent and not condition;continue
        elif text.startswith('#elif'):
            assert frames and not frames[-1][0],'compact elif is outside the reviewed syntax'
        elif text=='#endif':
            assert frames,'unmatched endif'
            target,parent,_=frames.pop()
            if target:active=parent;continue
        if active:output.append(line)
    assert not frames,'unclosed conditional'
    return ''.join(output)


def main():
    assert os.environ.get('GITHUB_ACTIONS')=='true'
    source=os.environ['GITHUB_SHA'];assert git('rev-parse','HEAD').strip()==source
    spec=importlib.util.spec_from_file_location('sealed_guard',ROOT/'tests/reader_gtk_341_final/guard.py')
    old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
    for parent in (BASE,PRODUCTION,old.COMMON,old.SDK,old.MODULES,*old.DELIVERIES):
        subprocess.run(['git','merge-base','--is-ancestor',parent,source],check=True)
    changed=git('diff','--name-only',BASE,source).splitlines()
    assert all(path in PRODUCTION_PATHS or path==WORKFLOW or path.startswith('tests/reader_gtk_compact/') or
               path in ('docs/READER-GTK-COMPACT.md','docs/validation/reader-gtk-compact.json') for path in changed),changed
    assert set(git('diff','--name-only',BASE,PRODUCTION,'--','apps','examples','extras','tools').splitlines())==PRODUCTION_PATHS
    subprocess.run(['git','diff','--exit-code',PRODUCTION,source,'--','apps','examples','extras','tools'],check=True)
    original=git('show',BASE+':examples/linux/reader.c')
    assert off_projection((ROOT/'examples/linux/reader.c').read_text(encoding='utf-8'))==original,'OFF changed bytes beyond CRLF/LF'
    cmake=(ROOT/'examples/linux/CMakeLists.txt').read_text(encoding='utf-8')
    assert cmake.count(CMAKE_BLOCK)==1
    assert cmake.replace(CMAKE_BLOCK,'')==git('show',BASE+':examples/linux/CMakeLists.txt'),'unreviewed CMake change'
    for path in old.PROTECTED+['licenses']:
        assert git('rev-parse',source+':'+path)==git('rev-parse',old.SDK+':'+path),path
    assert git('rev-parse',source+':apps/reader/store/001_catalog.sql')==git('rev-parse',BASE+':apps/reader/store/001_catalog.sql')
    assert '#define READER_REVISION_ANCHOR_MAX_VERSION 2u' in (ROOT/'apps/reader/revisions/include/reader_revisions.h').read_text(encoding='utf-8')
    import yaml
    before=yaml.load(git('show',BASE+':'+OLD_WORKFLOW),Loader=yaml.BaseLoader)
    after=yaml.load((ROOT/WORKFLOW).read_text(encoding='utf-8'),Loader=yaml.BaseLoader)
    old_steps=before['jobs']['account']['steps'];all_steps=after['jobs']['account']['steps']
    added=[step for step in all_steps if step.get('name')==ON_STEP];assert len(added)==1
    new_steps=[step for step in all_steps if step.get('name')!=ON_STEP]
    assert len(old_steps)==len(new_steps)==31
    assert all_steps.index(added[0])<next(i for i,s in enumerate(all_steps) if s.get('name')=='Build actual frozen old owner and exercise real cross-process record compatibility')
    for prior,current in zip(old_steps,new_steps):
        assert prior.get('name')==current.get('name') and prior.get('uses')==current.get('uses')
        if prior.get('name')=='Require fixed SDK candidate and unchanged legacy tests':
            assert current['run']==prior['run'].replace('python3 tests/reader_hosts_341/guard_gtk.py','python3 tests/reader_gtk_compact/guard.py')
        elif prior.get('uses')=='actions/upload-artifact@v4':
            assert {key:value for key,value in prior['with'].items() if key!='path'}=={key:value for key,value in current['with'].items() if key!='path'}
            assert set(prior['with']['path'].splitlines())<=set(current['with']['path'].splitlines())
        else:assert prior==current,prior.get('name',prior.get('uses'))
    expected=before['jobs']['evidence']['steps'][1]['run'].replace('python3 tests/reader_hosts_341/aggregate_gtk.py','python3 tests/reader_gtk_compact/aggregate_off.py')
    assert after['jobs']['evidence']['steps'][1]['run']==expected
    shared=['tools/build_linux_host.py']
    for module,config in [('batch-import','BatchImport'),('navigation','Navigation'),('reading-state','ReadingState'),('search','Search')]:
        shared+=['apps/reader/'+module+'/CMakeLists.txt','apps/reader/'+module+'/EXReader'+config+'Config.cmake.in']
    for path in shared:assert git('rev-parse',source+':'+path)==git('rev-parse',old.MODULES+':'+path),path
    sys.path.insert(0,str(ROOT/'tests/reader_hosts_341'))
    cloud_spec=importlib.util.spec_from_file_location('sealed_cloud_guard',ROOT/'tests/reader_webdav_import/check_guards.py')
    cloud=importlib.util.module_from_spec(cloud_spec);cloud_spec.loader.exec_module(cloud);controls=cloud.selftest()
    joined=''
    for path in (ROOT/'apps/reader/cloud-import').rglob('*'):
        if path.suffix not in ('.c','.h'):continue
        text=path.read_text(encoding='utf-8');joined+=text
        assert not [pattern for pattern in cloud.FORBIDDEN if re.search(pattern,text) and not(pattern=='Authorization' and path.suffix=='.h')],str(path)
    assert all(re.search(pattern,joined) for pattern,_ in cloud.BOUNDARY)
    assert 'EXR_SIDELOAD_STREAM_LIMIT' in joined and 'EXR_SIDELOAD_MEMORY_LIMIT' in joined
    common=dict(source_sha=source,run_id=os.environ['GITHUB_RUN_ID'],attempt=os.environ['GITHUB_RUN_ATTEMPT'])
    report=dict(**common,accepted=True,ordinary_merge_source=PRODUCTION,common_source=old.COMMON,sdk=old.SDK,
        shared_version_support=old.MODULES,deliveries=old.DELIVERIES,production_trees={path:git('rev-parse',source+':'+path).strip() for path in ('apps','examples','extras','tools')},
        shared_version_paths=shared,changed=changed,original_failed_run_retained=40177143143,retained_original_producer_steps=31,
        off_projection_base=BASE,off_projection_exact=True,whitespace_normalization='CRLF to LF only',
        cloud_adapter_source_guard=True,cloud_source_controls=controls,compact_ui_accepted=False)
    folder=ROOT/'build';folder.mkdir(exist_ok=True)
    (folder/'gtk-341-source-guard.json').write_text(json.dumps(report,indent=2)+'\n')
    sys.path.insert(0,str(ROOT/'tests/reader_gtk_record_compatibility'))
    from run import BASE as RECORD_BASE,OLD_HOST,OLD_SDK,NEW_SDK
    assert NEW_SDK==old.SDK
    for path in old.PROTECTED:assert git('rev-parse',OLD_HOST+':'+path)==git('rev-parse',OLD_SDK+':'+path),path
    pair=dict(**common,accepted=True,base=RECORD_BASE,old_host=OLD_HOST,old_sdk=OLD_SDK,new_sdk=old.SDK,
        owner_trees={name:git('rev-parse',sha+':examples/linux').strip() for name,sha in [('old',OLD_HOST),('new',source)]},
        protected_trees={name:{path:git('rev-parse',sha+':'+path).strip() for path in old.PROTECTED} for name,sha in [('old',OLD_SDK),('new',old.SDK)]},
        paths=changed,integration_guard=report)
    (folder/'gtk-record-compatibility-guard.json').write_text(json.dumps(pair,indent=2)+'\n')
    print(json.dumps(report),flush=True)


if __name__=='__main__':main()
