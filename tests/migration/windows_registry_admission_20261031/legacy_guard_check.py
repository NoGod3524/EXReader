"""Actions-only installed legacy command admission checks."""
import argparse, hashlib, json, os, subprocess
from pathlib import Path
assert os.environ.get("GITHUB_ACTIONS") == "true" and os.name == "nt"
p=argparse.ArgumentParser()
p.add_argument("--prefix",type=Path,required=True)
p.add_argument("--admission",type=Path,required=True)
p.add_argument("--consumer",type=Path,required=True)
p.add_argument("--output",type=Path,required=True)
a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
rows=[]
def call(name,args,ok=False):
 r=subprocess.run(list(map(str,args)),capture_output=True,timeout=30)
 (out/(name+".stdout")).write_bytes(r.stdout);(out/(name+".stderr")).write_bytes(r.stderr)
 assert (r.returncode==0) is ok,(name,r.returncode,r.stdout,r.stderr)
 return r
unknown=out/"unknown.sqlite";report=out/"report.json";pack=out/"absent.exrpack"
for executable in ("exreader-legacy-migrate","exreader-legacy-migrate-tx","exreader-legacy-migrate-recovery"):
 tool=a.prefix.resolve()/"bin"/(executable+".exe")
 assert tool.is_file()
 call(executable+"-version",[tool,"--version"],True)
 for operation in ("migrate","recover-mirror","recover-migration"):
  rejected=call(executable+"-"+operation,[tool,operation,"--pack",pack,"--target",unknown,"--report",report,"--break-lock"])
  assert rejected.returncode==2 and b"c02-owner-required" in rejected.stdout
  assert not unknown.exists() and not report.exists() and not Path(str(unknown)+".migrate-lock").exists()
  rows.append(dict(name=executable+"-"+operation+"-before-files",passed=True))
 call(executable+"-unknown-dump",[tool,"dump","--target",unknown])
 assert not unknown.exists()
 rows.append(dict(name=executable+"-unknown-dump",passed=True))
library=out/"registered.sqlite"
call("create",[a.admission.resolve(),"create",library,out/"registered-domain"],True)
before=hashlib.sha256(library.read_bytes()).hexdigest()
for executable in ("exreader-legacy-migrate","exreader-legacy-migrate-tx","exreader-legacy-migrate-recovery"):
 tool=a.prefix.resolve()/"bin"/(executable+".exe")
 call(executable+"-admitted-dump",[tool,"dump","--target",library],True)
 call(executable+"-report-library",[tool,"dump","--target",library,"--report",library])
 assert hashlib.sha256(library.read_bytes()).hexdigest()==before
 rows.append(dict(name=executable+"-read-grant-and-report-refusal",passed=True))
pending=out/"pending";pending.mkdir()
r=subprocess.run(
 [a.consumer.resolve(),"--prepare-pending"],cwd=pending,capture_output=True,timeout=30)
(out/"pending-seed.log").write_bytes(r.stdout+r.stderr)
assert r.returncode==0
path=Path(next(s[13:] for s in r.stdout.decode().splitlines() if s.startswith("HOST_LIBRARY ")))
raw=hashlib.sha256(path.read_bytes()).hexdigest()
for executable in ("exreader-legacy-migrate","exreader-legacy-migrate-tx","exreader-legacy-migrate-recovery"):
 call(executable+"-pending-dump",[a.prefix.resolve()/"bin"/(executable+".exe"),"dump","--target",path])
 assert hashlib.sha256(path.read_bytes()).hexdigest()==raw
 rows.append(dict(name=executable+"-pending-sdk-refusal",passed=True))
assert len(rows)==18
(out/"guard-report.json").write_text(json.dumps(dict(source=os.environ["GITHUB_SHA"],
 run=os.environ["GITHUB_RUN_ID"],attempt=os.environ["GITHUB_RUN_ATTEMPT"],cases=rows,passed=True),indent=2)+"\n")
print("C02-LEGACY-GUARD cases=18 failed=0")
