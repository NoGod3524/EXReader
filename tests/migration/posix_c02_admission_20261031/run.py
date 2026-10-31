#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actions-only native POSIX admission consumer. Preserves every raw case."""
import argparse, hashlib, json, os, pathlib, platform, stat, subprocess, sys

def sha(path):
    h=hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda:stream.read(65536),b""):h.update(block)
    return h.hexdigest()

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--tool",required=True,type=pathlib.Path)
    ap.add_argument("--output",required=True,type=pathlib.Path)
    a=ap.parse_args()
    if os.environ.get("GITHUB_ACTIONS")!="true" or os.name!="posix":
        raise SystemExit("Native fixtures and execution are restricted to GitHub Actions on POSIX.")
    tool=a.tool.resolve(strict=True);output=a.output.resolve()
    output.mkdir(parents=True,exist_ok=True,mode=0o700)
    work=output/"native"
    work.mkdir(mode=0o700)
    assert len(str(work))<512
    result=subprocess.run([str(tool),str(work)],capture_output=True,timeout=180)
    stdout=result.stdout.decode("utf-8","replace");stderr=result.stderr.decode("utf-8","replace")
    (output/"native.stdout").write_text(stdout,encoding="utf-8")
    (output/"native.stderr").write_text(stderr,encoding="utf-8")
    scope_work=output/"native-scope"
    scope_work.mkdir(mode=0o700)
    scope_result=subprocess.run([str(tool),"--scope-cases",str(scope_work)],capture_output=True,timeout=180)
    scope_stdout=scope_result.stdout.decode("utf-8","replace");scope_stderr=scope_result.stderr.decode("utf-8","replace")
    (output/"scope.stdout").write_text(scope_stdout,encoding="utf-8")
    (output/"scope.stderr").write_text(scope_stderr,encoding="utf-8")
    scope_rows=[json.loads(line) for line in scope_stdout.splitlines() if line.startswith('{"')]
    scope_summaries=[row for row in scope_rows if "source" in row]
    scope_cases=[row for row in scope_rows if "case" in row]
    rows=[json.loads(line) for line in stdout.splitlines() if line.startswith('{"')]
    summaries=[row for row in rows if "source" in row]
    cases=[row for row in rows if "case" in row]
    api_work=output/"native-migration-api"
    api_work.mkdir(mode=0o700)
    api_result=subprocess.run([str(tool),"--migration-cases",str(api_work)],capture_output=True,timeout=180)
    api_stdout=api_result.stdout.decode("utf-8","replace");api_stderr=api_result.stderr.decode("utf-8","replace")
    (output/"migration-api.stdout").write_text(api_stdout,encoding="utf-8")
    (output/"migration-api.stderr").write_text(api_stderr,encoding="utf-8")
    api_rows=[json.loads(line) for line in api_stdout.splitlines() if line.startswith('{"')]
    api_summaries=[row for row in api_rows if "source" in row]
    api_cases=[row for row in api_rows if "case" in row]
    receipt=dict(source=os.environ["GITHUB_SHA"],run=os.environ["GITHUB_RUN_ID"],attempt=os.environ["GITHUB_RUN_ATTEMPT"],
                 platform=platform.platform(),tool=dict(name=tool.name,bytes=tool.stat().st_size,sha256=sha(tool)),exit=result.returncode,
                 summaries=summaries,case_rows=cases,scoped=dict(exit=scope_result.returncode,summaries=scope_summaries,case_rows=scope_cases),
                 migration_api=dict(exit=api_result.returncode,summaries=api_summaries,case_rows=api_cases),actual_sdk=False,host_wiring=False,power_loss=False)
    (output/"receipt.json").write_text(json.dumps(receipt,indent=2)+"\n",encoding="utf-8")
    inventory=[]
    for path in sorted(output.rglob("*")):
        info=path.lstat()
        row=dict(path=path.relative_to(output).as_posix(),mode=oct(stat.S_IMODE(info.st_mode)),
                 uid=info.st_uid,gid=info.st_gid,device=info.st_dev,inode=info.st_ino,links=info.st_nlink)
        if stat.S_ISREG(info.st_mode):row.update(bytes=info.st_size,sha256=sha(path))
        elif stat.S_ISLNK(info.st_mode):row["symlink"]=os.readlink(path)
        inventory.append(row)
    (output/"file-hashes.json").write_text(json.dumps(inventory,indent=2)+"\n",encoding="utf-8")
    print(stdout,end="");print(stderr,end="",file=sys.stderr)
    assert len(summaries)==1,summaries
    r=summaries[0]
    assert r["source"]==os.environ["GITHUB_SHA"] and r["cases"]==28 and len(cases)==28
    assert r["checks"]==sum(c["checks"] for c in cases) and r["failed"]==sum(c["failed"] for c in cases)==0
    assert r["passed"] is True and r["native_posix"] is True and r["process_kill"] is True
    assert r["power_loss"] is False and r["actual_sdk"] is False and r["host_wiring"] is False
    assert result.returncode==0
    print(scope_stdout,end="");print(scope_stderr,end="",file=sys.stderr)
    assert len(scope_summaries)==1
    scoped=scope_summaries[0]
    assert scoped["source"]==os.environ["GITHUB_SHA"] and scoped["cases"]==10 and len(scope_cases)==10
    assert scoped["checks"]==sum(c["checks"] for c in scope_cases) and scoped["failed"]==sum(c["failed"] for c in scope_cases)==0
    assert scoped["passed"] is True and scoped["scoped"] is True and scoped["process_kill"] is True
    assert scoped["actual_sdk"] is False and scoped["host_wiring"] is False and scoped["power_loss"] is False
    assert scope_result.returncode==0
    print(api_stdout,end="");print(api_stderr,end="",file=sys.stderr)
    assert len(api_summaries)==1
    api=api_summaries[0]
    assert api["source"]==os.environ["GITHUB_SHA"] and api["cases"]==17 and len(api_cases)==17
    assert api["checks"]==sum(c["checks"] for c in api_cases) and api["failed"]==sum(c["failed"] for c in api_cases)==0
    assert api["passed"] is True and api["migration_api"] is True and api["process_kill"] is True
    assert api["actual_sdk"] is False and api["host_wiring"] is False and api["power_loss"] is False
    assert api_result.returncode==0
    print(f"POSIX-C02-MIGRATION-API cases=17 checks={api['checks']} failed=0")
    print(f"POSIX-C02-SCOPED cases=10 checks={scoped['checks']} failed=0")
    print(f"POSIX-C02-ADMISSION cases={r['cases']} checks={r['checks']} failed=0")
    return 0
if __name__=="__main__":sys.exit(main())
