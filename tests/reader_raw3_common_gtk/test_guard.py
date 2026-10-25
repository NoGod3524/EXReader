"""Actions-only refusal controls for new source-gate semantics and exact projection."""
import copy
import os
import guard
from retained import validate_retained_proof


def refused(call):
    try:call()
    except RuntimeError:return
    raise AssertionError('Malformed common GTK source proof accepted')


def main():
    assert os.environ.get('GITHUB_ACTIONS')=='true'
    baseline={'examples/linux/reading.c':'100644 blob owner','tests/old_judge.py':'100644 blob judge'}
    valid={**baseline,**{path:'100644 blob wrapper' for path in guard.NEW_FILES}}
    guard.validate_tree(baseline,valid)
    tree_refusals=0
    for path in baseline:
        bad=dict(valid);bad[path]='100644 blob changed'
        refused(lambda:guard.validate_tree(baseline,bad));tree_refusals+=1
        bad=dict(valid);del bad[path]
        refused(lambda:guard.validate_tree(baseline,bad));tree_refusals+=1
    for mode in ('120000','100755','160000'):
        bad=dict(valid);bad[guard.WORKFLOW]=mode+' blob wrapper'
        refused(lambda:guard.validate_tree(baseline,bad));tree_refusals+=1
    bad=dict(valid);bad['examples/new_owner.c']='100644 blob added'
    refused(lambda:guard.validate_tree(baseline,bad));tree_refusals+=1
    bad=dict(valid);del bad[guard.WORKFLOW]
    refused(lambda:guard.validate_tree(baseline,bad));tree_refusals+=1

    source='a'*40;run=1;attempt=2
    header=dict(source_sha=source,run_id=run,attempt=attempt,guard_kind=guard.GUARD_KIND,guard_schema=1,
      composition_source=guard.BASE,gtk_source_pin=guard.GTK_PIN,gtk_tested_source=guard.GTK_TESTED,
      workflow=guard.WORKFLOW,original_workflow=guard.ORIGINAL,accepted=True,source_guard_passed=True,
      runtime_accepted=False,old_guard_executed=False,all_existing_blobs_and_modes_unchanged=True,
      original_gtk_workflow_projection_exact=True,allowed_new_files=sorted(guard.NEW_FILES))
    guard.validate_header(header,source,run,attempt)
    mutations=[('guard_kind','old-gtk-source-guard'),('guard_schema',0),('guard_schema',True),('composition_source','foreign'),
      ('gtk_source_pin','foreign'),('gtk_tested_source','foreign'),('source_sha','foreign'),
      ('run_id',0),('attempt',0),('workflow',guard.ORIGINAL),('original_workflow','foreign'),
      ('accepted',False),('source_guard_passed',False),('runtime_accepted',True),('old_guard_executed',True),
      ('all_existing_blobs_and_modes_unchanged',False),('original_gtk_workflow_projection_exact',False),
      ('allowed_new_files',[]),('allowed_new_files',sorted(guard.NEW_FILES|{'examples/new_owner.c'}))]
    for key,replacement in mutations:
        bad=copy.deepcopy(header);bad[key]=replacement
        refused(lambda:guard.validate_header(bad,source,run,attempt))

    marker=dict(guard_kind=guard.GUARD_KIND,composition_source=guard.BASE,
                common_source_guard_verified=True,old_guard_executed=False)
    retained=dict(accepted=True,source_sha=source,run_id=run,attempt=attempt,
                  record_compatibility=dict(marker),navigation_frame=dict(marker))
    validate_retained_proof(retained,source,run,attempt)
    strict_refusals=0
    for name in ('record_compatibility','navigation_frame'):
        for key,replacement in (('guard_kind','old-guard'),('composition_source','foreign'),
                                ('common_source_guard_verified',False),('old_guard_executed',True)):
            bad=copy.deepcopy(retained);bad[name][key]=replacement
            refused(lambda:validate_retained_proof(bad,source,run,attempt));strict_refusals+=1

    original=guard.git('show',guard.GTK_PIN+':'+guard.ORIGINAL).decode('utf-8')
    current=(guard.ROOT/guard.WORKFLOW).read_text(encoding='utf-8')
    assert guard.project_workflow(current)==original
    changes=[('timeout-minutes: 65','timeout-minutes: 2'),
      ('python3 tests/reader_gtk_raw3/run.py --mode "$MODE"','echo omitted-actual-owner'),
      ('include-hidden-files: true','include-hidden-files: false'),
      ('EXR_SDK_VERSION','FORGED_SDK_VERSION'),
      ('--fixtures build/gtk-raw3/raw-ui-fixtures','--fixtures fabricated')]
    for before,after in changes:
        assert before in current
        assert guard.project_workflow(current.replace(before,after,1))!=original
    refused(lambda:guard.project_workflow(current.replace(guard.SELF_TEST_STEP,'',1)))
    refused(lambda:guard.project_workflow(current.replace('python3 tests/reader_raw3_common_gtk/guard.py','echo fake-guard',1)))
    print('Common GTK guard refusals: tree='+str(tree_refusals)+' header='+str(len(mutations))+
          ' retained-kind='+str(strict_refusals)+' altered-original-projection='+str(len(changes))+
          ' projection-shape=2; no runtime grant',flush=True)


if __name__=='__main__':main()
