"""Actions-only actual host frames; raw PNG and RGBA are collected without transformation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

assert os.environ.get('GITHUB_ACTIONS') == 'true'
p=argparse.ArgumentParser();p.add_argument('--fixtures',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
identity={key:os.environ[value] for key,value in [('source_sha','GITHUB_SHA'),('run_id','GITHUB_RUN_ID'),('attempt','GITHUB_RUN_ATTEMPT')]}
package='org.exreader.host'
expected={
 'first':['original_default_uses_existing_unmodified_render_path','txt_dark_light_actual_ink_canvas_and_state','txt_themed_turn_back_and_actual_selection_anchors','bounded_epub_theme_preserves_author_and_png','legacy_epub_theme_preserves_author_and_png','fixed_pdf_cbz_theme_leaves_image_pixels_identical','theme_cancel_discards_entire_candidate_palette','system_ui_sample_serial_owner_and_latest_coalesced_palette','theme_failure_keeps_last_model_bitmap_and_file'],
 'reopen':['fresh_process_restores_saved_system_theme_real_dark_frame']}
def adb(*args,input=None):return subprocess.check_output(['adb',*map(str,args)],input=input,stderr=subprocess.STDOUT,timeout=120)
def private(name):return adb('exec-out','run-as',package,'cat','files/'+name)
def save(name,data):
 path=a.output/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
manifest=json.loads((a.fixtures/'manifest.json').read_text());reports=[];captures=[];stops=[];sources=[];accepted=False
try:
 adb('shell','cmd','uimode','night','no');assert adb('shell','pm','clear',package).strip()==b'Success'
 adb('shell','am','start','-W','-n',package+'/.MainActivity');adb('shell','am','force-stop',package);adb('exec-out','run-as',package,'mkdir','-p','files/preferences-fixtures')
 for row in manifest['books']:
  data=(a.fixtures/row['file']).read_bytes();assert len(data)==row['bytes'] and hashlib.sha256(data).hexdigest()==row['sha256']
  target='/data/local/tmp/theme-'+row['file'];adb('push',a.fixtures/row['file'],target);adb('exec-out','run-as',package,'cp',target,'files/preferences-fixtures/'+row['file'])
 adb('shell',f"run-as {package} sh -c 'cat > files/preferences-input.json'",input=json.dumps(manifest,ensure_ascii=False).encode())
 for phase,names in expected.items():
  adb('shell','am','force-stop',package);adb('logcat','-c')
  if phase=='reopen':adb('shell','cmd','uimode','night','yes')
  command=['adb','shell','am','instrument','-w','-r','-e','phase',phase]
  for key,value in identity.items():command.extend(('-e',key,value))
  command.append(package+'.test/'+package+'.PageThemeUiTest')
  process=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=1800,check=False);save(phase+'-instrumentation.txt',process.stdout)
  body=private('page-theme-ui-'+phase+'.json');save(phase+'-raw-report.json',body);report=json.loads(body);print(json.dumps(report,ensure_ascii=False),flush=True)
  logs=adb('logcat','-d','-v','threadtime','-t','5000');save(phase+'-logcat.txt',logs)
  for image in report['theme_frames']:
   for extension in ('rgba','png'):
    data=private('page-theme-captures/'+image['name']+'.'+extension);save('theme-frames/'+image['name']+'.'+extension,data);assert hashlib.sha256(data).hexdigest()==image[extension+'_sha256']
  for observation in report['observations']:
   data=private('preferences-captures/'+observation['name']+'.png');save('captures/'+phase+'-'+observation['name']+'.png',data);captures.append({'phase':phase,'name':observation['name'],'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'nodes':observation['nodes']})
  assert process.returncode==0 and all(report.get(key)==value for key,value in identity.items())
  assert report['passed'] is True and report['phase']==phase and report['sdk']=='3.41.0' and report['page_colors_accepted'] is True
  assert report['count']==len(names) and [check['name'] for check in report['checks']]==names and all(check['pass'] is True for check in report['checks'])
  assert ('PAGE_THEME_UI_PASS '+phase).encode() in process.stdout and b'INSTRUMENTATION_CODE: -1' in process.stdout
  reports.append(report)
  for row in manifest['books']:
   raw=private('preferences-fixtures/'+row['file']);assert len(raw)==row['bytes'] and hashlib.sha256(raw).hexdigest()==row['sha256'];sources.append({'phase':phase,**row})
  preferences=private('reading-settings/preferences.json');assert json.loads(preferences)['theme']=='system';save(phase+'-preferences.json',preferences)
  before=subprocess.run(['adb','shell','pidof',package],capture_output=True,text=True,timeout=10).stdout.strip();assert str(report['pid']) in before.split();adb('shell','am','force-stop',package)
  after=subprocess.run(['adb','shell','pidof',package],capture_output=True,text=True,timeout=10).stdout.strip();assert not after;stops.append({'phase':phase,'instrumentation_pid':report['pid'],'pid_before_stop':before,'pid_after_stop':after})
 assert len(reports)==2 and len({row['pid'] for row in reports})==2 and sum(row['count'] for row in reports)==10
 accepted=True
finally:
 adb('shell','cmd','uimode','night','no')
 result={**identity,'accepted':accepted,'sdk':'3.41.0','api':34,'abi':'x86_64','physical_device':False,'checks':sum(row['count'] for row in reports),'phases':reports,'captures':captures,'sources':sources,'process_stops':stops,'page_colors_accepted':accepted,'complete_product':False,'performance_accepted':False}
 save('result.json',(json.dumps(result,ensure_ascii=False,indent=2)+'\n').encode());print(json.dumps({**identity,'accepted':accepted,'checks':result['checks']}),flush=True)
