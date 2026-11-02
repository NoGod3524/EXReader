#!/usr/bin/env python3
"""F03 SDK 3.42 production admission and explicit original-driver adapter. Actions only."""
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import shlex
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
BASE = "94fb236a4a2da87dfbaf4f1dd2a47885d615a230"
CANONICAL = "ec11cf862ca3b44483d7e8c4726ae748ab438337"
INTAKE = "48bd5a35d99c3a21a8159288dd08ac8dbb41c677"
SDK = "8357eafa28423a7ab93ba08b823af80f01ad1505"
FIXTURE_SOURCE = "39600d0d3a3a5e4bc2599a92e94e494a542f06f1"
BRANCH = "dot/f03-production-acceptance-v342-20261102"
MARKER = "[F03-PRODUCTION-ACCEPTANCE-V342-20261102]"

def require(value, message):
    if not value:
        raise ValueError(message)

def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()

def blob(source, path):
    return subprocess.check_output(["git", "show", source + ":" + path], cwd=ROOT)

def digest(data):
    return hashlib.sha256(data).hexdigest()

def configuration():
    c = json.loads((HERE / "contract.json").read_text())
    require((c["review_base"], c["canonical_source"], c["product_intake_head"], c["sdk_source"],
             c["sdk_version"], c["fixture_source"], c["branch"]) ==
            (BASE, CANONICAL, INTAKE, SDK, "3.42.0", FIXTURE_SOURCE, BRANCH), "fixed admission identity")
    require(c.get("commit_marker") == MARKER, "fixed authorized commit marker")
    return c

def verify_source():
    c = configuration()
    require(os.environ.get("GITHUB_ACTIONS") == "true", "Actions only")
    require(os.environ.get("GITHUB_REF") == "refs/heads/" + BRANCH, "exclusive acceptance branch")
    require(os.environ.get("GITHUB_RUN_ATTEMPT") == "1", "one authorized run; no retry")
    require(not any(value for key, value in os.environ.items() if key.startswith("ANDROID_CANDIDATE_")),
            "candidate evidence cannot enter production admission")
    require(os.environ.get("ANDROID_OWNERSHIP_HEAD") == CANONICAL, "reviewed ownership boundary")
    require(MARKER in git("log", "-1", "--format=%B"), "authorized acceptance commit marker")
    source = git("rev-parse", "HEAD")
    require(source == os.environ["GITHUB_SHA"], "tested source differs from run")
    require(git("rev-list", "--parents", "-n", "1", source).split() == [source, INTAKE],
            "exact single acceptance commit directly on the fixed intake")
    for parent, child in ((BASE, CANONICAL), (CANONICAL, INTAKE), (INTAKE, source)):
        require(git("merge-base", parent, child) == parent, "source ancestry mismatch")
    for start, end, key in ((BASE, CANONICAL, "canonical_delta"),
                            (CANONICAL, INTAKE, "intake_delta")):
        records = c[key]
        changed = git("diff", "--name-only", start, end).splitlines()
        require(set(changed) == set(records), "exact reviewed delta paths: " + key)
        for path, expected in records.items():
            require(git("rev-parse", end + ":" + path) == expected, "fixed delta blob: " + path)
    require(set(git("diff", "--name-only", INTAKE, source).splitlines()) == set(c["new_paths"]),
            "acceptance commit must add exactly the ten authorized files")
    for path in c["new_paths"]:
        require(git("cat-file", "-t", source + ":" + path) == "blob", "new path must be a file")
        require((ROOT / path).read_bytes() == blob(source, path), "modified acceptance file: " + path)
    require(all(line.startswith("A\t") for line in git("diff", "--name-status", INTAKE, source).splitlines()),
            "acceptance paths must be additions, not old-file modifications")
    require(not git("diff", "--name-only", SDK, source, "--", *c["sdk_frozen_paths"]),
            "SDK and original fixture/workflow freeze")
    for path, expected in c["jni_blobs"].items():
        require(git("rev-parse", source + ":" + path) == expected, "reviewed JNI identity: " + path)
        require(digest((ROOT / path).read_bytes()) == digest(blob(CANONICAL, path)), "dirty JNI: " + path)
    require(not git("diff", "--name-only", "f32bb8aa18ed3de286900f19ce4230fd93435dd0",
                    source, "--", "apps/reader/store/001_catalog.sql"), "original catalog freeze")
    for path in c["intake_delta"]:
        require((ROOT / path).read_bytes() == blob(INTAKE, path), "intake bytes changed: " + path)
    require(not git("diff", "--name-only", "HEAD", "--", *c["immutable_worktree_paths"]),
            "tracked SDK, production, old checks or old tests modified")
    original_contract = json.loads(blob(CANONICAL, "tests/dot_f04_reading_sync_20261031/contract.json"))
    require(set(c["canonical_delta"]) == set(original_contract["canonical"]["union_paths"]),
            "reuse the exact previously reviewed source union")
    for path in c["original_f04_protected_paths"]:
        require(not git("diff", "--name-only", BASE, CANONICAL, "--", path), "old F04 protected source: " + path)
    parser_delta = {
        "examples/android/app/src/main/java/org/exreader/host/ReadingParserPolicy.java": (
            '        if (recorded.equals("exreader-sdk-" + actual)) return true;',
            '        if (actual.equals("3.42.0") && recorded.equals("3.42.0")) return true;'),
        "apps/reader/desktop/windows_records_owner.cpp": (
            ' if(!std::strcmp(recorded,exr_version()))return true;',
            ' if(!std::strcmp(exr_version(),"3.42.0")&&!std::strcmp(recorded,"exreader-sdk-3.42.0"))return true;'),
        "examples/apple/HostReadingRecords.swift": (
            '        if recorded == actual { return true }',
            '        if actual == "3.42.0" && recorded == "exreader-sdk-3.42.0" { return true }')}
    require(set(git("diff", "--name-only", BASE, CANONICAL, "--", "apps", "examples").splitlines()) ==
            set(parser_delta), "only the three reviewed parser changes")
    for path, (anchor, added) in parser_delta.items():
        old = blob(BASE, path)
        require(old.count(anchor.encode()) == 1, "unique parser anchor")
        require(blob(CANONICAL, path) == old.replace(anchor.encode(), (anchor + "\n" + added).encode(), 1),
                "exact reviewed parser delta")
    require(b'#define EXR_VERSION "3.42.0"' in (ROOT / "include/exr/base.h").read_bytes(),
            "actual frozen SDK version, not a Gradle label")
    for relative, original in c["overlay_sources"].items():
        require((ROOT / relative).read_bytes() == blob(FIXTURE_SOURCE, original), "reviewed overlay bytes")
    return {"source_sha": source, "review_base": BASE, "ownership_head": CANONICAL,
            "product_intake_head": INTAKE, "sdk_source": SDK, "sdk_version": "3.42.0",
            "contract_sha256": digest((HERE / "contract.json").read_bytes()),
            "run_id": os.environ["GITHUB_RUN_ID"], "attempt": os.environ["GITHUB_RUN_ATTEMPT"],
            "source_admitted": True, "runtime_accepted": False}

def write_report(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")

def prepare():
    report = verify_source()
    c = configuration()
    temporary = Path(os.environ["RUNNER_TEMP"]) / "f03-production-v342"
    temporary.mkdir(exist_ok=False)
    java = temporary / "androidTest-java"
    shutil.copytree(ROOT / "examples/android/app/src/androidTest/java", java)
    for relative, original in c["overlay_sources"].items():
        target = java / Path(original).relative_to("examples/android/app/src/androidTest/java")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    # Compare every staged original except the two explicitly reviewed overlay classes.
    old_root = ROOT / "examples/android/app/src/androidTest/java"
    overlay_names = {Path(p).relative_to("examples/android/app/src/androidTest/java").as_posix()
                     for p in c["overlay_sources"].values()}
    for path in old_root.rglob("*"):
        if path.is_file() and path.relative_to(old_root).as_posix() not in overlay_names:
            require((java / path.relative_to(old_root)).read_bytes() == path.read_bytes(),
                    "overlay changed another original test")
    require(len(list(java.rglob("OrganizationTest.java"))) == 1 and
            len(list(java.rglob("OrganizationBootstrapRecoveryTest.java"))) == 1, "unique overlay classes")
    real_gradle = shutil.which("gradle")
    require(real_gradle and Path(real_gradle).is_file(), "installed Gradle 8.9 launcher")
    wrapper = temporary / "gradle"
    init = HERE / "android-test-overlay.init.gradle"
    wrapper.write_text("#!/usr/bin/env bash\nset -euo pipefail\nexec " + shlex.quote(real_gradle) +
                       " --init-script " + shlex.quote(str(init)) + ' -PexrSdkVersion=3.42.0 "$@"\n')
    wrapper.chmod(0o755)
    with open(os.environ["GITHUB_ENV"], "a") as stream:
        stream.write("F03_GRADLE=" + str(wrapper) + "\nF03_ANDROID_TEST_JAVA=" + str(java) + "\n")
    report["overlay_files_sha256"] = {p.relative_to(java).as_posix(): digest(p.read_bytes())
                                     for p in sorted(java.rglob("*")) if p.is_file()}
    report["gradle_wrapper_sha256"] = digest(wrapper.read_bytes())
    report["gradle_real_launcher"] = real_gradle
    write_report(ROOT / "build/f03-production/source-admission.json", report)

def original_build(arguments):
    verify_source()
    import android_host_evidence_v342 as versioned
    previous = sys.modules.get("android_host_evidence")
    old_argv = sys.argv[:]
    try:
        # Process-local adapter: unchanged original driver receives the versioned ownership helper.
        sys.modules["android_host_evidence"] = versioned
        sys.argv = [str(ROOT / "tools/build_android_host.py"), *arguments]
        runpy.run_path(sys.argv[0], run_name="__main__")
    finally:
        sys.argv = old_argv
        if previous is None:
            sys.modules.pop("android_host_evidence", None)
        else:
            sys.modules["android_host_evidence"] = previous

def recovery():
    c = configuration()
    root = ROOT / "build/f03-recovery"
    report = json.loads((root / "device-report.json").read_text())
    for key, env in (("source_sha", "GITHUB_SHA"), ("run_id", "GITHUB_RUN_ID"), ("attempt", "GITHUB_RUN_ATTEMPT")):
        require(report.get(key) == os.environ[env], "recovery actual run identity: " + key)
    require(report.get("api") == 34 and report.get("abi") == "x86_64", "recovery device identity")
    checks = report.get("checks", [])
    require(report.get("count") == 12 and report.get("failed") == 0 and
            [item.get("id") for item in checks] == c["recovery_cases"] and
            all(item.get("passed") is True and item.get("source_preserved") is True for item in checks),
            "all twelve original recovery cases must pass in order")
    log = (root / "instrumentation.txt").read_text()
    require(re.findall(r"^INSTRUMENTATION_STATUS_CODE: (-?\d+)\s*$", log, re.M) == ["1", "0"] * 12,
            "recovery case completion status")
    require(re.findall(r"^INSTRUMENTATION_CODE: (-?\d+)\s*$", log, re.M) == ["-1"] and
            re.search(r"^OK \(12 tests\)\s*$", log, re.M), "recovery terminal result")
    require(not any(x in log for x in ("FAILURES!!!", "INSTRUMENTATION_FAILED", "INSTRUMENTATION_ABORTED")),
            "recovery instrumentation failure")
    require(set(re.findall(r"^INSTRUMENTATION_STATUS: class=(.+)\s*$", log, re.M)) ==
            {"org.exreader.host.OrganizationBootstrapRecoveryTest"}, "recovery class identity")
    names = re.findall(r"^INSTRUMENTATION_STATUS: test=(.+)\s*$", log, re.M)
    require(names == [name for name in c["recovery_cases"] for _ in (0, 1)], "recovery case log identity")
    result = {key: report[key] for key in ("source_sha", "run_id", "attempt")}
    result.update({"recovery_accepted": True, "runtime_accepted": False,
                   "device_report_sha256": digest((root / "device-report.json").read_bytes()),
                   "instrumentation_sha256": digest((root / "instrumentation.txt").read_bytes())})
    write_report(root / "result.json", result)
    print(json.dumps(result))

def final_result():
    destination = ROOT / "build/f03-production/result.json"
    result = {"accepted": False, "problems": [], "source_sha": os.environ.get("GITHUB_SHA"),
              "run_id": os.environ.get("GITHUB_RUN_ID"), "attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
              "scope": "F03 intake historical-state recovery and complete retained Android acceptance",
              "old_apk_upgrade_accepted": False, "complete_product": False}
    try:
        admitted = verify_source()
        outcomes = json.loads(os.environ["F03_UPSTREAM"])
        required = {"admission", "prepare", "build", "emulator", "catalog", "preflight", "gate48",
                    "gate20", "host", "shelf", "shelf_gate", "owner", "owner_gate", "organization", "organization_gate"}
        require(set(outcomes) == required and all(v == "success" for v in outcomes.values()),
                "a required original or new stage failed, skipped or was cancelled")
        identity = {k: result[k] for k in ("source_sha", "run_id", "attempt")}
        records = {
            "host": "build/shelf-android/original-result.json",
            "gate48": "build/android-host/gate-review.json",
            "gate20": "build/android-host/bounded-gate-review.json",
            "shelf": "build/shelf-android/shelf-result.json",
            "shelf_gate": "build/shelf-android/shelf-gate-review.json",
            "owner": "build/owner-android/result.json",
            "owner_gate": "build/owner-android/gate-review.json",
            "organization": "build/organization-android/result.json",
            "organization_gate": "build/organization-android/gate-review.json"}
        proofs = {}
        for name, relative in records.items():
            path = ROOT / relative
            value = json.loads(path.read_text())
            require(value.get("accepted") is True and not value.get("problems") and not value.get("problem"),
                    "actual acceptance missing: " + name)
            if name == "host":
                summary = value["summary"]
                require(value.get("candidate_only") is False and value.get("candidate_validated") is False and
                        summary["source_sha"] == identity["source_sha"] and
                        summary["run"]["id"] == identity["run_id"] and
                        summary["run"]["attempt"] == identity["attempt"], "formal host identity")
            else:
                require(all(value.get(k) == v for k, v in identity.items()), "same-run final identity: " + name)
            if "checks" in value:
                require(value["checks"] and all(item.get("passed") is True for item in value["checks"]),
                        "gate checks incomplete: " + name)
            proofs[name] = {"path": relative, "sha256": digest(path.read_bytes())}
        for name, count in (("gate48", 48), ("gate20", 20), ("shelf_gate", 19), ("owner_gate", 19)):
            value = json.loads((ROOT / records[name]).read_text())
            require(len(value["checks"]) == count, "original gate count: " + name)
        recovery()
        recovered = json.loads((ROOT / "build/f03-recovery/result.json").read_text())
        require(recovered["recovery_accepted"] is True and all(recovered.get(k) == v for k, v in identity.items()),
                "twelve same-run recovery cases")
        proofs["recovery"] = {"path": "build/f03-recovery/result.json",
                              "sha256": digest((ROOT / "build/f03-recovery/result.json").read_bytes())}
        result.update(accepted=True, source_admission=admitted, evidence=proofs,
                      original_host_checks=66, original_gate_checks=[48, 20],
                      original_organization_cases=8, recovery_cases=12, upstream=outcomes)
    except Exception as error:
        result["problems"].append(type(error).__name__ + ": " + str(error))
    write_report(destination, result)
    print(json.dumps(result))
    return 0 if result["accepted"] else 1


def main():
    require(len(sys.argv) > 1, "explicit action required")
    action = sys.argv[1]
    if action == "admit":
        print(json.dumps(verify_source()))
    elif action == "prepare":
        prepare()
    elif action == "build":
        original_build(sys.argv[2:])
    elif action == "recovery":
        recovery()
    elif action == "final":
        return final_result()
    else:
        raise ValueError("unknown action")

if __name__ == "__main__":
    raise SystemExit(main())
