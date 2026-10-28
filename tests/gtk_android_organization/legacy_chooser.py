"""Actions adapter for old GTK account driver's chooser only; assertions unchanged.

Keep the independent unadapted historical run and its exit code. This adapter
uses exactly the Session.dialog 30-second budget, sends a second Enter only to
the same visible native chooser when its first Enter resolves the path, and
requires actual closure. It never injects a file or changes host state directly.
"""
import hashlib,json,os,re,runpy,subprocess,sys,time
from pathlib import Path
assert os.environ.get('GITHUB_ACTIONS')=='true'
root=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(root/'tools'));sys.path.insert(0,str(root/'tests/linux_host'))
from check_linux_host import Session,command

def dialog(self,path=None):
    before=self.read()['sequence'];self.key('F1')
    def visible():
        r=subprocess.run(['xdotool','search','--onlyvisible','--all','--pid',str(self.process.pid),'--name','^Import book$'],capture_output=True,text=True)
        return r.stdout.split()
    deadline=time.monotonic()+30
    while not visible():
        assert self.process.poll() is None
        if time.monotonic()>=deadline:raise TimeoutError('Native import chooser did not appear')
        time.sleep(.1)
    chooser=visible()[-1];command('xdotool','windowactivate','--sync',chooser)
    if path is None:self.key('Escape')
    else:self.key('ctrl+l');self.paste(str(path));self.key('Return')
    second=False;started=time.monotonic()
    while chooser in visible():
        assert self.process.poll() is None
        if path is not None and not second and time.monotonic()-started>=3 and not self.read().get('busy'):
            command('xdotool','windowactivate','--sync',chooser);self.key('Return');second=True
        if time.monotonic()>=deadline:raise TimeoutError('Native import chooser did not close within original 30 seconds')
        time.sleep(.1)
    self.wait(lambda s:s['sequence']>before)
    event={'path':str(path) if path else None,'source_sha256':hashlib.sha256(Path(path).read_bytes()).hexdigest() if path else None,'chooser_pid':self.process.pid,'chooser_window':chooser,'second_enter':second,'host':self.read()}
    with (self.folder/'chooser-adapter-events.jsonl').open('a') as output:output.write(json.dumps(event)+'\n')
Session.dialog=dialog
runpy.run_path(str(root/'tests/linux_host/check_account_ui.py'),run_name='__main__')
