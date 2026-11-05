"""Actions-only display capabilities and supported Settings UI scale requests.

No registry DPI edits, forced app awareness, synthetic WM_DPICHANGED, display
image resizing, undocumented DPI setter or user-computer operation is used.
"""
import ctypes as C
from ctypes import wintypes as W
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import time
import traceback
from contract import actual_scale
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'build/d20-evidence/display'
sys.path.insert(0, str(ROOT / 'tests/reader_a11y_windows'))
import w32
U = w32.user32
K = C.WinDLL('kernel32', use_last_error=True)
S = C.WinDLL('shcore', use_last_error=True)
MONPROC = C.WINFUNCTYPE(W.BOOL, W.HANDLE, W.HDC, C.POINTER(W.RECT), W.LPARAM)
_MODE = None


class MonitorInfo(C.Structure):
    _fields_ = [('size',W.DWORD),('monitor',W.RECT),('work',W.RECT),('flags',W.DWORD),('device',W.WCHAR*32)]


U.EnumDisplayMonitors.argtypes = [W.HDC,C.POINTER(W.RECT),MONPROC,W.LPARAM]
U.EnumDisplayMonitors.restype = W.BOOL
U.GetMonitorInfoW.argtypes = [W.HANDLE,C.POINTER(MonitorInfo)]
U.GetMonitorInfoW.restype = W.BOOL
U.SetThreadDpiAwarenessContext.argtypes = [W.HANDLE]
U.SetThreadDpiAwarenessContext.restype = W.HANDLE
U.GetThreadDpiAwarenessContext.restype = W.HANDLE
U.GetAwarenessFromDpiAwarenessContext.argtypes = [W.HANDLE]
U.GetAwarenessFromDpiAwarenessContext.restype = C.c_int
U.CreateWindowExW.argtypes = [W.DWORD,W.LPCWSTR,W.LPCWSTR,W.DWORD,C.c_int,C.c_int,C.c_int,C.c_int,W.HWND,W.HMENU,W.HINSTANCE,W.LPVOID]
U.CreateWindowExW.restype = W.HWND
U.DestroyWindow.argtypes = [W.HWND]
U.GetDpiForWindow.argtypes = [W.HWND]
U.GetDpiForWindow.restype = W.UINT
U.GetWindowDpiAwarenessContext.argtypes = [W.HWND]
U.GetWindowDpiAwarenessContext.restype = W.HANDLE
S.GetScaleFactorForMonitor.argtypes = [W.HANDLE,C.POINTER(C.c_int)]
S.GetScaleFactorForMonitor.restype = C.c_long
K.ProcessIdToSessionId.argtypes = [W.DWORD,C.POINTER(W.DWORD)]
K.ProcessIdToSessionId.restype = W.BOOL


def allowed():
    assert os.environ.get('GITHUB_ACTIONS') == 'true' and os.name == 'nt'
    # This workflow only uses GitHub-hosted ephemeral runners; never a named PC.
    assert os.environ.get('RUNNER_ENVIRONMENT') == 'github-hosted'


def save(name, value):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def rect(r): return [r.left,r.top,r.right,r.bottom]


def readback():
    allowed()
    monitors=[]; errors=[]
    @MONPROC
    def visit(handle, dc, bounds, unused):
        info=MonitorInfo(); info.size=C.sizeof(info)
        if not U.GetMonitorInfoW(handle,C.byref(info)):
            errors.append({'GetMonitorInfoW':C.get_last_error()});return True
        scale=C.c_int();hr=S.GetScaleFactorForMonitor(handle,C.byref(scale))
        previous=U.SetThreadDpiAwarenessContext(C.c_void_p(-4))
        probe=0
        try:
            assert previous, ('PMv2 context unavailable',C.get_last_error())
            probe=U.CreateWindowExW(0,'STATIC','D20 independent DPI probe',0x80000000,
                info.monitor.left+32,info.monitor.top+32,64,64,None,None,None,None)
            assert probe, ('probe window unavailable',C.get_last_error())
            dpi=int(U.GetDpiForWindow(probe))
            awareness=int(U.GetAwarenessFromDpiAwarenessContext(U.GetWindowDpiAwarenessContext(probe)))
            monitors.append(dict(handle=int(handle),device=info.device,primary=bool(info.flags&1),
                monitor_pixels=rect(info.monitor),work_pixels=rect(info.work),scale_hresult=hr,
                scale_percent=scale.value if hr==0 else None,probe_dpi=dpi,probe_awareness=awareness,
                probe_kind='new independent hidden PMv2 STATIC window; not the product window'))
        except Exception:
            errors.append({'monitor':info.device,'probe_error':traceback.format_exc()})
        finally:
            if probe:U.DestroyWindow(probe)
            if previous:U.SetThreadDpiAwarenessContext(previous)
        return True
    assert U.EnumDisplayMonitors(None,None,visit,0)
    return dict(monitors=monitors,errors=errors,remote_session=bool(U.GetSystemMetrics(0x1000)),
                virtual_screen_pixels=[U.GetSystemMetrics(i) for i in (76,77,78,79)])


def inventory():
    allowed(); OUT.mkdir(parents=True,exist_ok=True)
    spec=importlib.util.spec_from_file_location('original_display_structs',ROOT/'tests/reader_native_owner_repairs/display.py')
    old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
    assert C.sizeof(old.MODE)==220
    U.EnumDisplaySettingsW.argtypes=[W.LPCWSTR,W.DWORD,C.POINTER(old.MODE)]
    U.EnumDisplaySettingsW.restype=W.BOOL
    modes=[]
    for index in range(2048):
        mode=old.MODE();mode.size=C.sizeof(mode)
        if not U.EnumDisplaySettingsW(None,index,C.byref(mode)):break
        modes.append(dict(width=mode.width,height=mode.height,bits=mode.bits,frequency=mode.frequency,log_pixels=mode.log_pixels))
    session=W.DWORD();assert K.ProcessIdToSessionId(os.getpid(),C.byref(session))
    r=dict(source_sha=os.environ['GITHUB_SHA'],run_id=os.environ['GITHUB_RUN_ID'],attempt=os.environ['GITHUB_RUN_ATTEMPT'],
           os=platform.platform(),runner_environment=os.environ['RUNNER_ENVIRONMENT'],session_id=session.value,
           display_modes=modes,readback=readback(),mutation_performed=False)
    for label,argv in [('session',['query','session']),('adapters',['powershell','-NoProfile','-Command',
        'Get-CimInstance Win32_VideoController | Select-Object Name,DriverVersion,VideoModeDescription,CurrentHorizontalResolution,CurrentVerticalResolution | ConvertTo-Json -Depth 4'])]:
        p=subprocess.run(argv,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=30)
        (OUT/(label+'.txt')).write_bytes(p.stdout);r[label+'_exit']=p.returncode
    save('inventory.json',r); print(json.dumps(r),flush=True)


def walk(control, max_depth=10):
    stack=[(control,0)];count=0
    while stack and count<3000:
        node,depth=stack.pop();count+=1;yield node
        if depth<max_depth:
            try:stack.extend((child,depth+1) for child in reversed(node.GetChildren()))
            except Exception:continue


def mode_api():
    global _MODE
    allowed()
    if _MODE is None:
        spec=importlib.util.spec_from_file_location('d20_mode_structs',ROOT/'tests/reader_native_owner_repairs/display.py')
        original=importlib.util.module_from_spec(spec);spec.loader.exec_module(original)
        _MODE=original.MODE
    U.EnumDisplaySettingsW.argtypes=[W.LPCWSTR,W.DWORD,C.POINTER(_MODE)]
    U.EnumDisplaySettingsW.restype=W.BOOL
    U.ChangeDisplaySettingsExW.argtypes=[W.LPCWSTR,C.POINTER(_MODE),W.HWND,W.DWORD,W.LPVOID]
    U.ChangeDisplaySettingsExW.restype=W.LONG
    return _MODE


def current_mode():
    cls=mode_api();mode=cls();mode.size=C.sizeof(mode)
    assert U.EnumDisplaySettingsW(None,0xFFFFFFFF,C.byref(mode))
    return mode


def mode_fields(mode):
    return dict(width=mode.width,height=mode.height,bits=mode.bits,frequency=mode.frequency)


def apply_mode(mode,label):
    allowed();before=mode_fields(current_mode())
    mode.fields=0x40000|0x80000|0x100000
    test=int(U.ChangeDisplaySettingsExW(None,C.byref(mode),None,2,None))
    result=int(U.ChangeDisplaySettingsExW(None,C.byref(mode),None,0,None)) if test==0 else None
    time.sleep(1)
    actual=mode_fields(current_mode())
    r=dict(before=before,requested=mode_fields(mode),native_test_return=test,native_apply_return=result,
           actual_mode=actual,readback=readback(),applied=result==0 and actual==mode_fields(mode),
           method='enumerated native ChangeDisplaySettingsEx mode; no image rescaling or registry persistence')
    save(label+'.json',r);print('DISPLAY_MODE',json.dumps(r),flush=True)
    return r


def prepare_high_scale_mode():
    # CI1 enumerated real 1600x1200 support while the 1024x768 Settings UI
    # exposed no high-scale option. Preserve the complete 100% run first,
    # then use an actually enumerated mode with room for 800x600 at 200%.
    cls=mode_api();modes=[]
    for i in range(2048):
        mode=cls();mode.size=C.sizeof(mode)
        if not U.EnumDisplaySettingsW(None,i,C.byref(mode)):break
        if mode.width>=1600 and mode.height>=1200 and mode.bits>=24:modes.append(mode)
    if not modes:
        r=dict(applied=False,reason='no enumerated physical mode with 1600x1200 capacity',readback=readback())
        save('high-scale-mode.json',r);return r
    mode=min(modes,key=lambda m:(m.width*m.height,-m.bits))
    return apply_mode(mode,'high-scale-mode')


def request_scale(percent, label):
    allowed()
    before=readback()
    r=dict(requested_percent=percent,before=before,method='ms-settings:display UIA SelectionItemPattern',actions=[],available=False)
    if actual_scale(before,percent):
        r.update(available=True,readback=before,reason='already active, independently read back')
        save(label+'.json',r);return r
    from uia_layer import Uia
    import png
    ui=Uia();assert ui.available
    window=None
    def capture(suffix):
        if window is None:return
        hwnd=window.NativeWindowHandle
        save(label+'-'+suffix+'-uia.json',ui.dump(hwnd,max_depth=10,pattern_depth=3))
        shot=w32.capture_rgb(hwnd)
        if 'error' in shot:
            r.setdefault('capture_errors',[]).append(shot);return
        png.write_png(OUT/(label+'-'+suffix+'.png'),shot['width'],shot['height'],shot['rgb'])
    try:
        os.startfile('ms-settings:display');r['actions'].append('ShellExecute ms-settings:display')
        end=time.monotonic()+20
        while time.monotonic()<end:
            candidates=[c for c in ui.auto.GetRootControl().GetChildren()
                        if c.Name in ('Settings','Display') and c.ClassName in ('ApplicationFrameWindow','Windows.UI.Core.CoreWindow')]
            if len(candidates)==1:window=candidates[0];break
            time.sleep(.25)
        if window is None:
            r['reason']='Settings display page absent in this runner/session; no alternate mutation attempted'
            r['top_level_windows']=[ui.describe(c) for c in ui.auto.GetRootControl().GetChildren()]
        else:
            time.sleep(1);capture('before')
            nodes=list(walk(window));combos=[]
            for node in nodes:
                if node.ControlTypeName=='ComboBoxControl':
                    ident=(node.Name+' '+node.AutomationId).lower()
                    if 'scale' in ident or 'size of text' in ident or 'dpi' in ident:combos.append(node)
            r['scale_controls']=[ui.describe(n,patterns=True) for n in combos]
            if len(combos)!=1:
                r['reason']='No unique native scale ComboBox exposed; unsupported capability remains pending'
            elif not combos[0].IsEnabled:
                r['reason']='Native Settings scale ComboBox is disabled in this actual session'
            else:
                combo=combos[0];combo.GetExpandCollapsePattern().Expand();time.sleep(.4)
                capture('expanded')
                # XAML ComboBox popup items may be a sibling desktop subtree,
                # not descendants of ApplicationFrameWindow. Enumerate only
                # the actual Settings provider PID and advertised selection
                # items, preserving all offered option names/patterns.
                provider_pid=combo.ProcessId
                options=[];candidates=[];seen=set()
                for n in walk(ui.auto.GetRootControl(),max_depth=14):
                    if n.ProcessId!=provider_pid or not re.match(r'^\d+%($|\s|\()',n.Name):continue
                    item=ui.describe(n,patterns=True)
                    try:identity=tuple(n.Element.GetRuntimeId())
                    except Exception:identity=(n.Name,n.AutomationId,str(n.BoundingRectangle))
                    if identity in seen:continue
                    seen.add(identity);options.append(item)
                    if re.match(r'^'+str(percent)+r'%($|\s|\()',n.Name) and not item['offscreen'] and 'SelectionItemPattern' in item.get('patterns',[]):candidates.append(n)
                r['offered_scale_options']=options
                r['matching_options']=[ui.describe(n,patterns=True) for n in candidates]
                if len(candidates)!=1:
                    r['reason']='Requested exact scale is not uniquely offered by native Settings'
                elif not candidates[0].IsEnabled:
                    r['reason']='Requested native Settings scale option disabled'
                else:
                    candidates[0].GetSelectionItemPattern().Select()
                    r['actions'].append('Select offered native option '+candidates[0].Name)
                    end=time.monotonic()+15
                    while time.monotonic()<end:
                        current=readback()
                        if actual_scale(current,percent):break
                        time.sleep(.25)
                    r['reason']='native request completed; only independent readback grants actual scale'
                capture('after')
    except Exception:
        r['driver_exception']=traceback.format_exc()
        r['reason']='Settings capability probe failed; not a scale success'
    finally:
        if window is not None:
            # Close only the Settings window opened for this capability probe.
            try:window.GetWindowPattern().Close()
            except Exception:r['settings_close_error']=traceback.format_exc()
        r['readback']=readback();r['available']=actual_scale(r['readback'],percent)
        save(label+'.json',r)
        print('DISPLAY_CAPABILITY',json.dumps(r,ensure_ascii=True),flush=True)
    return r


if __name__=='__main__':
    assert sys.argv[1:]==['--inventory']
    inventory()
