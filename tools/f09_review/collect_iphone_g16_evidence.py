import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import plistlib
import re
import signal
import shutil
import stat
import subprocess
import sys
import time
import zipfile

SOURCE = "e9e20eada714bc6b8045d3e943ac46ff26844559"
AID, RID, SIZE = 13106222783, 41363868404, 22428356
DIGEST = "2fecacc093e5e74fb8d81b074f55982ab626f6013c8048ae0ab86949d171a3b6"
REPO = "repos/NoGod3524/EXReader/"
OUT = Path("build/f09-g16-iphone-evidence")
OUT.mkdir(parents=True, exist_ok=True)
OUT = OUT.resolve()
ROOT = Path.cwd()
FORBIDDEN = ("EXR_APPLE_HOST_REVIEW", "EXR_APPLE_IMPORT_REVIEW", "EXR_APPLE_READING_REVIEW")
REPORT = {"schema": 1, "acceptance_eligible": False, "product_source_base": SOURCE,
          "diagnostic_source": os.environ["GITHUB_SHA"], "run": os.environ["GITHUB_RUN_ID"],
          "attempt": os.environ["GITHUB_RUN_ATTEMPT"], "sdk_artifact": AID,
          "sdk_archive_sha256": DIGEST, "commands": [], "tests": [],
          "test_scope": "one new exact-ID G16 production evidence case; current-app XCUI scope only",
          "original_a2_failure_preserved": True, "stop_reason": None}
DEADLINE = time.monotonic() + 2220
UDID = None

def alarm(_s, _f):
    raise TimeoutError("37-minute orchestration ceiling; leave time to upload")
signal.signal(signal.SIGALRM, alarm)
signal.signal(signal.SIGTERM, alarm)
signal.alarm(2220)

def remaining(seconds):
    n = min(seconds, int(DEADLINE-time.monotonic()))
    if n <= 0:
        raise TimeoutError("orchestration deadline reached")
    return n

def execute(args, name, seconds=120, separate_error=False):
    log = OUT/(name+".log")
    error = OUT/(name+".stderr")
    record = {"name": name, "command": args, "log": log.name}
    REPORT["commands"].append(record)
    started = time.monotonic()
    with log.open("wb") as out, error.open("wb") as err:
        try:
            proc = subprocess.run(args, stdout=out,
                stderr=err if separate_error else subprocess.STDOUT, timeout=remaining(seconds))
            record["exit"] = proc.returncode
        except subprocess.TimeoutExpired:
            record["exit"] = 124
    record["seconds"] = round(time.monotonic()-started, 2)
    return record["exit"]

def require(args, name, seconds=120, separate_error=False):
    rc = execute(args, name, seconds, separate_error)
    if rc:
        raise RuntimeError(name+" failed with exit "+str(rc))
    return OUT/(name+".log")

def api(path):
    raw = subprocess.check_output(["gh", "api", REPO+path], timeout=remaining(60))
    if len(raw) > 4*1024*1024:
        raise RuntimeError("oversized API metadata")
    return json.loads(raw)

def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()

def save():
    (OUT/"report.json").write_text(json.dumps(REPORT, ensure_ascii=False, indent=2))

def stage_sdk():
    meta = api("actions/artifacts/"+str(AID))
    if (meta.get("id") != AID or meta.get("size_in_bytes") != SIZE or
        meta.get("digest") != "sha256:"+DIGEST or meta.get("expired") is not False or
        meta.get("name") != "f09-apple-sdk-iphonesimulator-41363868404-1" or
        meta.get("workflow_run", {}).get("id") != RID or
        meta.get("workflow_run", {}).get("head_sha") != SOURCE):
        raise RuntimeError("fixed SDK artifact identity mismatch")
    original = api("actions/runs/"+str(RID)+"/attempts/1")
    if (original.get("id") != RID or original.get("head_sha") != SOURCE or
        original.get("run_attempt") != 1 or original.get("status") != "completed"):
        raise RuntimeError("SDK producer attempt identity mismatch")
    archive = ROOT/"build/f09-retained-sdk.zip"
    process = subprocess.Popen(["gh", "api", REPO+"actions/artifacts/"+str(AID)+"/zip"],
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    count = 0
    try:
        with archive.open("wb") as f:
            while True:
                block = process.stdout.read(65536)
                if not block:
                    break
                count += len(block)
                if count > SIZE:
                    raise RuntimeError("SDK download exceeds fixed size")
                f.write(block)
        if process.wait(timeout=remaining(60)) or count != SIZE or sha(archive) != DIGEST:
            raise RuntimeError("SDK archive size/hash verification failed")
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        process.stdout.close()
    stage = ROOT/"build/f09-retained-sdk"
    stage.mkdir(exist_ok=True)
    inventory, names, expanded = [], set(), 0
    with zipfile.ZipFile(archive) as z:
        items = z.infolist()
        if len(items) > 10000:
            raise RuntimeError("SDK archive member budget exceeded")
        for item in items:
            p = PurePosixPath(item.filename)
            normalized = p.as_posix()
            kind = stat.S_IFMT(item.external_attr >> 16)
            if (item.filename.rstrip("/") != normalized or normalized in names or
                p.is_absolute() or ".." in p.parts or "\\" in item.filename or ":" in item.filename or
                "\x00" in item.orig_filename or item.flag_bits & 1 or
                kind not in (0, stat.S_IFREG, stat.S_IFDIR)):
                raise RuntimeError("unsafe SDK member")
            names.add(normalized)
            expanded += item.file_size
            if item.file_size > 256*1024*1024 or expanded > 512*1024*1024:
                raise RuntimeError("SDK unpack budget exceeded")
            target = stage.joinpath(*p.parts)
            if item.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with z.open(item) as src, target.open("wb") as dst:
                    written = 0
                    while True:
                        block = src.read(65536)
                        if not block:
                            break
                        written += len(block)
                        if written > item.file_size:
                            raise RuntimeError("SDK member length mismatch")
                        dst.write(block)
                if written != item.file_size:
                    raise RuntimeError("short SDK member")
            inventory.append({"path": normalized, "bytes": item.file_size})
    archive.unlink()
    sdk, products = stage/"iphonesimulator", stage/"iphonesimulator-products"
    if not (sdk/"lib/libexreader.dylib").is_file() or not (products/"lib").is_dir():
        raise RuntimeError("retained SDK/product prefix layout mismatch; no fallback")
    REPORT["sdk_receipt"] = {"id": AID, "bytes": count, "unpacked_bytes": expanded,
        "members": len(inventory), "source": SOURCE, "run": RID, "attempt": 1,
        "libexreader_sha256": sha(sdk/"lib/libexreader.dylib")}
    (OUT/"sdk-members.json").write_text(json.dumps(inventory, indent=2))
    return sdk, products

def program_identity(bundle):
    info_path = bundle/"Info.plist"
    info = plistlib.loads(info_path.read_bytes())
    executable = bundle/info["CFBundleExecutable"]
    return {"bundle": str(bundle), "bundle_id": info["CFBundleIdentifier"],
            "executable": info["CFBundleExecutable"], "executable_sha256": sha(executable),
            "info_plist_sha256": sha(info_path), "embedded_source": info.get("EXRSourceSHA")}

exit_code = 1
try:
    if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ["GITHUB_RUN_ATTEMPT"] != "1":
        raise RuntimeError("Actions attempt 1 only")
    base = "5511a29328c214d63bfaa96e5a8d7552699f77a3"
    changed = subprocess.check_output(["git", "diff", "--name-only", base, "HEAD"], text=True).splitlines()
    expected = ['.github/workflows/f09-g16-iphone-evidence-20261102.yml', 'docs/reader-total-progress/F09_G16_IPHONE_EVIDENCE_20261102.md', 'tests/f09_audit/G16ProductionEvidenceUITests.swift', 'tests/f09_audit/g16_evidence_overlay.rb', 'tools/f09_review/collect_iphone_g16_evidence.py']
    if sorted(changed) != expected:
        raise RuntimeError("source delta is not the five approved new paths")
    added = subprocess.check_output(["git", "diff", "--diff-filter=A", "--name-only", base, "HEAD"], text=True).splitlines()
    if sorted(added) != expected:
        raise RuntimeError("all five diagnostic paths must be new")
    REPORT["changed_paths"] = changed
    sdk, products = stage_sdk()
    require(["python3", "tests/apple_host/prepare_fixtures.py", "--resources", "build/f09-focus-resources"],
            "fixtures", 120)
    require(["ruby", "tests/reader_team24_apple/make_project.rb", "build/f09-focus-project",
             "build/f09-focus-resources", "tests/f09_audit/apple", "base"], "generate", 120)
    project = ROOT/"build/f09-focus-project/EXReaderHost.xcodeproj"
    require(["ruby", "tests/f09_audit/apple_product_overlay.rb", str(project), str(products), "--production"],
            "production-overlay", 120)
    require(["ruby", "tests/f09_audit/g16_evidence_overlay.rb", str(project),
             "tests/f09_audit/G16ProductionEvidenceUITests.swift"], "evidence-overlay", 120)
    devices = json.loads(subprocess.check_output(
        ["xcrun", "simctl", "list", "devices", "available", "--json"], timeout=remaining(60)))
    choices = [(runtime, d["name"], d["udid"]) for runtime, ds in devices["devices"].items()
               for d in ds if d.get("isAvailable") and d["name"] == "iPhone SE (3rd generation)"
               and ".iOS-" in runtime]
    if not choices:
        raise RuntimeError("required iPhone SE (3rd generation) unavailable; no device substitution")
    runtime, device_name, UDID = max(choices)
    REPORT["device"] = {"name": device_name, "udid": UDID, "runtime": runtime}
    execute(["xcrun", "simctl", "shutdown", UDID], "shutdown-initial", 60)
    require(["xcrun", "simctl", "erase", UDID], "erase-initial", 90)
    require(["xcrun", "simctl", "boot", UDID], "boot", 120)
    require(["xcrun", "simctl", "bootstatus", UDID, "-b"], "boot-ready", 180)
    destination = "platform=iOS Simulator,id="+UDID
    derived = ROOT/"build/f09-focus-derived"
    common = ["-project", str(project), "-scheme", "EXReaderHost-iOS", "-destination", destination,
              "-derivedDataPath", str(derived), "EXR_SDK_DIR="+str(sdk), "CODE_SIGNING_ALLOWED=NO"]
    settings_path = require(["xcodebuild", "-showBuildSettings", "-json"]+common,
                            "actual-build-settings", 180, separate_error=True)
    settings = json.loads(settings_path.read_text())
    app_rows = [x for x in settings if x.get("target") == "EXReaderHost-iOS"]
    if len(app_rows) != 1:
        raise RuntimeError("application build settings target not uniquely identified")
    build_settings = app_rows[0]["buildSettings"]
    flags = str(build_settings.get("SWIFT_ACTIVE_COMPILATION_CONDITIONS", ""))+" "+str(build_settings.get("OTHER_SWIFT_FLAGS", ""))
    if any(x in flags for x in FORBIDDEN) or re.search(r"EXR_[A-Z0-9_]*REVIEW", flags):
        raise RuntimeError("review compilation conditions remain in actual application settings")
    REPORT["application_build_settings"] = {k: build_settings.get(k) for k in
        ("SWIFT_ACTIVE_COMPILATION_CONDITIONS", "OTHER_SWIFT_FLAGS", "PRODUCT_BUNDLE_IDENTIFIER", "SDKROOT", "CONFIGURATION")}
    require(["xcodebuild", "build-for-testing"]+common, "build-for-testing", 600)
    bundle = derived/"Build/Products/Debug-iphonesimulator/EXReaderHost.app"
    REPORT["built_program"] = program_identity(bundle)
    built = REPORT["built_program"]
    if built["embedded_source"] != os.environ["GITHUB_SHA"]:
        raise RuntimeError("built embedded source mismatch")
    identity_out = OUT/"program-identity"
    identity_out.mkdir()
    identity_files = []
    for source, dest, limit in ((bundle/built["executable"], identity_out/"EXReaderHost", 64*1024*1024),
                                (bundle/"Info.plist", identity_out/"Info.plist", 1024*1024)):
        if not source.is_file() or source.is_symlink() or source.stat().st_size > limit:
            raise RuntimeError("unexpected identity file size/type")
        shutil.copyfile(source, dest)
        identity_files.append({"path": str(dest.relative_to(OUT)), "bytes": dest.stat().st_size,
                               "sha256": sha(dest)})
    REPORT["retained_built_identity_files"] = identity_files
    REPORT["build_settings_file_sha256"] = sha(settings_path)
    require(["xcrun", "simctl", "install", UDID, str(bundle)], "install-before-case", 120)
    def installed_identity():
        path = require(["xcrun", "simctl", "get_app_container", UDID,
                        built["bundle_id"], "app"], "installed-container-"+str(len(REPORT["commands"])), 30)
        identity = program_identity(Path(path.read_text().strip()))
        for key in ("bundle_id", "executable_sha256", "info_plist_sha256", "embedded_source"):
            if identity[key] != built[key]:
                raise RuntimeError("installed program differs from built: "+key)
        return identity
    REPORT["installed_before"] = installed_identity()
    require(["xcrun", "simctl", "ui", UDID, "content_size", "medium"], "normal-set-size", 60)
    REPORT["requested_content_size"] = "medium"
    REPORT["observed_content_size_raw"] = require(
        ["xcrun", "simctl", "ui", UDID, "content_size"], "normal-actual-size", 60).read_text().strip()
    if REPORT["observed_content_size_raw"] != "medium":
        raise RuntimeError("normal content size not verified")
    result = OUT/"normal-1.xcresult"
    args = ["xcodebuild", "test-without-building"]+common+[
        "-resultBundlePath", str(result), "-parallel-testing-enabled", "NO",
        "-test-timeouts-enabled", "YES", "-default-test-execution-time-allowance", "360",
        "-maximum-test-execution-time-allowance", "420",
        "-only-testing:EXReaderHostUITests-iOS/G16ProductionEvidenceUITests/testProductionG16Evidence"]
    rc = execute(args, "normal-1", 480)
    text = (OUT/"normal-1.log").read_text(errors="replace")
    completed = re.findall(r"Test Case .*testProductionG16Evidence.* (passed|failed) \(", text)
    REPORT["tests"] = [{"case": "G16ProductionEvidenceUITests/testProductionG16Evidence",
                        "exit": rc, "observed_case_completions": completed}]
    REPORT["raw_test_log_sha256"] = sha(OUT/"normal-1.log")
    if result.exists():
        REPORT["attachment_export_exit"] = execute(["xcrun", "xcresulttool", "export", "attachments",
            "--path", str(result), "--output-path", str(OUT/"normal-1-attachments")], "normal-1-export", 90)
    REPORT["installed_after"] = installed_identity()
    if program_identity(bundle) != built:
        raise RuntimeError("built program identity changed")
    records = []
    for line in text.splitlines():
        marker = "F09_G16_EXACT_QUERY "
        if marker in line:
            records.append(json.loads(line.split(marker, 1)[1]))
    REPORT["exact_query_records"] = records
    if rc or completed != ["passed"] or REPORT.get("attachment_export_exit") != 0:
        raise RuntimeError("single collector case did not complete successfully")
    if len(records) != 2 or [x.get("state") for x in records] != ["library.empty", "reader.epub"]:
        raise RuntimeError("expected exactly two ordered raw query records")
    if not records[0].get("session") or records[0]["session"] != records[1].get("session"):
        raise RuntimeError("collector session identity mismatch")
    for record in records:
        if (record.get("schema") != 1 or record.get("case") != "testProductionG16Evidence"
            or record.get("query_completed") is not True or record.get("nodes_truncated") is not False
            or record.get("anchor_exists") is not True or record.get("app_foreground") is not True):
            raise RuntimeError("incomplete exact query evidence")
    empty, reader = records
    if empty.get("anchor_id") != "library.organization" or reader.get("anchor_id") != "reader.page":
        raise RuntimeError("unexpected state anchors")
    if empty["target_id"] != "library.empty" or empty["query_count"] != 1 or len(empty["nodes"]) != 1:
        raise RuntimeError("empty shelf query not unique")
    node = empty["nodes"][0]
    label = node.get("label")
    name = label if isinstance(label, str) and label.strip() else node.get("value", "")
    if node.get("id") != "library.empty" or node.get("is_static_text") is not True or name.strip() != "\u4e66\u67b6\u4e3a\u7a7a\uff0c\u6253\u5f00\u6587\u4ef6\u5373\u53ef\u5bfc\u5165\u3002":
        raise RuntimeError("empty shelf role/name mismatch")
    if reader["target_id"] != "reader.state" or reader["query_count"] != 0 or reader["nodes"] != []:
        raise RuntimeError("reader.state observed or query inconsistent")
    REPORT["receipt"] = {
        "source": os.environ["GITHUB_SHA"], "product_base": SOURCE,
        "run": os.environ["GITHUB_RUN_ID"], "attempt": os.environ["GITHUB_RUN_ATTEMPT"],
        "session": empty["session"], "build_settings_sha256": sha(settings_path),
        "raw_log_sha256": sha(OUT/"normal-1.log"),
        "raw_query_records_sha256": hashlib.sha256(json.dumps(records, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
        "built_program_sha256": built["executable_sha256"],
        "installed_before_sha256": REPORT["installed_before"]["executable_sha256"],
        "installed_after_sha256": REPORT["installed_after"]["executable_sha256"],
        "evidence_scope": "one iPhone production case; two current-app XCUI exact-ID queries",
        "acceptance_eligible": False
    }
    REPORT["stop_reason"] = "single normal-size iPhone evidence collection completed; not formal G16 acceptance"
    exit_code = 0
except Exception as exc:
    REPORT["stop_reason"] = type(exc).__name__+": "+str(exc)
    REPORT["diagnostic_error"] = True
finally:
    signal.alarm(0)
    if UDID:
        try:
            subprocess.run(["xcrun", "simctl", "ui", UDID, "content_size", "medium"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
        except Exception:
            REPORT["content_size_restore"] = "unverified"
    REPORT["exit_code"] = exit_code
    save()
    brief = {k: REPORT.get(k) for k in ("acceptance_eligible", "diagnostic_source",
        "product_source_base", "sdk_receipt", "device", "application_build_settings", "built_program",
        "retained_built_identity_files", "tests", "exact_query_records", "receipt", "installed_before", "installed_after", "stop_reason", "exit_code")}
    print("F09_G16_IPHONE_EVIDENCE_RESULT_BEGIN")
    print(json.dumps(brief, ensure_ascii=False, indent=2))
    print("F09_G16_IPHONE_EVIDENCE_RESULT_END")
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
        f.write("# F09 single-iPhone evidence\n\nAcceptance eligible: **false**. Original failures preserved.\n\n")
        f.write("~~~json\n"+json.dumps(brief, ensure_ascii=False, indent=2)+"\n~~~\n")
sys.exit(exit_code)
