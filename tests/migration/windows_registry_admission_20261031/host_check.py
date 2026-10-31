"""Actions-only actual product admission and final owner-release checks."""
import argparse, ctypes, hashlib, json, os, shutil, subprocess
from pathlib import Path
from ctypes import wintypes as W
assert os.environ.get("GITHUB_ACTIONS") == "true" and os.name == "nt"

WINDOWS_C02_PRODUCT_EVIDENCE = 1
class ProductEvidence:
    def __init__(self, output, programs):
        self.output=output;self.binaries={};self.by_path={};self.rows=[]
        (output/"binaries").mkdir();(output/"commands").mkdir()
        for role,path in programs.items():
            path=Path(path).resolve()
            with path.open("rb") as stream:
                first=os.fstat(stream.fileno());raw=stream.read();last=os.fstat(stream.fileno())
            assert (first.st_dev,first.st_ino,first.st_size,first.st_mtime_ns)==(
                last.st_dev,last.st_ino,last.st_size,last.st_mtime_ns)
            retained="binaries/"+role+".exe";(output/retained).write_bytes(raw)
            item=dict(source_path=str(path),retained=retained,bytes=len(raw),
                sha256=hashlib.sha256(raw).hexdigest(),identity=[first.st_dev,first.st_ino])
            self.binaries[role]=item;self.by_path[str(path).casefold()]=role
        (output/"binaries.json").write_text(json.dumps(self.binaries,indent=2)+"\n")
    def command(self,args):
        command=list(map(str,args));path=Path(command[0]).resolve()
        role=self.by_path[str(path).casefold()];item=self.binaries[role]
        assert hashlib.sha256(path.read_bytes()).hexdigest()==item["sha256"]
        return command,role
    def finished(self,label,proc,args,stdout,stderr,cwd=None,timed_out=False):
        command,role=self.command(args);index=len(self.rows)+1
        stdout_name="commands/%03d.stdout"%index;stderr_name="commands/%03d.stderr"%index
        (self.output/stdout_name).write_bytes(stdout);(self.output/stderr_name).write_bytes(stderr)
        row=dict(index=index,label=label,role=role,argv=command,pid=proc.pid,exit=proc.returncode,
            cwd=str(Path(cwd).resolve() if cwd is not None else Path.cwd().resolve()),timed_out=timed_out,
            binary_sha256=self.binaries[role]["sha256"],stdout=stdout_name,stderr=stderr_name,
            stdout_bytes=len(stdout),stderr_bytes=len(stderr),
            stdout_sha256=hashlib.sha256(stdout).hexdigest(),stderr_sha256=hashlib.sha256(stderr).hexdigest())
        self.rows.append(row)
        with (self.output/"commands.jsonl").open("ab") as stream:
            stream.write((json.dumps(row)+"\n").encode());stream.flush();os.fsync(stream.fileno())
    def start(self,args,**kwargs):
        command,_=self.command(args)
        return subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,**kwargs)
    def run(self,label,args,timeout=30,capture_output=True,**kwargs):
        assert capture_output is True
        command,_=self.command(args);proc=self.start(command,**kwargs)
        try:
            stdout,stderr=proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill();stdout,stderr=proc.communicate()
            self.finished(label,proc,command,stdout,stderr,kwargs.get("cwd"),True)
            raise
        self.finished(label,proc,command,stdout,stderr,kwargs.get("cwd"))
        return subprocess.CompletedProcess(command,proc.returncode,stdout,stderr)
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
evidence=ProductEvidence(out,dict(host=a.host,consumer=a.consumer))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def record(name,**evidence):
    results.append(dict(name=name,passed=True,**evidence))
    (out/"report.json").write_text(json.dumps(dict(source=os.environ["GITHUB_SHA"],
        run=os.environ["GITHUB_RUN_ID"],attempt=os.environ["GITHUB_RUN_ATTEMPT"],
        cases=results,complete=False,passed=False,full_c02_acceptance=False,
        platform="Windows",evidence_schema="c02-windows-products-v1",catalog_mode=a.catalog_mode,
        binaries=evidence.binaries,command_log="commands.jsonl"),indent=2)+"\n")
def seed(name,mode="--prepare-host"):
    folder=out/name;folder.mkdir()
    r=evidence.run("seed-"+name,[a.consumer,mode],cwd=folder,capture_output=True,timeout=40)
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
    (folder/"target-before.sqlite").write_bytes(library.read_bytes())
    r=evidence.run("host-"+name,command(folder,library),capture_output=True,timeout=40)
    (folder/"stdout.txt").write_bytes(r.stdout);(folder/"stderr.txt").write_bytes(r.stderr)
    if name=="registered":
        assert r.returncode==0,(r.returncode,r.stdout,r.stderr)
        assert Path(str(library)+".product.sqlite").is_file() is (a.catalog_mode=="product")
        assert b"C02 admission] refused" not in r.stderr
    else:
        assert r.returncode==2 and b"C02 admission] refused before SDK open" in r.stderr,(r.returncode,r.stderr)
        assert not Path(str(library)+".product.sqlite").exists()
        assert before==dict(sha256=sha(library),identity=[library.stat().st_dev,library.stat().st_ino])
    (folder/"target-observation.json").write_text(json.dumps(dict(source_path=str(library),
        before=before,after=dict(sha256=sha(library),identity=[library.stat().st_dev,library.stat().st_ino])),indent=2)+"\n")
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
live_command=command(folder,library,False)
proc=evidence.start(live_command)
try:
    idle=user.WaitForInputIdle(W.HANDLE(int(proc._handle)),30000)
    (folder/"input-idle.json").write_text(json.dumps(dict(pid=proc.pid,result=idle))+"\n")
    assert idle==0,"actual product did not reach input idle"
    windows=[]
    @CALL
    def visit(hwnd,_):
        pid=W.DWORD();user.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
        if pid.value==proc.pid and user.IsWindowVisible(hwnd):windows.append(hwnd)
        return True
    user.EnumWindows(visit,0)
    (folder/"window-observation.json").write_text(json.dumps(dict(
        schema="c02-win32-visible-owner-v1",pid=proc.pid,input_idle=idle,
        windows=[dict(handle=int(hwnd),pid=proc.pid,visible=bool(user.IsWindowVisible(hwnd))) for hwnd in windows]),indent=2)+"\n")
    assert len(windows)==1,(proc.pid,windows)
    probe=evidence.run("owner-probe-live",[a.consumer,"--probe-owner",library],capture_output=True,timeout=20)
    assert probe.returncode==10,(probe.returncode,probe.stderr)
    assert user.PostMessageW(windows[0],0x0010,0,0)
    stdout,stderr=proc.communicate(timeout=30)
    evidence.finished("host-actual-host-final-release",proc,live_command,stdout,stderr)
    (folder/"stdout.txt").write_bytes(stdout);(folder/"stderr.txt").write_bytes(stderr)
    assert proc.returncode==0,(proc.returncode,stderr)
    probe=evidence.run("owner-probe-after-close",[a.consumer,"--probe-owner",library],capture_output=True,timeout=20)
    assert probe.returncode==0,(probe.returncode,probe.stderr)
    record("actual-host-final-release",pid=proc.pid,visible_window=True,blocked_while_live=True,admitted_after_close=True)
finally:
    if proc.poll() is None:proc.kill();proc.communicate(timeout=15)
assert len(results)==6
report=json.loads((out/"report.json").read_text())
report.update(complete=True,passed=True)
(out/"report.json").write_text(json.dumps(report,indent=2)+"\n")
print("C02-HOST cases=6 failed=0")
