"""Actions-only installed legacy command admission checks."""
import argparse, hashlib, json, os, subprocess
from pathlib import Path
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
p.add_argument("--prefix",type=Path,required=True)
p.add_argument("--admission",type=Path,required=True)
p.add_argument("--consumer",type=Path,required=True)
p.add_argument("--output",type=Path,required=True)
a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
rows=[]
programs={name:a.prefix.resolve()/"bin"/(name+".exe") for name in (
 "exreader-legacy-migrate","exreader-legacy-migrate-tx","exreader-legacy-migrate-recovery")}
programs.update(admission=a.admission.resolve(),consumer=a.consumer.resolve())
evidence=ProductEvidence(out,programs)
def call(name,args,ok=False):
 r=evidence.run(name,args,capture_output=True,timeout=30)
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
(out/"registered-before.sqlite").write_bytes(library.read_bytes())
for executable in ("exreader-legacy-migrate","exreader-legacy-migrate-tx","exreader-legacy-migrate-recovery"):
 tool=a.prefix.resolve()/"bin"/(executable+".exe")
 call(executable+"-admitted-dump",[tool,"dump","--target",library],True)
 call(executable+"-report-library",[tool,"dump","--target",library,"--report",library])
 assert hashlib.sha256(library.read_bytes()).hexdigest()==before
 rows.append(dict(name=executable+"-read-grant-and-report-refusal",passed=True))
pending=out/"pending";pending.mkdir()
r=evidence.run("pending-seed",
 [a.consumer.resolve(),"--prepare-pending"],cwd=pending,capture_output=True,timeout=30)
(out/"pending-seed.log").write_bytes(r.stdout+r.stderr)
assert r.returncode==0
path=Path(next(s[13:] for s in r.stdout.decode().splitlines() if s.startswith("HOST_LIBRARY ")))
raw=hashlib.sha256(path.read_bytes()).hexdigest()
(out/"pending-before.sqlite").write_bytes(path.read_bytes())
for executable in ("exreader-legacy-migrate","exreader-legacy-migrate-tx","exreader-legacy-migrate-recovery"):
 call(executable+"-pending-dump",[a.prefix.resolve()/"bin"/(executable+".exe"),"dump","--target",path])
 assert hashlib.sha256(path.read_bytes()).hexdigest()==raw
 rows.append(dict(name=executable+"-pending-sdk-refusal",passed=True))
(out/"target-observations.json").write_text(json.dumps(dict(
 registered=dict(source_path=str(library),before_sha256=before,after_sha256=hashlib.sha256(library.read_bytes()).hexdigest()),
 pending=dict(source_path=str(path),before_sha256=raw,after_sha256=hashlib.sha256(path.read_bytes()).hexdigest())),indent=2)+"\n")
assert len(rows)==18
(out/"guard-report.json").write_text(json.dumps(dict(source=os.environ["GITHUB_SHA"],
 run=os.environ["GITHUB_RUN_ID"],attempt=os.environ["GITHUB_RUN_ATTEMPT"],cases=rows,passed=True,
 platform="Windows",evidence_schema="c02-windows-products-v1",binaries=evidence.binaries,
 command_log="commands.jsonl"),indent=2)+"\n")
print("C02-LEGACY-GUARD cases=18 failed=0")
