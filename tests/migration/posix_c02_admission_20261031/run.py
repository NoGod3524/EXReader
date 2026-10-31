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
    rows=[json.loads(line) for line in stdout.splitlines() if line.startswith('{"')]
    summaries=[row for row in rows if "source" in row]
    cases=[row for row in rows if "case" in row]
    receipt=dict(source=os.environ["GITHUB_SHA"],run=os.environ["GITHUB_RUN_ID"],attempt=os.environ["GITHUB_RUN_ATTEMPT"],
                 platform=platform.platform(),tool=dict(name=tool.name,bytes=tool.stat().st_size,sha256=sha(tool)),exit=result.returncode,
                 summaries=summaries,case_rows=cases,actual_sdk=False,host_wiring=False,power_loss=False)
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
    print(f"POSIX-C02-ADMISSION cases={r['cases']} checks={r['checks']} failed=0")
    return 0
if __name__=="__main__":sys.exit(main())
