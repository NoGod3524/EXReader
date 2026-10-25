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
    a.basic_summary('apple_page_theme',theme,source,ref)
    wrong=copy.deepcopy(theme);wrong['artifacts'].pop();refuse('missing-apple-platform',lambda:a.basic_summary('apple_page_theme',wrong,source,ref))
    wrong=copy.deepcopy(theme);wrong['artifacts'][0]['reports']['sdk']['sdk_version']='3.40.0';refuse('old-apple-sdk-scope',lambda:a.basic_summary('apple_page_theme',wrong,source,ref))
    wrong=copy.deepcopy(theme);wrong['artifacts'][-1]['reports']['ui']['cases'][0]['result']='Skipped';refuse('skipped-apple-ui-case',lambda:a.basic_summary('apple_page_theme',wrong,source,ref))
    refuse('unreviewed-windows-schema',lambda:a.basic_summary('windows_full_f3',android,source,ref))
    result=dict(leaves={key:dict(status='verified') for key in a.REQUIRED},product_conditions={key:dict(status='pending') for key in a.PRODUCT_REQUIRED},problems=[])
    a.finish(result);a.require(result['accepted'] is False and set(result['pending_contracts'])==set(a.WINDOWS_CONTRACTS) and
        all(result['leaves'][key]['status']=='pending' for key in a.WINDOWS_CONTRACTS),'unresolved Windows contract gave green')
    wrong=copy.deepcopy(result);wrong['leaves'].pop('windows_full_f3');refuse('drop-required-slot-to-green',lambda:a.finish(wrong))
    wrong=copy.deepcopy(result);wrong['product_conditions'].pop('apple_to_android');refuse('drop-required-peer-condition',lambda:a.finish(wrong))
    a.require(a.SPECS['apple_mapping']['summary_name'] is None and len(a.expected_names('apple_mapping',a.SPECS['apple_mapping'],123,2))==6,'mapping summary invented')
    a.require(len(rejected)==57,'a protocol refusal control was omitted')
    print('native upper collector protocol negatives: '+str(len(rejected))+' actual rejections; synthetic fixtures only',flush=True)


if __name__=='__main__':run_tests()
