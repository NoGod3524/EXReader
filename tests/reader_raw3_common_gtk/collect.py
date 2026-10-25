"""Execute the complete sealed raw collector, then require the new common gate proof."""
import json
import os
import guard
from retained import validate_retained_proof


def main():
    guard.require(os.environ.get('GITHUB_ACTIONS')=='true','Actions only')
    source=os.environ['GITHUB_SHA'];guard.check_source(source)
    original=guard.load('sealed_gtk_raw3_complete_collector','tests/reader_gtk_raw3/collect.py')
    original.WORKFLOW=guard.WORKFLOW
    original.PRODUCTION=guard.BASE
    output=guard.ROOT/'build/gtk-raw3-summary/result.json'
    try:
        original.main()
        value=json.loads(output.read_text(encoding='utf-8'))
        guard.require(value.get('accepted') is True and value.get('production_pin')==guard.BASE,
                      'Final raw result does not bind the actual common baseline')
        retained=value.get('retained_summary',{})
        guard.require(retained.get('guard_kind')==guard.GUARD_KIND and
            retained.get('composition_source')==guard.BASE and retained.get('common_source_guard_verified') is True,
            'Missing new common-source compact/OFF authentication')
        validate_retained_proof(retained.get('off_strict_report',{}),source,
                               os.environ['GITHUB_RUN_ID'],os.environ['GITHUB_RUN_ATTEMPT'])
        value.update(guard_kind=guard.GUARD_KIND,composition_source=guard.BASE,gtk_source_pin=guard.GTK_PIN,
                     common_source_guard_verified=True,old_guard_executed=False)
        output.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(dict(accepted=True,guard_kind=guard.GUARD_KIND,
                             common_source_guard_verified=True,problems=value['problems'])),flush=True)
    except Exception as error:
        if output.exists():
            value=json.loads(output.read_text(encoding='utf-8'));value['accepted']=False
            value.setdefault('problems',[]).append('common GTK adapter: '+type(error).__name__+': '+str(error))
            output.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
        raise


if __name__=='__main__':main()
