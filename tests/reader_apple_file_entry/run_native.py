#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Builds and runs the installed-package native probe and consumer on macOS or
an iPhone/iPad simulator, then writes a source-bound platform report.

Actions-only: it needs Xcode, the installed file-entry module (extras/apple-file-entry/
install.sh), the installed public SDK and the installed sideload module.
"""
import argparse
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
NINE = [("txt", "notes.txt"), ("html", "sample.html"), ("fb2", "sample.fb2"), ("epub", "sample.epub"),
        ("docx", "sample.docx"), ("rtf", "sample.rtf"), ("mobi", "sample.mobi"), ("pdf", "pdf-public.pdf"),
        ("cbz", "comic.cbz")]
CHECK_LINE = re.compile(r"^check (\S+) (pass|fail) (.*)$")
NOT_EXERCISED = {
    "all": [
        "real iCloud Drive / third-party File Provider downloads (no account on the runner); not-downloaded is exercised through the ubiquity seam only",
        "system picker UI interaction: FileEntryPicker is compiled, not driven",
        "app-sandbox security-scoped URLs from a real picker or bookmark: scope pairing is exercised through the scope seam; live start/stop returns false for plain URLs",
        "Files app / Finder file-sharing delivery into Documents/Inbox: the Inbox layout is reproduced on disk",
        "physical iPhone/iPad hardware",
    ],
    "macos": ["App Sandbox entitlements on macOS"],
    "iphone": [], "ipad": [],
}


def sh(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def make_fixtures(work):
    fixtures = work / "fixtures"
    fixtures.mkdir(parents=True)
    multi = secrets.token_bytes(3 * 65536 + 17)
    (fixtures / "multi-chunk.epub").write_bytes(multi)
    text = ("Plain text with Unicode: café 中文 \U0001F600\r\nsecond line\n" * 40).encode("utf-8")
    (fixtures / "notes.txt").write_bytes(text)
    for _, name in NINE:
        if name != "notes.txt":
            shutil.copyfile(REPO / "tests" / "fixtures" / name, fixtures / name)
    listing = {}
    for path in sorted(fixtures.iterdir()):
        listing[path.name] = {"size": path.stat().st_size, "sha256": sha256(path)}
    nine = [{"format": fmt, "file": name, "sha256": listing[name]["sha256"]} for fmt, name in NINE]
    (work / "expectations.json").write_text(json.dumps({"fixtures": listing, "nine": nine}, indent=2), encoding="utf-8")


def compile_all(args, logs):
    triple = {"macos": os.uname().machine + "-apple-macos12.0"}.get(args.platform, "arm64-apple-ios15.0-simulator")
    sdk_name = "macosx" if args.platform == "macos" else "iphonesimulator"
    sdk_path = sh(["xcrun", "--sdk", sdk_name, "--show-sdk-path"]).stdout.strip()
    prefix, sdk, sideload = Path(args.prefix), Path(args.sdk), Path(args.sideload)
    base = ["xcrun", "--sdk", sdk_name, "swiftc", "-swift-version", "5", "-O", "-target", triple, "-sdk", sdk_path,
            "-I", str(prefix / "lib" / "swift"), "-L", str(prefix / "lib"), "-lEXRFileEntry"]
    out = Path(args.out)
    steps = {
        "probe": base + [str(HERE / "probe" / "main.swift"), "-o", str(out / "probe")],
        "consumer": base + ["-import-objc-header", str(prefix / "share/exreader-apple-file-entry/examples/SdkBridge.h"),
                            "-I", str(sdk / "include"), "-I", str(sideload / "include"),
                            "-L", str(sideload / "lib"), "-L", str(sdk / "lib"), "-lexr_sideload", "-lexreader",
                            "-Xlinker", "-rpath", "-Xlinker", str(sdk / "lib"),
                            str(HERE / "consumer" / "main.swift"),
                            str(prefix / "share/exreader-apple-file-entry/examples/ImportStagedRequest.swift"),
                            "-o", str(out / "consumer")],
    }
    for name, cmd in steps.items():
        done = sh(cmd, timeout=900)
        (logs / f"build-{name}.log").write_text(" ".join(cmd) + "\n" + done.stdout + done.stderr, encoding="utf-8")
        if done.returncode != 0:
            print(done.stdout + done.stderr)
            raise SystemExit(f"build {name} failed")
    return triple


def pick_device(platform):
    runtimes = json.loads(sh(["xcrun", "simctl", "list", "runtimes", "available", "-j"]).stdout)["runtimes"]
    ios = sorted((r for r in runtimes if r.get("platform") == "iOS"), key=lambda r: [int(x) for x in r["version"].split(".")])
    runtime = ios[-1]
    family = "iPhone" if platform == "iphone" else "iPad"
    types = [d for d in runtime.get("supportedDeviceTypes", []) if d.get("productFamily") == family]
    return runtime, types[-1]


def run_binary(args, name, work, logs, udid):
    result = work / f"{name}-result.txt"
    command = [str(Path(args.out) / name), str(work), str(result)]
    if udid:
        command = ["xcrun", "simctl", "spawn", udid] + command
    done = sh(command, timeout=1500)
    (logs / f"run-{name}.log").write_text(done.stdout + done.stderr, encoding="utf-8")
    lines = result.read_text(encoding="utf-8").splitlines() if result.exists() else []
    return done.returncode, lines


def parse(lines):
    checks = []
    for line in lines:
        match = CHECK_LINE.match(line)
        if match:
            checks.append({"id": match[1], "result": match[2], "detail": match[3]})
    return checks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", choices=["macos", "iphone", "ipad"], required=True)
    parser.add_argument("--prefix", required=True, help="installed file-entry prefix for this platform")
    parser.add_argument("--sdk", required=True, help="installed SDK prefix")
    parser.add_argument("--sideload", required=True, help="installed sideload prefix")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    out = Path(args.out).resolve()
    args.out = str(out)
    if out.exists():
        raise SystemExit("output directory must not exist")
    logs = out / "logs"
    logs.mkdir(parents=True)
    expected = json.loads((HERE / "expected_checks.json").read_text())
    triple = compile_all(args, logs)

    device = None
    udid = None
    try:
        if args.platform != "macos":
            runtime, kind = pick_device(args.platform)
            udid = sh(["xcrun", "simctl", "create", "exr-file-entry-" + secrets.token_hex(4), kind["identifier"], runtime["identifier"]]).stdout.strip()
            boot = sh(["xcrun", "simctl", "bootstatus", udid, "-b"], timeout=900)
            device = {"runtime": runtime["identifier"], "version": runtime["version"], "device_type": kind["identifier"],
                      "name": kind.get("name"), "udid": udid, "boot": boot.returncode, "fresh_device": True}
            if boot.returncode != 0:
                raise SystemExit("simulator did not boot")
        reports = {}
        for name in ("probe", "consumer"):
            work = out / f"work-{name}"
            make_fixtures(work)
            code, lines = run_binary(args, name, work, logs, udid)
            keep = out / "evidence" / name
            keep.mkdir(parents=True)
            shutil.copyfile(work / "expectations.json", keep / "expectations.json")
            if (work / f"{name}-result.txt").exists():
                shutil.copyfile(work / f"{name}-result.txt", keep / "result.txt")
            shutil.rmtree(work, ignore_errors=True)  # sparse >100 MiB fixtures must not be uploaded
            reports[name] = {"exit": code, "checks": parse(lines), "expected": expected[name]}
    finally:
        if udid:
            sh(["xcrun", "simctl", "shutdown", udid])
            sh(["xcrun", "simctl", "delete", udid])

    problems = []
    total = passed = 0
    for name, report in reports.items():
        ids = [c["id"] for c in report["checks"]]
        if ids != report["expected"]:
            problems.append(f"{name}: check ids differ from expected_checks.json")
        for c in report["checks"]:
            total += 1
            passed += c["result"] == "pass"
        if report["exit"] != 0 or any(c["result"] != "pass" for c in report["checks"]):
            problems.append(f"{name}: failures or non-zero exit")
        report["passed"] = sum(c["result"] == "pass" for c in report["checks"])
        report["failed"] = sum(c["result"] == "fail" for c in report["checks"])
    xcode = sh(["xcodebuild", "-version"]).stdout.strip().replace("\n", " ")
    summary = {
        "schema": 1, "platform": args.platform, "accepted": not problems and total > 0, "problems": problems,
        "source_sha": os.environ.get("GITHUB_SHA", ""), "run_id": os.environ.get("GITHUB_RUN_ID", ""),
        "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT", ""), "job": os.environ.get("GITHUB_JOB", ""),
        "target": triple, "xcode": xcode, "simulator": device, "reports": reports,
        "total_checks": total, "passed_checks": passed,
        "not_exercised": NOT_EXERCISED["all"] + NOT_EXERCISED[args.platform],
        "binaries": {n: sha256(out / n) for n in ("probe", "consumer")},
    }
    (out / "report.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for name, report in reports.items():
        print(f"{name}: {report['passed']} pass, {report['failed']} fail, exit {report['exit']}")
        for c in report["checks"]:
            if c["result"] != "pass":
                print("  FAIL", c["id"], c["detail"])
    for problem in problems:
        print("PROBLEM", problem)
    return 0 if summary["accepted"] else 1


if __name__ == "__main__":
    sys.exit(main())
