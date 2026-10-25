"""Actions-only actual displayed fixed page panning and unchanged inherited contracts."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
assert os.environ.get('GITHUB_ACTIONS')=='true'
p=argparse.ArgumentParser();p.add_argument('--fixtures',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
identity={key:os.environ[value] for key,value in [('source_sha','GITHUB_SHA'),('run_id','GITHUB_RUN_ID'),('attempt','GITHUB_RUN_ATTEMPT')]}
package='org.exreader.host'
expected={'first':['real_pdf_cbz_four_corners_strict_display_pixels_and_no_store_write','panned_pdf_selection_and_clipped_semantic_bounds_match_actual_page','directional_accessibility_pan_clamps_and_keeps_page_navigation_distinct','cancel_and_multitouch_never_emit_spurious_fixed_page_turn','nonoverflow_axis_retains_swipe_and_new_page_resets_pan','fit_fixed_and_reflow_keep_original_turn_controls','actual_rotation_reopens_same_fixed_page_with_transient_pan_reset'],'reopen':['fresh_process_keeps_native_zoom_source_and_zero_pan_then_drags']}
def adb(*args,input=None,timeout=90):return subprocess.check_output(['adb',*map(str,args)],input=input,stderr=subprocess.STDOUT,timeout=timeout)
def private(name):return adb('exec-out','run-as',package,'cat','files/'+name)
def save(name,data):
    path=a.output/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
manifest=json.loads((a.fixtures/'manifest.json').read_text(encoding='utf-8'));reports=[];captures=[];sources=[];stops=[];accepted=False
try:
    assert adb('shell','pm','clear',package).strip()==b'Success'
    adb('shell','am','start','-W','-n',package+'/.MainActivity');adb('shell','am','force-stop',package)
    adb('exec-out','run-as',package,'mkdir','-p','files/fixed-pan-fixtures')
    for row in manifest['books']:
        data=(a.fixtures/row['file']).read_bytes();assert len(data)==row['bytes'] and hashlib.sha256(data).hexdigest()==row['sha256']
        temporary='/data/local/tmp/reader-pan-'+row['file'];adb('push',a.fixtures/row['file'],temporary);adb('exec-out','run-as',package,'cp',temporary,'files/fixed-pan-fixtures/'+row['file'])
    adb('shell',f"run-as {package} sh -c 'cat > files/fixed-pan-input.json'",input=json.dumps(manifest,ensure_ascii=False).encode())
    for phase,names in expected.items():
        adb('shell','am','force-stop',package);adb('logcat','-c')
        command=['adb','shell','am','instrument','-w','-r','-e','phase',phase]
        for key,value in identity.items():command.extend(('-e',key,value))
        command.append(package+'.test/'+package+'.FixedPanUiTest')
        process=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=1200,check=False)
        save(phase+'-instrumentation.txt',process.stdout)
        raw_report=private('fixed-pan-ui-'+phase+'.json');save(phase+'-raw-report.txt',raw_report)
        save(phase+'-logcat.txt',adb('logcat','-d','-v','threadtime','-t','3000'))
        try:report=json.loads(raw_report)
        except json.JSONDecodeError:
            print(process.stdout.decode(errors='replace'),flush=True);print(raw_report.decode(errors='replace'),flush=True);raise
        save(phase+'-report.json',(json.dumps(report,ensure_ascii=False,indent=2)+'\n').encode())
        print(json.dumps({key:report.get(key) for key in ['phase','pid','passed','checks','count','failed_check','failure','failure_trace','display_pixels','pan_frames']},ensure_ascii=False),flush=True)
        for observation in report['observations']:
            image=private('fixed-pan-captures/'+observation['name']+'.png');assert image.startswith(b'\x89PNG\r\n\x1a\n') and len(image)>1000
            save('captures/'+phase+'-'+observation['name']+'.png',image);captures.append({'phase':phase,'name':observation['name'],'bytes':len(image),'sha256':hashlib.sha256(image).hexdigest(),'nodes':observation['nodes']})
        assert process.returncode==0 and all(report.get(key)==value for key,value in identity.items())
        assert report['phase']==phase and report['passed'] is True and report['count']==len(names)
        assert [check['name'] for check in report['checks']]==names and all(check['pass'] is True for check in report['checks'])
        assert ('FIXED_PAN_UI_PASS '+phase).encode() in process.stdout and b'INSTRUMENTATION_CODE: -1' in process.stdout
        for point in report['display_pixels']:assert point['argb']==point['expected_argb']
        reports.append(report)
        for row in manifest['books']:
            original=private('fixed-pan-fixtures/'+row['file']);assert len(original)==row['bytes'] and hashlib.sha256(original).hexdigest()==row['sha256']
            sources.append({'phase':phase,'file':row['file'],'bytes':len(original),'sha256':row['sha256']})
        save(phase+'-preferences.json',private('reading-settings/preferences.json'))
        pid=subprocess.run(['adb','shell','pidof',package],capture_output=True,text=True,timeout=10).stdout.strip()
        assert not pid or str(report['pid']) in pid.split()
        adb('shell','am','force-stop',package);after=subprocess.run(['adb','shell','pidof',package],capture_output=True,text=True,timeout=10).stdout.strip();assert not after
        stops.append({'phase':phase,'instrumentation_pid':report['pid'],'pid_before_stop':pid,'pid_after_stop':after,'requested':True})
    assert len({report['pid'] for report in reports})==2 and sum(report['count'] for report in reports)==8
    accepted=True
finally:
    value={**identity,'accepted':accepted,'checks':sum(report['count'] for report in reports),'phases':reports,'captures':captures,'sources':sources,'process_stops':stops,'api':34,'abi':'x86_64','physical_device':False,'fixed_page_pan_accepted':accepted,'page_colors_accepted':False,'performance_accepted':False,'complete_product':False,'talkback_speech_accepted':False}
    save('result.json',(json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode());print(json.dumps({**identity,'accepted':accepted,'checks':value['checks'],'phases':len(reports)}),flush=True)
