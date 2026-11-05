"""Actions-only diagnosis; no original run control, budget change or performance grant."""
import configparser
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time

ROOT=Path(__file__).resolve().parents[2]
SOURCE='169b0be3c1c8199be0211649412d23d9e34041e4'
RUN=40214285241
ATTEMPT=1
PRODUCER='0889f7d1e9a537c6c1b05456547e016b26e1cd85'
WORKFLOW='.github/workflows/reader-c02-timeout-diagnostic.yml'
OWNED={WORKFLOW,'tests/reader_c02_timeout_diagnostic/diagnose.py','docs/READER-C02-TIMEOUT-DIAGNOSTIC.md'}
SPECS={
 'round1':dict(id=12612017276,name='c02-win-round1-40214285241-1',size_in_bytes=1733980,
    digest='sha256:290f9061d18cd30bd3152fe05b95a113678a6070bf09d26015e6cab69aa041e0',job=121232981888),
 'round2':dict(id=12612261619,name='c02-win-round2-40214285241-1',size_in_bytes=1828201,
    digest='sha256:09f5936fb56a2d5b8f34f9d65e4463855d4b5987631bed237f39bafcbf1f27c9',job=121232981941),
 'build':dict(id=12606728463,name='c02-win-build-40214285241-1',size_in_bytes=20442779,
    digest='sha256:62b03b07ec90a1d593a82bfe8ea01b044a60a3dd13b9fc0daa18116685e7a792',job=121231999964),
}
sys.path.insert(0,str(ROOT/'tests/reader_hosts_integration'))
from final import Bundle,fetch,require


def sha(data):return hashlib.sha256(data).hexdigest()


def source_gate():
    require(os.environ.get('GITHUB_ACTIONS')=='true','Actions only')
    current=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    require(current==os.environ['GITHUB_SHA'],'Actual diagnostic checkout differs')
    rows=subprocess.check_output(['git','diff','--name-status',SOURCE,current],cwd=ROOT,text=True).splitlines()
    require({row.split('\t',1)[1] for row in rows}==OWNED and all(row.startswith('A\t') for row in rows),
            'Diagnostic changed an original C02/source file or another path')
    subprocess.run(['git','diff','--exit-code',current,'--','.'],cwd=ROOT,check=True)


def original_run():
    value=fetch('actions/runs/'+str(RUN))
    require(value['head_sha']==SOURCE and value['run_attempt']==ATTEMPT and
            value['path'].split('@')[0]=='.github/workflows/reader-final-c02.yml','Original source/run/attempt differs')
    return dict(id=RUN,source_sha=SOURCE,attempt=ATTEMPT,status=value['status'],conclusion=value['conclusion'])


def artifact(key):
    expected=SPECS[key];meta=fetch('actions/artifacts/'+str(expected['id']))
    require(all(meta[field]==expected[field] for field in ('id','name','size_in_bytes','digest')),
            'Pinned original artifact metadata differs: '+key)
    require(meta['workflow_run']['id']==RUN and meta['workflow_run']['head_sha']==SOURCE,'Foreign original artifact')
    job=fetch('actions/jobs/'+str(expected['job']))
    require(job['run_id']==RUN and job['head_sha']==SOURCE and job['run_attempt']==ATTEMPT,
            'Foreign original job')
    return meta,job,Bundle(meta)


def launches(text):
    result=[]
    for line in text.splitlines():
        match=re.search(r'LAUNCH (w[12]-n(?:500|5000)-(?:cold|warm|resume|import)-\d+) ok=(True|False) faults=\[(.*)\]',line)
        if not match:continue
        timestamp=re.search(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z',line)
        result.append(dict(launch=match[1],ok=match[2]=='True',fault_classes=sorted(set(
          re.findall(r'\b(?:TimeoutError|MeasurementFault|RuntimeError)\b',match[3]))),
          no_transition='no transition' in match[3],line_sha256=sha(line.encode()),
          timestamp=timestamp[0] if timestamp else None))
    return result


def summarize_json(name,value):
    result=dict(type=type(value).__name__)
    if not isinstance(value,dict):return result
    for key in ('schema','books','long_book_bytes','total_original_bytes','size','catalog_rows','round'):
        if key in value and isinstance(value[key],(int,float,str)):result[key]=value[key]
    if isinstance(value.get('originals'),list):result['original_count']=len(value['originals'])
    if name.startswith('raw/memory/') and isinstance(value.get('samples'),list):
        samples=value['samples'];result['memory_sample_count']=len(samples)
        if samples:
            result.update(sample_span_ms=samples[-1][0]-samples[0][0],
                          peak_working_set_bytes=max(row[2] for row in samples))
    if isinstance(value.get('reading_key'),list):result['reading_key']=value['reading_key']
    # No originals' titles, authors, text, paths, note bodies or arbitrary logs.
    return result


def inspect(report):
    report['original_run']=original_run();rounds={}
    for key in ('round1','round2'):
        meta,job,bundle=artifact(key)
        try:
            files=[entry for entry in bundle.zip.infolist() if not entry.is_dir()]
            require(len(files)==21,'Original round file count differs from 21')
            require(sum(row.file_size for row in files)<=128*1024**2,'Original diagnostic input exceeds bound')
            rows=[]
            for entry in sorted(files,key=lambda row:row.filename):
                data=bundle.zip.read(entry);row=dict(path=entry.filename,bytes=len(data),sha256=sha(data))
                require(len(data)==entry.file_size,'Original member byte count differs')
                if entry.filename.endswith('.json'):
                    try:row['summary']=summarize_json(entry.filename,json.loads(data))
                    except (ValueError,TypeError,KeyError,IndexError):row['parse_status']='incomplete-or-unexpected-json'
                elif entry.filename.endswith('.log'):
                    text=data.decode('utf-8','replace')
                    row.update(line_count=len(text.splitlines()),launches=launches(text))
                rows.append(row)
            listing={row.filename for row in files}
            log=subprocess.run(['gh','api','repos/'+os.environ['GITHUB_REPOSITORY']+
                '/actions/jobs/'+str(SPECS[key]['job'])+'/logs'],capture_output=True,timeout=60)
            rounds[key]=dict(artifact={field:meta[field] for field in ('id','name','size_in_bytes','digest','expires_at')},
              job_id=job['id'],job_conclusion=job['conclusion'],started_at=job['started_at'],completed_at=job['completed_at'],
              file_count=len(files),files=rows,job_log_available=log.returncode==0,
              job_log_sha256=sha(log.stdout) if log.returncode==0 else None,
              job_log_failure_sha256=sha(log.stderr) if log.returncode else None,
              job_log_failure_http_status=re.findall(r'HTTP [0-9]{3}',log.stderr.decode('utf-8','replace')) if log.returncode else [],
              timestamped_launches=launches(log.stdout.decode('utf-8','replace')) if log.returncode==0 else [],
              missing_final_round_files=[name for name in ('samples.json','launches.json','memory.json','plan.json','bundle.json') if name not in listing],
              original_profiles_uploaded=any(name.endswith(('.sqlite','.ini')) for name in listing))
        finally:bundle.close()
    report.update(rounds=rounds,authenticated_original_evidence=True,
      source_findings=dict(warm_profile='shared-warm-profile',last_shelf_query_persisted=True,
        original_rows_ready_minimum=50,original_cold_deadline_seconds=3600,
        predicate_checks_shelf_visibility=False,window_observation_executed=False))


def profile_state(profile):
    path=profile/'host.ini'
    if not path.exists():return dict(exists=False)
    data=path.read_bytes();text=data.decode('utf-16' if data.startswith((b'\xff\xfe',b'\xfe\xff')) else 'utf-8-sig','replace')
    value=configparser.ConfigParser(interpolation=None);value.read_string(text)
    query=value.get('Shelf','Query',fallback='')
    return dict(exists=True,bytes=len(data),sha256=sha(data),shelf_query_characters=len(query),
      shelf_query_equals_generated_long_title=query=='Shelf 0000',shelf_query_sha256=sha(query.encode()),
      active_book=value.getint('Host','ActiveBook',fallback=0))


def reproduce(report,output):
    require(os.name=='nt','Native Windows diagnostic only')
    report['original_run']=original_run();meta,job,bundle=artifact('build')
    private=ROOT/'build/c02-timeout-private';private.mkdir(parents=True,exist_ok=False)
    build=private/'build';build.mkdir()
    try:
        identity=json.loads(bundle.zip.read('build-identity.json'))
        require(identity['consumer_sha']==SOURCE and identity['producer_source']==PRODUCER and
                str(identity['run_id'])==str(RUN) and str(identity['attempt'])==str(ATTEMPT) and
                identity['ui_variant']=='EXR_READER_WINDOWS_COMPACT=ON' and identity['sdk_version']=='3.41.0',
                'Original build identity differs')
        for name,field in (('EXReaderProduct.exe','program_sha256'),('Reader.otf','font_sha256'),('c02_seed.exe','seed_sha256')):
            data=bundle.zip.read(name);require(sha(data)==identity[field],'Original consumed build member differs')
            (build/name).write_bytes(data)
    finally:bundle.close()
    report['build']=dict(artifact_id=meta['id'],artifact_digest=meta['digest'],identity=identity,job_id=job['id'])
    profile=private/'shared-warm-profile';profile.mkdir()
    seeded=subprocess.run([str(build/'c02_seed.exe'),str(profile/'library.sqlite'),str(private/'corpus.json'),'500'],
                          capture_output=True,timeout=120)
    require(seeded.returncode==0,'Original public-SDK seed failed')
    corpus=json.loads((private/'corpus.json').read_text());require(corpus['books']==500,'Diagnostic corpus differs')
    report['synthetic_corpus']=dict(books=corpus['books'],long_book_bytes=corpus['long_book_bytes'],
                                  corpus_sha256=sha((private/'corpus.json').read_bytes()))
    sys.path.insert(0,str(ROOT/'tests/reader_perf_windows'))
    import perf_windows as PW
    active=[];states=[];watchdog_fired=[]
    def kill_windows():
        watchdog_fired.append(True)
        for host in active:
            if host.process.poll() is None:host.process.kill()
    timer=threading.Timer(55,kill_windows);timer.daemon=True
    started=time.monotonic();timer.start()
    host=None
    def snapshot(label):
        value=dict(label=label,pid=host.process.pid,elapsed_ms=round((time.monotonic()-started)*1000,3),
                   alive=host.process.poll() is None,profile=profile_state(profile),controls={})
        for name in ('books','metadata','search','page','next','open'):
            handle=host.control(name)
            value['controls'][name]=dict(id=PW.IDS[name],visible=bool(PW.U.IsWindowVisible(handle)),
                                        enabled=bool(PW.U.IsWindowEnabled(handle)))
        query=host.text(host.control('search'),512,300)
        count=host.lb_count(300);first=host.lb_item(0,300) if count else ''
        value.update(book_rows=count,search_characters=len(query),search_sha256=sha(query.encode()),
          search_equals_generated_long_title=query=='Shelf 0000',page_key=PW.page_key(host.label(300)),
          first_row_contains_legacy_offset='偏移' in first,ui_roundtrip_ms=round(host.roundtrip(500),3))
        value['exact_original_rows_ready']=(value['controls']['metadata']['enabled'] and count>=50 and '偏移' not in first)
        states.append(value);return value
    def launch(label):
        result=PW.Host(build/'EXReaderProduct.exe',build/'Reader.otf',profile,private/(label+'.log'))
        active.append(result);return result
    try:
        host=launch('first-warm-launch');PW.op_first_screen(host,12);snapshot('initial_unfiltered_50_rows')
        host.set_text(host.control('search'),'Shelf 0000')
        host.poll(lambda:(True,) if host.lb_count(300)==1 and host.enabled('open') else None,8)
        snapshot('real_search_filter_one_row_before_close')
        host.close();report['persisted_after_first_close']=profile_state(profile);host=None
        host=launch('second-warm-launch');PW.op_window(host,8)
        host.poll(lambda:(True,) if host.enabled('metadata') and host.lb_count(300)>0 else None,8)
        snapshot('same_profile_reopened_before_original_predicate')
        try:
            PW.op_first_screen(host,4)
            report['original_predicate_observation']=dict(status='unexpectedly_completed',diagnostic_deadline_seconds=4)
        except TimeoutError as error:
            report['original_predicate_observation']=dict(status='failed',fault_class=type(error).__name__,
              no_transition='no transition' in str(error),diagnostic_deadline_seconds=4,
              original_3600_second_budget_unchanged=True)
        settled=snapshot('after_bounded_original_predicate')
        host.set_text(host.control('search'),'')
        host.poll(lambda:(True,) if host.lb_count(300)>=50 and host.enabled('metadata') else None,8)
        PW.op_first_screen(host,4);after=snapshot('clear_via_real_search_control_restores_50_rows')
        report['persistent_query_wait_condition_confirmed']=(settled['book_rows']==1 and
          settled['search_equals_generated_long_title'] and settled['controls']['metadata']['enabled'] and
          not settled['first_row_contains_legacy_offset'] and settled['ui_roundtrip_ms']<500 and
          report['original_predicate_observation']['status']=='failed' and after['exact_original_rows_ready'])
        # Isolate compact compatibility after preserving the query failure above.
        opened=PW.op_open(host,'Shelf 0000',timeout=8);key=opened['key']
        hidden=snapshot('compact_reading_hides_library_with_50_existing_rows')
        try:
            PW.op_first_screen(host,2)
            report['compact_reading_predicate_observation']=dict(status='completed_with_reading_view',diagnostic_deadline_seconds=2)
        except TimeoutError:
            report['compact_reading_predicate_observation']=dict(status='failed',diagnostic_deadline_seconds=2)
        report['hidden_shelf_can_satisfy_legacy_predicate']=(hidden['book_rows']>=50 and
          not hidden['controls']['books']['visible'] and report['compact_reading_predicate_observation']['status']=='completed_with_reading_view')
        for _ in range(8):key=PW.op_page_turn(host,key,timeout=4)['to']
        host.send(host.window,0x0111,46001)
        host.poll(lambda:(True,) if PW.U.IsWindowVisible(host.control('books')) else None,4)
        snapshot('after_real_eight_turns_and_back_to_shelf')
        host.close();report['persisted_after_reading_close']=profile_state(profile);host=None
    finally:
        if host is not None:host.close()
        timer.cancel()
        report.update(states=states,window_observation_seconds=round(time.monotonic()-started,3),
                      hard_watchdog_seconds=55,watchdog_fired=bool(watchdog_fired),
                      original_program_not_rebuilt=True,performance_sample_recorded=False)
    require(report['window_observation_seconds']<=60,'Bounded diagnostic window observation exceeded 60 seconds')


def main():
    require(len(sys.argv)==2 and sys.argv[1] in ('inspect','reproduce'),'Use inspect or reproduce')
    mode=sys.argv[1];output=ROOT/('build/c02-timeout-inspection' if mode=='inspect' else 'build/c02-timeout-reproduction')
    output.mkdir(parents=True,exist_ok=False)
    report=dict(diagnostic_only=True,accepted=False,performance_accepted=False,complete_product=False,
      diagnostic_source=os.environ.get('GITHUB_SHA'),diagnostic_run=os.environ.get('GITHUB_RUN_ID'),
      diagnostic_attempt=os.environ.get('GITHUB_RUN_ATTEMPT'),original_source=SOURCE,
      original_run=RUN,original_attempt=ATTEMPT,original_budget_or_sample_plan_modified=False)
    try:
        source_gate()
        if mode=='inspect':inspect(report)
        else:reproduce(report,output)
        report['diagnostic_completed']=True
    except Exception as error:
        report.update(diagnostic_completed=False,diagnostic_error_class=type(error).__name__,
                      diagnostic_error_sha256=sha(str(error).encode()))
        raise
    finally:
        (output/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(report),flush=True)


if __name__=='__main__':main()
