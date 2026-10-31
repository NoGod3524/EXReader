#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actions-only independent component-byte audit, with original assertions intact."""
import argparse
import json
import os
from pathlib import Path
import posixpath
import re
import shutil
import stat
import struct
import subprocess

from protocols import need, sha, hexadecimal, integer, json_value
from posix_protocols import binding, states, native_id, observed_id, metadata
from posix_migration import audit_transaction, committed_head

BASE = ["missing-explicit-enrollment","explicit-create","last-borrow-retains-shared",
        "child-shared-before-owner","child-owner-before-shared","process-kill-pending-1101",
        "process-kill-pending-1102","stale-grants-and-descriptors",
        *["process-kill-finish-"+str(n) for n in (1202,1203,1204,1205)],
        "enrollment-process-death-1001","enrollment-process-death-1002",
        *["native-begin-fault-"+str(n) for n in (1,2,3)],
        "replaced-target","target-hardlink","replaced-state","partial-state","permissive-authority-file",
        "legacy-pending","symlink-library-prefix","replaced-authority","replaced-binding",
        "root-permissions","symlink-authority-ancestor"]
SCOPED = ["scope-fd-lifetime-and-sdk-path","scope-native-identity-and-private-mode",
          "scope-relative-path-escape","scope-symlink-escape","scope-anchor-path-rebinding",
          "scope-anchor-permission-drift","scope-process-death-and-exact-recovery",
          "scope-readonly-anchor-0755","scope-readonly-anchor-0711","scope-group-other-write-rejected"]
API = ["native-immutable-input-prepared-and-borrow","native-input-inode-replacement",
       "native-input-complete-tail","native-input-permission-change","native-floor-cas-head-and-temp",
       "native-floor-hole","native-floor-last-rollback","native-floor-inode-replacement",
       "native-floor-complete-tail","native-floor-noncanonical-name","native-floor-confirm-process-kill",
       "native-head-inode-replacement","native-head-complete-contradictory-tail",
       "native-two-members-absent-mirror","native-two-members-original-mirror",
       "native-member-process-kill-1301","native-member-process-kill-1302"]
REJECT = {API[1]:"pm-envelope-payload-size-self-id",API[2]:"pm-envelope-payload-size-self-id",
          API[3]:"posix-native-file-mode",API[5]:"pm-no-immutable-floor-holes",
          API[6]:"pm-committed-head-forbids-lost-final-floor",API[7]:"pm-envelope-payload-size-self-id",
          API[8]:"pm-envelope-payload-size-self-id",API[9]:"pm-all-final-floor-names-canonical",
          API[11]:"pm-head-final-name-self-id",API[12]:"pm-head-complete-records-only"}

def relative(value):
    need(isinstance(value,str) and value and not value.startswith("/") and
         posixpath.normpath(value) == value and all(p not in ("",".","..") for p in value.split("/")),
         "pn-canonical-relative-path")
    return value

def _fd_record(path, name):
    original = path.lstat()
    link = stat.S_ISLNK(original.st_mode)
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW
    method = "fstat"
    if link:
        if hasattr(os,"O_PATH"):
            flags = os.O_PATH | os.O_NOFOLLOW | os.O_CLOEXEC
        elif hasattr(os,"O_SYMLINK"):
            flags = os.O_SYMLINK | os.O_CLOEXEC
        else:
            method = "lstat-symlink"
    descriptor = None
    data = None
    if method == "fstat":
        descriptor = os.open(path,flags)
        value = os.fstat(descriptor)
        need((value.st_dev,value.st_ino,stat.S_IFMT(value.st_mode)) ==
             (original.st_dev,original.st_ino,stat.S_IFMT(original.st_mode)), "pn-lstat-open-fstat-same-object")
    else:
        value = original
    try:
        row = dict(path=name,physical_path=str(path),device=value.st_dev,inode=value.st_ino,
                   mode=value.st_mode,uid=value.st_uid,gid=value.st_gid,links=value.st_nlink,
                   bytes=value.st_size,sha256=None,method=method)
        if stat.S_ISREG(value.st_mode):
            need(value.st_size <= 16*1024*1024,"pn-bounded-component-file")
            pieces = []
            while True:
                chunk = os.read(descriptor,65536)
                if not chunk:
                    break
                pieces.append(chunk)
            data = b"".join(pieces)
            need(len(data) == value.st_size,"pn-fstat-complete-file")
            row["sha256"] = sha(data)
        elif link:
            row["symlink"] = os.readlink(path)
        else:
            need(stat.S_ISDIR(value.st_mode),"pn-no-unknown-special-object")
        return row,data
    finally:
        if descriptor is not None:
            os.close(descriptor)

def capture(root):
    objects,files = {},{}
    row,_ = _fd_record(root,".")
    objects["."] = row
    for directory,dirs,names in os.walk(root,followlinks=False):
        for leaf in sorted(dirs+names):
            path = Path(directory)/leaf
            name = relative(path.relative_to(root).as_posix())
            row,data = _fd_record(path,name)
            need(name not in objects,"pn-capture-duplicate")
            objects[name] = row
            if data is not None:
                files[name] = data
    return objects,files

def producer_inventory(files, objects):
    rows = json_value(files["file-hashes.json"])
    need(isinstance(rows,list) and rows,"pn-original-inventory")
    seen,regular = set(),set()
    for row in rows:
        name = relative(row["path"])
        need(name not in seen and name in objects,"pn-original-object-present-unique")
        seen.add(name)
        current = objects[name]
        need(all(row[key] == current[key] for key in ("device","inode","uid","gid","links")) and
             int(row["mode"],8) == stat.S_IMODE(current["mode"]),"pn-original-lstat-and-actual-fstat-identities")
        if "bytes" in row:
            need(stat.S_ISREG(current["mode"]) and current["method"] == "fstat" and name in files and
                 row["bytes"] == len(files[name]) == current["bytes"] and
                 row["sha256"] == current["sha256"] == sha(files[name]),"pn-original-regular-bytes")
            regular.add(name)
        elif "symlink" in row:
            need(stat.S_ISLNK(current["mode"]) and row["symlink"] == current["symlink"],"pn-original-symlink-refused-objects")
        else:
            need(stat.S_ISDIR(current["mode"]),"pn-original-directory")
    need(seen == set(objects)-{".","file-hashes.json"} and
         regular == set(files)-{"file-hashes.json"},"pn-complete-original-inventory")

def _group(files, receipt, name, section, names, count):
    stdout = files[name+".stdout"].decode().replace("\r\n","\n")
    stderr = files[name+".stderr"].decode().replace("\r\n","\n")
    need(not re.search(r"^FAIL ",stdout+"\n"+stderr,re.M),"pn-original-no-failed-assertions")
    rows = [json_value(line) for line in stdout.splitlines() if line.startswith("{")]
    summaries = [row for row in rows if "source" in row]
    cases = [row for row in rows if "case" in row]
    need(len(summaries) == 1 and [row["case"] for row in cases] == names and
         section["summaries"] == summaries and section["case_rows"] == cases and section["exit"] == 0,
         "pn-original-complete-case-rows:"+name)
    summary = summaries[0]
    need(summary["source"] == receipt["source"] and summary["cases"] == len(names) and
         summary["checks"] == sum(row["checks"] for row in cases) == count and
         summary["failed"] == sum(row["failed"] for row in cases) == 0 and summary["passed"] is True,
         "pn-original-fixed-checks:"+name)
    need(all(type(row["checks"]) is int and row["checks"] > 0 and type(row["failed"]) is int for row in cases),
         "pn-original-check-types")
    need(summary["native_posix"] is True and summary["process_kill"] is True and
         summary["actual_sdk"] is False and summary["host_wiring"] is False and summary["power_loss"] is False,
         "pn-component-scope:"+name)
    named = re.findall(r"^CASE ([0-9]+) (.+)$",stdout,re.M)
    need([(int(n),text) for n,text in named] == list(enumerate(names,1)),"pn-original-named-cases:"+name)
    if name == "scope":
        need(summary["scoped"] is True,"pn-scope-flag")
    if name == "migration-api":
        need(summary["migration_api"] is True,"pn-migration-api-flag")
    return summary

def members(raw):
    need(len(raw) == 2*808,"pn-component-member-abi-size")
    result = []
    for offset in (0,808):
        row = raw[offset:offset+808]
        names = []
        for start in (0,256,512):
            field = row[start:start+256]
            at = field.find(b"\0")
            need(at > 0 and not any(field[at:]),"pn-component-member-canonical-c-string")
            text = field[:at].decode("ascii")
            need(re.fullmatch(r"[A-Za-z0-9._-]+",text) and text not in (".","..") and not text.endswith("."),
                 "pn-component-member-basename")
            names.append(text)
        present = struct.unpack_from("<I",row,768)[0]
        need(present in (0,1) and row[772:776] == bytes(4) and len(set(names)) == 3,"pn-component-member-flags-padding")
        result.append(dict(target=names[0],stage=names[1],retained=names[2],original_present=bool(present),
                           original=native_id(row,776),prepared=native_id(row,792)))
    need([row["target"] for row in result] == ["library.sqlite","library.sqlite.legacy-map.json"] and
         result[0]["original_present"],"pn-component-exact-targets")
    return result

def _member_images(files, objects, case, decoded, euid):
    packet = decoded["input_record"]
    prepared = decoded["prepared_record"]
    need(prepared is not None and packet["payload"] == prepared["payload"],"pn-input-prepared-actual-member-array")
    entries = members(packet["payload"])
    committed = objects[case+"/library.sqlite"]["device"],objects[case+"/library.sqlite"]["inode"]
    clean = decoded["begin"]["target"] != committed
    for index,entry in enumerate(entries):
        need(entry["prepared"][1] > 0 and (not entry["original_present"] or
             entry["original"][1] > 0 and entry["original"] != entry["prepared"]),"pn-member-distinct-native-identities")
        if clean:
            expected = {entry["target"]:(entry["prepared"],b"published\n" if index == 0 else b"new mirror\n",True)}
            if entry["original_present"]:
                expected[entry["retained"]] = (entry["original"],b"original\n" if index == 0 else b"old mirror\n",False)
            absent = {entry["stage"]}
            if not entry["original_present"]:
                absent.add(entry["retained"])
        else:
            expected = {entry["stage"]:(entry["prepared"],b"published\n" if index == 0 else b"new mirror\n",True)}
            if entry["original_present"]:
                expected[entry["target"]] = (entry["original"],b"original\n" if index == 0 else b"old mirror\n",False)
            absent = {entry["retained"]}
            if not entry["original_present"]:
                absent.add(entry["target"])
        for name,(identity,data,private) in expected.items():
            key = case+"/"+name
            need(key in objects and key in files and metadata(objects[key],euid,private=private) == identity and
                 files[key] == data,"pn-actual-member-native-id-bytes-state")
        need(all(case+"/"+name not in objects for name in absent),"pn-member-exact-absence-contract")
    need(entries[0]["original"] == decoded["begin"]["target"],"pn-original-member-bound-to-original-b")
    return dict(state="published" if clean else "original",members=entries)

def audit_api(files, objects, euid):
    classified = []
    for ordinal,name in enumerate(API,1):
        case = f"native-migration-api/{ordinal:02d}-{name}"
        need(case in objects and stat.S_ISDIR(objects[case]["mode"]),"pn-original-api-fixture-directory")
        authority = case+"/authority"
        prefix = authority+"/"
        names = [path[len(prefix):] for path in objects if path.startswith(prefix)]
        observed = {".":dict(objects[authority],path=".")}
        observed.update({name:dict(objects[prefix+name],path=name) for name in names})
        routes = [value for value in names if "/" not in value and re.fullmatch("[0-9a-f]{64}",value)]
        need(len(routes) == 1,"pn-actual-single-native-route")
        route = routes[0]
        b = files[prefix+route+"/binding"]
        state = files[prefix+route+"/state"]
        history = states(state)
        begin = history[-2] if history[-1]["kind"] == "C" else history[-1]
        need(begin["kind"] == "B","pn-component-has-original-b")
        exact = {key:begin[key] for key in ("generation","seal","manifest","input")}
        parent = dict(objects[case],path=objects[case]["physical_path"])
        try:
            decoded = audit_transaction(files,observed,current_binding=b,raw_state=state,exact=exact,euid=euid,
                library_path=objects[case]["physical_path"]+"/library.sqlite",parent=parent,
                authority_prefix=prefix,profile="component")
        except ValueError as error:
            need(name in REJECT and str(error) == REJECT[name],"pn-unexpected-independent-decoder-refusal:"+name+":"+str(error))
            classified.append(dict(name=name,valid=False,reason=str(error)))
            continue
        need(name not in REJECT,"pn-invalid-component-accepted:"+name)
        published = ordinal >= 14
        current = binding(b)
        need(len(history) == (3 if published else 2) and history[-1]["kind"] == ("C" if published else "B") and
             current["generation"] == (1 if published else 0) and begin["generation"] == 1 and
             begin["manifest"] == "a"*64, "pn-source-exact-terminal-or-pending-generation")
        if published:
            need(current["grant"] == history[-1]["seal"] and current["target"] == history[-1]["target"] and
                 history[-1]["terminal"] == "c"*64, "pn-actual-published-independent-binding")
        content = _member_images(files,objects,case,decoded,euid)
        need(content["state"] == ("published" if published else "original"), "pn-source-exact-member-publication-state")
        expected_count = 2 if name == API[4] else 1 if name == API[10] else 0
        need(decoded["floor"]["count"] == decoded["head"]["count"] == expected_count and
             decoded["journal_bound"] is False,"pn-component-exact-floor-head-not-production")
        if expected_count:
            need(decoded["floors"][0]["last_line_sha256"] == sha(b"actual-line-1"),"pn-component-first-line")
        if expected_count == 2:
            need(decoded["floors"][1]["last_line_sha256"] == sha(b"second actual line") and
                 any(row["name"] == ".metadata-uncommitted-fixture" for row in decoded["retained_temporary"]),
                 "pn-source-preserved-temp-and-stale-cas-control")
        classified.append(dict(name=name,valid=True,floor_count=expected_count,head_count=expected_count,
                               input_native=decoded["input_record"]["identity"],head_native=decoded["head"]["identity"],**content))
    need(len(classified) == 17 and sum(row["valid"] for row in classified) == 7,"pn-all17-independent-classifications")
    return classified

def audit(files, objects, *, source, run, attempt, euid):
    producer_inventory(files,objects)
    receipt = json_value(files["receipt.json"])
    need(receipt["source"] == source and str(receipt["run"]) == str(run) and str(receipt["attempt"]) == str(attempt) and
         receipt["actual_sdk"] is False and receipt["host_wiring"] is False and receipt["power_loss"] is False,
         "pn-producer-component-provenance")
    need(hexadecimal(source,40) and type(euid) is int and euid > 0,"pn-qualified-source-real-uid")
    original = dict(exit=receipt["exit"],summaries=receipt["summaries"],case_rows=receipt["case_rows"])
    summaries = [_group(files,receipt,"native",original,BASE,207),
                 _group(files,receipt,"scope",receipt["scoped"],SCOPED,81),
                 _group(files,receipt,"migration-api",receipt["migration_api"],API,130)]
    classified = audit_api(files,objects,euid)
    return dict(source=source,run=str(run),attempt=str(attempt),passed=True,actual_sdk=False,host_wiring=False,
                full_c02_complete=False,power_loss=False,original_counts=summaries,migration_api=classified,
                migration_api_positive=7,migration_api_negative=10,
                independent_pre_confirm_snapshot=False,
                evidence_limits=["Producer retained post-confirm head, not an independent464-byte pre-confirm fstat snapshot.",
                                 "Original28/scope10 assertions and raw inventory are preserved; this adapter newly classifies API17."])

def main():
    need(os.environ.get("GITHUB_ACTIONS") == "true" and os.name == "posix","pn-all-execution-only-Actions-POSIX")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence",type=Path,required=True)
    parser.add_argument("--tool",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args = parser.parse_args()
    root = args.evidence.resolve(strict=True)
    output = args.output.resolve()
    need(root != output and root not in output.parents and not output.exists(),"pn-preserve-original-output")
    output.mkdir(parents=True)
    result = dict(passed=False,full_c02_complete=False)
    try:
        objects,files = capture(root)
        (output/"fstat.json").write_text(json.dumps(dict(
            schema="pc02-component-fstat-v1",root=str(root),euid=os.geteuid(),
            original_bytes_prefix="original/",objects=objects),indent=2)+"\n")
        for name,data in files.items():
            destination = output/"original"/relative(name)
            destination.parent.mkdir(parents=True,exist_ok=True)
            destination.write_bytes(data)
        receipt = json_value(files["receipt.json"])
        tool = args.tool.resolve(strict=True)
        raw = tool.read_bytes()
        need(receipt["tool"]["name"] == tool.name and receipt["tool"]["bytes"] == len(raw) and
             receipt["tool"]["sha256"] == sha(raw),"pn-original-executed-consumer-binary")
        (output/tool.name).write_bytes(raw)
        source = subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip()
        need(source == os.environ["GITHUB_SHA"],"pn-current-exact-source")
        result = audit(files,objects,source=source,run=os.environ["GITHUB_RUN_ID"],
                       attempt=os.environ["GITHUB_RUN_ATTEMPT"],euid=os.geteuid())
        print(json.dumps(result),flush=True)
    except BaseException as error:
        result["error"] = type(error).__name__+":"+str(error)
        print(json.dumps(result),flush=True)
        raise
    finally:
        (output/"result.json").write_text(json.dumps(result,indent=2)+"\n")
        original = root/"file-hashes.json"
        if original.is_file():
            shutil.copyfile(original,output/"producer-file-hashes.json")
        (output/"file-hashes.json").write_text(json.dumps([
            dict(path=path.relative_to(output).as_posix(),bytes=path.stat().st_size,sha256=sha(path.read_bytes()))
            for path in sorted(output.rglob("*")) if path.is_file() and path != output/"file-hashes.json"],indent=2)+"\n")

if __name__ == "__main__":
    main()
