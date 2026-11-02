import base64
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import plistlib
import re
import signal
import stat
import subprocess
import sys
import zipfile

BASE = "d41dc991d0cf04694a5b549fa12c4854182fe8da"
PRODUCT = "e9e20eada714bc6b8045d3e943ac46ff26844559"
LEGACY_HASH = "0d330a6841831494a15fafbf1f318d8441cffd9bee0a068fca9b10b3105ed2f1"
POLICY_PATH = Path("tests/f09_audit/g16_production_adjudication_v1.json")
PINS_PATH = Path("tests/f09_audit/g16_production_evidence_pins_20261102.json")
PATHS = sorted([str(POLICY_PATH), str(PINS_PATH),
    "tools/f09_review/adjudicate_g16_production_20261102.py",
    ".github/workflows/f09-g16-production-adjudication-20261102.yml",
    "docs/reader-total-progress/F09_G16_PRODUCTION_ADJUDICATION_20261102.md"])
OUT = Path("build/f09-g16-production-adjudication")
OUT.mkdir(parents=True, exist_ok=True)
TOTAL = {"download": 0, "declared_expanded": 0, "selected_read": 0}
RESULT = {"schema": 1, "source": os.environ.get("GITHUB_SHA"),
          "run": os.environ.get("GITHUB_RUN_ID"), "attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
          "acceptance_eligible": False, "f09_complete": False,
          "legacy_gate_executed": False, "legacy_results_modified": False,
          "historical_finding_rows_reloaded": False, "legacy_blockers_cleared": 0,
          "same_diagnostic_sha_three_platform_acceptance": False,
          "new_rule_results": [], "historical_references": [], "archives": [],
          "remaining_independent_gaps": [
              "Windows and GTK original audit failures",
              "iPhone/iPad actual screen-reader evidence",
              "historical intermittent failures are not erased",
              "other original suite impact not fully verified",
              "legacy finding row matching and formal old-gate integration not performed"]}
def ceiling(_sig, _frame):
    raise TimeoutError("eight-minute inspection ceiling; no retry")
signal.signal(signal.SIGALRM, ceiling)
signal.alarm(480)

def need(ok, message):
    if not ok:
        raise RuntimeError(message)

def sha(data):
    return hashlib.sha256(data).hexdigest()

def api(path):
    raw = subprocess.check_output(["gh", "api", "repos/NoGod3524/EXReader/"+path], timeout=60)
    need(len(raw) <= 4*1024*1024, "API response too large")
    return json.loads(raw)

def archive(pin):
    meta = api("actions/artifacts/"+str(pin["id"]))
    need(all(meta.get(k) == pin[k] for k in ("id", "name", "size_in_bytes")),
         "artifact id/name/size mismatch")
    need(meta.get("digest") == "sha256:"+pin["sha256"] and meta.get("expired") is False,
         "artifact digest/expiry mismatch")
    producer = meta.get("workflow_run", {})
    need(producer.get("id") == pin["run"] and producer.get("head_sha") == pin["source"],
         "artifact producer mismatch")
    run = api("actions/runs/"+str(pin["run"])+"/attempts/1")
    need(run.get("id") == pin["run"] and run.get("head_sha") == pin["source"]
         and run.get("run_attempt") == 1 and run.get("status") == "completed"
         and run.get("conclusion") == "success", "fixed producer attempt not successful")
    target = OUT/(str(pin["id"])+".zip")
    proc = subprocess.Popen(["gh", "api", "repos/NoGod3524/EXReader/actions/artifacts/"+
                             str(pin["id"])+"/zip"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    count = 0
    try:
        with target.open("wb") as f:
            while True:
                block = proc.stdout.read(65536)
                if not block:
                    break
                count += len(block)
                TOTAL["download"] += len(block)
                need(count <= pin["size_in_bytes"] and TOTAL["download"] <= 16*1024*1024,
                     "download budget exceeded")
                f.write(block)
        need(proc.wait(timeout=60) == 0 and count == pin["size_in_bytes"],
             "archive download incomplete")
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        proc.stdout.close()
    need(sha(target.read_bytes()) == pin["sha256"], "archive hash mismatch")
    z = zipfile.ZipFile(target)
    names = {}
    try:
        need(len(z.infolist()) <= 20000, "archive member budget exceeded")
        for member in z.infolist():
            p = PurePosixPath(member.filename)
            n = p.as_posix()
            mode = stat.S_IFMT(member.external_attr >> 16)
            need(member.filename.rstrip("/") == n and n not in names and not p.is_absolute()
                 and ".." not in p.parts and "\\" not in member.filename
                 and ":" not in member.filename and "\x00" not in member.orig_filename
                 and not member.flag_bits & 1 and mode in (0, stat.S_IFREG, stat.S_IFDIR),
                 "unsafe archive member")
            need(mode == 0 or (mode == stat.S_IFDIR) == member.is_dir(),
                 "archive directory/type mismatch")
            TOTAL["declared_expanded"] += member.file_size
            need(member.file_size <= 128*1024*1024 and TOTAL["declared_expanded"] <= 512*1024*1024,
                 "expanded archive budget exceeded")
            names[n] = member
        RESULT["archives"].append({"id": pin["id"], "run": pin["run"], "source": pin["source"],
                                   "bytes": count, "sha256": pin["sha256"], "members": len(names)})
        return z, names, target
    except Exception:
        z.close()
        raise

def read_member(z, members, name, limit):
    need(name in members and not members[name].is_dir(), "required member missing: "+name)
    item = members[name]
    need(item.file_size <= limit, "selected member too large: "+name)
    data = bytearray()
    with z.open(item) as f:
        while True:
            block = f.read(65536)
            if not block:
                break
            data.extend(block)
            TOTAL["selected_read"] += len(block)
            need(len(data) <= item.file_size and TOTAL["selected_read"] <= 512*1024*1024,
                 "selected read budget exceeded")
    need(len(data) == item.file_size, "short member")
    return bytes(data)

def inspect_current(pin, policy):
    z, names, path = archive(pin)
    try:
        report = json.loads(read_member(z, names, "report.json", 8*1024*1024))
        log = read_member(z, names, "normal-1.log", 32*1024*1024)
        settings_raw = read_member(z, names, "actual-build-settings.log", 16*1024*1024)
        executable = read_member(z, names, "program-identity/EXReaderHost", 64*1024*1024)
        plist_raw = read_member(z, names, "program-identity/Info.plist", 1024*1024)
        receipt = report.get("receipt")
        need(receipt == pin["receipt"], "report receipt differs from independent fixed pin")
        need(report.get("diagnostic_source") == pin["source"] and report.get("product_source_base") == PRODUCT
             and report.get("exit_code") == 0 and report.get("acceptance_eligible") is False,
             "report scope/source mismatch")
        need(sha(log) == receipt["raw_log_sha256"] and sha(settings_raw) == receipt["build_settings_sha256"],
             "raw log/build settings digest mismatch")
        need(sha(executable) == receipt["built_program_sha256"], "retained executable digest mismatch")
        info = plistlib.loads(plist_raw)
        need(info.get("CFBundleIdentifier") == "org.exreader.host" and info.get("EXRSourceSHA") == pin["source"],
             "retained plist identity mismatch")
        built = report.get("built_program")
        need(built == pin["built_program"] and built["executable_sha256"] == sha(executable)
             and built["info_plist_sha256"] == sha(plist_raw), "built identity mismatch")
        settings = json.loads(settings_raw)
        need(isinstance(settings, list), "build settings must be a list")
        rows = [x for x in settings if isinstance(x, dict) and x.get("target") == pin["app_target"]]
        need(len(rows) == 1 and isinstance(rows[0].get("buildSettings"), dict), "ambiguous application settings")
        bs = rows[0]["buildSettings"]
        summary_keys = ("SWIFT_ACTIVE_COMPILATION_CONDITIONS", "OTHER_SWIFT_FLAGS",
                        "PRODUCT_BUNDLE_IDENTIFIER", "SDKROOT", "CONFIGURATION")
        need(all(k in bs and isinstance(bs[k], str) and bs[k].strip() for k in summary_keys),
             "missing or invalid actual build settings; mode is unverified")
        need(bs["PRODUCT_BUNDLE_IDENTIFIER"] == "org.exreader.host" and bs["CONFIGURATION"] == "Debug",
             "actual bundle/configuration mismatch")
        expected_sdk = "/MacOSX.platform/" if pin["platform"] == "macos" else "/iPhoneSimulator.platform/"
        need(expected_sdk in bs["SDKROOT"], "unexpected actual platform SDK")
        flags = bs["SWIFT_ACTIVE_COMPILATION_CONDITIONS"]+" "+bs["OTHER_SWIFT_FLAGS"]
        need(not re.search(r"EXR_[A-Z0-9_]*REVIEW", flags), "actual build is not production")
        summary = report.get("application_build_settings")
        need(isinstance(summary, dict) and set(summary) == set(summary_keys)
             and {k: bs[k] for k in summary_keys} == summary,
             "fixed five summarized settings differ from raw settings")
        text = log.decode("utf-8", "replace")
        marker = "F09_G16_MAC_EXACT_QUERY " if pin["platform"] == "macos" else "F09_G16_EXACT_QUERY "
        records = [json.loads(line.split(marker, 1)[1]) for line in text.splitlines() if marker in line]
        need(records == report.get("exact_query_records") and len(records) == 2, "raw query records mismatch")
        need(sha(json.dumps(records, sort_keys=True, ensure_ascii=False).encode()) ==
             receipt["raw_query_records_sha256"], "query record digest mismatch")
        completions = re.findall(r"Test Case .*testProductionG16Evidence.* (passed|failed) \(", text)
        need(completions == ["passed"], "expected exactly one completed collector case")
        need(report.get("tests") == [{"case": pin["case"], "exit": 0, "observed_case_completions": ["passed"]}],
             "reported case completion mismatch")
        for record, state, anchor in zip(records, ["library.empty", "reader.epub"],
                                         ["library.organization", "reader.page"]):
            need(record.get("schema") == 1 and record.get("case") == "testProductionG16Evidence"
                 and record.get("session") == receipt["session"] and record.get("state") == state
                 and record.get("anchor_id") == anchor and record.get("anchor_exists") is True
                 and record.get("app_foreground") is True and record.get("query_completed") is True
                 and record.get("nodes_truncated") is False
                 and record.get("scope") == "current-app XCUI descendants matching exact identifier",
                 "incomplete anchored exact-query evidence")
        empty, reader = records
        need(empty.get("target_id") == "library.empty" and type(empty.get("query_count")) is int
             and empty["query_count"] == 1 and isinstance(empty.get("nodes"), list) and len(empty["nodes"]) == 1,
             "empty shelf exact query mismatch")
        node = empty["nodes"][0]
        label = node.get("label")
        name = label if isinstance(label, str) and label.strip() else node.get("value", "")
        need(node.get("id") == "library.empty" and node.get("is_static_text") is True
             and isinstance(name, str) and name.strip() == policy["rules"]["library.empty"]["name_equals"],
             "empty shelf current name/role mismatch")
        need(reader.get("target_id") == "reader.state" and type(reader.get("query_count")) is int
             and reader["query_count"] == 0 and reader.get("nodes") == [],
             "production reader.state was present or query inconsistent")
        if pin["platform"] == "macos":
            live = [x.get("running_host") for x in records]
            need(all(isinstance(x, dict) for x in live), "missing running mac host identity")
            for x in live:
                need(type(x.get("pid")) is int and x["pid"] > 0 and x.get("alive_at_capture") is True
                     and x.get("is_terminated") is False and type(x.get("launch_date")) in (int, float),
                     "invalid during-case mac process observation")
                need(x.get("bundle_path") == built["bundle"] and x.get("executable_path") == built["executable_path"],
                     "running host path mismatch")
                for key in ("bundle_id", "executable_sha256", "info_plist_sha256", "embedded_source"):
                    need(x.get(key) == built[key], "running host identity mismatch")
            for key in ("pid", "launch_date", "bundle_path", "executable_path", "executable_sha256", "info_plist_sha256"):
                need(live[0][key] == live[1][key], "mac process changed between query states")
            need(report.get("post_case_file_identity") == built, "post-case files changed")
        else:
            for key in ("installed_before", "installed_after"):
                actual = report.get(key)
                need(isinstance(actual, dict), "missing simulator installed identity")
                for field in ("bundle_id", "executable_sha256", "info_plist_sha256", "embedded_source"):
                    need(actual.get(field) == built[field], "simulator installed identity mismatch")
        return {"platform": pin["platform"], "source": pin["source"], "run": pin["run"],
                "artifact": pin["id"], "session": receipt["session"], "mode": "production",
                "program_sha256": sha(executable), "raw_log_sha256": sha(log),
                "query_records_sha256": receipt["raw_query_records_sha256"],
                "library.empty": {"count": 1, "observed_name": name.strip()},
                "reader.state": {"count": 0},
                "scope": "current-app anchored XCUI exact-ID queries; no VoiceOver/full-tree claim"}
    finally:
        z.close()
        path.unlink()

exit_code = 1
try:
    need(os.environ.get("GITHUB_ACTIONS") == "true" and RESULT["attempt"] == "1", "Actions A1 only")
    for flags in ([], ["--diff-filter=A"]):
        changed = subprocess.check_output(["git", "diff"]+flags+["--name-only", BASE, "HEAD"], text=True, timeout=30).splitlines()
        need(sorted(changed) == PATHS, "exact five-new-path scope required")
    legacy_bytes = Path("tests/reader_a11y_apple/a11y_contract.json").read_bytes()
    need(sha(legacy_bytes) == LEGACY_HASH, "legacy contract changed")
    policy = json.loads(POLICY_PATH.read_text())
    pins = json.loads(PINS_PATH.read_text())
    need(policy.get("schema") == 1 and policy.get("f09_acceptance_eligible") is False
         and policy.get("legacy_finding_supersession_verified") is False,
         "policy schema or acceptance boundary mismatch")
    need(policy["rules"]["library.empty"].get("normalization") ==
         "nonblank label else string value; compare strip", "unapproved name normalization")
    need(policy["version"] == "f09-production-adjudication-v1" and policy["legacy_contract_sha256"] == LEGACY_HASH,
         "policy version/legacy pin mismatch")
    need(policy["rules"]["reader.state"] == {"production": "absent", "review": "required"}
         and policy["rules"]["library.empty"]["name_equals"] ==
         "\u4e66\u67b6\u4e3a\u7a7a\uff0c\u6253\u5f00\u6587\u4ef6\u5373\u53ef\u5bfc\u5165\u3002",
         "unapproved policy mutation")
    need([p["platform"] for p in pins["current"]] == ["iphone", "ipad", "macos"], "unexpected current evidence set")
    need([p["id"] for p in pins["current"]] == [13145656551, 13150886644, 13153191977]
         and pins["historical"]["id"] == 13134519939, "unexpected artifact set")
    need(sum(p["size_in_bytes"] for p in pins["current"]+[pins["historical"]]) == 10024600,
         "fixed archive byte total mismatch")
    historical = pins["historical"]
    z, names, path = archive(historical)
    try:
        old = json.loads(read_member(z, names, "report.json", 8*1024*1024))
        need(old.get("source") == PRODUCT and old.get("run") == 41363868404 and old.get("attempt") == 1
             and old.get("archive_inspection_complete") is True
             and old.get("remaining_historical_blockers_not_reclassified") == 6,
             "historical inspection identity mismatch")
        old_refs = {}
        for platform in ("iphone", "ipad", "macos"):
            rows = [a for a in old["artifacts"] if a.get("platform") == platform]
            need(len(rows) == 1, "historical platform not unique")
            a = rows[0]
            reports = [t for t in a["text_evidence"] if t.get("path") == "audit/"+platform+"/report.json"]
            need(len(reports) == 1, "historical report reference missing")
            t = reports[0]
            expected = pins["historical_report_references"][platform]
            need(a["artifact_id"] == expected["artifact_id"] and a["archive_sha256"] == expected["archive_sha256"]
                 and t["sha256"] == expected["report_sha256"], "historical reference digest mismatch")
            old_refs[platform] = dict(expected, source=PRODUCT, run=41363868404, attempt=1,
                historical_finding_rows_reloaded=False,
                reference_status="pending original-finding row matching; not a verified supersession",
                old_run_result_preserved="failure")
    finally:
        z.close()
        path.unlink()
    RESULT["policy_sha256"] = sha(POLICY_PATH.read_bytes())
    RESULT["pins_sha256"] = sha(PINS_PATH.read_bytes())
    for pin in pins["current"]:
        evidence = inspect_current(pin, policy)
        for rule in ("reader.state", "library.empty"):
            RESULT["new_rule_results"].append({
                "platform": pin["platform"], "rule_id": rule, "rule_version": policy["version"],
                "result": "pass_under_user_approved_new_rule", "evidence": evidence,
                "historical_reference": dict(old_refs[pin["platform"]],
                    old_contract_locator=policy["legacy_locators"][rule]),
                "supersession_verified": False})
    RESULT["historical_references"] = list(old_refs.values())
    RESULT["new_rule_pass_count"] = len(RESULT["new_rule_results"])
    RESULT["stop_reason"] = "six new-rule observations verified; old findings and full F09 not adjudicated"
    exit_code = 0
except Exception as exc:
    RESULT["stop_reason"] = type(exc).__name__+": "+str(exc)
finally:
    signal.alarm(0)
    RESULT["totals"] = TOTAL
    RESULT["exit_code"] = exit_code
    (OUT/"report.json").write_text(json.dumps(RESULT, ensure_ascii=False, indent=2))
    print("F09_PRODUCTION_ADJUDICATION_BEGIN")
    print(json.dumps(RESULT, ensure_ascii=False, indent=2))
    print("F09_PRODUCTION_ADJUDICATION_END")
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
        f.write("# F09 independent production-rule adjudication\n\n~~~json\n"+
                json.dumps(RESULT, ensure_ascii=False, indent=2)+"\n~~~\n")
sys.exit(exit_code)
