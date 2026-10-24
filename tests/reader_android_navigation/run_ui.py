"""Actions-only actual Android navigation controls and retained evidence."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

assert os.environ.get('GITHUB_ACTIONS')=='true'
p=argparse.ArgumentParser();p.add_argument('--fixtures',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
identity={key:os.environ[value] for key,value in [('source_sha','GITHUB_SHA'),('run_id','GITHUB_RUN_ID'),('attempt','GITHUB_RUN_ATTEMPT')]}
package='org.exreader.host'
expected={
 'first':['installed_navigation_and_single_shared_sdk_provider','root_pagination_and_read_only_directory_preserve_actual_frame_and_stores','hierarchy_unicode_fragment_selects_independently_verified_part','external_targets_do_not_launch_or_change_reader','part_only_requires_explicit_start_confirmation','unresolved_and_container_escape_never_guess','plain_label_and_empty_authored_navigation','repeated_spine_needs_explicit_identity_and_never_first_match','full_cfi_from_public_sdk_resolves_again_and_navigates','surrogate_collapsed_and_corrupt_cfi_stay_unmoved','pdf_pages_are_not_authored_outline','cbz_pages_use_actual_page_ids','jni_boundaries_thread_and_verified_identity_are_enforced','cancel_real_resolve_then_close_and_retry_is_clean','close_and_actual_rotation_cancel_stale_results','background_releases_snapshot_and_manual_reopen_starts_at_root'],
 'reopen':['process_reopen_has_no_snapshot_or_stale_destination','real_navigation_works_after_process_restart']}
def adb(*args,input=None,timeout=90):return subprocess.check_output(['adb',*map(str,args)],input=input,stderr=subprocess.STDOUT,timeout=timeout)
def private(name):return adb('exec-out','run-as',package,'cat','files/'+name)
def write_private(name,data):adb('shell',f"run-as {package} sh -c 'cat > files/{name}'",input=data)
def save(name,data):path=a.output/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
manifest=json.loads((a.fixtures/'manifest.json').read_text(encoding='utf-8'));reports=[];captures=[];sources=[];accepted=False;stops=[]
try:
    assert adb('shell','pm','clear',package).strip()==b'Success'
    adb('shell','am','start','-W','-n',package+'/.MainActivity');adb('shell','am','force-stop',package)
    adb('exec-out','run-as',package,'mkdir','-p','files/navigation-fixtures');adb('logcat','-c')
    for row in manifest['books']:
        data=(a.fixtures/row['file']).read_bytes();assert len(data)==row['bytes'] and hashlib.sha256(data).hexdigest()==row['sha256']
        temporary='/data/local/tmp/reader-navigation-'+row['file'];adb('push',a.fixtures/row['file'],temporary);adb('exec-out','run-as',package,'cp',temporary,'files/navigation-fixtures/'+row['file'])
    write_private('navigation-input.json',json.dumps(manifest,ensure_ascii=False).encode())
    for phase,names in expected.items():
        adb('shell','am','force-stop',package)
        command=['adb','shell','am','instrument','-w','-r','-e','phase',phase]
        for key,value in identity.items():command.extend(('-e',key,value))
        command.append(package+'.test/'+package+'.NavigationUiTest')
        try:
            process=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=900,check=False);raw=process.stdout
        except subprocess.TimeoutExpired as error:
            save(phase+'-instrumentation.txt',error.stdout or b'');raise
        save(phase+'-instrumentation.txt',raw)
        report=json.loads(private('navigation-ui-'+phase+'.json'));save(phase+'-report.json',(json.dumps(report,ensure_ascii=False,indent=2)+'\n').encode())
        print(json.dumps({'phase':phase,'expected':names,'actual':report['checks'],'failed_check':report.get('failed_check'),'failure_class':report.get('failure_class'),'failure':report.get('failure'),'failure_trace':report.get('failure_trace'),'failure_module_code':report.get('failure_module_code'),'failure_sdk_code':report.get('failure_sdk_code'),'observations':report['observations']},ensure_ascii=False),flush=True)
        save(phase+'-logcat.txt',adb('logcat','-d','-v','threadtime','-t','3000'))
        for observation in report['observations']:
            image=private('navigation-captures/'+observation['name']+'.png');assert image.startswith(b'\x89PNG\r\n\x1a\n') and len(image)>1000
            save('captures/'+phase+'-'+observation['name']+'.png',image);captures.append({'phase':phase,'name':observation['name'],'bytes':len(image),'sha256':hashlib.sha256(image).hexdigest(),'nodes':observation['nodes']})
        assert process.returncode==0 and all(report.get(key)==value for key,value in identity.items())
        assert report['phase']==phase and report['passed'] is True and report['native_live']==0
        assert [check['name'] for check in report['checks']]==names and all(check['pass'] is True for check in report['checks']) and report['count']==len(names)
        assert ('NAVIGATION_UI_PASS '+phase).encode() in raw and b'INSTRUMENTATION_CODE: -1' in raw
        reports.append(report)
        for row in manifest['books']:
            original=private('navigation-fixtures/'+row['file']);assert len(original)==row['bytes'] and hashlib.sha256(original).hexdigest()==row['sha256']
            sources.append({'phase':phase,'file':row['file'],'bytes':len(original),'sha256':row['sha256']})
        pid=subprocess.run(['adb','shell','pidof',package],capture_output=True,text=True,timeout=10).stdout.strip()
        adb('shell','am','force-stop',package)
        after=subprocess.run(['adb','shell','pidof',package],capture_output=True,text=True,timeout=10).stdout.strip();assert not after
        stops.append({'phase':phase,'pid_before_stop':pid,'pid_after_stop':after,'requested':True})
    assert len({report['pid'] for report in reports})==2 and sum(report['count'] for report in reports)==18
    accepted=True
finally:
    result={**identity,'accepted':accepted,'checks':sum(report['count'] for report in reports),'phases':reports,'captures':captures,'sources':sources,'process_stops':stops,
            'api':34,'abi':'x86_64','physical_device':False,'navigation_ui_accepted':accepted,'performance_accepted':False,'complete_product':False,'talkback_speech_accepted':False}
    save('result.json',(json.dumps(result,ensure_ascii=False,indent=2)+'\n').encode());print(json.dumps({**identity,'accepted':accepted,'checks':result['checks'],'phases':len(reports)},ensure_ascii=False),flush=True)
