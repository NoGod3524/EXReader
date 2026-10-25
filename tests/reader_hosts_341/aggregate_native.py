"""Actions-only upper collector: whole current-attempt leaves, never platform splicing."""
import argparse
import importlib.util
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
BASE='5e8b132626cfe7540f675285787d24bf488857a8'
SDK='edddc463c06ed5731195cdb8f06b2df6dff7699e'
SCHEMA_OWNER='07ebe8786434ef384c97ccdb451242d3c6aee6cb'
sys.path.insert(0,str(ROOT/'tests/reader_hosts_integration'))
from final import Bundle,fetch,identity,pages,require
import apple as original_apple

APPLE=('records','navigation','search','shelf','mapping','wp13','page_theme')
REQUIRED=('composition','gtk41','android130','windows_full_f3','windows_atomic13',*('apple_'+name for name in APPLE))
PRODUCT_REQUIRED=('apple_record_compatibility','android_to_apple','apple_to_android')
# Reviewed Windows strict schemas use one whole run for two required scopes.
# Product peer contracts still require separate actual common-source evidence.
WINDOWS_CONTRACTS={}
PRODUCT_CONTRACTS={name:None for name in PRODUCT_REQUIRED}
SCOPES={
 'composition':'fixed-source 26 optional packages plus SDK: 27 installed package configs',
 'gtk41':'Linux GTK 3.41 full retained suites and explicit actual owner record pair',
 'android130':'API34 default x86_64 Android SDK3.41 actual page theme plus 120 inherited business checks',
 'apple_records':'native Apple product reading records only',
 'apple_navigation':'native Apple navigation interface only',
 'apple_search':'native Apple search interface only',
 'windows_full_f3':'Windows SDK3.41 same full native host: original retained suites plus F3 25',
 'windows_atomic13':'Windows SDK3.41 actual full-host atomic preference commit13 and old-veto control',
 'apple_page_theme':'SDK3.41 Apple explicit page themes on macOS and iPhone/iPad simulators only'}


def spec(workflow,jobs,summary_job,summary_name,report,upstream,optional=(),guard=None):
    return dict(workflow='.github/workflows/'+workflow+'.yml',jobs=jobs,summary_job=summary_job,
                summary_name=summary_name,report=report,upstream=upstream,optional=optional,guard=guard)


SPECS={
 'composition':spec('reader-composition-341',5,'strict same-source composition report',
   'reader-module-composition-report-{run}-{attempt}','result.json',
   tuple('reader-reviewed-composition-'+p+'-{run}-{attempt}' for p in ('linux','windows','macos'))),
 'gtk41':spec('reader-gtk-341-final',3,'Authenticate candidate canvas raw ZIP and source-bound reports',
   'reader-gtk-341-final-summary-{run}-{attempt}','verified.json',('reader-gtk-341-final-{run}-{attempt}',),
   ('Read-only failed GTK owner evidence diagnosis',)),
 'android130':spec('reader-android-page-theme',2,'summary','reader-android-page-theme-summary-{run}-{attempt}',
   'summary.json',('reader-android-page-theme-{run}-{attempt}',)),
}
for key,report in (('windows_full_f3','full-f3.json'),('windows_atomic13','atomic13.json')):
    WINDOWS_CONTRACTS[key]=spec('reader-windows-341-common',3,
        'same-source native Windows search artifact authentication',
        'reader-windows-search-summary-{run}-{attempt}','windows-341-summary/'+report,
        ('reader-windows-search-initial-{run}-{attempt}',),
        guard=('Pin exact common production and unchanged original judges',1))
for key in APPLE:
    if key=='page_theme':
        SPECS['apple_'+key]=spec('reader-apple-page-theme',8,'Strict same-source page theme summary',
          'apple-theme-summary-{run}-{attempt}','summary.json',
          tuple('apple-theme-'+part+'-{run}-{attempt}' for part in ('sdk-macos','sdk-iphonesimulator','native','ui-macos','ui-iphone','ui-ipad','fast-import')),
          guard=('Authenticate exact SDK source and unchanged original business suites',2))
        continue
    workflow,stem,count=original_apple.SPECS[key]
    summary={'records':'Strict same-source reading records summary','navigation':'Strict same-source navigation summary',
             'search':'Strict same-source search summary','shelf':'summary','mapping':None,'wp13':'summary'}[key]
    name=None if key=='mapping' else ('wp13-apple-validation' if key=='wp13' else
         stem+('-validation' if key=='shelf' else '-summary')+'-{run}-{attempt}')
    report='wp13-apple-summary.json' if key=='wp13' else 'shelf-summary.json' if key=='shelf' else 'summary.json'
    SPECS['apple_'+key]=spec(workflow,count,summary,name,report,(),guard=('Authenticate exact common-source host merge',3 if key=='wp13' else 2))


def positive(value):return type(value) is int and value>0


def ref_check(value):
    require(isinstance(value,dict) and set(value)=={'run_id','attempt'} and
            positive(value['run_id']) and positive(value['attempt']),'leaf requires one whole {run_id,attempt}')


def validate_input(value,source):
    require(isinstance(value,dict) and set(value)<= {'source_sha','runs','product_conditions','history'} and
            value.get('source_sha')==source and re.fullmatch('[0-9a-f]{40}',source),'fixed source missing/differs')
    require(isinstance(value.get('runs'),dict) and set(value['runs'])==set(REQUIRED),'all twelve mandatory leaf keys are required')
    used={}
    for key,ref in value['runs'].items():
        if ref is None:continue
        ref_check(ref)
        if ref['run_id'] in used:
            other=used[ref['run_id']]
            require({key,other}==set(WINDOWS_CONTRACTS) and ref==value['runs'][other],
                    'duplicate/reused run across mandatory workflows or split Windows attempt')
        else:used[ref['run_id']]=key
    conditions=value.get('product_conditions',{key:None for key in PRODUCT_REQUIRED})
    require(isinstance(conditions,dict) and set(conditions)==set(PRODUCT_REQUIRED),'required product facts missing')
    for ref in conditions.values():
        if ref is not None:ref_check(ref)
    history=value.get('history',[]);require(isinstance(history,list) and len(history)<=32,'unbounded history')
    for row in history:
        require(isinstance(row,dict) and set(row)<= {'label','source_sha','run_id','attempt','scope'},'history is separate declared data')
    return conditions


def timestamp(value):return datetime.fromisoformat(value.replace('Z','+00:00'))


def artifact_check(row,source,run,window):
    require(positive(row.get('id')) and positive(row.get('size_in_bytes')) and row['size_in_bytes']<=512*1024**2 and
            row.get('expired') is False and isinstance(row.get('name'),str),'artifact ID/bytes/expiry invalid')
    require(re.fullmatch('sha256:[0-9a-f]{64}',row.get('digest') or ''),'API artifact digest absent/invalid')
    require(row.get('workflow_run',{}).get('head_sha')==source and row['workflow_run']['id']==run,'artifact source/run differs')
    require(timestamp(row['expires_at'])>datetime.now(timezone.utc),'artifact expired')
    require(window[0]<=timestamp(row['created_at'])<=window[1],'artifact not created in this complete attempt/job window')


def expected_names(key,contract,run,attempt):
    if key.startswith('apple_') and key!='apple_page_theme':
        return original_apple.expected_artifacts(key[6:],run,attempt)
    names={name.format(run=run,attempt=attempt) for name in contract['upstream']}
    if contract['summary_name']:names.add(contract['summary_name'].format(run=run,attempt=attempt))
    return names


def validate_metadata(key,contract,ref,run,jobs,artifacts,source):
    require((run.get('id'),run.get('head_sha'),run.get('run_attempt'),run.get('path','').split('@')[0])==
            (ref['run_id'],source,ref['attempt'],contract['workflow']),'run source/workflow/latest attempt differs')
    require(run['status']=='completed' and run['conclusion']=='success','complete leaf has not succeeded')
    require(len(jobs)==len({row['id'] for row in jobs})==len({row['name'] for row in jobs})==contract['jobs'],'leaf jobs omitted/duplicated')
    active=[]
    for job in jobs:
        require(job['head_sha']==source and job['run_id']==ref['run_id'] and job['run_attempt']==ref['attempt'] and
                job['status']=='completed','foreign/incomplete job')
        if job['name'] in contract['optional']:
            require(job['conclusion']=='skipped','unrequested diagnosis must not replace a mandatory producer')
            continue
        require(job['conclusion']=='success' and all(step.get('conclusion') in ('success','skipped') for step in job['steps']),
                'failed job/hidden failed step')
        active.append(job)
    if contract['guard']:
        label,count=contract['guard'];guards=[step for job in active for step in job['steps'] if step.get('name')==label]
        require(len(guards)==count and all(step['conclusion']=='success' for step in guards),'mandatory exact common source guard absent/skipped')
    summary=None
    if contract['summary_job']:
        found=[job for job in active if job['name']==contract['summary_job']];require(len(found)==1,'strict job absent/duplicate');summary=found[0]
    require(active and all(job.get('started_at') and job.get('completed_at') for job in active),'job timestamps absent')
    window=(min(timestamp(job['started_at']) for job in active),max(timestamp(job['completed_at']) for job in active))
    names=expected_names(key,contract,ref['run_id'],ref['attempt']);selected={}
    require(len(artifacts)==len({row['id'] for row in artifacts}),'duplicate API artifact IDs')
    for name in names:
        found=[row for row in artifacts if row['name']==name];require(len(found)==1,'required artifact missing/duplicate: '+name)
        artifact_check(found[0],source,ref['run_id'],window);selected[name]=found[0]
    if summary:
        name=contract['summary_name'].format(run=ref['run_id'],attempt=ref['attempt'])
        artifact_check(selected[name],source,ref['run_id'],(timestamp(summary['started_at']),timestamp(summary['completed_at'])))
        require(selected[name]['size_in_bytes']<=32*1024**2,'strict summary ZIP unexpectedly large')
        for other,row in selected.items():
            if other!=name:require(timestamp(row['created_at'])<=timestamp(summary['started_at']),'upstream artifact created after strict started')
    return selected,summary


def bind_declared(rows,live):
    require(isinstance(rows,list) and len(rows)==len(live) and len({row['id'] for row in rows})==len(rows),'summary upstream inventory missing/duplicate')
    require({row['name'] for row in rows}==set(live),'summary upstream set differs')
    for row in rows:
        actual=live[row['name']]
        require(row['id']==actual['id'] and row.get('size_in_bytes',row.get('bytes'))==actual['size_in_bytes'] and
                row['digest']==actual['digest'] and row['expires_at']==actual['expires_at'],'summary upstream metadata differs from API')


def bind_jobs(rows,live):
    require(isinstance(rows,list) and len(rows)==len({row['id'] for row in rows})==len(live) and
            {row['id'] for row in rows}==set(live),'summary jobs omitted/duplicated/substituted')
    for row in rows:
        require(all(row.get(field)==live[row['id']].get(field) for field in
                    ('name','head_sha','run_id','run_attempt','status','conclusion')),'summary job source/attempt/status differs from API')


def basic_summary(key,value,source,ref):
    require(isinstance(value,dict) and value.get('accepted') is True,'real strict summary did not accept')
    actual_run=value.get('run_id',value.get('run',{}).get('id'));actual_attempt=value.get('attempt',value.get('run',{}).get('attempt'))
    require(value.get('source_sha')==source and str(actual_run)==str(ref['run_id']) and str(actual_attempt)==str(ref['attempt']),'strict summary source/run/attempt differs')
    require(not value.get('problems') and value.get('complete_product',False) is False and
            value.get('performance_accepted',False) is False and value.get('physical_device_execution',False) is False and
            value.get('physical_device',False) is False,'wrong/failed/broader strict scope')
    if key in SCOPES:require(value.get('acceptance_scope',value.get('scope'))==SCOPES[key],'wrong leaf scope')
    if key.startswith('windows_'):
        windows_summary(key,value,source,ref)
    elif key=='composition':
        require(value.get('task_wide_accepted') is True and len(value.get('packages',[]))==27 and value.get('negative_controls')==41 and
                set(value.get('platforms',{}))=={'linux','windows','macos'},'complete 27-package three-platform composition absent')
        for platform in value['platforms'].values():
            retained=platform['named_results']['retained_g1'];require(set(retained)=={'fresh','relocated'} and retained['fresh']==retained['relocated'],'original G1 relocation absent')
            require(all(retained['fresh'][key]==count for key,count in {'chain':20,'reading_commands':1413,'annotation_view':56,
                    'annotation_export':25,'local_downloads':54,'local_regressions':7}.items()),'retained original G1 counts differ')
    elif key=='gtk41':
        require(value.get('sdk_candidate_source')==SDK and value.get('page_background_scope_passed') is True and
                value.get('settings_whole_page_palette_accepted') is True and value.get('all_original_producer_steps_passed')==34,'full GTK producer/settings absent')
        expected={'preferences-ui/result.json':41,'gtk-drop-ui/report.json':20,'gtk-drop-backend/report.json':23,'records-ui/report.json':30,
          'gtk-navigation-ui/result.json':29,'gtk-search-ui/result.json':30,'account-ui/result.json':46,'account-shelf/shelf-result.json':14,
          'account-original/report.json':20,'account-atspi-fixes/result.json':10,'account-product-ui/product-result.json':5,
          'account-fixed-ui/fixed-ui.json':24,'account-metadata-ui/metadata-ui.json':15,'account-collections-ui/collections-ui.json':27,
          'account-regressions/regressions.json':4,'gtk-drop-j03/portable.log':52,'gtk-drop-j03/gtk.log':28}
        require(value.get('retained_gate_counts')==expected and value.get('protocol_rejections')==15,'retained complete GTK gates differ')
        records=value['record_compatibility'];require(value.get('record_compatibility_accepted') is True and records['accepted'] is True and
            records['reopened_cases']==16 and records['real_kill_cases']==12 and records['protocol_rejections']==12 and records['new_sdk']==SDK and
            records['runtime_versions']=={'old':'3.40.0','new':'3.41.0'},'actual GTK old/new owner compatibility absent')
        nav=value['navigation_frame'];barrier=nav['draw_barrier']
        require(nav['accepted'] is True and nav['navigation_checks']==29 and nav['installed_f2_checks']==130 and nav['protocol_rejections']==13 and
            barrier['painted_serial']>barrier['after_draw'] and barrier['sensitive']==barrier['focused']==1 and
            barrier['frame_generation']==barrier['painted_generation'] and nav['original_source_reaccepted'] is False,'actual new sensitive native draw absent')
    elif key=='android130':
        expected={'host-session-android':16,'android-search':15,'android-navigation':18,'android-reading':16,'android-preferences':17,
                  'android-cbz-reading':10,'android-fixed-pan':8,'android-host-import':20,'android-page-theme':10}
        require(value.get('checks')==130 and len(value.get('reports',[]))==9 and
                {row['suite']:row['checks'] for row in value['reports']}==expected,'Android original120+theme10 incomplete')
    elif key in ('apple_shelf','apple_wp13'):
        require(set(value.get('platforms',{}))==set(original_apple.PLATFORMS),'whole Apple platform set missing')
        if key=='apple_shelf':
            require(value.get('problems')==[] and value.get('sdk_startup_bounded') is False and value.get('hard_performance_budget_accepted') is False,'wrong shelf budget/scope')
            require(all((row['ui_cases'],row['named_observations'],row['attachments'],row['originals'])==(7,11,14,2202) for row in value['platforms'].values()),'complete original shelf UI absent')
        else:
            require(value.get('schema')==2 and value.get('package')=='WP13 Apple host' and
                    re.fullmatch('[0-9a-f]{64}',value.get('gate_review_sha256','')),'original WP13 gate review absent')
    if key.startswith('apple_') and key not in ('apple_shelf','apple_wp13','apple_mapping'):
        rows=value.get('artifacts',[]);sdks=[row['reports']['sdk'] for row in rows if '-sdk-' in row['name']]
        require(len(sdks)==2 and all(row['sdk_version']=='3.41.0' and row['abi']==1 for row in sdks),'actual Apple SDK3.41 identities missing')
        uis=[row['reports']['ui'] for row in rows if '-ui-' in row['name']]
        require(len(uis)==3 and {row['platform'] for row in uis}==set(original_apple.PLATFORMS),'whole native Apple UI platform set absent')
        count={'apple_records':7,'apple_navigation':6,'apple_search':4,'apple_page_theme':4}[key]
        require(all(len(row['cases'])==count and all(case['result']=='Passed' for case in row['cases']) for row in uis),'original Apple UI cases missing/failed')
    if key=='apple_page_theme':
        native=[row['reports']['native'] for row in rows if '-native-' in row['name']]
        require(len(native)==1 and native[0]['accepted'] is True and native[0]['original_on_off_exact'] is True and
                native[0]['mixed_version_rejections']==5 and native[0]['sdk_version']=='3.41.0' and
                native[0]['sdk_abi']==1 and native[0]['old_340_migration_tested'] is False,'original theme native controls absent')
        for mode,count in (('on',37),('off',10)):
            report=native[0]['reports'][mode]
            require(report['accepted'] is True and report['theme_enabled']==(mode=='on') and
                    len(report['checks'])==len({row['id'] for row in report['checks']})==count and
                    all(row['passed'] is True for row in report['checks']),'original theme named native checks incomplete')
        publication=[row['reports']['initialization_and_publication'] for row in rows if '-fast-import-' in row['name']]
        require(len(publication)==1,'actual initialization/publication cases absent')
        report=publication[0]
        require(report['accepted_fast_import_fixture_only'] is True and len(report['cases'])==2 and
                all(row['result']=='Passed' for row in report['cases']) and report['sdk_producer_source']==source and
                report['sdk_producer_run']==ref['run_id'] and report['sdk_producer_attempt']==ref['attempt'] and
                report['provider']['static_sdk_linked'] is False,'actual same-source initialization/publication cases incomplete')


def windows_summary(key,value,source,ref):
    require(value.get('sdk_version')=='3.41.0' and value.get('sdk_abi')==1 and
            value.get('original_judges_preserved') is True and value.get('protocol_rejections')==13,
            'complete original Windows strict judges/SDK identity absent')
    identity=value['identity'];files=identity['files']
    require(identity['source_sha']==source and str(identity['run_id'])==str(ref['run_id']) and
            str(identity['attempt'])==str(ref['attempt']) and identity['sdk_version']=='3.41.0' and
            identity['sdk_abi']==1 and identity['sdk_source']==SDK and identity['baseline_sdk_version']=='3.40.0' and
            identity['baseline_source']=='9854061be331fe603a1822d9b2b36ee357154927' and
            identity['complete_product'] is False and identity['full_host_options']==
            {name:True for name in ('SEARCH','NAVIGATION','RECORDS','IMPORT_ORGANIZE','PREFERENCES')},
            'one full native Windows host and independent old SDK baseline absent')
    expected={'production','packaged_production','f3_production','shelf_review','atomic_review','old_veto_control',
              'baseline','production_map','atomic_map','control_map','baseline_map','host_cache','baseline_cache',
              'sdk_header','sdk_config','sdk_version','baseline_header','baseline_config','baseline_version'}
    require(set(files)==expected and all(positive(row['bytes']) and isinstance(row['path'],str) and
            re.fullmatch('[0-9a-f]{64}',row['sha256']) for row in files.values()),'actual Windows file identity inventory incomplete')
    product=files['production']['sha256'];review=files['atomic_review']['sha256'];control=files['old_veto_control']['sha256']
    require(product==files['packaged_production']['sha256']==files['f3_production']['sha256']==value['consumer_sha256'] and
            len({files[name]['sha256'] for name in ('production','shelf_review','atomic_review','old_veto_control','baseline')})==5 and
            review==value['atomic_review_sha256'] and control==value['old_veto_control_sha256'] and
            files['production_map']['sha256']==value['production_map_sha256'],'substituted/split Windows production or control identity')
    proof=value['catalog_identity_adapter']
    require(proof['source_sha']==source and str(proof['run_id'])==str(ref['run_id']) and str(proof['attempt'])==str(ref['attempt']) and
            proof['changed_literal_count']==1 and proof['expected_runtime']=='3.41.0' and proof['original_assertions_retained'] is True and
            all(re.fullmatch('[0-9a-f]{64}',proof[field]) for field in ('original_source_sha256','adapted_source_sha256')) and
            proof['original_source_sha256']!=proof['adapted_source_sha256'],'original catalog identity adaptation absent')
    if key=='windows_full_f3':
        counts={'f3_checks':25,'original_f1_checks':264,'original_f2_checks':130,'navigation_checks':31,
                'records_checks':32,'original_ui158':158,'original_j01_checks':47,'original_j10_checks':21}
        require(all(value.get(name)==count for name,count in counts.items()),'full retained Windows suites incomplete')
        retained=value['retained_summaries']
        require(set(retained)=={'winsearch-summary','winnav-summary','winrecords-summary','wprefs-summary'},'original recursive strict summaries absent')
        for row in [*retained.values(),value['import_organize_summary']]:
            require(row['accepted'] is True and not row.get('problems') and row['source_sha']==source and
                    str(row['run_id'])==str(ref['run_id']) and str(row['attempt'])==str(ref['attempt']) and
                    row['consumer_sha256']==product,'foreign/failed original Windows strict result')
        require(positive(value['import_organize_checks']) and
                value['import_organize_summary']['ui_checks']==value['import_organize_checks'], 'full import organization suite missing')
    else:
        require(value['checks']==13 and value['original_atomic_protocol_rejections']==9 and
                value['original_f3_suite_accepted'] is False,'actual atomic13 control scope incomplete')
        path=ROOT/'tests/reader_windows_preferences/verify_commit.py'
        module_spec=importlib.util.spec_from_file_location('native_original_atomic',path)
        original=importlib.util.module_from_spec(module_spec);module_spec.loader.exec_module(original)
        original.validate(value['atomic_report'],source,ref['run_id'],ref['attempt'],review,control)


def load_summary(key,contract,ref,run,jobs,selected,summary_job,source):
    name=contract['summary_name'].format(run=ref['run_id'],attempt=ref['attempt']);meta=selected[name]
    bundle=Bundle(meta)
    try:value=bundle.report(contract['report'])
    finally:bundle.close()
    basic_summary(key,value,source,ref);upstream={name:row for name,row in selected.items() if row['id']!=meta['id']}
    if key in ('gtk41','android130') or key.startswith('windows_'):bind_declared([value['artifact']],upstream)
    elif key!='apple_wp13':bind_declared(value['artifacts'],upstream)
    # WP13's actual schema has no copied API manifest. Keep that limitation:
    # authenticate its original strict result and the complete live metadata,
    # never manufacture a manifest or a mapping summary.
    if 'jobs' in value:
        actual={row['id']:row for row in jobs if row['id']!=summary_job['id'] and row['conclusion']!='skipped'}
        if key=='composition':actual={row['id']:row for row in jobs if row['name'].startswith('one-prefix composition (')}
        bind_jobs(value['jobs'],actual)
    if key=='gtk41':require(value['host_job_id']==next(row['id'] for row in jobs if row['name']=='GTK 3.41 complete retained suites and actual owner record compatibility'),'GTK actual host job differs')
    if key=='android130':require(value['producer_job']==next(row['id'] for row in jobs if row['name']=='android'),'Android producer job differs')
    if key.startswith('windows_'):
        require(value['producer_job']==next(row['id'] for row in jobs if row['name']=='installed F1 and native Windows search controls and lifecycle'),
                'Windows complete native producer differs')
    return dict(mode='actual original strict summary ZIP plus complete current-attempt metadata',summary_artifact=compact(meta),
                upstream_artifacts=[compact(row) for row in upstream.values()],summary_scope=value.get('acceptance_scope',value.get('scope',value.get('package'))),
                original_strict_accepted=True,upstream_manifest_present=key!='apple_wp13')


def compact(row):return {key:row[key] for key in ('id','name','size_in_bytes','digest','expires_at','created_at')}


def finish(result):
    require(set(result['leaves'])==set(REQUIRED),'mandatory result slot removed')
    require(set(result['product_conditions'])==set(PRODUCT_REQUIRED),'required product condition removed')
    result['pending_contracts']=[key for key in WINDOWS_CONTRACTS if WINDOWS_CONTRACTS[key] is None]
    for key in result['pending_contracts']:
        result['leaves'][key].update(status='pending',reason='required Windows contract is not yet pinned; root review required')
    result['accepted']=all(result['leaves'][key]['status']=='verified' for key in REQUIRED) and not result['problems'] and not result['pending_contracts']
    result['pending']=[key for key in REQUIRED if result['leaves'][key]['status']=='pending']
    result['refused']=[key for key in REQUIRED if result['leaves'][key]['status']=='refused']
    result['pending_product_conditions']=[key for key in PRODUCT_REQUIRED if result['product_conditions'][key]['status']=='pending']
    return result


def collect(manifest,source):
    result=dict(accepted=False,scope='declared complete native UI foundation workflows at one exact common source',source_sha=source,
      verifier_source=os.environ['GITHUB_SHA'],validation_run_id=os.environ['GITHUB_RUN_ID'],validation_attempt=os.environ['GITHUB_RUN_ATTEMPT'],
      leaves={key:dict(required=True,status='pending',reason='run not supplied') for key in REQUIRED},
      product_conditions={key:dict(required_for_product=True,status='pending',reason='reviewed same-common-source contract and evidence not supplied') for key in PRODUCT_REQUIRED},
      declared_history=[],problems=[],upgrade_accepted=False,bidirectional_accepted=False,physical_device_execution=False,
      performance_accepted=False,complete_product=False)
    try:conditions=validate_input(manifest,source)
    except (ValueError,KeyError,TypeError) as error:
        result['problems'].append(str(error));return finish(result)
    result['declared_history']=[dict(declared=row,counts_for_current_source=False,accepted_by_this_collector=False) for row in manifest.get('history',[])]
    for key,ref in conditions.items():
        if ref is not None:result['product_conditions'][key]['provided_run']=ref
    for key in REQUIRED:
        ref=manifest['runs'][key]
        contract=WINDOWS_CONTRACTS.get(key) if key in WINDOWS_CONTRACTS else SPECS[key]
        if contract is None:
            result['leaves'][key].update(reason='required Windows contract is not yet pinned; root review required',provided_run=ref);continue
        if ref is None:continue
        try:
            run=fetch('actions/runs/'+str(ref['run_id']))
            jobs=pages('actions/runs/%d/attempts/%d/jobs'%(ref['run_id'],ref['attempt']),'jobs')
            artifacts=pages('actions/runs/%d/artifacts'%ref['run_id'],'artifacts')
            selected,summary=validate_metadata(key,contract,ref,run,jobs,artifacts,source)
            if key.startswith('apple_') and key!='apple_page_theme':
                original_apple.check_artifacts(key[6:],list(selected.values()),source,ref['run_id'],ref['attempt'])
            if key=='apple_mapping':
                verified=[original_apple.verify_bundle('mapping',row,source,ref['run_id'],ref['attempt']) for row in selected.values()]
                proof=dict(mode='original per-artifact mapping collectors; no strict summary exists',original_strict_summary_exists=False,
                           artifacts=verified,original_collectors='tests/reader_hosts_integration/apple.py:verify_bundle(mapping)')
            else:proof=load_summary(key,contract,ref,run,jobs,selected,summary,source)
            result['leaves'][key]=dict(required=True,status='verified',run_id=ref['run_id'],attempt=ref['attempt'],workflow=contract['workflow'],
              jobs=[dict(id=row['id'],name=row['name'],conclusion=row['conclusion']) for row in jobs],proof=proof)
        except Exception as error:
            result['leaves'][key]=dict(required=True,status='refused',provided_run=ref,reason=type(error).__name__+': '+str(error).split('?')[0][:500])
    return finish(result)


def source_guard(source):
    require(source==os.environ['GITHUB_SHA'],'collector checkout must be the exact fixed leaf source')
    subprocess.run(['git','merge-base','--is-ancestor',BASE,source],check=True)
    subprocess.run(['git','diff','--exit-code',BASE,source,'--','apps','examples','extras','tools'],check=True)
    subprocess.run(['git','diff','--exit-code',SDK,source,'--','src','include','cmake','CMakeLists.txt','bindings','tests/fixtures','licenses'],check=True)
    subprocess.run(['git','diff','--exit-code',SCHEMA_OWNER,source,'--','apps/reader/store/001_catalog.sql'],check=True)
    header=subprocess.check_output(['git','show',source+':apps/reader/revisions/include/reader_revisions.h'],text=True)
    require('#define READER_REVISION_ANCHOR_MAX_VERSION 2u' in header,'this collector has not adopted raw selector v3')


def main():
    require(os.environ.get('GITHUB_ACTIONS')=='true','Actions only')
    parser=argparse.ArgumentParser();parser.add_argument('--self-test',action='store_true');parser.add_argument('--source');args=parser.parse_args()
    if args.self_test:
        from test_aggregate_native import run_tests
        run_tests();return 0
    require(args.source and re.fullmatch('[0-9a-f]{40}',args.source),'supply one full source SHA')
    folder=ROOT/'build/native-341-summary';folder.mkdir(parents=True,exist_ok=True)
    try:
        source_guard(args.source)
        result=collect(json.loads(os.environ['NATIVE_RUN_TABLE']),args.source)
    except Exception as error:
        result=collect(dict(source_sha=args.source,runs={key:None for key in REQUIRED}),args.source)
        result['problems'].append('source/input preflight: '+type(error).__name__+': '+str(error).split('?')[0][:500]);finish(result)
    (folder/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
    return 0 if result['accepted'] else 1


if __name__=='__main__':raise SystemExit(main())
