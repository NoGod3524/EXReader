"""Actions-only actual product admission and final owner-release checks."""
import argparse, ctypes, hashlib, json, os, shutil, subprocess
from pathlib import Path
from ctypes import wintypes as W
assert os.environ.get("GITHUB_ACTIONS") == "true" and os.name == "nt"
p=argparse.ArgumentParser()
p.add_argument("--host",type=Path,required=True)
p.add_argument("--consumer",type=Path,required=True)
p.add_argument("--font",type=Path,required=True)
p.add_argument("--output",type=Path,required=True)
p.add_argument("--catalog-mode",choices=("product","none"),default="product")
a=p.parse_args()
a.host=a.host.resolve();a.consumer=a.consumer.resolve();a.font=a.font.resolve()
out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
results=[]
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def record(name,**evidence):
    results.append(dict(name=name,passed=True,**evidence))
    (out/"report.json").write_text(json.dumps(dict(source=os.environ["GITHUB_SHA"],
        run=os.environ["GITHUB_RUN_ID"],attempt=os.environ["GITHUB_RUN_ATTEMPT"],
        cases=results,complete=False,passed=False,full_c02_acceptance=False),indent=2)+"\n")
def seed(name,mode="--prepare-host"):
    folder=out/name;folder.mkdir()
    r=subprocess.run([a.consumer,mode],cwd=folder,capture_output=True,timeout=40)
    (folder/"seed.log").write_bytes(r.stdout+r.stderr)
    assert r.returncode==0,(r.returncode,r.stdout,r.stderr)
    lines=r.stdout.decode("utf-8").splitlines()
    library=Path(next(s[13:] for s in lines if s.startswith("HOST_LIBRARY ")))
    gate=Path(next(s[10:] for s in lines if s.startswith("HOST_GATE ")))
    return folder,library,gate
def command(folder,library,drive=True):
    args=[str(a.host),"--data",str(folder/"profile"),"--library",str(library),"--font",str(a.font)]
    if drive:
        script=folder/"quit.drive";script.write_text("quit\n")
        args+=["--drive",str(script),"--evidence",str(folder/"drive")]
    return args
for name,mode in [("registered","--prepare-host"),("unregistered","--prepare-unregistered"),
                   ("pending","--prepare-pending"),("missing-gate","--prepare-host"),("replaced-target","--prepare-host")]:
    folder,library,gate=seed(name,mode)
    if name=="missing-gate":(gate/"admission.bin").unlink()
    if name=="replaced-target":
        retained=library.with_suffix(".retained");library.rename(retained);shutil.copyfile(retained,library)
        assert retained.stat().st_ino!=library.stat().st_ino
    before=dict(sha256=sha(library),identity=[library.stat().st_dev,library.stat().st_ino])
    r=subprocess.run(command(folder,library),capture_output=True,timeout=40)
    (folder/"stdout.txt").write_bytes(r.stdout);(folder/"stderr.txt").write_bytes(r.stderr)
    if name=="registered":
        assert r.returncode==0,(r.returncode,r.stdout,r.stderr)
        assert Path(str(library)+".product.sqlite").is_file() is (a.catalog_mode=="product")
        assert b"C02 admission] refused" not in r.stderr
    else:
        assert r.returncode==2 and b"C02 admission] refused before SDK open" in r.stderr,(r.returncode,r.stderr)
        assert not Path(str(library)+".product.sqlite").exists()
        assert before==dict(sha256=sha(library),identity=[library.stat().st_dev,library.stat().st_ino])
    record(name,exit=r.returncode,target=before)
# The actual interactive product holds shared custody until its cleanup finishes.
# WaitForInputIdle and native window enumeration observe readiness; no sleep
# chooses an owner/reader race point.
folder,library,gate=seed("actual-host-final-release")
kernel=ctypes.WinDLL("kernel32",use_last_error=True)
user=ctypes.WinDLL("user32",use_last_error=True)
user.WaitForInputIdle.argtypes=[W.HANDLE,W.DWORD];user.WaitForInputIdle.restype=W.DWORD
CALL=ctypes.WINFUNCTYPE(W.BOOL,W.HWND,W.LPARAM)
user.EnumWindows.argtypes=[CALL,W.LPARAM]
user.GetWindowThreadProcessId.argtypes=[W.HWND,ctypes.POINTER(W.DWORD)]
user.IsWindowVisible.argtypes=[W.HWND];user.IsWindowVisible.restype=W.BOOL
user.PostMessageW.argtypes=[W.HWND,W.UINT,W.WPARAM,W.LPARAM];user.PostMessageW.restype=W.BOOL
proc=subprocess.Popen(command(folder,library,False),stdout=subprocess.PIPE,stderr=subprocess.PIPE)
try:
    assert user.WaitForInputIdle(W.HANDLE(int(proc._handle)),30000)==0,"actual product did not reach input idle"
    windows=[]
    @CALL
    def visit(hwnd,_):
        pid=W.DWORD();user.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
        if pid.value==proc.pid and user.IsWindowVisible(hwnd):windows.append(hwnd)
        return True
    user.EnumWindows(visit,0)
    assert len(windows)==1,(proc.pid,windows)
    probe=subprocess.run([a.consumer,"--probe-owner",library],capture_output=True,timeout=20)
    assert probe.returncode==10,(probe.returncode,probe.stderr)
    assert user.PostMessageW(windows[0],0x0010,0,0)
    stdout,stderr=proc.communicate(timeout=30)
    (folder/"stdout.txt").write_bytes(stdout);(folder/"stderr.txt").write_bytes(stderr)
    assert proc.returncode==0,(proc.returncode,stderr)
    probe=subprocess.run([a.consumer,"--probe-owner",library],capture_output=True,timeout=20)
    assert probe.returncode==0,(probe.returncode,probe.stderr)
    record("actual-host-final-release",pid=proc.pid,visible_window=True,blocked_while_live=True,admitted_after_close=True)
finally:
    if proc.poll() is None:proc.kill();proc.communicate(timeout=15)
assert len(results)==6
report=json.loads((out/"report.json").read_text())
report.update(complete=True,passed=True)
(out/"report.json").write_text(json.dumps(report,indent=2)+"\n")
print("C02-HOST cases=6 failed=0")
