"""Real GTK/XTest input controls; these are not product recovery acceptance."""
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import tempfile
import time

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
PROGRAM=r'''
import gi,json,os,sys
gi.require_version('Gtk','3.0');gi.require_version('GdkX11','3.0')
from gi.repository import Gtk,Gdk,GdkX11,GLib
from pathlib import Path
path=Path(sys.argv[1]);state={'chooser_returns':0,'main_returns':0}
main=Gtk.Window(title='F05 input control main');main.set_default_size(300,100)
chooser=Gtk.Dialog(title='F05 input control chooser',transient_for=main,modal=True)
def save():path.write_text(json.dumps(state))
def on_main(widget,event):
    if event.keyval==Gdk.KEY_Return:state['main_returns']+=1;save();return True
def on_chooser(widget,event):
    if event.keyval==Gdk.KEY_Return:
        state['chooser_returns']+=1;state['send_event']=bool(event.send_event)
        state['control_held']=bool(event.state&Gdk.ModifierType.CONTROL_MASK)
        chooser.destroy();main.get_window().focus(Gdk.CURRENT_TIME);save();return True
def ready():
    save();print(json.dumps({'chooser':str(GdkX11.X11Window.get_xid(chooser.get_window())),
        'main':str(GdkX11.X11Window.get_xid(main.get_window())),'pid':os.getpid()}),flush=True);return False
main.connect('key-press-event',on_main);chooser.connect('key-press-event',on_chooser)
main.show_all();chooser.show_all();GLib.idle_add(ready);Gtk.main()
'''


def main():
    if os.environ.get('GITHUB_ACTIONS')!='true':raise RuntimeError('Actions only')
    report={k:os.environ[v] for k,v in (('source_sha','GITHUB_SHA'),('run_id','GITHUB_RUN_ID'),('attempt','GITHUB_RUN_ATTEMPT'))}
    report.update(passed=False,native_product_acceptance=False)
    with tempfile.TemporaryDirectory() as folder:
        state=Path(folder)/'state.json'
        child=subprocess.Popen([sys.executable,'-c',PROGRAM,str(state)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        def run(*args):return subprocess.run(list(map(str,args)),capture_output=True,text=True,timeout=5)
        def observe(predicate):
            end=time.monotonic()+5
            while time.monotonic()<end:
                try:
                    data=json.loads(state.read_text())
                    if predicate(data):return data
                except (FileNotFoundError,json.JSONDecodeError):pass
                time.sleep(.02)
            raise TimeoutError('native input control did not arrive')
        try:
            if not select.select([child.stdout],[],[],5)[0]:raise TimeoutError('GTK control did not map')
            identity=json.loads(child.stdout.readline());pid=identity['pid'];window=identity['chooser']
            run('xdotool','windowfocus','--sync',window).check_returncode()
            refused=run(sys.executable,HERE/'x11_return.py',window,pid+1)
            assert refused.returncode!=0,'foreign owner accepted'
            run('xdotool','keydown','Control_L').check_returncode()
            sent=run(sys.executable,HERE/'x11_return.py',window,pid);sent.check_returncode()
            assert json.loads(sent.stdout)['sent'] is True
            observed=observe(lambda value:value['chooser_returns']==1)
            run('xdotool','keyup','Control_L').check_returncode()
            assert not observed['send_event'] and not observed['control_held'],'GTK did not receive unmodified XTest input'
            run('xdotool','windowfocus','--sync',identity['main']).check_returncode()
            late=run(sys.executable,HERE/'x11_return.py',window,pid);late.check_returncode()
            assert json.loads(late.stdout)['sent'] is False
            assert observe(lambda value:value['chooser_returns']==1)['main_returns']==0,'late Return reached main'
            # Counterexample: the old unscoped event reaches the real main window.
            run('xdotool','key','Return').check_returncode()
            final=observe(lambda value:value['main_returns']==1)
            report.update(passed=True,foreign_owner_refused=True,chooser_return_count=1,
                late_return_suppressed=True,unscoped_counterexample_observed=True,native_gtk_state=final)
        finally:
            primary=sys.exc_info()[1];errors=[]
            try:run('xdotool','keyup','Control_L')
            except BaseException as error:errors.append(repr(error))
            try:
                child.terminate()
                try:child.wait(timeout=5)
                except subprocess.TimeoutExpired:child.kill();child.wait(timeout=5)
            except BaseException as error:errors.append(repr(error))
            report['fixture_stderr']=''
            if select.select([child.stderr],[],[],0)[0]:
                report['fixture_stderr']=os.read(child.stderr.fileno(),4000).decode(errors='replace')
            child.stdout.close();child.stderr.close()
            report['cleanup_errors']=errors
            if errors:report['passed']=False
            output=ROOT/'build/f05-gtk/x11-return-controls.json';output.parent.mkdir(parents=True,exist_ok=True)
            output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
            if errors and primary is None:raise RuntimeError('Native input control cleanup failed')


if __name__=='__main__':main()
