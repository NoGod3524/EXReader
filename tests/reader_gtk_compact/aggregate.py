"""Independent compact ON function report plus unchanged complete OFF scope."""
import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from guard import BASE,PRODUCTION,WORKFLOW,ON_STEP,off_projection

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tests/reader_hosts_integration'))
from final import Bundle,fetch,identity,pages,require
HOST='GTK 3.41 complete retained suites and actual owner record compatibility'
OLD_STRICT='Authenticate candidate canvas raw ZIP and source-bound reports'
DIAGNOSTIC='Read-only failed GTK owner evidence diagnosis'
SUMMARY='Authenticate distinct compact ON and complete original OFF scopes'
SCREENS={'library-empty','reading-txt','reading-epub','reading-pdf','reading-cbz','library-four-formats','reading-reopened-cbz'}
DENIED=('complete_product','performance_accepted','frame_accepted','six_platform_accepted','physical_device_execution','screen_reader_accepted')


def declaration(name):
    for node in ast.parse((ROOT/'tests/reader_gtk_compact/check_ui.py').read_text(encoding='utf-8')).body:
        if isinstance(node,ast.Assign) and any(isinstance(target,ast.Name) and target.id==name for target in node.targets):
            return ast.literal_eval(node.value)
    raise ValueError('missing pinned UI contract '+name)


def validate_ui(value,source,run,attempt,program):
    identity(value,source,run,attempt)
    require(value.get('accepted') is True and value.get('compact_enabled') is True and value.get('scope')=='optional compact GTK native UI functions only','wrong compact scope')
    require(all(value.get(key) is False for key in DENIED) and not value.get('failure'),'broader compact grant or recorded failure')
    expected=declaration('REQUIRED');rows=value.get('checks',[])
    require(value.get('count')==len(rows)==len(expected) and {row['name'] for row in rows}==set(expected) and
            len({row['name'] for row in rows})==len(rows) and all(row.get('passed') is True for row in rows),'missing/duplicate/failed actual compact cases')
    require(value.get('program_sha256')==program and re.fullmatch('[0-9a-f]{64}',program),'wrong actual ON program')
    require(set(value.get('menu_entries',[]))==set(declaration('MENU_ENTRIES')),'missing native More entry activation')
    fixtures=value.get('fixtures',{});require(set(fixtures)=={'txt','epub','pdf','cbz'},'four formats incomplete')
    require(all(row['fixed']==(kind in ('pdf','cbz')) and type(row['bytes']) is int and row['bytes']>0 and
                re.fullmatch('[0-9a-f]{64}',row['sha256']) for kind,row in fixtures.items()),'invalid four-format fixture identity')
    shots=value.get('screenshots',{});require(SCREENS<=set(shots),'missing actual screenshots')
    require(all(row['width']>=800 and row['height']>=600 and re.fullmatch('[0-9a-f]{64}',row['sha256']) for row in shots.values()),'screenshot size/hash absent')
    headers=value.get('primary_controls',[]);require({row['reading'] for row in headers}=={False,True},'both default views missing')
    for row in headers:
        expected={'Back to library','Previous page','Next page','Contents / pages','More reader actions'} if row['reading'] else {'Import book','Continue reading','More reader actions'}
        require(set(row['actual'])==expected and len(row['actual'])==len(expected),'dense or inaccessible primary controls')
    focus=value.get('focus_observations',[])
    require(any(row['label']=='txt-page' and any(node['name']=='Reading page' for node in row['nodes']) for row in focus),'real page keyboard focus missing')
    return len(rows)


def self_test():
    source='a'*40;run=1;attempt=2;program='b'*64
    good=dict(source_sha=source,run_id=run,attempt=attempt,accepted=True,compact_enabled=True,
        scope='optional compact GTK native UI functions only',program_sha256=program,
        count=len(declaration('REQUIRED')),checks=[dict(name=name,passed=True) for name in declaration('REQUIRED')],
        menu_entries=list(declaration('MENU_ENTRIES')),fixtures={kind:dict(fixed=kind in ('pdf','cbz'),bytes=10,sha256='c'*64) for kind in ('txt','epub','pdf','cbz')},
        screenshots={name:dict(width=1040,height=820,sha256='d'*64) for name in SCREENS},
        primary_controls=[dict(reading=False,actual=['Import book','Continue reading','More reader actions']),
                          dict(reading=True,actual=['Back to library','Previous page','Next page','Contents / pages','More reader actions'])],
        focus_observations=[dict(label='txt-page',nodes=[dict(name='Reading page')])],**{key:False for key in DENIED})
    validate_ui(good,source,run,attempt,program)
    changes=[dict(source_sha='foreign'),dict(run_id=3),dict(attempt=1),dict(accepted=False),dict(compact_enabled=False),
             dict(scope='all platforms'),dict(checks=good['checks'][:-1]),dict(checks=[good['checks'][0]]*len(good['checks'])),
             dict(program_sha256='e'*64),dict(menu_entries=[]),dict(fixtures={}),dict(screenshots={}),
             dict(primary_controls=[]),dict(focus_observations=[]),dict(failure='injected')]+[dict([(key,True)]) for key in DENIED]
    count=0
    for change in changes:
        bad=copy.deepcopy(good);bad.update(change)
        try:validate_ui(bad,source,run,attempt,program)
        except (ValueError,KeyError,TypeError):count+=1;continue
        raise ValueError('compact protocol admitted '+repr(change))
    # Only newline normalization is permitted by the OFF projection.
    sample='old line\n#ifdef EXR_READER_GTK_COMPACT\nnew line\n#else\nretained line\n#endif\n'
    require(off_projection(sample)=='old line\nretained line\n','OFF projection selects wrong arm')
    require(off_projection(sample.replace('old line','old  line'))!='old line\nretained line\n','OFF projection erased whitespace')
    for bad in ('#else\n','#endif\n','#ifdef EXR_READER_GTK_COMPACT\n'):
        try:off_projection(bad)
        except AssertionError:count+=1;continue
        raise ValueError('invalid OFF projection accepted')
    require(count==24,'independent rejection control omitted')
    return count


def main():
    require(os.environ.get('GITHUB_ACTIONS')=='true','Actions only')
    negatives=self_test()
    if '--self-test' in sys.argv:
        print('compact UI independent protocol: '+str(negatives)+' actual refusals');return
    source,run,attempt=os.environ['GITHUB_SHA'],int(os.environ['GITHUB_RUN_ID']),int(os.environ['GITHUB_RUN_ATTEMPT'])
    out=ROOT/'build/gtk-compact-summary';out.mkdir(parents=True,exist_ok=False)
    result=dict(accepted=False,source_sha=source,run_id=run,attempt=attempt,
        scope='optional GTK compact ON native functions plus complete original OFF regressions at one exact source',
        problems=[],off_full_original_scope_accepted=False,compact_native_ui_accepted=False,
        independent_protocol_rejections=negatives,production_pin=PRODUCTION,previous_common_source=BASE,
        **{key:False for key in DENIED})
    try:
        metadata=fetch('actions/runs/'+str(run))
        require(metadata['head_sha']==source and metadata['run_attempt']==attempt and metadata['path'].split('@')[0]==WORKFLOW,'wrong workflow/source/latest attempt')
        jobs=pages('actions/runs/%d/attempts/%d/jobs'%(run,attempt),'jobs')
        require(len(jobs)==5 and len({row['id'] for row in jobs})==5 and {row['name'] for row in jobs}=={'preflight',HOST,OLD_STRICT,DIAGNOSTIC,SUMMARY},'whole job set missing/duplicated')
        for row in jobs:
            require(row['head_sha']==source and row['run_attempt']==attempt,'foreign job source/attempt')
            if row['name']==SUMMARY:continue
            require(row['conclusion']==('skipped' if row['name']==DIAGNOSTIC else 'success'),'upstream original/ON job failed')
            if row['name']!=DIAGNOSTIC:require(all(step['conclusion'] in ('success','skipped') for step in row['steps']),'hidden failed step')
        host,=[row for row in jobs if row['name']==HOST]
        require(len(host['steps'])==35 and any(step['name']==ON_STEP and step['conclusion']=='success' for step in host['steps']),'new ON or retained original actual steps absent')
        artifacts=pages('actions/runs/%d/artifacts'%run,'artifacts')
        raw_name='reader-gtk-341-final-%d-%d'%(run,attempt);strict_name='reader-gtk-341-final-summary-%d-%d'%(run,attempt)
        raw_meta,=[row for row in artifacts if row['name']==raw_name];strict_meta,=[row for row in artifacts if row['name']==strict_name]
        for meta in (raw_meta,strict_meta):require(meta['workflow_run']['head_sha']==source and meta['workflow_run']['id']==run,'foreign original artifact')
        strict=Bundle(strict_meta)
        try:off=strict.report('verified.json')
        finally:strict.close()
        identity(off,source,run,attempt)
        require(off['accepted'] is True and off['all_original_producer_steps_passed']==35 and off['record_compatibility_accepted'] is True and
                off['settings_whole_page_palette_accepted'] is True and off['complete_product'] is False and
                off['artifact']['id']==raw_meta['id'] and off['artifact']['digest']==raw_meta['digest'],'unchanged complete original OFF strict result missing')
        raw=Bundle(raw_meta)
        try:
            on=raw.report('compact-ui/report.json')
            binary=raw.bytes('compact-package/EXReader-Linux/bin/exreader-linux',64*1024**2)
            program=hashlib.sha256(binary).hexdigest();count=validate_ui(on,source,run,attempt,program)
            require(program!=off['program_sha256'],'compact ON was substituted with OFF executable')
            require(binary==raw.bytes('compact-desktop/gtk-host/exreader-linux',64*1024**2),'packaged ON executable differs')
            for prefix,enabled in [('compact-desktop',True),('account-desktop',False)]:
                cache=raw.bytes(prefix+'/CMakeCache.txt',2*1024**2).decode('utf-8')
                require('EXR_READER_GTK_COMPACT:BOOL='+('ON' if enabled else 'OFF') in cache,'actual ON/OFF option drift')
                require('EXR_SDK_VERSION:STRING=3.41.0' in cache,'SDK source drift')
            mapping=raw.bytes('compact-desktop/gtk-account-host.map',16*1024**2)
            for symbol in (b'reader_navigation_resolve_cfi',b'reader_search_next',b'reader_rc_apply',b'reader_av_page_get',b'reader_preferences_save',b'exr_render_page_background'):
                require(symbol in mapping,'existing installed feature lost from ON map')
            for row in on['screenshots'].values():
                data=raw.bytes('compact-ui/'+row['path'],32*1024**2)
                require(data.startswith(b'\x89PNG\r\n\x1a\n') and hashlib.sha256(data).hexdigest()==row['sha256'],'actual native screenshot differs')
            fixture=raw.report('compact-fixtures/manifest.json');require(fixture==on['fixtures'],'fixture manifest differs')
            for row in fixture.values():
                data=raw.bytes('compact-fixtures/'+row['path'],64*1024**2)
                require(len(data)==row['bytes'] and hashlib.sha256(data).hexdigest()==row['sha256'],'four-format source changed')
        finally:raw.close()
        result.update(accepted=True,off_full_original_scope_accepted=True,compact_native_ui_accepted=True,
            off_program_sha256=off['program_sha256'],on_program_sha256=program,on_checks=count,
            off_original_authored_steps=31,actual_producer_steps=35,off_strict_report=off,compact_ui_report=on,
            artifacts=[{key:row[key] for key in ('id','name','size_in_bytes','digest','expires_at')} for row in (raw_meta,strict_meta)],
            jobs=[dict(id=row['id'],name=row['name'],conclusion=row['conclusion']) for row in jobs if row['name']!=SUMMARY])
    except Exception as error:result['problems'].append(type(error).__name__+': '+str(error))
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({key:result[key] for key in ('accepted','off_full_original_scope_accepted','compact_native_ui_accepted','problems')}),flush=True)
    require(result['accepted'],'compact ON plus original OFF acceptance refused')


if __name__=='__main__':main()
