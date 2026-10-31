#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actions-only independent repair helper consumer; retains all native inputs."""
import argparse
import hashlib
import json
import os
import pathlib
import platform
import stat
import struct
import subprocess
import sys

LIMIT = 4*1024*1024

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def observe(path,root):
    named = path.lstat()
    row = dict(path=path.relative_to(root).as_posix(),device=named.st_dev,inode=named.st_ino,
               uid=named.st_uid,gid=named.st_gid,mode=named.st_mode,links=named.st_nlink,
               bytes=named.st_size,sha256=None)
    if stat.S_ISLNK(named.st_mode):
        row["symlink"] = os.readlink(path)
        return row,None
    if stat.S_ISFIFO(named.st_mode):
        fd = os.open(path,os.O_RDONLY|os.O_NONBLOCK|os.O_NOFOLLOW)
        try:
            actual = os.fstat(fd)
            assert (actual.st_dev,actual.st_ino,actual.st_mode,actual.st_uid,actual.st_nlink) == (
                    named.st_dev,named.st_ino,named.st_mode,named.st_uid,named.st_nlink)
        finally:
            os.close(fd)
        row["fifo"] = True
        return row,None
    assert stat.S_ISREG(named.st_mode) or stat.S_ISDIR(named.st_mode)
    fd = os.open(path,os.O_RDONLY|os.O_NOFOLLOW|(os.O_DIRECTORY if stat.S_ISDIR(named.st_mode) else 0))
    try:
        before = os.fstat(fd)
        assert (before.st_dev,before.st_ino,before.st_mode) == (named.st_dev,named.st_ino,named.st_mode)
        raw = None
        if stat.S_ISREG(before.st_mode):
            blocks = []
            while True:
                part = os.read(fd,65536)
                if not part:
                    break
                blocks.append(part)
            raw = b"".join(blocks)
            assert len(raw) == before.st_size
            row["sha256"] = digest(raw)
        after = os.fstat(fd)
        assert (before.st_dev,before.st_ino,before.st_mode,before.st_uid,before.st_gid,
                before.st_nlink,before.st_size,before.st_mtime_ns,before.st_ctime_ns) == (
                after.st_dev,after.st_ino,after.st_mode,after.st_uid,after.st_gid,
                after.st_nlink,after.st_size,after.st_mtime_ns,after.st_ctime_ns)
        current = path.lstat()
        assert (current.st_dev,current.st_ino) == (before.st_dev,before.st_ino)
        if hasattr(os,"listxattr"):
            try:
                row["xattrs"] = {name:os.getxattr(fd,name).hex() for name in sorted(os.listxattr(fd))}
            except (OSError,TypeError) as error:
                row["xattr_errno"] = getattr(error,"errno",None)
        return row,raw
    finally:
        os.close(fd)

def wrapper(raw,row):
    if len(raw) < 177 or raw[:8] != b"PC02R001":
        return None
    kind,sequence,count,device,inode = struct.unpack_from("<QQQQQ",raw,8)
    fields = raw[48:112]+raw[-64:]
    valid = (0 < kind and 0 < sequence and 0 < count <= LIMIT-176 and
             count+176 == len(raw) and (device,inode) == (row["device"],row["inode"]) and
             all(c in b"0123456789abcdef" for c in fields) and
             raw[48:112] == digest(raw[112:-64]).encode() and
             raw[-64:] == digest(raw[:-64]).encode())
    return dict(kind=kind,sequence=sequence,payload_bytes=count,actual_self_id=valid,
                valid=valid,payload_sha256=digest(raw[112:-64]),raw_sha256=digest(raw))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tool",type=pathlib.Path,required=True)
    ap.add_argument("--output",type=pathlib.Path,required=True)
    a = ap.parse_args()
    assert os.environ.get("GITHUB_ACTIONS") == "true" and os.name == "posix"
    assert os.geteuid() > 0 and os.getuid() == os.geteuid()
    tool = a.tool.resolve(strict=True)
    output = a.output.resolve()
    output.mkdir(parents=True,exist_ok=False,mode=0o700)
    work = output/"native"
    work.mkdir(mode=0o700)
    process = subprocess.run([str(tool),str(work)],capture_output=True,timeout=240)
    (output/"native.stdout").write_bytes(process.stdout)
    (output/"native.stderr").write_bytes(process.stderr)
    stdout = process.stdout.decode("utf-8","replace")
    stderr = process.stderr.decode("utf-8","replace")
    rows = [json.loads(line) for line in stdout.splitlines() if line.startswith('{"')]
    summaries = [r for r in rows if "source" in r]
    cases = [r for r in rows if "case" in r]
    inventory,objects,wrappers = [],{},{}
    for path in sorted(work.rglob("*")):
        row,raw = observe(path,work)
        inventory.append(row)
        if raw is not None:
            objects[row["path"]] = (row,raw)
            decoded = wrapper(raw,row)
            if decoded is not None:
                wrappers[row["path"]] = decoded
    binary = tool.read_bytes()
    receipt = dict(schema="pc02-repair-helpers-v1",source=os.environ["GITHUB_SHA"],
                   run=os.environ["GITHUB_RUN_ID"],attempt=os.environ["GITHUB_RUN_ATTEMPT"],
                   platform=platform.platform(),process_uid=os.getuid(),process_euid=os.geteuid(),
                   command=[str(tool),str(work)],exit=process.returncode,
                   tool=dict(path=str(tool),bytes=len(binary),sha256=digest(binary)),
                   summaries=summaries,cases=cases,wrappers=wrappers,actual_sdk=False,
                   production_repair=False,power_loss=False,process_kill=False)
    (output/"receipt.json").write_text(json.dumps(receipt,indent=2)+"\n")
    (output/"native-source-observations.json").write_text(json.dumps(inventory,indent=2)+"\n")
    print(stdout,end="")
    print(stderr,end="",file=sys.stderr)
    file_hashes = [dict(path=p.relative_to(output).as_posix(),bytes=p.stat().st_size,
                        sha256=digest(p.read_bytes())) for p in sorted(output.rglob("*"))
                   if stat.S_ISREG(p.lstat().st_mode)]
    (output/"file-hashes.json").write_text(json.dumps(file_hashes,indent=2)+"\n")
    assert process.returncode == 0
    assert len(summaries) == 1 and len(cases) == len({r["case"] for r in cases}) == 30
    summary = summaries[0]
    assert summary["source"] == os.environ["GITHUB_SHA"] and summary["euid"] == os.geteuid()
    assert summary["cases"] == 30 and summary["checks"] == sum(r["checks"] for r in cases)
    assert summary["checks"] >= 3800 and summary["failed"] == sum(r["failed"] for r in cases) == 0
    assert summary["passed"] is True and summary["native_posix"] is True
    assert summary["actual_sdk"] is False and summary["production_repair"] is False
    plan = wrappers["store/plan-1"]
    assert plan["valid"] and plan["kind"] == plan["sequence"] == 1
    for name in ("same-bytes-rebound","bad-footer","bad-length","wrong-payload-hash"):
        assert wrappers["store/"+name]["valid"] is False,name
    assert wrappers["store/wrong-kind"]["valid"] and wrappers["store/wrong-kind"]["kind"] == 2
    assert wrappers["store/wrong-sequence"]["valid"] and wrappers["store/wrong-sequence"]["sequence"] == 2
    source,archive = objects["store/source-raw"],objects["store/archive-raw"]
    assert source[1] == archive[1] == b"original raw bytes\n"
    assert (source[0]["device"],source[0]["inode"]) != (archive[0]["device"],archive[0]["inode"])
    empty,copy = objects["store/source-empty"],objects["store/archive-empty"]
    assert empty[1] == copy[1] == b""
    assert (empty[0]["device"],empty[0]["inode"]) != (copy[0]["device"],copy[0]["inode"])
    assert any(name.startswith("store/repair-next-") for name in wrappers)
    assert not any("must-not-" in row["path"] for row in inventory)
    print(f"POSIX-C02-REPAIR-HELPERS cases=30 checks={summary['checks']} failed=0 "
          f"actual_sdk=false production_repair=false wrappers={len(wrappers)}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
