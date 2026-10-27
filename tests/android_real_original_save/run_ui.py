"""Actions-only real Android DocumentsUI original-export check."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

assert os.environ.get('GITHUB_ACTIONS') == 'true'
base=Path('build/wave3')
output=base/'evidence/real-original-save'
output.mkdir(parents=True,exist_ok=True)
package='org.exreader.host'
identity={'source_sha':os.environ['GITHUB_SHA'],'run_id':os.environ['GITHUB_RUN_ID'],'attempt':os.environ['GITHUB_RUN_ATTEMPT']}
def adb(*args):
    return subprocess.check_output(['adb',*map(str,args)],stderr=subprocess.STDOUT,timeout=180)
def push(local,name):
    remote='/data/local/tmp/exr-save-'+Path(name).name
    adb('push',local,remote)
    adb('exec-out','run-as',package,'cp',remote,'files/'+name)
accepted=False
try:
    path=adb('shell','pm','path',package).decode().strip()
    assert path.startswith('package:')
    installed=output/'installed.apk'
    subprocess.run(['adb','pull',path[len('package:'):],str(installed)],check=True,timeout=180)
    apk=base/'artifacts/app-debug.apk'
    digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    assert digest(apk)==digest(installed)
    manifest=json.loads((base/'fixtures/manifest.json').read_text(encoding='utf-8'))
    rows=[row for row in manifest['books'] if row['role'] in ('txt','epub')]
    assert [row['role'] for row in rows]==['txt','epub']
    assert adb('shell','pm','clear',package).strip()==b'Success'
    adb('shell','am','start','-W','-n',package+'/.MainActivity')
    adb('shell','am','force-stop',package)
    adb('exec-out','run-as',package,'mkdir','-p','files/wave3-fixtures')
    for row in rows:
        fixture=base/'fixtures'/row['file']
        assert fixture.stat().st_size==row['bytes'] and digest(fixture)==row['sha256']
        push(fixture,'wave3-fixtures/'+row['file'])
    with tempfile.TemporaryDirectory() as folder:
        input_file=Path(folder)/'input.json'
        input_file.write_text(json.dumps({'books':rows}),encoding='utf-8')
        push(input_file,'wave3-input.json')
    command=['adb','shell','am','instrument','-w','-r']
    for key,value in identity.items():command+=['-e',key,value]
    command+=[package+'.test/'+package+'.OriginalSaveUiTest']
    process=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=900)
    (output/'instrumentation.txt').write_bytes(process.stdout)
    report=json.loads(adb('exec-out','run-as',package,'cat','files/real-original-save.json'))
    (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    picker=adb('exec-out','run-as',package,'cat','files/real-original-picker.png')
    assert picker.startswith(bytes.fromhex('89504e470d0a1a0a')) and len(picker)>1000
    (output/'picker.png').write_bytes(picker)
    print(json.dumps(report,ensure_ascii=False),flush=True)
    assert process.returncode==0 and b'ORIGINAL_SAVE_PASS' in process.stdout
    assert all(report.get(k)==v for k,v in identity.items())
    assert report['passed'] and report['count']==2
    assert [r['name'] for r in report['checks']]==['real_documentsui_opened','system_saved_original_matches_source']
    assert all(r['pass'] for r in report['checks'])
    accepted=True
finally:
    if not accepted:
        try:
            adb('shell','uiautomator','dump','/sdcard/exr-save-window.xml')
            tree=adb('shell','cat','/sdcard/exr-save-window.xml')
            (output/'failure-window.xml').write_bytes(tree)
            print(tree.decode('utf-8','replace')[:30000],flush=True)
        except Exception as error:
            print('window dump unavailable:',error,flush=True)
    try:(output/'logcat.txt').write_bytes(adb('logcat','-d','-v','threadtime'))
    except Exception:pass
    try:(output/'screen.png').write_bytes(adb('exec-out','screencap','-p'))
    except Exception:pass
    (output/'result.json').write_text(json.dumps({**identity,'accepted':accepted,'picker':'real Android DocumentsUI Downloads','physical_device':False},indent=2)+'\n')
assert accepted
