"""Synthetic protocol controls only; never reader/platform acceptance evidence."""
import copy
import os
import aggregate_native as a


def run_tests():
    a.require(os.environ.get('GITHUB_ACTIONS')=='true','Actions only')
    rejected=[]
    def refuse(label,fn):
        try:fn()
        except (ValueError,KeyError,TypeError):rejected.append(label);return
        raise AssertionError('accepted protocol negative: '+label)
    source='a'*40;ref=dict(run_id=123,attempt=2)
    manifest=dict(source_sha=source,runs={key:None for key in a.REQUIRED})
    a.validate_input(manifest,source)
    wrong=copy.deepcopy(manifest);wrong['runs'].pop('windows_atomic13');refuse('missing-required-windows',lambda:a.validate_input(wrong,source))
    wrong=copy.deepcopy(manifest);wrong['runs'].pop('apple_page_theme');refuse('six-apple-instead-of-seven',lambda:a.validate_input(wrong,source))
    wrong=copy.deepcopy(manifest);wrong['runs']['composition']={'linux':ref,'macos':ref,'windows':ref};refuse('platform-spliced-input',lambda:a.validate_input(wrong,source))
    wrong=copy.deepcopy(manifest);wrong['runs']['gtk41']=ref;wrong['runs']['android130']=ref;refuse('duplicate-whole-run',lambda:a.validate_input(wrong,source))
    coupled=copy.deepcopy(manifest);coupled['runs']['windows_full_f3']=dict(ref);coupled['runs']['windows_atomic13']=dict(ref)
    a.validate_input(coupled,source)
    wrong=copy.deepcopy(coupled);wrong['runs']['windows_atomic13']['attempt']=1;refuse('split-Windows-attempt',lambda:a.validate_input(wrong,source))
    wrong=copy.deepcopy(coupled);wrong['runs']['apple_records']=dict(ref);refuse('third-scope-reuses-Windows-run',lambda:a.validate_input(wrong,source))
    refuse('foreign-fixed-source',lambda:a.validate_input(manifest,'b'*40))
    refuse('boolean-run-id',lambda:a.ref_check(dict(run_id=True,attempt=1)))
    refuse('implicit-latest-attempt',lambda:a.ref_check(dict(run_id=123)))
    refuse('per-leaf-artifact-substitution',lambda:a.ref_check(dict(run_id=123,attempt=2,artifact_id=4)))
    contract=a.SPECS['composition']
    run=dict(id=123,head_sha=source,run_attempt=2,path=contract['workflow'],status='completed',conclusion='success')
    labels=['authenticate exact candidate and complete original job',*('one-prefix composition ('+p+')' for p in ('linux','windows','macos')),contract['summary_job']]
    jobs=[dict(id=i+1,name=name,head_sha=source,run_id=123,run_attempt=2,status='completed',conclusion='success',
               started_at='2026-01-01T00:00:00Z' if i<4 else '2026-01-01T00:03:00Z',
               completed_at='2026-01-01T00:02:00Z' if i<4 else '2026-01-01T00:04:00Z',
               steps=[dict(name='real job check',conclusion='success')]) for i,name in enumerate(labels)]
    summary_name=contract['summary_name'].format(run=123,attempt=2)
    artifacts=[dict(id=i+10,name=name,size_in_bytes=100,digest='sha256:'+'c'*64,expired=False,
                    expires_at='2099-01-01T00:00:00Z',created_at='2026-01-01T00:03:30Z' if name==summary_name else '2026-01-01T00:01:30Z',
                    workflow_run=dict(id=123,head_sha=source))
               for i,name in enumerate(sorted(a.expected_names('composition',contract,123,2)))]
    def verify(r=run,j=jobs,ar=artifacts,rf=ref):return a.validate_metadata('composition',contract,rf,r,j,ar,source)
    selected,_=verify()
    for field,value in [('head_sha','b'*40),('path','.github/workflows/other.yml'),('run_attempt',3),('status','in_progress'),('conclusion','failure')]:
        wrong=copy.deepcopy(run);wrong[field]=value;refuse('run-'+field,lambda wrong=wrong:verify(r=wrong))
    refuse('old-successful-attempt',lambda:verify(rf=dict(run_id=123,attempt=1)))
    refuse('missing-platform-job',lambda:verify(j=jobs[:-1]))
    for field,value in [('id',1),('name',jobs[0]['name']),('head_sha','b'*40),('run_id',456),('run_attempt',1),('status','queued'),('conclusion','failure')]:
        wrong=copy.deepcopy(jobs);wrong[1][field]=value;refuse('job-'+field,lambda wrong=wrong:verify(j=wrong))
    wrong=copy.deepcopy(jobs);wrong[1]['steps'][0]['conclusion']='failure';refuse('hidden-step-failure',lambda:verify(j=wrong))
    refuse('missing-raw-artifact',lambda:verify(ar=artifacts[:-1]))
    wrong=copy.deepcopy(artifacts);wrong.append(dict(wrong[0],id=999));refuse('duplicate-artifact-name',lambda:verify(ar=wrong))
    for field,value in [('id',True),('size_in_bytes',0),('digest','sha256:'+'z'*64),('expired',True),('expires_at','2000-01-01T00:00:00Z'),
                        ('created_at','2025-01-01T00:00:00Z')]:
        wrong=copy.deepcopy(artifacts);wrong[0][field]=value;refuse('artifact-'+field,lambda wrong=wrong:verify(ar=wrong))
    wrong=copy.deepcopy(artifacts);wrong[0]['workflow_run']['head_sha']='b'*40;refuse('foreign-artifact-source',lambda:verify(ar=wrong))
    wrong=copy.deepcopy(artifacts);wrong[0]['name']=wrong[0]['name'].replace('-123-2','-123-1');refuse('old-attempt-artifact-name',lambda:verify(ar=wrong))
    upstream={key:row for key,row in selected.items() if key!=summary_name}
    declarations=[{key:row[key] for key in ('id','name','size_in_bytes','digest','expires_at')} for row in upstream.values()]
    a.bind_declared(declarations,upstream)
    refuse('missing-upstream-manifest-row',lambda:a.bind_declared(declarations[:-1],upstream))
    for field,value in [('id',999),('size_in_bytes',3),('digest','sha256:'+'d'*64),('expires_at','2098-01-01T00:00:00Z')]:
        wrong=copy.deepcopy(declarations);wrong[0][field]=value;refuse('strict-manifest-'+field,lambda wrong=wrong:a.bind_declared(wrong,upstream))
    declared_jobs=copy.deepcopy(jobs[1:4]);live_jobs={row['id']:row for row in jobs[1:4]};a.bind_jobs(declared_jobs,live_jobs)
    refuse('duplicate-summary-job',lambda:a.bind_jobs(declared_jobs+[declared_jobs[0]],live_jobs))
    wrong=copy.deepcopy(declared_jobs);wrong[0]['run_attempt']=1;refuse('old-attempt-summary-job',lambda:a.bind_jobs(wrong,live_jobs))
    wrong=copy.deepcopy(declared_jobs);wrong[0]['head_sha']='b'*40;refuse('foreign-summary-job',lambda:a.bind_jobs(wrong,live_jobs))
    counts={'host-session-android':16,'android-search':15,'android-navigation':18,'android-reading':16,'android-preferences':17,
            'android-cbz-reading':10,'android-fixed-pan':8,'android-host-import':20,'android-page-theme':10}
    android=dict(accepted=True,source_sha=source,run_id=123,attempt=2,scope=a.SCOPES['android130'],checks=130,
                 reports=[dict(suite=key,checks=count) for key,count in counts.items()],physical_device=False,complete_product=False,performance_accepted=False)
    a.basic_summary('android130',android,source,ref)
    for field,value in [('source_sha','b'*40),('attempt',1),('run_id',456),('scope','partial sampler'),('accepted',False),
                        ('checks',120),('reports',[]),('complete_product',True),('physical_device',True),('performance_accepted',True)]:
        wrong=copy.deepcopy(android);wrong[field]=value;refuse('summary-'+field,lambda wrong=wrong:a.basic_summary('android130',wrong,source,ref))
    theme=dict(accepted=True,source_sha=source,run_id=123,attempt=2,scope=a.SCOPES['apple_page_theme'],physical_device_execution=False,
               complete_product=False,artifacts=[dict(name='apple-theme-sdk-'+p,reports=dict(sdk=dict(sdk_version='3.41.0',abi=1))) for p in ('macos','iphonesimulator')]+
                 [dict(name='apple-theme-ui-'+p,reports=dict(ui=dict(platform=p,cases=[dict(result='Passed') for _ in range(4)]))) for p in a.original_apple.PLATFORMS])
    theme['artifacts'] += [dict(name='apple-theme-native-123-2',reports=dict(native=dict(accepted=True,original_on_off_exact=True,
        mixed_version_rejections=5,sdk_version='3.41.0',sdk_abi=1,old_340_migration_tested=False,
        reports={mode:dict(accepted=True,theme_enabled=mode=='on',checks=[dict(id=str(i),passed=True) for i in range(count)])
                 for mode,count in (('on',37),('off',10))}))),
        dict(name='apple-theme-fast-import-123-2',reports=dict(initialization_and_publication=dict(
            accepted_fast_import_fixture_only=True,cases=[dict(result='Passed'),dict(result='Passed')],sdk_producer_source=source,
            sdk_producer_run=123,sdk_producer_attempt=2,provider=dict(static_sdk_linked=False))))]
    a.basic_summary('apple_page_theme',theme,source,ref)
    wrong=copy.deepcopy(theme);wrong['artifacts'].pop(4);refuse('missing-apple-platform',lambda:a.basic_summary('apple_page_theme',wrong,source,ref))
    wrong=copy.deepcopy(theme);wrong['artifacts'][0]['reports']['sdk']['sdk_version']='3.40.0';refuse('old-apple-sdk-scope',lambda:a.basic_summary('apple_page_theme',wrong,source,ref))
    wrong=copy.deepcopy(theme);wrong['artifacts'][4]['reports']['ui']['cases'][0]['result']='Skipped';refuse('skipped-apple-ui-case',lambda:a.basic_summary('apple_page_theme',wrong,source,ref))
    wrong=copy.deepcopy(theme);wrong['artifacts'].pop();refuse('missing-initialization-publication',lambda:a.basic_summary('apple_page_theme',wrong,source,ref))
    wrong=copy.deepcopy(theme);wrong['artifacts'][-1]['reports']['initialization_and_publication']['cases'][0]['result']='Skipped';refuse('skipped-publication-case',lambda:a.basic_summary('apple_page_theme',wrong,source,ref))
    wrong=copy.deepcopy(theme);wrong['artifacts'][-2]['reports']['native']['reports']['on']['checks'].pop();refuse('missing-native-theme-case',lambda:a.basic_summary('apple_page_theme',wrong,source,ref))
    wrong=copy.deepcopy(theme);wrong['artifacts'].pop(-2);refuse('missing-native-theme-controls',lambda:a.basic_summary('apple_page_theme',wrong,source,ref))
    theme_contract=a.SPECS['apple_page_theme']
    theme_run=dict(run,path=theme_contract['workflow'])
    theme_jobs=[]
    for i in range(8):
        job=copy.deepcopy(jobs[0] if i<7 else jobs[-1])
        job.update(id=100+i,name='theme-producer-'+str(i) if i<7 else theme_contract['summary_job'])
        if i<2:job['steps']=[dict(name=theme_contract['guard'][0],conclusion='success')]
        theme_jobs.append(job)
    theme_summary=theme_contract['summary_name'].format(run=123,attempt=2)
    theme_artifacts=[]
    for i,name in enumerate(sorted(a.expected_names('apple_page_theme',theme_contract,123,2))):
        row=copy.deepcopy(artifacts[0]);row.update(id=100+i,name=name,
            created_at='2026-01-01T00:03:30Z' if name==theme_summary else '2026-01-01T00:01:30Z')
        theme_artifacts.append(row)
    def verify_theme(j=theme_jobs,ar=theme_artifacts):
        return a.validate_metadata('apple_page_theme',theme_contract,ref,theme_run,j,ar,source)
    verify_theme()
    refuse('old-seven-job-theme-contract',lambda:verify_theme(j=theme_jobs[:-2]+theme_jobs[-1:]))
    fast=[row for row in theme_artifacts if '-fast-import-' in row['name']][0]
    refuse('missing-fast-import-artifact',lambda:verify_theme(ar=[row for row in theme_artifacts if row['id']!=fast['id']]))
    wrong=copy.deepcopy(theme_jobs);wrong[0]['steps'][0]['conclusion']='skipped'
    refuse('skipped-theme-source-guard',lambda:verify_theme(j=wrong))
    wrong=copy.deepcopy(theme_artifacts)
    next(row for row in wrong if '-fast-import-' in row['name'])['name']=fast['name'].replace('-123-2','-123-1')
    refuse('old-attempt-fast-import-artifact',lambda:verify_theme(ar=wrong))
    refuse('unreviewed-windows-schema',lambda:a.basic_summary('windows_full_f3',android,source,ref))
    file_names=('production','packaged_production','f3_production','shelf_review','atomic_review','old_veto_control','baseline',
                'production_map','atomic_map','control_map','baseline_map','host_cache','baseline_cache','sdk_header','sdk_config',
                'sdk_version','baseline_header','baseline_config','baseline_version')
    files={name:dict(path=name,bytes=100,sha256=format(i+1,'064x')) for i,name in enumerate(file_names)}
    for name in ('packaged_production','f3_production'):files[name]['sha256']=files['production']['sha256']
    identity=dict(source_sha=source,run_id=123,attempt=2,sdk_version='3.41.0',sdk_abi=1,sdk_source=a.SDK,
        baseline_sdk_version='3.40.0',baseline_source='9854061be331fe603a1822d9b2b36ee357154927',complete_product=False,
        full_host_options={name:True for name in ('SEARCH','NAVIGATION','RECORDS','IMPORT_ORGANIZE','PREFERENCES')},files=files)
    product=files['production']['sha256'];review=files['atomic_review']['sha256'];control=files['old_veto_control']['sha256']
    common=dict(accepted=True,source_sha=source,run_id=123,attempt=2,sdk_version='3.41.0',sdk_abi=1,complete_product=False,
        original_judges_preserved=True,protocol_rejections=13,identity=identity,consumer_sha256=product,
        atomic_review_sha256=review,old_veto_control_sha256=control,production_map_sha256=files['production_map']['sha256'],
        catalog_identity_adapter=dict(source_sha=source,run_id=123,attempt=2,changed_literal_count=1,expected_runtime='3.41.0',
            original_assertions_retained=True,original_source_sha256='d'*64,adapted_source_sha256='e'*64))
    retained=dict(accepted=True,source_sha=source,run_id=123,attempt=2,consumer_sha256=product)
    full=dict(common,scope=a.SCOPES['windows_full_f3'],f3_checks=25,original_f1_checks=264,original_f2_checks=130,
        navigation_checks=31,records_checks=32,original_ui158=158,original_j01_checks=47,original_j10_checks=21,
        import_organize_checks=10,import_organize_summary=dict(retained,ui_checks=10),
        retained_summaries={name:dict(retained) for name in ('winsearch-summary','winnav-summary','winrecords-summary','wprefs-summary')})
    names=[role+suffix for role in ('empty','txt','epub','pdf') for suffix in
           ('-before-save-cancel-retains','-after-save-cancel-publishes','-reopened-committed-choice')]+['old-post-save-veto-control-rejected']
    boundary=dict(common,scope=a.SCOPES['windows_atomic13'],checks=13,original_atomic_protocol_rejections=9,
        original_f3_suite_accepted=False,atomic_report=dict(accepted=True,source_sha=source,run_id=123,attempt=2,count=13,
            checks=[dict(name=name,passed=True,pid=1) for name in names],consumer_sha256=review,control_sha256=control,
            complete_product=False,original_f3_suite_accepted=False))
    a.basic_summary('windows_full_f3',full,source,ref);a.basic_summary('windows_atomic13',boundary,source,ref)
    def windows_negative(label,record,path,new_value,key='windows_full_f3'):
        wrong=copy.deepcopy(record);target=wrong
        for part in path[:-1]:target=target[part]
        target[path[-1]]=new_value
        refuse(label,lambda:a.basic_summary(key,wrong,source,ref))
    for label,path,new_value in (
        ('missing-full-F3',('f3_checks',),24),('missing-full-host-option',('identity','full_host_options'),{}),
        ('split-F3-production',('identity','files','f3_production','sha256'),'f'*64),
        ('control-equals-review',('identity','files','old_veto_control','sha256'),review),
        ('missing-sdk-header-digest',('identity','files','sdk_header','sha256'),''),
        ('catalog-rewrites-more-than-identity',('catalog_identity_adapter','changed_literal_count'),2),
        ('foreign-retained-attempt',('retained_summaries','wprefs-summary','attempt'),1),
        ('missing-import-suite',('import_organize_checks',),0),('old-Windows-SDK',('sdk_version',),'3.40.0'),
        ('missing-identity-refusal',('protocol_rejections',),12),('substituted-production-map',('production_map_sha256',),'f'*64)):
        windows_negative(label,full,path,new_value)
    for label,path,new_value in (
        ('atomic12-instead-of13',('checks',),12),('failed-actual-atomic-case',('atomic_report','checks',0,'passed'),False),
        ('foreign-atomic-source',('atomic_report','source_sha'),'b'*40),('substituted-atomic-control',('atomic_report','control_sha256'),'f'*64)):
        windows_negative(label,boundary,path,new_value,'windows_atomic13')
    result=dict(leaves={key:dict(status='pending' if key in a.WINDOWS_CONTRACTS else 'verified') for key in a.REQUIRED},
                product_conditions={key:dict(status='pending') for key in a.PRODUCT_REQUIRED},problems=[])
    a.finish(result);a.require(result['accepted'] is False and result['pending_contracts']==[] and
        all(result['leaves'][key]['status']=='pending' for key in a.WINDOWS_CONTRACTS),'unresolved Windows contract gave green')
    wrong=copy.deepcopy(result);wrong['leaves'].pop('windows_full_f3');refuse('drop-required-slot-to-green',lambda:a.finish(wrong))
    wrong=copy.deepcopy(result);wrong['product_conditions'].pop('apple_to_android');refuse('drop-required-peer-condition',lambda:a.finish(wrong))
    a.require(a.SPECS['apple_mapping']['summary_name'] is None and len(a.expected_names('apple_mapping',a.SPECS['apple_mapping'],123,2))==6,'mapping summary invented')
    a.require(len(rejected)==82,'a protocol refusal control was omitted')
    print('native upper collector protocol negatives: '+str(len(rejected))+' actual rejections; synthetic fixtures only',flush=True)


if __name__=='__main__':run_tests()
