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
AID, RID, SIZE = 13106576006, 41363868404, 22424085
DIGEST = "4f8509453079401841106161d91d9105ce7f87801be70fceb4212c86e1aca74f"
REPO = "repos/NoGod3524/EXReader/"
OUT = Path("build/f09-g16-macos-evidence")
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
    if record["exit"]:
        snippets = [error_excerpt(OUT/(name+suffix)) for suffix in (".log", ".stderr")]
        REPORT.setdefault("error_excerpts", []).extend(snippets)
        print("F09_DIAGNOSTIC_ERROR " + json.dumps({"step": name, "exit": record["exit"],
              "excerpts": snippets}, ensure_ascii=True))
    return record["exit"]

def error_excerpt(path):
    # Only logs created by this runner; never inspect process environment.
    size = path.stat().st_size
    with path.open("rb") as stream:
        stream.seek(max(0, size-4096))
        raw = stream.read(4096)
    value = raw.decode("utf-8", errors="replace")
    value = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", value)
    value = "".join(c for c in value if c in "\n\t" or (ord(c) >= 32 and not 127 <= ord(c) <= 159))
    value = re.sub(r"(?i)(authorization\s*[:=]\s*)(?:bearer\s+|basic\s+)?\S+", r"\1[REDACTED]", value)
    value = re.sub(r"(?i)((?:password|access_token|client_secret|cookie|credentials)\s*[:=]\s*)\S+", r"\1[REDACTED]", value)
    value = re.sub(r"\b(?:gh[pousr]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+)\b", "[REDACTED]", value)
    value = re.sub(r"https?://[^\s<>\"']+", "[URL REDACTED]", value)
    return {"path": path.name, "bytes": size, "sha256": sha(path),
            "redacted_tail": "\n".join(value.splitlines()[-40:]),
            "view": "redacted final at most 4096 input bytes / 40 lines"}

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
        meta.get("name") != "f09-apple-sdk-macos-41363868404-1" or
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
    sdk, products = stage/"macos", stage/"macos-products"
    if not (sdk/"lib/libexreader.dylib").is_file() or not (products/"lib").is_dir():
        raise RuntimeError("retained SDK/product prefix layout mismatch; no fallback")
    REPORT["sdk_receipt"] = {"id": AID, "bytes": count, "unpacked_bytes": expanded,
        "members": len(inventory), "source": SOURCE, "run": RID, "attempt": 1,
        "libexreader_sha256": sha(sdk/"lib/libexreader.dylib")}
    (OUT/"sdk-members.json").write_text(json.dumps(inventory, indent=2))
    return sdk, products

def program_identity(bundle):
    bundle = Path(bundle)
    info_path = bundle/"Contents/Info.plist"
    for item in [bundle, info_path]:
        current = item
        while current != current.parent:
            if current.is_symlink():
                raise RuntimeError("symlink identity path")
            current = current.parent
    if not info_path.is_file() or info_path.stat().st_size > 1024*1024:
        raise RuntimeError("invalid host plist")
    info = plistlib.loads(info_path.read_bytes())
    name = info.get("CFBundleExecutable")
    if not isinstance(name, str) or Path(name).name != name:
        raise RuntimeError("unsafe executable name")
    executable = bundle/"Contents/MacOS"/name
    current = executable
    while current != current.parent:
        if current.is_symlink():
            raise RuntimeError("symlink executable identity path")
        current = current.parent
    if not executable.is_file() or executable.is_symlink() or executable.stat().st_size > 64*1024*1024:
        raise RuntimeError("invalid executable")
    return {"bundle": str(bundle), "bundle_id": info["CFBundleIdentifier"],
            "executable": name, "executable_path": str(executable),
            "executable_sha256": sha(executable), "info_plist_sha256": sha(info_path),
            "embedded_source": info.get("EXRSourceSHA")}

exit_code = 1
try:
    if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ["GITHUB_RUN_ATTEMPT"] != "1":
        raise RuntimeError("Actions attempt 1 only")
    base = "ee627f12ef41e1c2a9c7d62fcb1cd583fcdc3126"
    changed = subprocess.check_output(["git", "diff", "--name-only", base, "HEAD"], text=True).splitlines()
    expected = ['.github/workflows/f09-g16-macos-evidence-20261102.yml', 'docs/reader-total-progress/F09_G16_MACOS_EVIDENCE_20261102.md', 'tests/f09_audit/G16MacProductionEvidenceUITests.swift', 'tests/f09_audit/g16_mac_evidence_overlay.rb', 'tools/f09_review/collect_macos_g16_evidence.py']
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
    require(["ruby", "tests/f09_audit/g16_mac_evidence_overlay.rb", str(project),
             "tests/f09_audit/G16MacProductionEvidenceUITests.swift"], "evidence-overlay", 120)
    destination = "platform=macOS"
    REPORT["device"] = {"platform": "macOS host", "no_simulator": True}
    derived = ROOT/"build/f09-focus-derived"
    common = ["-project", str(project), "-scheme", "EXReaderHost-macOS", "-destination", destination,
              "-derivedDataPath", str(derived), "EXR_SDK_DIR="+str(sdk), "CODE_SIGNING_ALLOWED=YES"]
    settings_path = require(["xcodebuild", "-showBuildSettings", "-json"]+common,
                            "actual-build-settings", 180, separate_error=True)
    settings = json.loads(settings_path.read_text())
    app_rows = [x for x in settings if x.get("target") == "EXReaderHost-macOS"]
    if len(app_rows) != 1:
        raise RuntimeError("application build settings target not uniquely identified")
    build_settings = app_rows[0]["buildSettings"]
    flags = str(build_settings.get("SWIFT_ACTIVE_COMPILATION_CONDITIONS", ""))+" "+str(build_settings.get("OTHER_SWIFT_FLAGS", ""))
    if any(x in flags for x in FORBIDDEN) or re.search(r"EXR_[A-Z0-9_]*REVIEW", flags):
        raise RuntimeError("review compilation conditions remain in actual application settings")
    REPORT["application_build_settings"] = {k: build_settings.get(k) for k in
        ("SWIFT_ACTIVE_COMPILATION_CONDITIONS", "OTHER_SWIFT_FLAGS", "PRODUCT_BUNDLE_IDENTIFIER", "SDKROOT", "CONFIGURATION")}
    require(["xcodebuild", "build-for-testing"]+common, "build-for-testing", 600)
    bundle = derived/"Build/Products/Debug/EXReaderHost.app"
    REPORT["built_program"] = program_identity(bundle)
    built = REPORT["built_program"]
    if built["embedded_source"] != os.environ["GITHUB_SHA"]:
        raise RuntimeError("built embedded source mismatch")
    identity_out = OUT/"program-identity"
    identity_out.mkdir()
    identity_files = []
    for source, dest, limit in ((bundle/"Contents/MacOS"/built["executable"], identity_out/"EXReaderHost", 64*1024*1024),
                                (bundle/"Contents/Info.plist", identity_out/"Info.plist", 1024*1024)):
        if not source.is_file() or source.is_symlink() or source.stat().st_size > limit:
            raise RuntimeError("unexpected identity file size/type")
        shutil.copyfile(source, dest)
        identity_files.append({"path": str(dest.relative_to(OUT)), "bytes": dest.stat().st_size,
                               "sha256": sha(dest)})
    REPORT["retained_built_identity_files"] = identity_files
    REPORT["build_settings_file_sha256"] = sha(settings_path)
    # Inspect the generated test configuration without changing the known
    # project/scheme invocation. Unsupported formats or ambiguous targets stop.
    product_root = derived/"Build/Products"
    def confined(path):
        path = Path(path)
        try:
            rel = path.relative_to(product_root)
        except ValueError:
            raise RuntimeError("test configuration path escapes products root")
        if ".." in rel.parts:
            raise RuntimeError("parent traversal in test configuration path")
        current = product_root
        if current.is_symlink():
            raise RuntimeError("symlink products root")
        for part in rel.parts:
            current = current/part
            if current.is_symlink():
                raise RuntimeError("symlink test configuration path")
        if not path.exists():
            raise RuntimeError("test configuration path missing: "+str(rel))
        return path
    configs = list(product_root.glob("*.xctestrun"))
    if len(configs) != 1:
        raise RuntimeError("expected one generated xctestrun configuration")
    config_path = confined(configs[0])
    if not config_path.is_file() or config_path.stat().st_size > 4*1024*1024:
        raise RuntimeError("invalid xctestrun metadata size/type")
    config = plistlib.loads(config_path.read_bytes())
    if not isinstance(config, dict):
        raise RuntimeError("xctestrun root is not a dictionary")
    REPORT["configuration_probe"] = {
        "path": str(config_path), "bytes": config_path.stat().st_size,
        "sha256": sha(config_path),
        "top_level_keys": [str(k)[:120] for k in list(config)[:40]],
        "keys_truncated": len(config) > 40
    }
    metadata = config.get("__xctestrun_metadata__", {})
    if not isinstance(metadata, dict):
        raise RuntimeError("malformed xctestrun metadata")
    version = metadata.get("FormatVersion", 1)
    REPORT["configuration_probe"]["format_version_repr"] = str(version)[:80]
    if type(version) is not int:
        raise RuntimeError("non-integer xctestrun FormatVersion")
    if version == 2:
        configurations = config.get("TestConfigurations")
        if not isinstance(configurations, list) or len(configurations) != 1:
            raise RuntimeError("expected one xctestrun test configuration")
        if not isinstance(configurations[0], dict):
            raise RuntimeError("malformed xctestrun test configuration")
        targets = configurations[0].get("TestTargets")
        if not isinstance(targets, list):
            raise RuntimeError("missing xctestrun test targets")
        matches = [x for x in targets if isinstance(x, dict) and
                   x.get("BlueprintName") == "EXReaderHostUITests-macOS"]
    elif version == 1:
        item = config.get("EXReaderHostUITests-macOS")
        matches = [item] if isinstance(item, dict) else []
    else:
        raise RuntimeError("unsupported xctestrun FormatVersion")
    if len(matches) != 1:
        raise RuntimeError("UI target not uniquely mapped in xctestrun")
    target_config = matches[0]
    permitted = ("BlueprintName", "TestHostPath", "TestBundlePath", "UITargetAppPath")
    REPORT["configuration_probe"]["raw_fields"] = {
        k: target_config.get(k)[:2048] if isinstance(target_config.get(k), str)
           else "<missing-or-non-string>" for k in permitted}
    if any(isinstance(target_config.get(k), str) and len(target_config[k]) > 2048 for k in permitted):
        raise RuntimeError("oversized xctestrun permitted field")
    def mapped(key, host=None):
        value = target_config.get(key)
        if not isinstance(value, str) or not value:
            raise RuntimeError("missing configuration field: "+key)
        value = value.replace("__TESTROOT__", str(product_root))
        if host is not None:
            value = value.replace("__TESTHOST__", str(host))
        if "__" in value:
            raise RuntimeError("unknown configuration placeholder: "+key)
        candidate = Path(value)
        if not candidate.is_absolute():
            raise RuntimeError("unresolved relative configuration path: "+key)
        return confined(candidate)
    runner_location = mapped("TestHostPath")
    target_app = mapped("UITargetAppPath")
    # macOS configurations may point at a runner bundle or its executable.
    parents = [runner_location] + list(runner_location.parents)
    runner_candidates = [p for p in parents if p.suffix == ".app" and p.is_relative_to(product_root)]
    if len(runner_candidates) != 1:
        raise RuntimeError("runner app cannot be uniquely identified inside Products")
    runner_bundle = confined(runner_candidates[0])
    runner_built = program_identity(runner_bundle)
    if runner_location not in (runner_bundle, Path(runner_built["executable_path"])):
        raise RuntimeError("runner TestHostPath not bundle or its declared executable")
    if runner_built["bundle_id"] != "org.exreader.host.uitests.xctrunner":
        raise RuntimeError("unexpected runner identifier")
    test_bundle = mapped("TestBundlePath", runner_bundle)
    allowed_test_paths = {
        runner_bundle/"Contents/PlugIns/EXReaderHostUITests-macOS.xctest",
        product_root/"Debug/EXReaderHostUITests-macOS.xctest",
    }
    if target_app != bundle or test_bundle not in allowed_test_paths:
        raise RuntimeError("configuration paths do not match exact macOS products")
    test_plist = confined(test_bundle/"Contents/Info.plist")
    test_info = plistlib.loads(test_plist.read_bytes())
    test_exe = test_info.get("CFBundleExecutable")
    if test_info.get("CFBundleIdentifier") != "org.exreader.host.uitests" or not isinstance(test_exe, str) or Path(test_exe).name != test_exe:
        raise RuntimeError("unexpected test bundle identity")
    test_exe_path = confined(test_bundle/"Contents/MacOS"/test_exe)
    REPORT["runner_configuration"] = {
        "format_version": version, "path": str(config_path), "sha256": sha(config_path),
        "runner": runner_built, "test_bundle": str(test_bundle),
        "test_executable_sha256": sha(test_exe_path), "target_app": str(target_app),
        "raw_fields": {k: target_config.get(k) for k in
                      ("BlueprintName", "TestHostPath", "TestBundlePath", "UITargetAppPath")}
    }
    shutil.copyfile(config_path, OUT/"generated.xctestrun")
    REPORT["size_scope"] = "default macOS UI, no content-size override"
    result = OUT/"normal-1.xcresult"
    args = ["xcodebuild", "test-without-building"]+common+[
        "-resultBundlePath", str(result), "-parallel-testing-enabled", "NO",
        "-test-timeouts-enabled", "YES", "-default-test-execution-time-allowance", "360",
        "-maximum-test-execution-time-allowance", "420",
        "-only-testing:EXReaderHostUITests-macOS/G16MacProductionEvidenceUITests/testProductionG16Evidence"]
    rc = execute(args, "normal-1", 480)
    text = (OUT/"normal-1.log").read_text(errors="replace")
    completed = re.findall(r"Test Case .*testProductionG16Evidence.* (passed|failed) \(", text)
    REPORT["tests"] = [{"case": "G16MacProductionEvidenceUITests/testProductionG16Evidence",
                        "exit": rc, "observed_case_completions": completed}]
    REPORT["raw_test_log_sha256"] = sha(OUT/"normal-1.log")
    if result.exists():
        REPORT["attachment_export_exit"] = execute(["xcrun", "xcresulttool", "export", "attachments",
            "--path", str(result), "--output-path", str(OUT/"normal-1-attachments")], "normal-1-export", 90)
    if program_identity(bundle) != built:
        raise RuntimeError("built program identity changed")
    records = []
    for line in text.splitlines():
        marker = "F09_G16_MAC_EXACT_QUERY "
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
    live = [r.get("running_host") for r in records]
    if any(not isinstance(x, dict) for x in live):
        raise RuntimeError("missing running-host observations")
    for x in live:
        if (type(x.get("pid")) is not int or x["pid"] <= 0 or
            type(x.get("launch_date")) not in (int, float) or
            x.get("alive_at_capture") is not True or x.get("is_terminated") is not False):
            raise RuntimeError("invalid process liveness observation")
        if x["launch_date"] > min(r["captured_at"] for r in records):
            raise RuntimeError("process launch after observation")
        expected_paths = {"bundle_path": bundle, "executable_path": bundle/"Contents/MacOS"/built["executable"],
                          "info_plist_path": bundle/"Contents/Info.plist"}
        for key, expected in expected_paths.items():
            value = x.get(key)
            if not isinstance(value, str) or confined(Path(value)) != expected:
                raise RuntimeError("observed running-host path differs from test target: "+key)
        for key in ("bundle_id", "executable_sha256", "info_plist_sha256", "embedded_source"):
            if x.get(key) != built[key]:
                raise RuntimeError("running-host identity mismatch: "+key)
    for key in ("pid", "launch_date", "bundle_path", "executable_path", "executable_sha256", "info_plist_sha256"):
        if live[0][key] != live[1][key]:
            raise RuntimeError("host process changed across states: "+key)
    after = program_identity(bundle)
    if after != built:
        raise RuntimeError("host files changed after case")
    REPORT["running_host_observations"] = live
    REPORT["post_case_file_identity"] = after
    REPORT["liveness_scope"] = "during-case test-process observations; runner post-case validates files, not process survival"
    REPORT["receipt"] = {
        "source": os.environ["GITHUB_SHA"], "product_base": SOURCE,
        "run": os.environ["GITHUB_RUN_ID"], "attempt": os.environ["GITHUB_RUN_ATTEMPT"],
        "session": empty["session"], "build_settings_sha256": sha(settings_path),
        "raw_log_sha256": sha(OUT/"normal-1.log"),
        "raw_query_records_sha256": hashlib.sha256(json.dumps(records, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
        "built_program_sha256": built["executable_sha256"],
        "observed_running_program_sha256": live[0]["executable_sha256"],
        "post_case_file_sha256": after["executable_sha256"],
        "evidence_scope": "one macOS production case; two current-app XCUI exact-ID queries",
        "acceptance_eligible": False
    }
    REPORT["stop_reason"] = "single default-size macOS evidence collection completed; not formal G16 acceptance"
    exit_code = 0
except Exception as exc:
    REPORT["stop_reason"] = type(exc).__name__+": "+str(exc)
    REPORT["diagnostic_error"] = True
finally:
    signal.alarm(0)
    REPORT["exit_code"] = exit_code
    save()
    brief = {k: REPORT.get(k) for k in ("acceptance_eligible", "diagnostic_source",
        "product_source_base", "sdk_receipt", "device", "application_build_settings", "built_program",
        "configuration_probe", "runner_configuration", "error_excerpts", "retained_built_identity_files", "tests", "exact_query_records", "receipt", "running_host_observations", "post_case_file_identity", "liveness_scope", "stop_reason", "exit_code")}
    print("F09_G16_MACOS_EVIDENCE_RESULT_BEGIN")
    print(json.dumps(brief, ensure_ascii=False, indent=2))
    print("F09_G16_MACOS_EVIDENCE_RESULT_END")
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
        f.write("# F09 single-macOS evidence\n\nAcceptance eligible: **false**. Original failures preserved.\n\n")
        f.write("~~~json\n"+json.dumps(brief, ensure_ascii=False, indent=2)+"\n~~~\n")
sys.exit(exit_code)
