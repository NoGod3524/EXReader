"""Real GTK account fields, session-only choice and complete raw native scan."""
import argparse
import base64
import configparser
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools'))
from check_linux_host import Session,command


def main():
    assert os.environ.get('GITHUB_ACTIONS')=='true'
    parser=argparse.ArgumentParser();parser.add_argument('--payload',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    host=Session((args.payload/'bin/exreader-linux').resolve(),(args.payload/'Reader.otf').resolve(),args.output)
    pair=base64.b64decode(os.environ['GTK_RAW3_DAV_AUTH'].split(' ',1)[1]).decode();user,password=pair.split(':',1)
    report=dict(accepted=False,source_sha=os.environ['GITHUB_SHA'],run_id=os.environ['GITHUB_RUN_ID'],attempt=os.environ['GITHUB_RUN_ATTEMPT'],
      program_sha256=hashlib.sha256(host.binary.read_bytes()).hexdigest(),actual_gtk_ui_executed=False,complete_product=False,physical_device_execution=False)
    def account():
        value=configparser.ConfigParser(interpolation=None);value.read(host.observe)
        return dict(value['account']) if value.has_section('account') else {}
    def wait(predicate,seconds=180):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            assert host.process.poll() is None,'actual GTK account host exited'
            value=account()
            if value and not int(value['owner_busy']) and not int(value['preparing']) and predicate(value):return value
            time.sleep(.05)
        raise TimeoutError('actual raw account state: '+repr(account()))
    try:
        # Retain the original host checker's desktop-ready barrier before Session.
        end=time.monotonic()+30
        while time.monotonic()<end:
            ready=command('xprop','-root','_NET_SUPPORTING_WM_CHECK')
            if 'window id #' in ready and '0x0' not in ready:break
            time.sleep(.1)
        else:raise TimeoutError('Window manager did not become ready')
        report['window_manager_ready']=True
        host.launch();report.update(pid=host.process.pid,actual_gtk_ui_executed=True)
        host.key('ctrl+shift+a');wait(lambda value:value['visible']=='1')
        dialog=command('xdotool','search','--onlyvisible','--all','--pid',host.process.pid,'--name','^Account and Sync$').splitlines()[-1]
        command('xdotool','windowactivate','--sync',dialog)
        for mnemonic,value in [('w',os.environ['GTK_RAW3_DAV_URL']),('u',user),('p',password)]:
            host.key('alt+'+mnemonic,'ctrl+a');host.paste(value)
        host.key('alt+h','alt+s')
        value=wait(lambda state:state['session_state'] in ('4','5'))
        assert value['session_state']=='4' and value['completed_shards']=='256' and value['remember']=='0',value
        image=args.output/'account-completed.png';command('import','-window',dialog,image)
        report.update(accepted=True,completed_shards=int(value['completed_shards']),session_attempt=int(value['attempt']),session_state=int(value['session_state']),pulled=int(value['pulled']),
          account=value,screenshot=dict(path=image.name,sha256=hashlib.sha256(image.read_bytes()).hexdigest()))
        host.key('alt+F4');wait(lambda state:state['visible']=='0' and state['session_present']=='0')
    except Exception as error:
        report['failure']=type(error).__name__+': '+str(error)
        if host.process is not None and host.process.poll() is None:
            report['pid']=host.process.pid
            tree=subprocess.run(['xwininfo','-root','-tree'],text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=5)
            (args.output/'window-tree.txt').write_text(tree.stdout)
            if getattr(host,'window',None):
                subprocess.run(['import','-window',host.window,str(args.output/'failure.png')],timeout=5,check=False)
        raise
    finally:
        if host.process is not None:
            try:host.close()
            except Exception:
                if host.process.poll() is None:host.process.kill();host.process.wait()
                if host.log:host.log.close()
        (args.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({key:report[key] for key in ('accepted','completed_shards','session_state','pulled','actual_gtk_ui_executed')}),flush=True)


if __name__=='__main__':main()
