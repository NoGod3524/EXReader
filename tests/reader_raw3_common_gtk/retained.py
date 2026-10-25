"""Run every sealed retained judge with an explicitly authenticated new source gate."""
import json
import os
import sys
import guard

_OLD=guard.load('sealed_gtk_raw3_retained_entry','tests/reader_gtk_raw3/retained.py')
RAW_JOB=_OLD.RAW_JOB
FINAL_JOB=_OLD.FINAL_JOB


def install_common_contracts():
    # Imports requiring Pillow remain confined to the original OFF image job.
    sys.path.insert(0,str(guard.ROOT/'tests/reader_gtk_record_compatibility'))
    import compatibility_contract
    sys.path.insert(0,str(guard.ROOT/'tests/reader_gtk_341_final'))
    import navigation_contract
    original_compatibility=compatibility_contract.authenticate
    original_navigation=navigation_contract.authenticate
    navigation_contract.MERGED=guard.BASE

    def authenticate_compatibility(raw,source,run,attempt):
        value=json.loads(raw('gtk-record-compatibility-guard.json'))
        guard.validate_compatibility_report(value,source,run,attempt)
        proof=original_compatibility(raw,source,run,attempt)
        proof.update(guard_kind=guard.GUARD_KIND,composition_source=guard.BASE,
                     common_source_guard_verified=True,old_guard_executed=False)
        return proof

    def authenticate_navigation(raw,source,run,attempt,program):
        value=json.loads(raw('gtk-341-source-guard.json'))
        guard.validate_source_report(value,source,run,attempt)
        proof=original_navigation(raw,source,run,attempt,program)
        proof.update(guard_kind=guard.GUARD_KIND,composition_source=guard.BASE,
                     common_source_guard_verified=True,old_guard_executed=False)
        return proof

    compatibility_contract.authenticate=authenticate_compatibility
    navigation_contract.authenticate=authenticate_navigation


def validate_retained_proof(value,source,run,attempt):
    guard.require(value.get('accepted') is True and value.get('source_sha')==source and
        str(value.get('run_id'))==str(run) and str(value.get('attempt'))==str(attempt),
        'Wrong actual retained common-source result')
    for name in ('record_compatibility','navigation_frame'):
        proof=value.get(name,{})
        guard.require(proof.get('guard_kind')==guard.GUARD_KIND and
            proof.get('composition_source')==guard.BASE and proof.get('common_source_guard_verified') is True and
            proof.get('old_guard_executed') is False,'New common source guard was not authenticated: '+name)


def annotate(path,*,off):
    value=json.loads(path.read_text(encoding='utf-8'))
    source,run,attempt=(os.environ[key] for key in ('GITHUB_SHA','GITHUB_RUN_ID','GITHUB_RUN_ATTEMPT'))
    if off:validate_retained_proof(value,source,run,attempt)
    else:
        validate_retained_proof(value.get('off_strict_report',{}),source,run,attempt)
        guard.require(value.get('accepted') is True and value.get('production_pin')==guard.BASE,
                      'Compact strict result does not bind the actual common baseline')
    value.update(guard_kind=guard.GUARD_KIND,composition_source=guard.BASE,gtk_source_pin=guard.GTK_PIN,
                 common_source_guard_verified=True,old_guard_executed=False)
    path.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(accepted=True,guard_kind=guard.GUARD_KIND,
                         common_source_guard_verified=True,output=path.name)),flush=True)


def main():
    guard.require(os.environ.get('GITHUB_ACTIONS')=='true','Actions only')
    _OLD.WORKFLOW=guard.WORKFLOW
    _OLD.PRODUCTION=guard.BASE
    if '--self-test' in sys.argv:
        _OLD.main();return
    guard.check_source(os.environ['GITHUB_SHA'])
    off='--off' in sys.argv
    if off:install_common_contracts()
    output=guard.ROOT/('build/gtk-341-final-summary/verified.json' if off else 'build/gtk-compact-summary/result.json')
    try:
        _OLD.main()
        annotate(output,off=off)
    except Exception as error:
        if output.exists():
            value=json.loads(output.read_text(encoding='utf-8'));value['accepted']=False
            value.setdefault('problems',[]).append('common GTK adapter: '+type(error).__name__+': '+str(error))
            output.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
        raise


if __name__=='__main__':main()
