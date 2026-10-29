#!/usr/bin/env python3
"""Actions-only actual Windows product startup admission."""
import argparse,contextlib,ctypes,hashlib,json,os,sqlite3,subprocess,sys,time
from ctypes import wintypes as W
from pathlib import Path
assert os.environ.get('GITHUB_ACTIONS')=='true' and os.name=='nt'
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tests/migration'))
import legacy_data as L
p=argparse.ArgumentParser()
p.add_argument('--host',type=Path,required=True);p.add_argument('--old-tool',type=Path,required=True)
p.add_argument('--font',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
a=p.parse_args()
a.host=a.host.resolve();a.old_tool=a.old_tool.resolve();a.font=a.font.resolve()
out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
cases=[]
def record(value):
    cases.append(value)
    (out/'report.json').write_text(json.dumps(dict(source=os.environ['GITHUB_SHA'],run=os.environ['GITHUB_RUN_ID'],
        attempt=os.environ['GITHUB_RUN_ATTEMPT'],cases=cases,expected=10,passed=False,complete=False,
        full_p0_acceptance=False),indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def state(folder):
    result={}
    for path in folder.rglob('*'):
        assert not path.is_symlink()
        s=path.stat()
        result[str(path.relative_to(folder))]={'directory':path.is_dir(),'identity':[s.st_dev,s.st_ino],
            'bytes':None if path.is_dir() else s.st_size,'sha256':None if path.is_dir() else digest(path)}
    return result
def seed(name,empty=False):
    folder=out/name;library=folder/'library';library.mkdir(parents=True)
    target=library/'library.sqlite'
    if not empty:
        entries,notes=L.dataset();pack=folder/'legacy.exrpack';pack.write_bytes(L.build_pack(entries,notes))
        r=subprocess.run([a.old_tool,'migrate','--target',target,'--pack',pack,'--allow-partial'],capture_output=True,timeout=30)
        assert r.returncode==0,(r.stdout,r.stderr)
        with contextlib.closing(sqlite3.connect(target)) as db:assert db.execute('PRAGMA user_version').fetchone()[0]==6
    return folder,target
def command(folder,target,drive=True):
    result=[str(a.host),'--data',str(folder/'host-profile'),'--library',str(target),'--font',str(a.font)]
    if drive:
        script=folder/'quit.drive';script.write_text('quit\n',encoding='utf-8')
        result+=['--drive',str(script),'--evidence',str(folder/'host-evidence')]
    return result
def preserved(target,before):
    after=state(target.parent)
    assert all(after.get(k)==v for k,v in before.items()),(before,after)
    added=set(after)-set(before)
    assert added<={target.name+'.product.lock'},added
    if added:assert after[target.name+'.product.lock']['bytes']==0
    assert not Path(str(target)+'.product.sqlite').exists()
    return after
def blocked(name,suffix,directory=False,empty=False):
    folder,target=seed(name,empty)
    marker=Path(str(target)+suffix)
    if directory:
        marker.mkdir();(marker/'retained-evidence').write_bytes(b'unknown pending evidence stays exact')
    else:marker.write_bytes(b'{incomplete original pending state\n')
    before=state(target.parent)
    r=subprocess.run(command(folder,target),capture_output=True,timeout=30)
    (folder/'stdout.txt').write_bytes(r.stdout);(folder/'stderr.txt').write_bytes(r.stderr)
    assert r.returncode==2,(r.returncode,r.stdout,r.stderr)
    assert b'[EXReader migration startup gate] blocked' in r.stderr,r.stderr
    assert suffix.encode() in r.stderr,r.stderr
    after=preserved(target,before)
    if empty:assert not target.exists()
    else:
        with contextlib.closing(sqlite3.connect(target)) as db:assert db.execute('PRAGMA user_version').fetchone()[0]==6
    record(dict(name=name,passed=True,suffix=suffix,empty=empty,before=before,after=after,exit=r.returncode))
for suffix,label in [('.migration-recovery','recovery'),('.migration-pending.json','intent'),('.migrate-lock','lock')]:
    for directory in (False,True):blocked(label+('-directory' if directory else '-file'),suffix,directory)
blocked('pending-never-creates-target','.migration-pending.json',empty=True)
for name,keep in [('clean-library',False),('legacy-sidecar-only',True)]:
    folder,target=seed(name)
    sidecar=Path(str(target)+'.legacy-map.json')
    assert sidecar.exists()
    if not keep:sidecar.unlink() # Only this explicitly disposable newly seeded fixture.
    sidecar_before=digest(sidecar) if keep else None
    r=subprocess.run(command(folder,target),capture_output=True,timeout=45)
    (folder/'stdout.txt').write_bytes(r.stdout);(folder/'stderr.txt').write_bytes(r.stderr)
    assert r.returncode==0,(r.returncode,r.stdout,r.stderr)
    assert b'migration startup gate] blocked' not in r.stderr
    with contextlib.closing(sqlite3.connect(target)) as db:
        assert db.execute('PRAGMA user_version').fetchone()[0]==7,'actual ordinary SDK open was not reached'
    assert (digest(sidecar) if keep else None)==sidecar_before
    record(dict(name=name,passed=True,actual_sdk_schema_upgrade=True,legacy_sidecar_preserved=keep,exit=r.returncode))
# Actual normal startup must visibly explain refusal, not only emit a drive log.
folder,target=seed('visible-native-refusal')
marker=Path(str(target)+'.migration-pending.json');marker.write_bytes(b'original pending user state')
before=state(target.parent)
U=ctypes.WinDLL('user32',use_last_error=True)
CALL=ctypes.WINFUNCTYPE(W.BOOL,W.HWND,W.LPARAM)
U.EnumWindows.argtypes=[CALL,W.LPARAM];U.EnumWindows.restype=W.BOOL
U.EnumChildWindows.argtypes=[W.HWND,CALL,W.LPARAM];U.EnumChildWindows.restype=W.BOOL
U.GetWindowThreadProcessId.argtypes=[W.HWND,ctypes.POINTER(W.DWORD)]
U.IsWindowVisible.argtypes=[W.HWND];U.IsWindowVisible.restype=W.BOOL
U.IsWindowEnabled.argtypes=[W.HWND];U.IsWindowEnabled.restype=W.BOOL
U.GetWindowTextW.argtypes=[W.HWND,W.LPWSTR,ctypes.c_int]
U.GetClassNameW.argtypes=[W.HWND,W.LPWSTR,ctypes.c_int]
U.GetDlgItem.argtypes=[W.HWND,ctypes.c_int];U.GetDlgItem.restype=W.HWND
U.SendMessageW.argtypes=[W.HWND,W.UINT,W.WPARAM,W.LPARAM];U.SendMessageW.restype=ctypes.c_ssize_t
U.GetWindowRect.argtypes=[W.HWND,ctypes.POINTER(W.RECT)];U.GetWindowRect.restype=W.BOOL
def window_text(hwnd):
    b=ctypes.create_unicode_buffer(4096);U.GetWindowTextW(hwnd,b,len(b));return b.value
proc=subprocess.Popen(command(folder,target,False),stdout=subprocess.PIPE,stderr=subprocess.PIPE)
dialog=None;observed=[]
try:
    deadline=time.monotonic()+20
    while time.monotonic()<deadline and proc.poll() is None:
        found=[]
        @CALL
        def visit(hwnd,param):
            pid=W.DWORD();U.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
            cls=ctypes.create_unicode_buffer(128);U.GetClassNameW(hwnd,cls,len(cls))
            if pid.value==proc.pid and U.IsWindowVisible(hwnd) and cls.value=='#32770':found.append(hwnd)
            return True
        U.EnumWindows(visit,0)
        if found:dialog=found[0];break
        time.sleep(.05)
    assert dialog is not None,'No actual visible native migration message'
    @CALL
    def child(hwnd,param):
        value=window_text(hwnd)
        if value:observed.append(value)
        return True
    U.EnumChildWindows(dialog,child,0)
    message=' '.join(observed)
    assert '迁移状态' in message and '恢复迁移' in message and '现有文件已保留' in message,message
    title=window_text(dialog)
    rect=W.RECT();assert U.GetWindowRect(dialog,ctypes.byref(rect))
    assert rect.right>rect.left and rect.bottom>rect.top
    (folder/'visible-dialog.json').write_text(json.dumps(dict(title=title,visible=True,message=message,
        rectangle=[rect.left,rect.top,rect.right,rect.bottom]),ensure_ascii=False),encoding='utf-8')
    buttons=[]
    deadline=time.monotonic()+10
    while not buttons and time.monotonic()<deadline:
        @CALL
        def find_button(hwnd,param):
            cls=ctypes.create_unicode_buffer(128);U.GetClassNameW(hwnd,cls,len(cls))
            if cls.value=='Button' and U.IsWindowVisible(hwnd) and U.IsWindowEnabled(hwnd):buttons.append(hwnd)
            return True
        U.EnumChildWindows(dialog,find_button,0)
        if not buttons:time.sleep(.05)
    assert len(buttons)==1,('Expected the actual message dialog single visible enabled button',buttons,observed)
    button=buttons[0]
    U.SendMessageW(button,0x00F5,0,0)
    stdout,stderr=proc.communicate(timeout=15)
    assert proc.returncode==2 and b'[EXReader migration startup gate] blocked' in stderr
    (folder/'stdout.txt').write_bytes(stdout);(folder/'stderr.txt').write_bytes(stderr)
    preserved(target,before)
    record(dict(name='visible-native-refusal',passed=True,pid=proc.pid,title=title,
        visible=True,message=message,rectangle=[rect.left,rect.top,rect.right,rect.bottom],exit=proc.returncode))
finally:
    if proc.poll() is None:proc.kill();proc.wait(timeout=10)
report=dict(source=os.environ['GITHUB_SHA'],run=os.environ['GITHUB_RUN_ID'],attempt=os.environ['GITHUB_RUN_ATTEMPT'],
    host_sha256=digest(a.host),old_tool_sha256=digest(a.old_tool),cases=cases,expected=10,
    passed=len(cases)==10 and all(x['passed'] for x in cases),full_p0_acceptance=False,
    scope='actual Windows product startup rejects pre-existing migration policy before ordinary SDK open; cooperative startup only')
(out/'report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
print(json.dumps(dict(source=report['source'],passed=report['passed'],cases=len(cases),expected=10,full_p0_acceptance=False)))
assert report['passed']
