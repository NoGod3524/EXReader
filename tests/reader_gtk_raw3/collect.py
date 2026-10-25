"""Authenticate raw actual owners/packet, raw UI45, original compact45/OFF35."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
from guard import ROOT,WORKFLOW,PRODUCTION
from retained import RAW_JOB,FINAL_JOB

sys.path.insert(0,str(ROOT/'tests/reader_hosts_integration'))
from final import Bundle,fetch,pages,require,identity


def validate(value,source,run,attempt):
    identity(value,source,run,attempt)
    require(value.get('accepted') is True and value.get('built') is True,'raw owner build or cases incomplete')
    require(all(value.get(key) is False for key in ('complete_product','performance_accepted','six_platform_accepted','physical_device_execution')),'broader raw grant')
    phases=value.get('phases',[]);names={row['label'] for row in phases}
    expected={'raw-seed','raw-reopen','raw-retry-before','raw-verify-before','raw-retry-after','raw-verify-after','legacy-seed','raw-retained-v1-v2',
      'legacy-exact-raw-retry-before','legacy-exact-raw-retry-after','mac11-owner','mac11-reopen','mac-null-owner','mac-null-reopen'}
    require(len(phases)==len(names)==len(expected) and names==expected and all(row['checks']>0 for row in phases),'raw actual process phases missing/duplicated')
    kills=value.get('kills',[])
    require(len(kills)==4 and len({row['pid'] for row in kills})==4 and all(row['signal']=='SIGKILL' and row['pending_bytes']>0 for row in kills) and
      {(row['version'],row['stage']) for row in kills}=={(1,'before'),(1,'after'),(2,'before'),(2,'after')},'real durable-boundary kill pair missing')
    refusal=value.get('legacy_native_pending_refusals',[])
    require(len(refusal)==2 and {r['stage'] for r in refusal}=={'before','after'} and all(r['legacy_exit']==1 and r['pending_bytes']>0 for r in refusal),'legacy native intent refusal missing')
    network=value.get('network',{});peer=network.get('peer',{})
    require(peer.get('artifact',{}).get('id')==12600789926 and peer.get('source_sha')=='15dab6b2270dc296ed6239db67ced2e22d255e65' and
      peer.get('reading_records')==11 and peer.get('wire_count')==15 and peer.get('original_count')==4,'authentic Mac packet missing')
    rows=network.get('phases',[])
    require(len(rows)==2 and {row['label'] for row in rows}=={'mac11','mac-null'} and
      all(row['immutable_wires_unchanged'] is True and row['actual_gtk_ui_executed'] is True and row['session']['accepted'] is True and
        row['session']['actual_gtk_ui_executed'] is True and row['session']['completed_shards']==256 and row['session']['session_state']==4
        and row['session']['account']['password_visible']=='0' and row['session']['account']['remember']=='0' for row in rows),'actual GTK account network or immutable records incomplete')


def selftest():
    # Refusal protocol is exercised against the real completed raw report below.
    return [('accepted',False),('built',False),('phases',[]),('kills',[]),('legacy_native_pending_refusals',[]),('network',{})]


def main():
    require(os.environ.get('GITHUB_ACTIONS')=='true','Actions only')
    source,run,attempt=os.environ['GITHUB_SHA'],int(os.environ['GITHUB_RUN_ID']),int(os.environ['GITHUB_RUN_ATTEMPT'])
    output=ROOT/'build/gtk-raw3-summary';output.mkdir(parents=True,exist_ok=False)
    result=dict(accepted=False,source_sha=source,run_id=run,attempt=attempt,production_pin=PRODUCTION,problems=[],
      scope='optional GTK raw3 actual owners and authenticated Mac-to-GTK packet plus complete original compact/OFF regression',
      complete_product=False,performance_accepted=False,six_platform_accepted=False,physical_device_execution=False,screen_reader_accepted=False)
    try:
        meta=fetch('actions/runs/'+str(run));require(meta['head_sha']==source and meta['run_attempt']==attempt and meta['path'].split('@')[0]==WORKFLOW,'wrong complete run identity')
        jobs=pages('actions/runs/%d/attempts/%d/jobs'%(run,attempt),'jobs')
        expected={'preflight','GTK 3.41 complete retained suites and actual owner record compatibility','Authenticate candidate canvas raw ZIP and source-bound reports',
          'Read-only failed GTK owner evidence diagnosis','Authenticate distinct compact ON and complete original OFF scopes',RAW_JOB,FINAL_JOB}
        require(len(jobs)==7 and {r['name'] for r in jobs}==expected,'complete raw/legacy topology absent')
        for row in jobs:
            require(row['head_sha']==source and row['run_attempt']==attempt,'foreign actual job')
            if row['name']==FINAL_JOB:continue
            require(row['conclusion']==('skipped' if row['name']=='Read-only failed GTK owner evidence diagnosis' else 'success'),'upstream raw/retained scope failed')
            if row['name']!='Read-only failed GTK owner evidence diagnosis':require(all(s['conclusion'] in ('success','skipped') for s in row['steps']),'hidden failed actual step')
        artifacts=pages('actions/runs/%d/artifacts'%run,'artifacts')
        raw_meta,=[r for r in artifacts if r['name']=='gtk-raw3-candidate-%d-%d'%(run,attempt)]
        retained_meta,=[r for r in artifacts if r['name']=='reader-gtk-compact-summary-%d-%d'%(run,attempt)]
        for m in (raw_meta,retained_meta):require(m['workflow_run']['head_sha']==source and m['workflow_run']['id']==run,'foreign actual artifact')
        retained=Bundle(retained_meta)
        try:old=retained.report('result.json')
        finally:retained.close()
        identity(old,source,run,attempt);require(old['accepted'] and old['off_full_original_scope_accepted'] and old['compact_native_ui_accepted'] and old['on_checks']==45,'complete unchanged compact45/OFF35 unavailable')
        raw=Bundle(raw_meta)
        try:
            value=raw.report('result.json');validate(value,source,run,attempt)
            negatives=0
            for key,replacement in selftest()+[(key,True) for key in ('complete_product','performance_accepted','six_platform_accepted','physical_device_execution')]:
                bad=copy.deepcopy(value);bad[key]=replacement
                try:validate(bad,source,run,attempt)
                except (ValueError,KeyError,TypeError):negatives+=1;continue
                raise ValueError('raw evidence accepted corrupted '+key)
            for path,row in value['files'].items():
                data=raw.bytes(path,128*1024**2);require(len(data)==row['bytes'] and hashlib.sha256(data).hexdigest()==row['sha256'],'raw inventory differs: '+path)
            for row in value['phases']:
                report=raw.report(row['report']);require(report['accepted'] and report['check_count']==row['checks']==len(report['checks']) and
                  all(item['passed'] is True for item in report['checks']),'actual owner process checks incomplete')
            spec=importlib.util.spec_from_file_location('raw_actual_compact_ui',ROOT/'tests/reader_gtk_compact/aggregate.py');compact=importlib.util.module_from_spec(spec);spec.loader.exec_module(compact)
            binary=raw.bytes('package/EXReader-Linux/bin/exreader-linux',64*1024**2);program=hashlib.sha256(binary).hexdigest()
            ui=raw.report('raw-ui/report.json');count=compact.validate_ui(ui,source,run,attempt,program);require(count==45,'raw compact UI cases changed')
            mapping=raw.bytes('raw-owner/actual-owner/gtk-account-host.map',32*1024**2)
            for symbol in (b'reader_revisions_open_raw_v3',b'reader_metadata_open_raw_v3',b'reader_session_create_raw_v3',b'reader_rs_decode_raw_v3',
              b'reader_rs_resolve_fixed_v3',b'reader_rc_apply_raw_v3',b'reader_av_open_raw_v3',b'reader_av_page_get_raw_v3',b'reader_command_apply_book_raw_v3'):
                require(symbol in mapping,'actual GTK link lacks raw family path')
            for row in ui['screenshots'].values():
                data=raw.bytes('raw-ui/'+row['path'],32*1024**2);require(data.startswith(b'\x89PNG\r\n\x1a\n') and hashlib.sha256(data).hexdigest()==row['sha256'],'actual raw UI screenshot differs')
        finally:raw.close()
        result.update(accepted=True,raw_owner_and_packet_accepted=True,raw_compact_ui_checks=count,retained_compact_ui_checks=45,
          retained_actual_steps=35,independent_raw_protocol_refusals=negatives,raw_program_sha256=program,retained_summary=old,
          raw_owner_report=value,raw_ui_report=ui,jobs=[dict(id=r['id'],name=r['name'],conclusion=r['conclusion']) for r in jobs if r['name']!=FINAL_JOB],
          artifacts=[{key:r[key] for key in ('id','name','size_in_bytes','digest','expires_at')} for r in (raw_meta,retained_meta)])
    except Exception as error:result['problems'].append(type(error).__name__+': '+str(error))
    (output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('accepted','problems')}),flush=True);require(result['accepted'],'complete GTK raw3 acceptance refused')


if __name__=='__main__':main()
