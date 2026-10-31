"""Actions-only checks of the installed production admission command."""
import argparse, hashlib, json, os, subprocess
from pathlib import Path
assert os.environ.get("GITHUB_ACTIONS")=="true" and os.name=="nt"
p=argparse.ArgumentParser()
p.add_argument("--tool",type=Path,required=True);p.add_argument("--consumer",type=Path,required=True)
p.add_argument("--output",type=Path,required=True);a=p.parse_args()
tool=a.tool.resolve();consumer=a.consumer.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
results=[]
def run(name,args,success):
    r=subprocess.run([str(tool),*map(str,args)],capture_output=True,timeout=45)
    (out/(name+".stdout")).write_bytes(r.stdout);(out/(name+".stderr")).write_bytes(r.stderr)
    assert r.returncode==(0 if success else 2),(name,r.returncode,r.stdout,r.stderr)
    row=json.loads(r.stdout);assert row["admitted"] is success
    return row
def done(name):
    results.append(dict(name=name,passed=True))
    (out/"report.json").write_text(json.dumps(dict(source=os.environ["GITHUB_SHA"],run=os.environ["GITHUB_RUN_ID"],
        attempt=os.environ["GITHUB_RUN_ATTEMPT"],cases=results,complete=False,passed=False),indent=2)+"\n")
def state(path):return [path.stat().st_ino,hashlib.sha256(path.read_bytes()).hexdigest()]
def seed(name,mode="--prepare-unregistered"):
    folder=out/name;folder.mkdir()
    r=subprocess.run([consumer,mode],cwd=folder,capture_output=True,timeout=30)
    (folder/"seed.log").write_bytes(r.stdout+r.stderr);assert r.returncode==0,(name,r.stdout,r.stderr)
    lines=r.stdout.decode().splitlines()
    return Path(next(x[13:] for x in lines if x.startswith("HOST_LIBRARY "))),Path(next(x[10:] for x in lines if x.startswith("HOST_GATE ")))
unknown=out/"unknown.sqlite"
run("unknown",["check",unknown],False);assert not unknown.exists();done("unknown-check-never-creates")
library=out/"created.sqlite";root=out/"created-domain"
r=run("create",["create",library,root],True);assert r["books"]==0 and r["original_bytes"]==0
run("created-check",["check",library],True);done("explicit-create-and-check")
before=state(library);other=out/"not-created-domain"
run("overwrite",["create",library,other],False);assert state(library)==before and not other.exists();done("create-never-overwrites")
existing,gate=seed("existing")
r=run("enroll",["enroll",existing,gate],True);assert r["books"]==1 and r["original_bytes"]>0
run("enrolled-check",["check",existing],True);done("existing-real-sdk-enrollment")
failed,gate=seed("failed","--prepare-enrollment-failure")
run("failed-check",["check",failed],False)
r=run("recover",["recover-enrollment",failed],True);assert r["books"]==1
run("recovered-check",["check",failed],True);done("explicit-enrollment-recovery")
before=state(failed);run("repeat",["recover-enrollment",failed],False)
assert state(failed)==before;done("completed-binding-not-reenrolled")
incomplete,gate=seed("incomplete");(gate/"intent.bin").unlink();before=state(incomplete)
run("incomplete",["enroll",incomplete,gate],False)
assert not (gate/"intent.bin").exists() and state(incomplete)==before;done("incomplete-root-never-filled")
blocked=out/"blocked.sqlite";policy=Path(str(blocked)+".migration-pending.json");policy.write_bytes(b"retained policy")
run("legacy",["create",blocked,out/"blocked-domain"],False)
assert not blocked.exists() and policy.read_bytes()==b"retained policy";done("legacy-policy-before-target-creation")
actual=out/"actual-parent";actual.mkdir();alias=out/"alias-parent"
r=subprocess.run(["cmd","/c","mklink","/J",str(alias),str(actual)],capture_output=True,timeout=15)
assert r.returncode==0,(r.stdout,r.stderr)
run("reparse",["create",alias/"library.sqlite",alias/"domain"],False)
assert not (actual/"library.sqlite").exists() and not (actual/"domain").exists();done("reparse-parent-before-creation")
assert len(results)==9
report=json.loads((out/"report.json").read_text());report.update(complete=True,passed=True)
(out/"report.json").write_text(json.dumps(report,indent=2)+"\n")
print("C02-ADMISSION-CLI cases=9 failed=0")
