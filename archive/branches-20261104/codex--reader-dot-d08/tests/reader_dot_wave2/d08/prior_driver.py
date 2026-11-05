"""Real SendInput/UIA audit of authenticated producer binaries; no command injection."""
import argparse
import ctypes as C
from ctypes import wintypes as W
import hashlib
import json
import os
from pathlib import Path
import sys
if hasattr(sys.stdout,"reconfigure"): sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr,"reconfigure"): sys.stderr.reconfigure(encoding="utf-8")
import time
import traceback
from contract import *
ROOT=Path(__file__).resolve().parents[3]/'target'
sys.path.insert(0,str(ROOT/'tests/reader_windows_preferences'))
import check_ui as P
sys.path.insert(0,str(ROOT/'tests/reader_a11y_windows'))
import w32, uia_layer, keyboard, evidence, flows
from host import Host
from session import Session
U=P.U
U.GetDpiForWindow.argtypes=[W.HWND];U.GetDpiForWindow.restype=W.UINT
U.GetDpiForSystem.restype=W.UINT
U.GetWindowDpiAwarenessContext.argtypes=[W.HWND];U.GetWindowDpiAwarenessContext.restype=W.HANDLE
U.GetAwarenessFromDpiAwarenessContext.argtypes=[W.HANDLE];U.GetAwarenessFromDpiAwarenessContext.restype=C.c_int
U.SystemParametersInfoW.argtypes=[W.UINT,W.UINT,C.c_void_p,W.UINT];U.SystemParametersInfoW.restype=W.BOOL
U.GetSysColor.argtypes=[C.c_int];U.GetSysColor.restype=W.DWORD
U.MonitorFromWindow.argtypes=[W.HWND,W.DWORD];U.MonitorFromWindow.restype=W.HANDLE
SHCORE=C.WinDLL("shcore")
SHCORE.GetScaleFactorForMonitor.argtypes=[W.HANDLE,C.POINTER(C.c_int)];SHCORE.GetScaleFactorForMonitor.restype=C.c_long
def monitor_scale(hwnd):
    value=C.c_int();hr=SHCORE.GetScaleFactorForMonitor(U.MonitorFromWindow(hwnd,2),C.byref(value))
    return {"hresult":hr,"scale_percent":value.value if hr==0 else None}
class HC(C.Structure): _fields_=[('cbSize',W.UINT),('dwFlags',W.DWORD),('lpszDefaultScheme',W.LPWSTR)]
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,data):Path(p).write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding='utf-8')
def hc_read():
    h=HC();h.cbSize=C.sizeof(h);assert U.SystemParametersInfoW(0x42,h.cbSize,C.byref(h),0);return h
def lum(rgb):
    v=[x/255 for x in rgb];v=[x/12.92 if x<=.04045 else ((x+.055)/1.055)**2.4 for x in v]
    return sum(a*b for a,b in zip(v,[.2126,.7152,.0722]))
def rgb(n):return [n&255,(n>>8)&255,(n>>16)&255]
def colors():
    raw={str(i):rgb(U.GetSysColor(i)) for i in (5,8,13,14,15,17,18)}
    pairs={}
    for a,b in ((8,5),(14,13),(18,15),(17,15)):
        l1,l2=sorted((lum(raw[str(a)]),lum(raw[str(b)])))
        pairs[f'{a}/{b}']=(l2+.05)/(l1+.05)
    return {'source':'GetSysColor: WINDOW=5 WINDOWTEXT=8 HIGHLIGHT=13 HIGHLIGHTTEXT=14 BTNFACE=15 GRAYTEXT=17 BTNTEXT=18','rgb':raw,'WCAG_2_relative_luminance_ratios':pairs,'limitation':'system palette only, not proof of actual control/page paint; no antialiased screenshot compliance inference'}
class Audit:
    def __init__(self,args):
        self.args=args;self.out=args.output.resolve();self.out.mkdir(parents=True,exist_ok=True)
        self.trace=evidence.Trace(self.out/'key-trace.jsonl');self.uia=uia_layer.Uia();assert self.uia.available
        producer=ROOT/'build/d02-producer';self.fixtures=producer/'wprefs-fixtures'
        self.exe=producer/('compact-host/EXReaderProduct.exe' if args.mode=='ON' else 'ws-package/EXReader/EXReader.exe')
        self.font=producer/'ws-package/EXReader/Reader.otf'
        self.r=dict(harness_sha=os.environ['GITHUB_SHA'],run_id=os.environ['GITHUB_RUN_ID'],attempt=os.environ['GITHUB_RUN_ATTEMPT'],
            target_sha=TARGET,producer_sha=PRODUCER,producer_run=RUN,producer_attempt=1,sdk_source=SDK,sdk_version='3.41.0',sdk_abi=1,core_version='3.40.0',
            sdk_linkage='static; no standalone SDK DSO in audited producer package',sdk_sha256=None,compact=args.mode,
            program_sha256=digest(self.exe),accepted=False,audit_completed=False,keyboard_accepted=False,contrast_accepted=False,screen_reader_accepted=False,
            checks=[],snapshots=[],screenshots=[],limitations=['No human/NVDA/Narrator pass','Geometry resizing is not DPI scaling','Historical 22-check compact result is not rerun or transferred','System color ratios do not certify all painted pixels','One immutable producer candidate, not current unified source'],errors=[])
        self.app=None;self.n=0
    def launch(self,label):
        self.app=P.App(self.exe.resolve(),self.font.resolve(),self.out/('profile-'+label));self.app.wait_idle();self.app.focus()
        self.app.wait(lambda:U.IsWindowVisible(self.app.window),timeout=15)
        self.kb=keyboard.Keyboard(self.app.window,trace=self.trace,delay=.15);self.kb.transport='sendinput'
        self.trace.event('launch',{'pid':self.app.process.pid,'program_sha256':digest(self.exe),'profile':label})
    def close(self):
        if self.app:
            self.app.close();self.app=None
    def check(self,id,status,actual,scope='keyboard',refs=None):
        self.r['checks'].append(dict(id=id,status=status,scope=scope,actual=actual,evidence=refs or ['key-trace.jsonl']))
        print(json.dumps(self.r['checks'][-1],ensure_ascii=False),flush=True)
    def key(self,key,mods=()):self.kb.press(key,mods,note='D02 genuine input')
    def shot(self,label,hwnd=None):
        hwnd=hwnd or self.app.window;name=f'{self.n:03d}-{label}';self.n+=1
        P.M.screenshot(hwnd,self.out/(name+'.bmp'));self.r['screenshots'].append(name+'.bmp')
        tree=self.uia.dump(hwnd,max_depth=5,pattern_depth=3)
        payload={'tree':tree,'focus':self.uia.focused(),'native_focus':self.kb.focus(),'window_rect':w32.window_rect(hwnd),
                 'monitor_scale':monitor_scale(hwnd),'window_dpi':int(U.GetDpiForWindow(hwnd)),'system_dpi':int(U.GetDpiForSystem()),'awareness':int(U.GetAwarenessFromDpiAwarenessContext(U.GetWindowDpiAwarenessContext(hwnd)))}
        write(self.out/(name+'.json'),payload);self.r['snapshots'].append(name+'.json');return payload
    def goto(self,id,back=False):
        target=U.GetDlgItem(self.app.window,id);seen=[]
        for _ in range(60):
            focus=self.kb.focus()
            if focus==target:return True
            if focus in seen:return False
            seen.append(focus);self.key('tab',('shift',) if back else ())
        return False
    def dialog(self):
        candidates=[h for h in w32.top_windows() if w32.thread_id(h)[1]==self.app.process.pid and h!=self.app.window and U.IsWindowVisible(h)]
        return candidates[-1] if candidates else None
    def wait_dialog(self):return self.app.wait(self.dialog,timeout=8)
    def menu(self,letter,index):
        self.key(ord(letter),('alt',));self.key('home')
        for _ in range(index):self.key('down')
        self.shot('menu-'+letter);self.key('enter')
    def dpi(self):
        work=W.RECT();assert U.SystemParametersInfoW(0x30,0,C.byref(work),0)
        self.r['work_area']=[work.left,work.top,work.right,work.bottom]
        # SPI_SETLOGICALDPIOVERRIDE is a session request, not registry/account mutation.
        # Its index is relative to the display recommendation, so ONLY readback grants requested scale.
        for scale,override in ((100,0),(150,1),(200,2)):
            before=int(U.GetDpiForWindow(self.app.window));C.set_last_error(0)
            ok=bool(U.SystemParametersInfoW(0x009F,override,None,0));error=C.get_last_error();time.sleep(.5)
            snap=self.shot('dpi-request-'+str(scale));actual=snap['window_dpi']
            self.check('dpi-'+str(scale),'pass' if actual==96*scale/100 and snap['monitor_scale']['scale_percent']==scale else 'pending',{'requested_percent':scale,'relative_override_request':override,'api_return':ok,'winerror':error,'before':before,'readback':actual,'monitor_scale':snap['monitor_scale'],'system_dpi':snap['system_dpi'],'awareness':snap['awareness'],'limitation':'Relative override is not an absolute DPI API; unavailable readback remains pending'},'dpi',[self.r['snapshots'][-1],self.r['screenshots'][-1]])
        U.SystemParametersInfoW(0x009F,0,None,0)
    def geometry(self,label,size):
        self.app.settle(size);snap=self.shot(label);r=snap['window_rect'];issues=[];nodes=[]
        def walk(node):
            if node.get('native_hwnd') and node.get('rect') and not node.get('offscreen') and node.get('depth',0)>0:
                b=node['rect'];nodes.append(node)
                if b[2]>b[0] and b[3]>b[1] and (b[0]<r[0] or b[1]<r[1] or b[2]>r[2] or b[3]>r[3]):issues.append({'outside_window':node})
            for child in node.get('children',[]):walk(child)
        walk(snap['tree'])
        work=self.r['work_area']
        if r[0]<work[0] or r[1]<work[1] or r[2]>work[2] or r[3]>work[3]:issues.append({'window_outside_work_area':r,'work_area':work})
        for i,a in enumerate(nodes):
            if a.get('control_type') not in ('ButtonControl','EditControl'):continue
            for b in nodes[i+1:]:
                if b.get('control_type') not in ('ButtonControl','EditControl'):continue
                x,y=a['rect'],b['rect'];dx=min(x[2],y[2])-max(x[0],y[0]);dy=min(x[3],y[3])-max(x[1],y[1])
                if dx>2 and dy>2:issues.append({'overlap':[a['automation_id'],b['automation_id']],'intersection':[dx,dy]})
        self.check(label,'fail' if issues else 'pass',{'requested_geometry':size,'actual':r,'measured_bounds_findings':issues,'limited_to':'visible native button/edit overlap and exposed bounds, not glyph clipping'},'geometry',[self.r['snapshots'][-1],self.r['screenshots'][-1]])
    def tab(self,reverse=False):
        order=[]
        for _ in range(50):
            self.key('tab',('shift',) if reverse else ());state=self.uia.focused();hw=self.kb.focus();order.append({'hwnd':hw,'uia':state})
            if len(order)>1 and hw in [i['hwnd'] for i in order[:-1]]:break
        self.shot('reverse-tab' if reverse else 'forward-tab')
        no_trap=len({i['hwnd'] for i in order})>1 and all(i['hwnd'] and i['uia'] and i['uia'].get('native_hwnd')==i['hwnd'] for i in order)
        self.check('tab-reverse' if reverse else 'tab-forward','pass' if no_trap else 'fail',{'order':order,'limited_to':'observed initial page cycle; full journey separately gated'})
    def picker_cancel(self):
        if self.args.mode=='OFF':
            self.check('picker-cancel','pending','Default OFF has no compact system picker shortcut; original path-field import is audited separately');return
        before=self.kb.focus();self.key(ord('O'),('ctrl',));d=self.wait_dialog();self.shot('picker-cancel-before',d);self.key('escape');self.app.wait(lambda:not U.IsWindow(d),timeout=10);self.shot('picker-cancel-after')
        self.check('picker-cancel','pass' if self.kb.focus()==before else 'fail',{'focus_before':before,'focus_after':self.kb.focus(),'closed':True})
    def import_open(self,kind):
        file=(self.fixtures/FORMATS[kind]).resolve();assert file.is_file()
        if self.args.mode=='ON':
            self.key(ord('O'),('ctrl',));d=self.wait_dialog();self.shot(kind+'-picker',d)
            self.key(ord('N'),('alt',));self.key(ord('A'),('ctrl',));self.kb.type_text(str(file));self.key('enter');self.app.wait(lambda:not U.IsWindow(d),timeout=20)
        else:
            assert self.goto(101),'Tab cannot reach import path (no focus recovery)'
            self.key(ord('A'),('ctrl',));self.kb.type_text(str(file));assert self.goto(102),'Tab cannot reach import button';self.key('space')
        self.app.wait_idle();self.shot(kind+'-imported')
        assert P.send(self.app.control('books'),0x18B)>0,'No imported book row'
        assert self.goto(119),'Tab cannot reach bookshelf (no focus recovery)';self.key('home')
        assert self.goto(103),'Tab cannot reach Open (no focus recovery)';self.key('space');self.app.wait_idle();self.shot(kind+'-reading')
        assert self.app.label().strip() and U.IsWindowVisible(self.app.control('page')),'No reading view'
    def one_dialog(self,name,op):
        before=self.kb.focus();op();d=self.wait_dialog();s=self.shot(name,d)
        self.key('tab');self.key('tab',('shift',));self.key('escape')
        self.app.wait(lambda:not U.IsWindow(d),timeout=8);after=self.kb.focus();self.shot(name+'-closed')
        assert s['tree'].get('name') and 'Window' in s['tree'].get('control_type',''),'Dialog lacks name/role'
        assert after==before, f'Focus not restored: {before} -> {after}'
    def run(self):
        original_hc=hc_read()
        try:
            self.launch('initial');self.dpi();self.geometry('baseline-layout',(1100,720));self.geometry('small-layout',(700,480));self.app.settle((1100,720))
            # Preserve G12 launch assertions, without the old runner's false SDK3.40 identity.
            h=Host(self.exe,self.out/'profile-initial',trace=self.trace);h.hwnd=self.app.window;h.pid=self.app.process.pid;h.process=self.app.process;h.refresh()
            s=Session(h,self.kb,self.uia,self.trace,self.out/'reused-g12');rec=evidence.Recorder(self.trace);flows.phase_launch(s,rec)
            write(self.out/'g12-named-checks.json',rec.checks)
            for c in rec.checks:self.check('G12-'+c['id'],{'gap':'pending','not_verified':'pending'}.get(c['status'],c['status']),c,'uia',['g12-named-checks.json'])
            self.tab();self.tab(True)
            self.attempt('picker-cancel',self.picker_cancel)
            self.check('normal-colors','pass',colors(),'contrast',[self.r['screenshots'][-1]])
            h=hc_read();h.dwFlags|=1;C.set_last_error(0);ok=bool(U.SystemParametersInfoW(0x43,h.cbSize,C.byref(h),2));err=C.get_last_error();time.sleep(.5)
            actual=hc_read();self.shot('high-contrast');self.check('high-contrast-colors','pass' if ok and actual.dwFlags&1 else 'pending',{'api_return':ok,'winerror':err,'readback_flags':actual.dwFlags,'palette':colors(),'paint_review':'raw BMP retained; semantic/focus/disabled paint not certified'},'contrast',[self.r['screenshots'][-1]])
            U.SystemParametersInfoW(0x43,original_hc.cbSize,C.byref(original_hc),2)
            self.check('text-clipping','pending','UIA bounds alone cannot establish glyph clipping; raw baseline/small BMP and trees retained for visual review','geometry',list(self.r['screenshots']))
            before=self.kb.focus();a=P.shot(self.app.window);self.key('tab');b=P.shot(self.app.window)
            delta=sum(x!=y for x,y in zip(a[2],b[2]));self.shot('focus-after-tab')
            self.check('focus-visible','pending',{'focus_before':before,'focus_after':self.kb.focus(),'whole_window_changed_bytes':delta,'limitation':'whole-window repaint is not a verified focus-region difference'},'geometry',[self.r['screenshots'][-1]])
            self.close()
            for kind in FORMATS:
                self.launch(kind)
                self.attempt(kind+'-keyboard-import-open',lambda kind=kind:self.import_open(kind))
                if kind=='txt':
                    def journey():
                        assert any(c['id']=='txt-keyboard-import-open' and c['status']=='pass' for c in self.r['checks']),'Import/open was blocked'
                        assert self.goto(123),'Reading region unreachable'
                        before=self.app.label();self.key('right');self.app.wait_idle();self.shot('journey-turn');assert self.app.label()!=before,'Arrow did not turn page'
                        self.one_dialog('journey-search',lambda:self.key(ord('F'),('ctrl',)))
                        self.one_dialog('journey-records',lambda:self.key(ord('L'),('ctrl',)))
                        self.key('left',('alt',));self.shot('journey-return');assert U.IsWindowVisible(self.app.control('books')),'Shelf not visible'
                    self.attempt('keyboard-journey',journey)
                    for name,key in [('search',ord('F')),('directory',ord('G')),('records',ord('L')),('settings',0xBC)]:
                        self.attempt(name,lambda name=name,key=key:self.one_dialog(name,lambda:self.key(key,('ctrl',))))
                    def account():
                        if self.args.mode=='ON':self.one_dialog('account',lambda:self.menu('B',5))
                        else:
                            assert self.goto(137),'Account unreachable by Tab'
                            self.one_dialog('account',lambda:self.key('space'))
                    self.attempt('account',account)
                    def more():
                        if self.args.mode=='OFF':
                            assert U.IsWindowVisible(U.GetDlgItem(self.app.window,122));self.shot('default-full-panel');return
                        self.key(ord('V'),('alt',));self.shot('view-menu');self.key(ord('M'));self.shot('more-expanded')
                        assert U.IsWindowVisible(U.GetDlgItem(self.app.window,122)),'More panel not expanded'
                        self.geometry('expanded-small-layout',(700,480))
                    self.attempt('more-panel',more)
                self.close()
            self.check('screen-reader','pending','NVDA, Narrator and human speech/navigation not executed','screen-reader')
        except Exception:
            self.r['errors'].append(traceback.format_exc())
        finally:
            U.SystemParametersInfoW(0x43,original_hc.cbSize,C.byref(original_hc),2)
            self.close();self.trace.close()
            for id in SCOPES:
                if not any(c['id']==id for c in self.r['checks']):self.check(id,'error','Audit interrupted before this required observation: '+str(self.r['errors']),'environment')
            self.r['audit_completed']=not any(c['status']=='error' for c in self.r['checks'])
            self.r['files']=[{'path':str(p.relative_to(self.out)).replace('\\','/'),'bytes':p.stat().st_size,'sha256':digest(p)} for p in sorted(self.out.rglob('*')) if p.is_file() and 'profile-' not in str(p.relative_to(self.out)) and p.name!='report.json']
            write(self.out/'report.json',self.r);print(json.dumps(self.r,ensure_ascii=False),flush=True)
            validate(self.r,os.environ['GITHUB_SHA'],os.environ['GITHUB_RUN_ID'],os.environ['GITHUB_RUN_ATTEMPT'],self.args.mode)
            assert self.r['audit_completed'],self.r['errors']
    def attempt(self,id,fn):
        try:
            fn()
            if not any(c['id']==id for c in self.r['checks']):self.check(id,'pass','Actual keyboard/UIA step completed',refs=list(self.r['snapshots'][-2:])+['key-trace.jsonl'])
        except (AssertionError,TimeoutError) as exc:
            self.shot(id+'-failed');self.check(id,'fail',str(exc),refs=list(self.r['snapshots'][-2:])+['key-trace.jsonl'])
            # Close stuck dialogs with real Escape only, recording the recovery.
            for _ in range(3):
                if not self.dialog():break
                self.trace.event('recovery_escape',{'after_failed_check':id});self.key('escape')
if __name__=='__main__':
    assert os.name=='nt' and os.environ.get('GITHUB_ACTIONS')=='true'
    p=argparse.ArgumentParser();p.add_argument('--mode',choices=['ON','OFF'],required=True);p.add_argument('--output',type=Path,required=True)
    w32.make_dpi_aware()  # Audit process only; never changes the target awareness.
    Audit(p.parse_args()).run()
