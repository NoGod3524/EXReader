"""Actual Win32 compact controls, never review message/gate APIs."""
import ctypes as C
from ctypes import wintypes as W
import importlib.util,sys,time
from pathlib import Path
ROOT=Path('target').resolve()
sys.path.insert(0,str(ROOT/'tests/reader_windows_compact'))
spec=importlib.util.spec_from_file_location('compact_driver',ROOT/'tests/reader_windows_compact/check_ui.py')
saved_contract=sys.modules.get('contract')
cs=importlib.util.spec_from_file_location('contract',ROOT/'tests/reader_windows_compact/contract.py');cm=importlib.util.module_from_spec(cs);cs.loader.exec_module(cm);sys.modules['contract']=cm
N=importlib.util.module_from_spec(spec);spec.loader.exec_module(N)
sys.modules['contract']=saved_contract
P=N.P;U=N.U;send=N.send
class Driver:
    def __init__(self,out,program,font):self.out=out;self.program=program;self.font=font;self.app=None
    def launch(self,stage):
        self.app=P.App(self.program,self.font,self.out/'profile',existing=stage>1);self.app.wait_idle(timeout=30)
        return self.app.process
    def state(self):
        a=self.app
        return dict(label=a.label(),status=a.status(),books=send(a.control('books'),0x18B),reading=N.visible(a,123),library=N.visible(a,119),import_enabled=bool(U.IsWindowEnabled(a.control('import'))),dialogs=self.dialogs())
    def dialogs(self):
        found=[]
        @P.ENUM
        def visit(w,_):
            pid=W.DWORD();U.GetWindowThreadProcessId(w,C.byref(pid))
            if pid.value==self.app.process.pid and U.IsWindowVisible(w) and w!=self.app.window:found.append(dict(hwnd=w,title=P.text(w)))
            return True
        U.EnumWindows(visit,0);return found
    def open(self,path,importing=False):
        a=self.app
        N.command(a,46001);a.wait(lambda:N.visible(a,119))
        if importing:N.picker(a,path)
        a.focus()
        def found_row():
            try:return a.row(path.stem)+1
            except AssertionError:return None
        selected=a.wait(found_row,timeout=30)-1
        send(a.control('books'),0x186,selected);a.click('open');a.wait_idle(timeout=30)
        a.wait(lambda:N.visible(a,123));assert a.label()
    def forward(self):
        self.before_page=self.app.label();self.app.click('next');self.app.wait_idle(timeout=30)
        assert self.app.label()!=self.before_page,(self.before_page,self.app.label())
    def backward(self):
        self.app.click('previous');self.app.wait_idle(timeout=30);assert self.app.label()==self.before_page
    def library(self):
        self.before_page=self.app.label();N.command(self.app,46001);self.app.wait(lambda:N.visible(self.app,119) and not N.visible(self.app,123))
    def resume(self):
        N.command(self.app,46002);self.app.wait_idle(timeout=30);assert N.visible(self.app,123) and self.app.label()==self.before_page
    def modal(self,name):
        identifier,child={'search':(170,171),'directory':(190,191),'records':(210,211),'settings':(260,261)}[name]
        N.command(self.app,identifier);dialog=self.app.wait(lambda:N.owned_dialog(self.app,child),timeout=30)
        assert U.IsWindowVisible(dialog)
        U.PostMessageW(dialog,0x10,0,0);self.app.wait(lambda:not U.IsWindow(dialog),timeout=30);self.app.wait_idle(timeout=30)
    def import_cancel(self):
        before=self.state();N.picker(self.app);after=self.state()
        assert before['books']==after['books'] and before['label']==after['label'] and not after['dialogs']
    def close_processing(self,path):
        self.open(path,True);N.command(self.app,170);d=self.app.wait(lambda:N.owned_dialog(self.app,171))
        P.set_text(U.GetDlgItem(d,171),'ABSENT_QUERY_FOR_FULL_CHAPTER_SCAN')
        # Native Find button dispatch, immediately observe disabled Find and enabled Cancel.
        send(U.GetDlgItem(d,172),0xF5)
        self.app.wait(lambda:not U.IsWindowEnabled(U.GetDlgItem(d,172)) and U.IsWindowEnabled(U.GetDlgItem(d,176)),timeout=10)
        observed=dict(find_enabled=False,cancel_enabled=True,dialog=d,state=self.state())
        U.PostMessageW(self.app.window,0x10,0,0)
        self.app.process.wait(timeout=30);self.app.log.close();assert self.app.process.returncode==0
        return observed
    def no_replay(self):
        assert not self.dialogs();N.command(self.app,170);d=self.app.wait(lambda:N.owned_dialog(self.app,171))
        assert P.text(U.GetDlgItem(d,171))=='' and send(U.GetDlgItem(d,174),0x18B)==0
        U.PostMessageW(d,0x10,0,0);self.app.wait(lambda:not U.IsWindow(d));self.app.wait_idle(timeout=30)
        return self.state()
    def close(self):
        U.PostMessageW(self.app.window,0x10,0,0);self.app.process.wait(timeout=30);self.app.log.close();assert self.app.process.returncode==0
        return dict(exit_code=self.app.process.returncode)
    def snapshot(self,label):
        try:P.M.screenshot(self.app.window,self.out/(label+'.bmp'))
        finally:return dict(state=self.state(),windows=self.dialogs())
