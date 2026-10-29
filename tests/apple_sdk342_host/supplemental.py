#!/usr/bin/env python3
"""Actions-only original supplemental Apple host suites on one same-run SDK 3.42."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
VERSION = "3.42.0"
SDK_SOURCE = "8357eafa28423a7ab93ba08b823af80f01ad1505"

def main():
    assert os.environ.get("GITHUB_ACTIONS") == "true" and sys.platform == "darwin"
    assert os.environ.get("EXR_APPLE_SDK_VERSION") == VERSION
    p = argparse.ArgumentParser()
    p.add_argument("--platform", choices=("macos", "iphone", "ipad"), required=True)
    p.add_argument("--suite", choices=("font", "original", "organization", "sync"), required=True)
    a = p.parse_args()
    out = ROOT / "build/apple-sdk342-supplemental" / a.platform / a.suite
    out.mkdir(parents=True, exist_ok=False)
    cloud = {"source_sha": os.environ["GITHUB_SHA"], "run_id": os.environ["GITHUB_RUN_ID"],
             "attempt": os.environ["GITHUB_RUN_ATTEMPT"]}
    report = {**cloud, "platform": a.platform, "suite": a.suite, "sdk_version": VERSION,
              "accepted": False, "physical_device": False, "commands": [], "programs": {}}
    def run(role, *args, timeout=4800):
        argv = list(map(str, args))
        with (out / (role + ".log")).open("wb") as log:
            value = subprocess.run(argv, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, timeout=timeout)
        report["commands"].append({"role": role, "argv": argv, "exit": value.returncode})
        if value.returncode:
            print("\n".join((out / (role + ".log")).read_text(errors="replace").splitlines()[-100:]), flush=True)
            raise RuntimeError(role + " failed: " + str(value.returncode))
    def read(path):
        value = json.loads(path.read_text())
        assert value["accepted"] is True, path
        assert all(str(value[k]) == str(v) for k, v in cloud.items()), path
        assert value["platform"] == a.platform, path
        return value
    def program(role, app):
        info = plistlib.loads((app / ("Contents/Info.plist" if a.platform == "macos" else "Info.plist")).read_bytes())
        assert info["EXRSourceSHA"] == cloud["source_sha"] and info["EXRSDKVersion"] == VERSION
        assert info["CFBundleIdentifier"] == "org.exreader.host"
        binary = app / ("Contents/MacOS/EXReaderHost" if a.platform == "macos" else "EXReaderHost")
        dependencies = subprocess.check_output(["otool", "-L", binary], text=True)
        assert re.search(r"libexreader\.1\.dylib \(compatibility version [^,]+, current version 3\.42\.0\)", dependencies)
        run(role + "-package", "ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", app, out / (role + "-app.zip"))
        report["programs"][role] = {"sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
                                     "bundle_source_sha": info["EXRSourceSHA"], "sdk_version": info["EXRSDKVersion"]}
    try:
        installed = {}
        for target in ("macos", "iphonesimulator"):
            matches = list((ROOT / "sdk-input").glob("team24-apple-sdk-" + target + "-*"))
            assert len(matches) == 1
            root = matches[0]
            identity = json.loads((root / "sdk342-installed-identity.json").read_text())
            assert all(identity[k] == v for k, v in cloud.items())
            assert identity["sdk_version"] == VERSION and identity["sdk_content_candidate"] == SDK_SOURCE
            wave3 = json.loads((root / "wave3-packages.json").read_text())
            assert all(wave3[k] == v for k, v in cloud.items()) and wave3["target"] == target
            for label, directory in (("sdk", root / "sdk"), ("raw", root / "raw-products")):
                actual = {f.relative_to(directory).as_posix() for f in directory.rglob("*") if f.is_file()}
                expected = identity[label + "_files"]
                assert actual == set(expected), (target, label, "installed files differ")
                for path, item in expected.items():
                    data = (directory / path).read_bytes()
                    assert len(data) == item["bytes"] and hashlib.sha256(data).hexdigest() == item["sha256"]
                product = json.loads((directory / "share/exreader-apple/product.json").read_text())
                assert product["source_sha"] == cloud["source_sha"] and product["sdk_version"] == VERSION
            link = ROOT / "build/raw3-ios-sdk" / target
            link.parent.mkdir(parents=True, exist_ok=True)
            link.symlink_to(root.resolve(), target_is_directory=True)
            installed[target] = link
        target = "macos" if a.platform == "macos" else "iphonesimulator"
        sdk, products = installed[target] / "sdk", installed[target] / "raw-products"
        if a.suite == "font":
            run("original-font", sys.executable, "tests/reader_apple_font/run_ui.py", "--platform", a.platform)
            result = read(ROOT / "build/apple-font" / a.platform / "evidence/result.json")
            assert len(result["cases"]) == 1 and all(c["result"] == "Passed" for c in result["cases"])
            suffix = "Debug" if a.platform == "macos" else "Debug-iphonesimulator"
            program("font", ROOT / "build/apple-font" / a.platform / "derived/Build/Products" / suffix / "EXReaderHost.app")
        elif a.suite == "original":
            run("original-system-save", sys.executable, "tests/apple_native_original/run.py", "--platform", a.platform)
            result = read(ROOT / "build/apple-native-original" / a.platform / "result.json")
            assert len(result["cases"]) == 1 and result["cases"][0]["result"] == "Passed"
            assert result["readback"]["byte_equal"] is True
            assert result["readback"]["source_sha256"] == result["readback"]["saved_sha256"]
            suffix = "Debug" if a.platform == "macos" else "Debug-iphonesimulator"
            program("original", ROOT / "build/apple-native-original" / a.platform / "derived/Build/Products" / suffix / "EXReaderHost.app")
        else:
            suffix, scheme, signing = ("Debug", "EXReaderHost-macOS", "YES") if a.platform == "macos" else ("Debug-iphonesimulator", "EXReaderHost-iOS", "NO")
            udid, destination = "unused", "platform=macOS"
            if a.platform != "macos":
                data = json.loads(subprocess.check_output(["xcrun", "simctl", "list", "devices", "available", "--json"]))
                prefix = "iPhone" if a.platform == "iphone" else "iPad"
                runtime, device, udid = max((runtime, d["name"], d["udid"]) for runtime, values in data["devices"].items()
                                            for d in values if d.get("isAvailable") and d["name"].startswith(prefix))
                subprocess.run(["xcrun", "simctl", "shutdown", udid], capture_output=True)
                run("erase", "xcrun", "simctl", "erase", udid)
                run("boot", "xcrun", "simctl", "boot", udid)
                run("boot-ready", "xcrun", "simctl", "bootstatus", udid, "-b")
                destination = "platform=iOS Simulator,id=" + udid
                report["destination"] = {"runtime": runtime, "device": device, "udid": udid}
            resources = out / "resources"
            run("fixtures", sys.executable, "tests/apple_host/prepare_fixtures.py", "--resources", resources)
            def project(role, tests):
                path = out / (role + "-project")
                run(role + "-project", "ruby", "tests/reader_team24_apple/make_project.rb", path, resources, tests, "base")
                return path / "EXReaderHost.xcodeproj"
            def command(project, derived, bundle, default, maximum):
                return ["xcodebuild", "test", "-project", project, "-scheme", scheme, "-destination", destination,
                        "-derivedDataPath", derived, "-resultBundlePath", bundle, "-parallel-testing-enabled", "NO",
                        "-test-timeouts-enabled", "YES", "-default-test-execution-time-allowance", default,
                        "-maximum-test-execution-time-allowance", maximum, "EXR_SDK_DIR=" + str(sdk),
                        "EXR_PRODUCTS_DIR=" + str(products), "CODE_SIGNING_ALLOWED=" + signing]
            if a.suite == "organization":
                run("schema-unchanged", "git", "diff", "--exit-code", "a6d7dd81", "HEAD", "--", "apps/reader/store/001_catalog.sql")
                if a.platform == "macos":
                    executable = out / "catalog-original"
                    run("catalog-original-compile", sys.executable, "tools/apple_swift.py", "--sdk", sdk, "--",
                        "-swift-version", "5", "-parse-as-library", "-L", sdk / "lib", "-lexreader", "-Xlinker", "-rpath",
                        "-Xlinker", sdk / "lib", "examples/apple/HostCatalog.swift", "tests/reader_catalog/apple_catalog_check.swift", "-o", executable)
                    run("catalog-original", executable, "apps/reader/store/001_catalog.sql", out / "catalog-original.json")
                    executable = out / "catalog-reopen"
                    run("catalog-reopen-compile", sys.executable, "tools/apple_swift.py", "--sdk", sdk, "--",
                        "-swift-version", "5", "-parse-as-library", "-L", sdk / "lib", "-lexreader", "-Xlinker", "-rpath",
                        "-Xlinker", sdk / "lib", "examples/apple/HostCatalog.swift", "tests/apple_host/organization/catalog_reopen_check.swift", "-o", executable)
                    run("catalog-reopen", executable)
                proj = project("organization", "tests/apple_host/organization/ui")
                derived, bundle = out / "derived", out / "organization.xcresult"
                run("original-organization-six", *command(proj, derived, bundle, "300", "600"))
                app = derived / "Build/Products" / suffix / "EXReaderHost.app"
                run("original-organization-collect", sys.executable, "tests/apple_host/organization/collect.py",
                    "--platform", a.platform, "--result", bundle, "--app", app, "--output", out / "validated")
                result = read(out / "validated/organization-ui.json")
                assert len(result["cases"]) == 6 and result["problems"] == []
                program("organization", app)
            else:
                if a.platform == "macos":
                    sys.path.insert(0, str(ROOT / "tools"))
                    from apple_swift import flags
                    terminal = ROOT / "build/account-terminal"
                    terminal.mkdir(parents=True, exist_ok=True)
                    sources = ["examples/apple/HostSDK.swift", "examples/apple/HostCatalog.swift",
                               "examples/apple/HostAccount.swift", "tests/reader_team24_apple/AccountTerminalReview.swift"]
                    run("account-terminal-compile", "xcrun", "swiftc", "-swift-version", "5", "-parse-as-library", "-O",
                        "-I", sdk / "include", "-L", sdk / "lib", "-lexreader", "-Xlinker", "-rpath", "-Xlinker", sdk / "lib",
                        *sources, "-o", terminal / "account-terminal", *flags(sdk, products, True))
                    run("original-account-terminal", sys.executable, "tests/reader_team24_apple/run_account_terminal.py")
                account = project("account", "tests/apple_host/account/ui")
                derived, network = out / "account-derived", out / "account-ui"
                bundle = network / (a.platform + ".xcresult")
                run("original-account-tls", sys.executable, "tests/apple_host/account/run_account_ui.py", "--platform", a.platform,
                    "--udid", udid, "--resources", resources, "--output", network, "--",
                    *command(account, derived, bundle, "180", "300"))
                app = derived / "Build/Products" / suffix / "EXReaderHost.app"
                container = Path.home() / "Library/Application Support/EXReader" if a.platform == "macos" else Path(
                    subprocess.check_output(["xcrun", "simctl", "get_app_container", udid, "org.exreader.host", "data"], text=True).strip())
                run("original-account-collect", sys.executable, "tests/apple_host/account/collect_account_ui.py",
                    "--platform", a.platform, "--xcresult", bundle, "--app", app, "--container", container,
                    "--output", network / "evidence")
                account_report = read(network / "evidence/account-ui.json")
                assert account_report["cases"] == 3 and account_report["https"]["actual_shards"] == 256
                program("sync", app)
                failure = project("failure", "tests/apple_host/account/failure_ui")
                failure_derived, boundary = out / "failure-derived", out / "account-failure"
                failure_app = failure_derived / "Build/Products" / suffix / "EXReaderHost.app"
                run("original-account-401-recovery", sys.executable, "tests/apple_host/account/run_failure_ui.py",
                    "--platform", a.platform, "--udid", udid, "--resources", resources, "--app", failure_app,
                    "--output", boundary, "--", *command(failure, failure_derived, boundary / "failure.xcresult", "180", "300"))
                result = read(boundary / "failure-evidence.json")
                assert result["failure_requests"] > 0 and result["failed_state_pending_revisions"] == 1
                assert result["recovery_shards"] == 256 and result["outbox_after_retry"] == 0
                program("failure", failure_app)
        report["original_result"] = result
        report["accepted"] = True
    except BaseException as error:
        report["failure"] = repr(error)
    finally:
        report["files"] = {p.relative_to(out).as_posix(): {"bytes": p.stat().st_size,
                           "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                           for p in out.rglob("*") if p.is_file() and p.name != "sdk342-supplemental.json" and p.suffix != ".key"
                           and not {"derived", "account-derived", "failure-derived"}.intersection(p.relative_to(out).parts)}
        (out / "sdk342-supplemental.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps({k: v for k, v in report.items() if k != "files"}), flush=True)
    assert report["accepted"], "retain original supplemental failure evidence"

if __name__ == "__main__":
    main()
