"""Run unchanged retained GTK assertions with a process-scoped chooser driver.
The original driver/code and failed runs remain intact. No assertion, fixture,
product implementation or timeout budget is replaced.
"""
import hashlib,json,os,re,runpy,subprocess,sys,time
from pathlib import Path
assert os.environ.get('GITHUB_ACTIONS')=='true'
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools'))
from check_linux_host import Session,command

def dialog(self,path=None):
    before=self.read();events=[];started=time.monotonic();deadline=started+30
    def visible():
        p=subprocess.run(['xdotool','search','--onlyvisible','--all','--pid',str(self.process.pid),'--name','^Import book$'],text=True,capture_output=True,timeout=5)
        return p.stdout.split()
    def event(name):events.append({'event':name,'elapsed':time.monotonic()-started,'host':self.read(),'visible':visible()})
    try:
        command('xdotool','windowactivate','--sync',self.window);self.key('F1')
        while time.monotonic()<deadline:
            ids=visible()
            if ids:break
            time.sleep(.1)
        assert len(ids)==1,('Expected one owned import chooser',ids)
        chooser=ids[0];command('xdotool','windowactivate','--sync',chooser);event('owned-chooser')
        if path is None:self.key('Escape')
        else:
            self.key('ctrl+l');self.paste(str(Path(path).resolve()))
            command('xdotool','key','--clearmodifiers','Return');event('first-enter')
        second=False
        while time.monotonic()<deadline:
            assert self.process.poll() is None
            ids=visible();state=self.read();assert not ids or ids==[chooser],('Chooser identity changed',ids,chooser)
            if not ids and state.get('sequence',0)>before['sequence'] and not state.get('busy',0):
                event('closed');return
            # Only one additional user activation, after the async file chooser
            # has had time to select the path; never send it to the reader.
            if path is not None and not second and ids and time.monotonic()-started>=3 and not state.get('busy',0) and state.get('books')==before.get('books'):
                command('xdotool','windowactivate','--sync',chooser)
                if visible()==[chooser] and not self.read().get('busy',0):
                    command('xdotool','key','--clearmodifiers','Return');second=True;event('guarded-second-enter')
            time.sleep(.1)
        event('timeout');raise TimeoutError('Owned native import chooser did not close within original 30-second budget')
    finally:
        self.folder.mkdir(parents=True,exist_ok=True)
        with (self.folder/'owned-chooser-driver.jsonl').open('a',encoding='utf-8') as output:output.write(json.dumps(events)+'\n')
Session.dialog=dialog
script=Path(sys.argv[1]);sys.argv=sys.argv[1:]
sys.path.insert(0,str(script.resolve().parent))
identity={'adapter_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
          'original_driver_sha256':hashlib.sha256((ROOT/'tools/check_linux_host.py').read_bytes()).hexdigest(),
          'unchanged_test':str(script),'unchanged_test_sha256':hashlib.sha256(script.read_bytes()).hexdigest(),
          'source_sha':os.environ['GITHUB_SHA'],'run_id':os.environ['GITHUB_RUN_ID'],'attempt':os.environ['GITHUB_RUN_ATTEMPT'],
          'delta':'Session.dialog only: PID/window-scoped, one guarded second Enter, 30s closure budget; no assertion or fixture replacement'}
print(json.dumps({'retained_driver_identity':identity}),flush=True)
try:runpy.run_path(str(script),run_name='__main__')
finally:
    if '--output' in sys.argv:
        output=Path(sys.argv[sys.argv.index('--output')+1])
        if output.is_dir():(output/'driver-identity.json').write_text(json.dumps(identity,indent=2))
