#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actions-only audit of original C02 artifact ZIPs and resealed semantic negatives."""
import argparse
import ast
import copy
import datetime
import functools
import io
import json
import os
import pathlib
import posixpath
import re
import stat
import sqlite3
import subprocess
import sys
import zipfile

from production import bound_history, acknowledged_prefix, audit_repairs
from scanner import audit_scanner

from protocols import (SDK, C01, ABI2_FAILURES, need, sha, hexadecimal, integer, json_value,
                       summary, frames, history, native_pair, gate_records, registry_binding,
                       input_record, prepared_record, legacy_pack, sqlite_content)

ROLES = {"native-windows", "native-linux", "persistent-gate", "registry-product",
         "host-android", "host-macos", "host-gtk"}
OWNER_CASES = {"registered", "unregistered", "pending", "missing-gate", "replaced-target",
               "actual-host-final-release"}
CLI_CASES = {"unknown-check-never-creates", "explicit-create-and-check", "create-never-overwrites",
             "existing-real-sdk-enrollment", "explicit-enrollment-recovery", "completed-binding-not-reenrolled",
             "incomplete-root-never-filled", "legacy-policy-before-target-creation",
             "reparse-parent-before-creation", "repeated-native-epoch-retains-original-files",
             "epoch-cannot-bypass-pending"}
HOST_CASES = {"clean-admits-before-sdk", "pending-refuses-before-sdk",
              "missing-binding-refuses-before-sdk", "last-borrow-blocks-owner",
              "final-borrow-release-allows-owner", "fresh-process-pending-refusal"}
FROZEN_NATIVE_STEP = "Preserve original ABI2 81 checks and raw six contract failures"

def canonical_path(name):
    name = name.replace("\\", "/")
    parts = name.split("/")
    need(name and not name.startswith("/") and ":" not in parts[0] and
         all(part not in ("", ".", "..") for part in parts), "archive-path")
    return name

def zip_files(raw, maximum=2*1024*1024*1024):
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        records = [row for row in archive.infolist() if not row.is_dir()]
        need(len(records) <= 20000 and sum(row.file_size for row in records) <= maximum, "archive-bound")
        result = {}
        for row in records:
            name = canonical_path(row.filename)
            need(name not in result and not row.flag_bits & 1, "archive-duplicate-or-encryption")
            need(stat.S_IFMT(row.external_attr >> 16) != stat.S_IFLNK, "archive-symlink")
            data = archive.read(row)
            need(len(data) == row.file_size, "archive-entry-size")
            result[name] = data
    return result

def inventory(files, path="file-hashes.json"):
    need(path in files, "inventory-missing")
    rows = json_value(files[path])
    need(isinstance(rows,list), "inventory-shape")
    seen = set()
    for row in rows:
        name = canonical_path(row["path"])
        need(name not in seen and name in files and name != path, "inventory-entry")
        need(integer(row["bytes"]) and row["bytes"] == len(files[name]), "inventory-bytes")
        need(row["sha256"] == sha(files[name]), "inventory-sha256")
        seen.add(name)
    need(seen == set(files) - {path}, "inventory-complete")

def provenance(receipt, spec, source):
    need(receipt["source"] == source and str(receipt["run"]) == str(spec["run"]) and
         str(receipt["attempt"]) == str(spec["attempt"]), "receipt-producer")

def named_cases(log, count):
    rows = re.findall(r"^CASE (\d+) (.+)$", log, re.M)
    need([int(number) for number,_ in rows] == list(range(1,count+1)) and
         len({name for _,name in rows}) == count, "named-case-completeness")
    need(not re.search(r"^FAIL ",log,re.M), "unexpected-test-failure")

@functools.lru_cache(maxsize=None)
def native_fixture_binding(source):
    legacy = git_bytes(source,"tests/migration/windows_coordinator_hardening_20261030/wh_test.c").decode()
    native = git_bytes(source,"tests/migration/windows_coordinator_native_journal_20261030/wh3_win_test.c").decode()
    values = {}
    for macro, size in (("HX40",40),("HX64",64)):
        found = re.findall(r'^#define '+macro+r' "([0-9a-f]+)"$',legacy,re.M)
        need(len(found) == 1 and hexadecimal(found[0],size), "native-fixture-macro:"+macro)
        values[macro] = found[0]
    fields = {"source":"HX40","run":'"4100000000"',"attempt":'"1"',
              "artifact":"HX64","platform":'"ubuntu-22.04"',"sdk":'"3.42.0"',"provider":"HX64"}
    for name, literal in fields.items():
        statement = 'snprintf(b.'+name+', sizeof b.'+name+', "%s", '+literal+');'
        need(statement in legacy, "native-fixture-static-binding:"+name)
    need('#include "../windows_coordinator_hardening_20261030/wh_test.c"' in native and
         'f.b=binding_of();snprintf(f.b.platform,sizeof(f.b.platform),"windows-2022");f.g=gates_of(\'a\');' in native,
         "native-fixture-static-override")
    expected = {name:values[literal] if literal in values else literal[1:-1]
                for name,literal in fields.items()}
    expected["platform"] = "windows-2022"
    expected.update({name:"a"*64 for name in ("admission","publisher","recovery","observer","fault")})
    return expected

def native_evidence(files, spec, source):
    inventory(files)
    receipt = json_value(files["receipt.json"])
    provenance(receipt,spec,source)
    platform = "Windows" if spec["role"] == "native-windows" else "Linux"
    need(receipt["os"] == platform and receipt["real_owner_wiring"] is False and
         receipt["full_p0_acceptance"] is False, "native-receipt-scope")
    for kind, checks, failures in [("abi2",81,6),("abi3",64,0)]:
        result = summary(files[kind+".log"])
        need(result["source"] == source and result["checks"] == checks and
             result["failed"] == failures and result["passed"] is (failures == 0), "baseline-counts:" + kind)
        need(receipt[kind] == result and files[kind+"-exit.txt"].strip() == (b"1" if failures else b"0"),
             "baseline-raw-result:" + kind)
        failures_seen = [line for line in files[kind+".log"].decode().splitlines() if line.startswith("FAIL ")]
        need(failures_seen == (ABI2_FAILURES if kind == "abi2" else []), "baseline-known-signatures:" + kind)
        if kind == "abi3":
            need(result["cases"] == 16 and result["native_durability"] is False, "abi3-scope")
    if platform == "Linux":
        need(receipt["native"] is None and "native.log" not in files, "linux-native-claim")
        return dict(capabilities=["abi2-linux-known-six", "abi3-linux"])
    result = summary(files["native.log"])
    need(result["source"] == source and result["cases"] == 46 and result["checks"] == 301 and
         result["failed"] == 0 and result["passed"] is True, "native-fixed-46-301")
    need(result["native_io"] is True and result["subprocess_crash"] is True and
         result["power_loss"] is False and result["real_owner_wiring"] is False, "native-evidence-scope")
    need(receipt["native"] == result and files["native-exit.txt"].strip() == b"0", "native-raw-result")
    log = files["native.log"].decode().replace("\r\n","\n")
    named_cases(log,46)
    pairs = re.findall(r"^OBS reached=(\d+) expected=(\d+)$",log,re.M)
    need([int(a) for a,b in pairs] == [1,6,2,7,8,3,4,9,10,5] and all(a == b for a,b in pairs),
         "native-ten-real-barriers")
    need("OBS midopen root_move=1 error=0 reached=101" in log, "native-real-path-rebinding")
    invalid = set(range(10,17)) | set(range(19,27)) | set(range(36,43)) | {46}
    fixture = native_fixture_binding(source)
    for number in range(1,47):
        prefix = f"native-files/case-{number:03}/a/b/"
        journal, intents = files[prefix+"journal.bin"], files[prefix+"intent.bin"]
        decoder_error = None
        try:
            state = native_pair(journal,intents,fixture["source"])
            if state["count"]:
                need(state["binding"] == fixture, "native-fixture-manifest")
            valid = True
        except ValueError as error:
            valid = False
            decoder_error = type(error).__name__+":"+str(error)
        if valid is not (number not in invalid):
            try:
                raw_lines = [line.decode("ascii",errors="backslashreplace") for line in frames(journal)[:3]]
            except ValueError as error:
                raw_lines = ["frame-error:"+str(error), journal[:256].hex()]
            print(json.dumps(dict(diagnostic="native-classification-mismatch",case=number,
                                  expected_valid=number not in invalid,actual_valid=valid,
                                  decoder_error=decoder_error,journal_bytes=len(journal),
                                  intent_bytes=len(intents),first_lines=raw_lines,
                                  first_intent_hex=intents[:424].hex())),flush=True)
            raise ValueError(f"native-raw-case-{number:03}:"+str(decoder_error or "unexpectedly-valid"))
    return dict(capabilities=["abi2-windows-known-six","abi3-windows","native-46-301"])

def persistent_evidence(files, spec, source):
    inventory(files)
    receipt = json_value(files["receipt.json"])
    provenance(receipt,spec,source)
    need(receipt["frozen_c01"] == C01 and receipt["full_c02_acceptance"] is False, "gate-receipt")
    result = summary(files["gate.log"])
    need(result["source"] == source and result["cases"] == 28 and result["checks"] == 309 and
         result["failed"] == 0 and result["passed"] is True, "gate-fixed-28-309")
    need(result["persistent_gate"] is True and result["frozen_c01_drift"] is True and
         result["publication_proof_control"] is True and result["real_owner_wiring"] is False, "gate-scope")
    need(files["gate-exit.txt"].strip() == b"0", "gate-exit")
    log = files["gate.log"].decode().replace("\r\n","\n")
    named_cases(log,28)
    reached = re.findall(r"^OBS gate_reached=(\d+) expected=(\d+)$",log,re.M)
    if [int(a) for a,b in reached] != [201,202,203,204] or not all(a == b for a,b in reached):
        print(json.dumps(dict(diagnostic="gate-real-kills",parsed=reached,
                              raw_observations=[line for line in log.splitlines() if line.startswith("OBS gate_")])),flush=True)
        raise ValueError("gate-real-kills")
    # Retain and independently classify every raw gate, including planted invalid objects.
    classified = []
    for name in sorted(files):
        if not name.endswith("/admission.bin"):
            continue
        try:
            rows = gate_records(files[name])
            classified.append(dict(path=name,valid=True,state=rows[-1]["kind"],count=len(rows)))
        except ValueError:
            classified.append(dict(path=name,valid=False))
    need(classified and any(row["valid"] for row in classified) and any(not row["valid"] for row in classified),
         "gate-raw-positive-and-negative-objects")
    return dict(capabilities=["persistent-gate","frozen-c01-drift"],raw_gates=classified)

def result_cases(report, spec, source, names=None):
    provenance(report,spec,source)
    need(report["complete"] is True and report["passed"] is True, "case-report-completion")
    rows = report["cases"]
    need(isinstance(rows,list) and rows and len({row["name"] for row in rows}) == len(rows) and
         all(row["passed"] is True for row in rows), "case-report-results")
    if names is not None:
        need({row["name"] for row in rows} == names, "case-report-names")
    return rows

def registry_export(data):
    text = data.decode("utf-16") if data[:2] in (b"\xff\xfe",b"\xfe\xff") else data.decode("utf-8-sig")
    text = re.sub(r"\\\r?\n\s*","",text)
    result = {}
    section = None
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("Windows Registry Editor"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            need(section.startswith("HKEY_CURRENT_USER\\Software\\EXReaderC02Admission"), "registry-export-scope")
            need(section not in result, "registry-export-duplicate-key")
            result[section] = {}
            continue
        match = re.fullmatch(r'"([^"]+)"=(.*)',line)
        need(match is not None and section is not None, "registry-export-format")
        name,value = match.groups()
        need(name not in result[section], "registry-export-duplicate-value")
        if not value.startswith("hex:"):
            # Component tests deliberately retain REG_LINK and wrong-type bindings.
            result[section][name] = None
            continue
        raw = value[4:]
        values = raw.split(",") if raw else []
        need(all(re.fullmatch(r"[0-9a-fA-F]{2}",item) for item in values), "registry-export-hex")
        result[section][name] = bytes(int(item,16) for item in values)
    return result

def case_commands(files, folder):
    result = []
    for name in sorted(files):
        if name.startswith(folder+"/command-") and name.endswith(".json"):
            row = json_value(files[name])
            need(type(row["exit"]) is int and isinstance(row["command"],list) and
                 isinstance(row["stdout"],str) and isinstance(row["stderr"],str), "command-record")
            result.append(row)
    need(result, "case-command-records")
    return result

def check_commands(rows, source, allowed_source_provider, pre_admission=False):
    for row in rows:
        command = row["command"]
        if len(command) < 2:
            continue
        mode = command[1]
        leaf = pathlib.PureWindowsPath(command[0]).name
        if leaf == "exreader-c02-admission.exe":
            need(row["exit"] in (0,2), "admission-exact-exit")
            observed = json_value(row["stdout"])
            need(observed["admitted"] is (row["exit"] == 0), "admission-exact-observation")
        if leaf in ("exreader-c02-migrate.exe","exreader-c02-migrate-test.exe"):
            for line in row["stdout"].splitlines():
                if line.startswith('{"status":'):
                    result = json_value(line)
                    if result.get("status") == "abandoned_before_admission":
                        need(pre_admission and mode == "recover" and row["exit"] == 0 and
                             result == dict(status="abandoned_before_admission",live_capability=False),
                             "migration-exact-pre-admission-abandonment")
                        continue
                    need(result["source"] == source and result["provider"] == allowed_source_provider, "migration-command-producer")
                    need(result["status"] in ("completed","rolled_back","uncertain","lease_retained","refused","pending"),
                         "migration-command-status")

def migration_evidence(files, spec, source, missing):
    report = json_value(files["actual-migration/migration-result.json"])
    provenance(report,spec,source)
    rows = report["results"]
    need(report["actual_importer"] is True and report["synchronous_owner"] is True and
         report["power_loss"] is False, "migration-actual-owner-scope")
    need(report["cases"] == len(rows) and report["failed"] == 0 and rows and
         len({row["name"] for row in rows}) == len(rows) and all(row["passed"] is True for row in rows),
         "migration-all-cases-passed")
    tree=ast.parse(git_bytes(source,"tests/migration/windows_registry_admission_20261031/migration_check.py"))
    declared=[]
    for node in ast.walk(tree):
        if not isinstance(node,ast.Assert) or not isinstance(node.test,ast.Compare):
            continue
        check=node.test
        if (isinstance(check.left,ast.Call) and isinstance(check.left.func,ast.Name) and
            check.left.func.id=="len" and len(check.left.args)==1 and
            isinstance(check.left.args[0],ast.Attribute) and check.left.args[0].attr=="rows" and
            len(check.ops)==1 and isinstance(check.ops[0],ast.Eq) and
            isinstance(check.comparators[0],ast.Constant) and type(check.comparators[0].value) is int):
            declared.append(check.comparators[0].value)
    need(declared==[len(rows)], "migration-qualified-source-declared-case-count")
    versions = report["versions"]
    providers = {entry["provider"] for entry in versions.values()}
    need(len(providers) == 1 and all(entry["source"] == source for entry in versions.values()), "migration-binary-versions")
    provider = next(iter(providers))
    need(hexadecimal(provider,64), "migration-provider")
    binaries = report["binaries"]
    for name in ("exreader-c02-migrate.exe","exreader-c02-migrate-test.exe","exreader-c02-admission.exe"):
        need(integer(binaries[name]["bytes"]) and binaries[name]["bytes"] > 0 and
             hexadecimal(binaries[name]["sha256"],64), "migration-binary-identity")
    registry = registry_export(files["registration.reg"])
    values_by_domain = {}
    for values in registry.values():
        for name,data in values.items():
            if name.startswith("Transaction-") and isinstance(data,bytes) and len(data)>=1448 and data[1376:1384]==b"C02IN001":
                domain = name[len("Transaction-"):]
                need(domain not in values_by_domain and hexadecimal(domain,48), "registry-transaction-domain")
                values_by_domain[domain] = (data,values.get("Prepared-"+domain),values)
    details = []
    observed,native_orig,repair_observed,fault_observed,archive_negatives = set(),set(),set(),set(),set()
    for row in rows:
        detail = row["detail"]
        if "evidence_dir" in detail:
            case_name=detail["evidence_dir"]
        elif row["name"] in ("actual-import-and-second-epoch","strict-policy-abort"):
            case_name=row["name"]
        else:
            phase,member=detail["phase"],detail["member"]
            sequence=detail.get("sequence")
            case_name=f"kill-{phase}-{member}"+(f"-seq-{sequence}" if sequence is not None else "")
            if detail.get("tamper"):
                case_name+="-"+detail["tamper"]
            if detail.get("repair_phase") is not None:
                case_name+="-repair-"+str(detail["repair_phase"])
        need(canonical_path(case_name)==case_name and "/" not in case_name, "actual-case-evidence-directory")
        folder="actual-migration/cases/"+case_name
        commands=case_commands(files,folder)
        check_commands(commands,source,provider,detail.get("phase")==900)
        if "gate_fault" in detail:
            fault_observed.add(detail["gate_fault"])
            need(detail["exit"]==2 and detail["gate_fault"] in (201,203), "real-gate-short-write")
        if "phase" in detail:
            phase,member,sequence=detail["phase"],detail["member"],detail.get("sequence")
            observed.add((phase,member,sequence))
            if 1<=phase<=10 and detail.get("repair_phase") is None:
                native_orig.add((phase,sequence))
            barriers=[json_value(line) for line in files[folder+"/killed-owner.log"].decode().splitlines()
                      if line.startswith('{"barrier":')]
            need(len(barriers)==1 and barriers[0]["barrier"]==phase and barriers[0]["member"]==member,
                 "actual-owner-native-barrier")
            if sequence is not None:
                need(barriers[0]["sequence"]==sequence, "actual-owner-exact-sequence")
            need(type(detail["owner_exit"]) is int and detail["owner_exit"]!=0, "actual-owner-killed")
        if detail.get("repair_phase") is not None:
            repair_phase=detail["repair_phase"]
            barriers=[json_value(line) for line in files[folder+"/repair-owner.log"].decode().splitlines()
                      if line.startswith('{"barrier":')]
            need(len(barriers)==1 and barriers[0]["barrier"]==repair_phase and
                 type(detail["repair_owner_exit"]) is int and detail["repair_owner_exit"]!=0, "actual-repair-owner-killed")
            origin_sequence=detail.get("origin_sequence",detail.get("sequence"))
            if not detail.get("tamper","").startswith("archive-"):
                repair_observed.add((repair_phase,origin_sequence))
            else:
                archive_negatives.add(detail["tamper"])
        if detail.get("tamper") and detail["tamper"]!="ack-floor":
            prior,after=detail["prior_stage"],detail["after_stage"]
            need(hexadecimal(prior["sha"],64) and hexadecimal(after["sha"],64), "tamper-byte-observation")
            if detail["tamper"].endswith("identity"):
                need((prior["dev"],prior["ino"])!=(after["dev"],after["ino"]) and prior["sha"]==after["sha"],
                     "same-byte-different-native-identity-observed")
            else:
                need(prior["sha"]!=after["sha"], "changed-byte-negative-observed")
        packets=[]
        for data,prepared_data,values in values_by_domain.values():
            packet=input_record(data,source,spec["run"],spec["attempt"])
            if pathlib.PureWindowsPath(packet["library"]).parent.name!=case_name:
                continue
            need(packet["binding"]["provider"]==provider, "input-qualified-provider")
            producer=("exreader-c02-migrate-test.exe" if "phase" in detail or "gate_fault" in detail
                      else "exreader-c02-migrate.exe")
            need(packet["binding"]["artifact"]==binaries[producer]["sha256"], "input-executed-binary")
            input_name=folder+"/native-input-"+packet["registry"]["domain"]+".bin"
            if input_name in files:
                need(files[input_name]==data, "input-export-copy")
            pack_name=folder+"/"+pathlib.PureWindowsPath(packet["pack"]).name
            need(packet["pack_file"]["sha256"]==sha(files[pack_name]) and
                 packet["pack_file"]["size"]==len(files[pack_name]), "input-actual-pack")
            pack=legacy_pack(files[pack_name])
            root=folder+"/"+pathlib.PureWindowsPath(packet["registry"]["root"]).name
            journal,intents=files[root+"/journal.bin"],files[root+"/intent.bin"]
            repair=audit_repairs(files,root,values,packet,detail)
            if detail.get("long_root"):
                need(detail["root_characters"]==225 and len(packet["registry"]["root"])==225, "actual-long-registered-root")
            if detail.get("tamper","").startswith("archive-") or detail.get("tamper")=="ack-floor":
                # A rejected archive or acknowledged floor rollback stays pending.
                ack=acknowledged_prefix(journal,intents,packet)
                state=ack["state"]
                gates=gate_records(files[root+"/admission.bin"],packet["registry"]["domain"])
                need(gates[-1]["kind"]=="B" and not state["committed"] and not state["aborted"],
                     "bad-archive-retains-pending-originals")
            else:
                gates=gate_records(files[root+"/admission.bin"],packet["registry"]["domain"])
                state=bound_history(frames(journal),packet)
                need(native_pair(journal,intents,source)==state, "production-complete-pair")
                if detail.get("remains_pending"):
                    need(gates[-1]["kind"]=="B" and not state["committed"] and not state["aborted"],
                         "tampered-recovery-remains-pending")
                elif detail.get("phase")==900:
                    need(gates[-1]["kind"]=="I" and state["count"]==0, "pre-admission-no-publication")
                else:
                    need(gates[-1]["kind"]=="C" and state["event"]==12 and
                         gates[-1]["count"]==state["count"] and gates[-1]["tip"]==state["last_line_sha"] and
                         gates[-1]["manifest"]==state["manifest_sha"], "actual-terminal-gate-and-journal")
            need(gates[0]["seal"]==packet["registry"]["seal"], "input-independent-initial-grant")
            if state["committed"]:
                need(prepared_data is not None and state["publish_intent"] and not state["aborted"], "publication-prepared-proof")
                prepared=prepared_record(prepared_data,packet)
                images=[]
                for entry in prepared:
                    matches=[value for name,value in files.items() if name.startswith(folder+"/") and
                             len(value)==entry["size"] and sha(value)==entry["sha256"]]
                    need(matches, "retained-verified-publication-image")
                    images.append(matches[0])
                proof=sqlite_content(images[0],images[1],pack,fixture_txt(source))
                retained=files[folder+"/"+packet["retained"][0]]
                need(len(retained)==packet["original"]["size"] and
                     sha(retained)==packet["original"]["sha256"], "retained-original-database")
                if packet["mirror"] is not None:
                    need(sha(files[folder+"/"+packet["retained"][1]])==packet["mirror"]["sha256"], "retained-original-mirror")
                packets.append(dict(domain=packet["registry"]["domain"],committed=True,repairs=repair,**proof))
            else:
                need(sha(files[folder+"/library.sqlite"])==packet["original"]["sha256"], "unpublished-original-unchanged")
                packets.append(dict(domain=packet["registry"]["domain"],committed=False,
                                    pending=gates[-1]["kind"]=="B",repairs=repair))
        need(packets, "actual-case-native-input")
        if row["name"]=="actual-import-and-second-epoch":
            need(len(packets)>=2 and all(item["committed"] for item in packets), "actual-second-independent-epoch")
        details.append(dict(name=row["name"],transactions=packets))
    required={(phase,1 if phase in (906,907,908,203,204) else 0,None)
              for phase in (900,901,902,903,904,905,906,907,908,201,202,203,204)}
    required|={(phase,member,None) for member in (0,1) for phase in (800,802,803)}
    required|={(801,0,None),(801,1,None)}
    need(required<=observed, "actual-owner-required-existing-barriers")
    for phase in range(1,11):
        for sequence in (0,5,9,10):
            if (phase,sequence) not in native_orig:
                missing.add(f"actual-native-recovery-{phase}-sequence-{sequence}")
    required_repair=spec.get("required_repair_phases")
    if not required_repair:
        missing.add("explicit-native-repair-cutpoint-adapter")
    else:
        need(set(range(950,956))<=set(required_repair) and len(set(required_repair))==len(required_repair),
             "repair-phase-adapter")
        for phase in required_repair:
            for sequence in (0,10):
                if (phase,sequence) not in repair_observed:
                    missing.add(f"explicit-native-repair-phase-{phase}-sequence-{sequence}")
    if fault_observed!={201,203}:
        missing.add("actual-gate-short-write-recovery")
    if archive_negatives!={"archive-bytes","archive-identity"}:
        missing.add("actual-repair-archive-tamper-refusal")
    return dict(cases=len(rows),provider=provider,details=details,
                capabilities=["actual-migration","compound-publication","explicit-repair-raw-semantics"])

def legacy_evidence(files, source):
    report = json_value(files["legacy-scenarios.json"])
    rows = report["cases"]
    total = report["summary"]
    need(total["cases"] == len(rows) and total["failed"] == 0 and total["passed"] == len(rows), "legacy-all-cases")
    expected = set()
    tree = ast.parse(git_bytes(source,"tests/migration/run_cases.py"))
    for node in tree.body:
        if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and any(
            isinstance(decorator,ast.Call) and isinstance(decorator.func,ast.Name) and decorator.func.id == "case"
            for decorator in node.decorator_list):
            expected.add(node.name)
    need({row["name"] for row in rows} == expected and expected, "legacy-original-suite-complete")
    checks = [check for row in rows for check in row["checks"]]
    need(total["checks"] == len(checks) and total["checks_passed"] == len(checks) and
         all(row["passed"] is True and row["error"] is None and row["checks"] for row in rows) and
         all(check["ok"] is True for check in checks), "legacy-every-assertion")
    return dict(cases=len(rows),checks=len(checks))


def provider_sources(files,spec,source):
    material = files["wh3-provider-sources.txt"]
    lines = material.decode().splitlines()
    need(lines and lines[0] == "C02-SDK-"+SDK and material.endswith(b"\n"), "provider-material-header")
    base = "extras/migration/windows_coordinator_native_journal_20261030"
    cmake = git_bytes(source,base+"/CMakeLists.txt").decode()
    match = re.search(r"set\(provider_sources\s+([^)]*)\)",cmake,re.S)
    need(match is not None, "provider-source-set")
    expected = match[1].split()
    listed = []
    endings = {}
    for line in lines[1:]:
        path,sep,digest = line.partition("=")
        need(sep and hexadecimal(digest,64), "provider-material-line")
        resolved = posixpath.normpath(base+"/"+path)
        data = git_bytes(source,resolved)
        if sha(data)==digest:
            endings[path]="git-blob"
        else:
            crlf=data.replace(b"\r\n",b"\n").replace(b"\n",b"\r\n")
            need(sha(crlf)==digest, "provider-source-bytes:"+resolved)
            endings[path]="git-checkout-crlf"
        listed.append(path)
    need(listed==expected, "provider-complete-source-set")
    definitions = {}
    for name,value in re.findall(r'^#define (WH3_[A-Z_]+) "([^"]+)"$',files["wh3_build.h"].decode().replace("\r\n","\n"),re.M):
        need(name not in definitions, "provider-duplicate-definition")
        definitions[name]=value
    # Reconstruct the exact LF CMake string used by string(SHA256), while
    # accepting only its byte-identical LF or Windows text-file CRLF serialization.
    canonical = ("\n".join(lines)+"\n").encode("ascii")
    need(material in (canonical,canonical.replace(b"\n",b"\r\n")), "provider-material-line-endings")
    digest=sha(canonical)
    expected_build = dict(WH3_BUILD_SOURCE=source,WH3_BUILD_RUN=str(spec["run"]),
                          WH3_BUILD_ATTEMPT=str(spec["attempt"]),WH3_PROVIDER_SHA=digest)
    for key,value in expected_build.items():
        need(definitions.get(key)==value,
             "provider-configured-build-binding:"+key+":actual="+str(definitions.get(key))+":expected="+value)
    return digest,endings


def registry_evidence(files, spec, source, missing):
    inventory(files)
    receipt = json_value(files["receipt.json"])
    provenance(receipt,spec,source)
    need(receipt["frozen_sdk"] == SDK and receipt["full_c02_acceptance"] is False, "registry-scope")
    result = summary(files["registry.log"])
    expected = spec["expected_registry"]
    need(expected["cases"] >= 50 and expected["checks"] >= 530, "registry-preserved-floor")
    need(result["source"] == source and result["cases"] == expected["cases"] and
         result["checks"] == expected["checks"] and result["failed"] == 0 and result["passed"] is True,
         "registry-exact-current-counts")
    need(result["actual_sdk"] is True and result["trusted_registry"] is True and
         result["production_coordinator"] is False and result["full_c02_acceptance"] is False, "registry-component-scope")
    named_cases(files["registry.log"].decode(),expected["cases"])
    admission = result_cases(json_value(files["admission-command/report.json"]),spec,source,CLI_CASES)
    product = result_cases(json_value(files["product/report.json"]),spec,source,OWNER_CASES)
    final = next(row for row in product if row["name"] == "actual-host-final-release")
    need(final["visible_window"] is True and final["blocked_while_live"] is True and
         final["admitted_after_close"] is True, "actual-product-final-borrow")
    for row in product:
        if row["name"] in OWNER_CASES - {"registered","actual-host-final-release"}:
            need(row["exit"] == 2, "actual-product-refusal-exit")
            log = files["product/"+row["name"]+"/stderr.txt"]
            need(b"C02 admission] refused before SDK open" in log, "actual-product-refusal-before-sdk")
    legacy = legacy_evidence(files,source)
    scanner = audit_scanner(files,spec,source,missing)
    named_cases(files["repair-scan.log"].decode(),scanner["cases"])
    provider,endings = provider_sources(files,spec,source)
    migration = migration_evidence(files,spec,source,missing)
    need(migration["provider"]==provider, "provider-actual-binary-source-fingerprint")
    migration["source_line_endings"]=endings
    return dict(capabilities=["trusted-registry","windows-product-admission","legacy-regression",*migration["capabilities"]],
                registry=result,cli_cases=len(admission),host_cases=len(product),legacy=legacy,scanner=scanner,migration=migration)

def host_evidence(files, spec, source, missing):
    receipt = json_value(files[spec["receipt"]])
    provenance(receipt,spec,source)
    need(receipt["platform"] == spec["platform"] and receipt["full_c02_acceptance"] is False, "host-build-receipt")
    prefix = spec["role"]
    report_path, log_path = spec.get("admission_report"), spec.get("observation_log")
    if not report_path or not log_path:
        missing.add(prefix+"-persistent-admission-runtime-adapter")
        return dict(capabilities=[prefix+"-build"],runtime=False)
    report = json_value(files[report_path])
    provenance(report,spec,source)
    need(report["schema"] == "c02-host-admission-v1" and report["actual_sdk"] is True and
         report["platform"] == spec["platform"], "host-admission-schema")
    rows = result_cases(report,spec,source,HOST_CASES)
    observations = [json_value(line[len("C02-HOST-OBS "):]) for line in files[log_path].decode().splitlines()
                    if line.startswith("C02-HOST-OBS ")]
    need(len(observations) == len(rows) and {row["name"] for row in observations} == HOST_CASES, "host-raw-observations")
    observations = {row["name"]:row for row in observations}
    for row in rows:
        need(row["observation"] == observations[row["name"]], "host-report-raw-binding")
    need(observations["clean-admits-before-sdk"]["sdk_open_count"] == 1, "host-clean-sdk")
    for name in ("pending-refuses-before-sdk","missing-binding-refuses-before-sdk","fresh-process-pending-refusal"):
        need(observations[name]["sdk_open_count"] == 0 and observations[name]["admitted"] is False, "host-refuses-before-sdk")
    need(observations["last-borrow-blocks-owner"]["owner_admitted"] is False and
         observations["final-borrow-release-allows-owner"]["owner_admitted"] is True, "host-last-borrow")
    # This adapter validates runtime observations. A platform-specific native
    # authority decoder must be implemented before this can qualify all C02.
    missing.add(prefix+"-native-authority-semantic-adapter")
    return dict(capabilities=[prefix+"-build",prefix+"-runtime-observations"],runtime=True)

@functools.lru_cache(maxsize=None)
def fixture_txt(source):
    tree=ast.parse(git_bytes(source,"tests/migration/legacy_data.py"))
    candidates=[node.value for node in tree.body if isinstance(node,ast.Assign) and
                any(isinstance(target,ast.Name) and target.id=="TXT" for target in node.targets)]
    need(len(candidates)==1 and isinstance(candidates[0],ast.Call) and
         isinstance(candidates[0].func,ast.Attribute) and candidates[0].func.attr=="encode",
         "qualified-txt-static-literal")
    value=ast.literal_eval(candidates[0].func.value)
    need(isinstance(value,str), "qualified-txt-string")
    return value.encode("utf-8")

@functools.lru_cache(maxsize=None)
def git_bytes(source,path):
    need(hexadecimal(source,40) and not path.startswith("/") and ".." not in pathlib.PurePosixPath(path).parts,
         "git-source-path")
    result = subprocess.run(["git","show",source+":"+path],capture_output=True,check=True)
    return result.stdout

def download_json(repo,path,target):
    command = ["gh","api","repos/"+repo+"/"+path]
    result = subprocess.run(command,capture_output=True)
    need(result.returncode == 0, "github-api-json:" + path)
    value = json_value(result.stdout)
    target.write_bytes(result.stdout)
    return value

def acquire(repo,spec,source,directory):
    directory.mkdir()
    run_id,attempt,job_id = spec["run"],spec["attempt"],spec["job"]
    need(all(type(value) is int and value > 0 for value in (run_id,attempt,job_id)), "producer-positive-ids")
    run = download_json(repo,f"actions/runs/{run_id}/attempts/{attempt}",directory/"run.json")
    jobs = download_json(repo,f"actions/runs/{run_id}/attempts/{attempt}/jobs?per_page=100",directory/"jobs.json")
    artifact = spec["artifact"]
    need(type(artifact["id"]) is int and artifact["id"] > 0 and integer(artifact["bytes"]) and
         artifact["bytes"] > 0 and hexadecimal(artifact["sha256"],64), "artifact-expected-identity")
    metadata = download_json(repo,f"actions/artifacts/{artifact['id']}",directory/"artifact.json")
    need(run["id"] == run_id and run["run_attempt"] == attempt and run["head_sha"] == source and
         run["status"] == "completed" and run["path"] == spec["workflow"] and
         run["repository"]["full_name"] == repo, "producer-workflow-run")
    need(jobs["total_count"] == len(jobs["jobs"]), "jobs-pagination-unresolved")
    candidates = [job for job in jobs["jobs"] if job["id"] == job_id]
    need(len(candidates) == 1, "producer-job-id")
    job = candidates[0]
    need(job["run_id"] == run_id and job["name"] == spec["job_name"] and job["status"] == "completed",
         "producer-job-binding")
    need(metadata["id"] == artifact["id"] and metadata["name"] == artifact["name"] and
         metadata["size_in_bytes"] == artifact["bytes"] and metadata["digest"] == "sha256:"+artifact["sha256"] and
         metadata["expired"] is False and metadata["workflow_run"]["id"] == run_id and
         metadata["workflow_run"]["head_sha"] == source, "artifact-api-identity")
    created = datetime.datetime.fromisoformat(metadata["created_at"].replace("Z","+00:00"))
    started = datetime.datetime.fromisoformat(job["started_at"].replace("Z","+00:00"))
    completed = datetime.datetime.fromisoformat(job["completed_at"].replace("Z","+00:00"))
    need(started <= created <= completed, "artifact-exact-attempt-job-window")
    failed = [step["name"] for step in job["steps"] if step["conclusion"] == "failure"]
    if spec["role"].startswith("native-"):
        need(run["conclusion"] == "failure" and job["conclusion"] == "failure" and
             failed == [FROZEN_NATIVE_STEP], "native-only-original-abi2-failure")
        step_name = ("Real NTFS I/O, subprocess barriers, and resealed semantic attacks"
                     if spec["role"] == "native-windows" else "Independently run ABI3 memory transaction contract controls")
        need(any(step["name"] == step_name and step["conclusion"] == "success" for step in job["steps"]),
             "required-native-step")
    else:
        need(run["conclusion"] == "success" and job["conclusion"] == "success" and not failed, "component-job-success")
    raw_path = directory/"original.zip"
    with raw_path.open("xb") as output:
        result = subprocess.run(["gh","api",f"repos/{repo}/actions/artifacts/{artifact['id']}/zip"],stdout=output,stderr=subprocess.PIPE)
    need(result.returncode == 0, "original-zip-download")
    need(raw_path.stat().st_size == artifact["bytes"] and artifact["bytes"] <= 512*1024*1024, "original-zip-size")
    raw = raw_path.read_bytes()
    need(sha(raw) == artifact["sha256"], "original-zip-sha256")
    return raw,metadata

def semantic_diagnostic(files,spec,error):
    contexts = []
    trace = error.__traceback__
    keys = {"folder","number","index","offset","phase","sequence","name","path","kind",
            "prefix","count","event","repair_phase","origin_phase","origin_sequence"}
    while trace is not None:
        local = trace.tb_frame.f_locals
        values = {key:value for key,value in local.items() if key in keys and
                  (value is None or type(value) in (str,int,bool))}
        contexts.append(dict(function=trace.tb_frame.f_code.co_name,line=trace.tb_lineno,values=values))
        trace = trace.tb_next
    logs = {}
    for name,data in sorted(files.items()):
        if "/" not in name and name.endswith(".log"):
            lines = data.decode(errors="backslashreplace").splitlines()
            logs[name] = dict(lines=len(lines),tail=lines[-8:])
    return dict(diagnostic="component-semantic-failure",role=spec["role"],run=spec["run"],
                attempt=spec["attempt"],artifact=spec["artifact"]["id"],
                error=type(error).__name__,detail=str(error),contexts=contexts,logs=logs,
                files=[dict(path=name,bytes=len(data)) for name,data in sorted(files.items())])

def validate(files,spec,source,missing):
    role = spec["role"]
    if role.startswith("native-"):
        return native_evidence(files,spec,source)
    if role == "persistent-gate":
        return persistent_evidence(files,spec,source)
    if role == "registry-product":
        return registry_evidence(files,spec,source,missing)
    return host_evidence(files,spec,source,missing)

def reseal_intents(data,wrong_ack=False):
    data = bytearray(data)
    previous = b"0"*64
    begin = None
    for offset in range(0,len(data),424):
        data[offset+296:offset+360] = previous
        if data[offset+8] == ord("A"):
            data[offset+232:offset+296] = begin
            if wrong_ack and offset == 424:
                data[offset+232] ^= 1
        digest = sha(data[offset:offset+360]).encode()
        data[offset+360:offset+424] = digest
        if data[offset+8] == ord("B"):
            begin = digest
        previous = digest
    return bytes(data)

def negative_controls(original,spec,source,directory):
    controls = []
    def receipt_change(files,key,value):
        data = json_value(files["receipt.json"])
        data[key] = value
        files["receipt.json"] = (json.dumps(data)+"\n").encode()
    def reserved(files):
        key = "native-files/case-001/a/b/intent.bin"
        data = bytearray(files[key]);data[9] = 1
        files[key] = reseal_intents(data)
    def duplicate(files):
        key = "native-files/case-001/a/b/intent.bin"
        data = bytearray(files[key]);data[848:1696] = data[:848]
        import struct
        struct.pack_into("<Q",data,848+16,2);struct.pack_into("<Q",data,1272+16,2)
        files[key] = reseal_intents(data)
    def wrong_ack(files):
        key = "native-files/case-001/a/b/intent.bin"
        files[key] = reseal_intents(files[key],True)
    def interior(files):
        import struct
        key = "native-files/case-001/a/b/journal.bin"
        data = bytearray(files[key]);first = struct.unpack_from("<I",data)[0]
        data[4+first+4+10] ^= 1;files[key] = bytes(data)
    def counters(files):
        data = files["native.log"].decode()
        data = data.replace('"checks":301','"checks":300')
        files["native.log"] = data.encode()
        receipt = json_value(files["receipt.json"])
        receipt["native"]["checks"] = 300
        files["receipt.json"] = json.dumps(receipt).encode()
    mutations = [
        ("repacked-source",lambda f:receipt_change(f,"source","0"*40)),
        ("repacked-run",lambda f:receipt_change(f,"run","1")),
        ("repacked-attempt",lambda f:receipt_change(f,"attempt","2")),
        ("repacked-false-full-p0",lambda f:receipt_change(f,"full_p0_acceptance",True)),
        ("resealed-reserved-byte",reserved),("resealed-duplicate-count-gap",duplicate),
        ("resealed-wrong-ack",wrong_ack),("rehashed-interior-line",interior),
        ("repacked-weakened-native-count",counters)]
    for name,mutation in mutations:
        files = dict(original)
        mutation(files)
        files["file-hashes.json"] = (json.dumps([
            dict(path=key,bytes=len(value),sha256=sha(value))
            for key,value in sorted(files.items()) if key != "file-hashes.json"],indent=2)+"\n").encode()
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer,"w",zipfile.ZIP_DEFLATED) as archive:
            for path,data in sorted(files.items()):
                archive.writestr(path,data)
        raw = buffer.getvalue()
        path = directory/(name+".zip");path.write_bytes(raw)
        try:
            validate(zip_files(raw),spec,source,set())
        except ValueError as error:
            controls.append(dict(name=name,rejected=True,reason=str(error),bytes=len(raw),sha256=sha(raw)))
        else:
            raise ValueError("accepted-fully-repacked-negative:" + name)
    need(len(controls) >= 7, "at-least-seven-repacked-negatives")
    return controls

def main():
    need(os.environ.get("GITHUB_ACTIONS") == "true", "all-execution-only-github-actions")
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest",type=pathlib.Path,required=True)
    parser.add_argument("--output",type=pathlib.Path,required=True)
    parser.add_argument("--require-complete",action="store_true")
    parser.add_argument("--allow-incomplete",action="store_true")
    args = parser.parse_args()
    need(not (args.require_complete and args.allow_incomplete), "exclusive-audit-scope")
    manifest_data = args.manifest.read_bytes()
    requested = json_value(manifest_data)
    need(requested["schema"] == 1 and hexadecimal(requested["source"],40), "audit-manifest-schema")
    repo,source = requested["repository"],requested["source"]
    need(re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+",repo) is not None, "repository-name")
    specs = requested["packages"]
    need(specs and all(spec["role"] in ROLES for spec in specs) and
         len({spec["role"] for spec in specs}) == len(specs), "audit-package-roles")
    output = args.output.resolve()
    output.mkdir(parents=True,exist_ok=False)
    (output/"request.json").write_bytes(manifest_data)
    missing = set(ROLES - {spec["role"] for spec in specs})
    packages = []
    original_checks = []
    windows = None
    for spec in specs:
        role = spec["role"]
        raw,metadata = acquire(repo,spec,source,output/role)
        files = zip_files(raw)
        try:
            details = validate(files,spec,source,missing)
        except Exception as error:
            diagnostic = semantic_diagnostic(files,spec,error)
            (output/role/"semantic-failure.json").write_text(json.dumps(diagnostic,indent=2)+"\n")
            print(json.dumps({key:value for key,value in diagnostic.items() if key != "files"}),flush=True)
            raise
        packages.append(dict(role=role,run=spec["run"],attempt=spec["attempt"],job=spec["job"],
                             artifact=spec["artifact"],details=details))
        original_checks.append((output/role/"original.zip",spec["artifact"]))
        if role == "native-windows":
            windows = (files,spec)
    need(windows is not None, "negative-controls-require-original-windows-native")
    controls = negative_controls(windows[0],windows[1],source,output)
    for path,artifact in original_checks:
        need(path.stat().st_size == artifact["bytes"] and sha(path.read_bytes()) == artifact["sha256"],
             "retained-original-unchanged")
    result = dict(schema=1,audit_source=os.environ["GITHUB_SHA"],audit_run=os.environ["GITHUB_RUN_ID"],
                  audit_attempt=os.environ["GITHUB_RUN_ATTEMPT"],producer_source=source,
                  original_zips_verified=True,semantic_negative_controls=controls,packages=packages,
                  missing_capabilities=sorted(missing),full_c02_complete=not missing,power_loss_tested=False,
                  scope="complete-c02" if not args.allow_incomplete else "component-evidence",
                  passed=not missing or args.allow_incomplete)
    (output/"audit-result.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result),flush=True)
    return 0 if result["passed"] else 1

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print(json.dumps(dict(passed=False,error=type(error).__name__,detail=str(error))),file=sys.stderr)
        raise
