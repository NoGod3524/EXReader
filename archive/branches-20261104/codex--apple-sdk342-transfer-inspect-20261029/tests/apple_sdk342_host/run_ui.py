#!/usr/bin/env python3
"""Add real SDK 3.42 identity admission around the unchanged 39-case Team24 runner."""
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import runpy
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
VERSION = "3.42.0"
SDK_SOURCE = "8357eafa28423a7ab93ba08b823af80f01ad1505"

def main():
    assert os.environ.get("GITHUB_ACTIONS") == "true" and sys.platform == "darwin"
    assert os.environ.get("EXR_APPLE_SDK_VERSION") == VERSION
    assert len(sys.argv) == 3 and sys.argv[1] == "--platform"
    platform = sys.argv[2]
    assert platform in ("macos", "iphone", "ipad")
    cloud = {"source_sha": os.environ["GITHUB_SHA"], "run_id": os.environ["GITHUB_RUN_ID"],
             "attempt": os.environ["GITHUB_RUN_ATTEMPT"]}
    installed = {}
    for target in ("macos", "iphonesimulator"):
        roots = list((ROOT / "sdk-input").glob("team24-apple-sdk-" + target + "-*"))
        assert len(roots) == 1
        root = roots[0]
        identity = json.loads((root / "sdk342-installed-identity.json").read_text())
        assert all(identity[k] == v for k, v in cloud.items())
        assert identity["target"] == target and identity["sdk_version"] == VERSION
        assert identity["sdk_content_candidate"] == SDK_SOURCE
        for label, directory in (("sdk", root / "sdk"), ("raw", root / "raw-products")):
            expected = identity[label + "_files"]
            actual = {p.relative_to(directory).as_posix() for p in directory.rglob("*") if p.is_file()}
            assert actual == set(expected), (target, label, "installed file set differs")
            for path, item in expected.items():
                data = (directory / path).read_bytes()
                assert len(data) == item["bytes"] and hashlib.sha256(data).hexdigest() == item["sha256"]
        header = (root / "sdk/include/exr/base.h").read_text()
        assert re.search(r'#define EXR_VERSION "([^"]+)"', header)[1] == VERSION
        for directory in (root / "sdk", root / "raw-products"):
            product = json.loads((directory / "share/exreader-apple/product.json").read_text())
            assert product["source_sha"] == cloud["source_sha"] and product["sdk_version"] == VERSION
        installed[target] = {"sdk_version": VERSION, "sdk_content_candidate": SDK_SOURCE,
                             "installed_identity_sha256": hashlib.sha256(
                                 (root / "sdk342-installed-identity.json").read_bytes()).hexdigest()}
    failure = None
    try:
        runpy.run_path(str(ROOT / "tests/reader_team24_apple/run_ui.py"), run_name="__main__")
    except BaseException as error:
        failure = error
    evidence = ROOT / "build/team24-apple" / platform / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    identity = {**cloud, "platform": platform, "sdk_version": VERSION,
                "installed": installed, "accepted": False, "programs": {}}
    try:
        report = json.loads((evidence / "result.json").read_text())
        assert all(report[k] == v for k, v in cloud.items())
        assert report["platform"] == platform
        for phase in report["phases"]:
            mode = phase["mode"]
            app = evidence / ("program-" + mode) / "EXReaderHost.app"
            if not app.exists():
                assert not phase["accepted"]
                continue
            info = plistlib.loads((app / ("Contents/Info.plist" if platform == "macos" else "Info.plist")).read_bytes())
            assert info["EXRSourceSHA"] == cloud["source_sha"] and info["EXRSDKVersion"] == VERSION
            binary = app / ("Contents/MacOS/EXReaderHost" if platform == "macos" else "EXReaderHost")
            sha = hashlib.sha256(binary.read_bytes()).hexdigest()
            assert sha == phase["program"]["sha256"]
            dependencies = subprocess.check_output(["otool", "-L", binary], text=True)
            assert re.search(r"libexreader\.1\.dylib \(compatibility version [^,]+, current version 3\.42\.0\)", dependencies)
            identity["programs"][mode] = {"sha256": sha, "sdk_version": info["EXRSDKVersion"],
                                          "bundle_source_sha": info["EXRSourceSHA"]}
        identity["accepted"] = report["accepted"] and len(identity["programs"]) == 5 and failure is None
    except BaseException as error:
        identity["failure"] = str(error)
        if failure is None:
            failure = error
    finally:
        (evidence / "sdk342-native-identity.json").write_text(json.dumps(identity, indent=2) + "\n")
        print(json.dumps(identity), flush=True)
    if failure is not None:
        raise failure
    assert identity["accepted"]

if __name__ == "__main__":
    main()
