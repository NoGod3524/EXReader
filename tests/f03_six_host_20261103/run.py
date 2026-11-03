"""Same-source F03 integration. Reuse native drivers; never manufacture product history."""
import argparse
import importlib
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
LEGACY = ROOT / "tests/dot_f03_same_source_20261031"
BASE = "054df69524eed483759febdcc0ce20e634921f82"
SDK = "8357eafa28423a7ab93ba08b823af80f01ad1505"
HOSTS = ["windows", "gtk", "android", "macos", "iphone", "ipad"]
PHASES = ["create", "delete", "restore", "member-remove", "member-restore", "restart"]
FROZEN = {
    "apps/reader/desktop/windows_records_owner.cpp": "fb1b36b8ee6a0c48b81d8aff3b2097c7372c4b33",
    "examples/android/app/src/main/java/org/exreader/host/ReadingParserPolicy.java": "9566f21b7f38c3652d9a416cabd73d1b76a959d6",
    "examples/apple/HostReadingRecords.swift": "2c6185723fb523996b7c86ec5caf25f849a3f8cf",
}
EXACT_PATHS = {
    "examples/apple/HostCatalog.swift", "examples/apple/HostModel.swift", "examples/apple/HostViews.swift",
    "tests/dot_f03_same_source_20261031/AppleOrganizationInteropTests.swift",
    "tests/dot_f03_same_source_20261031/windows.py", "tests/dot_f03_same_source_20261031/gtk.py",
    ".github/workflows/f03-six-host-20261103.yml",
    "docs/reader-total-progress/F03_SIX_HOST_20261103.md",
}

def run(*args):
    subprocess.run(list(map(str, args)), cwd=ROOT, check=True)

def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()

def require(value, message):
    if not value:
        raise AssertionError(message)

def admission():
    require(os.environ.get("GITHUB_ACTIONS") == "true", "Native execution requires Actions")
    source = git("rev-parse", "HEAD")
    require(source == os.environ["GITHUB_SHA"], "checkout/source mismatch")
    run("git", "merge-base", "--is-ancestor", BASE, source)
    run("git", "diff", "--exit-code", SDK, source, "--", "src", "include", "cmake", "CMakeLists.txt", "bindings")
    changed = git("diff", "--name-only", BASE, source).splitlines()
    require(all(p in EXACT_PATHS or p.startswith("tests/f03_six_host_20261103/") for p in changed),
            "integration changed a path outside its contract")
    for path, expected in FROZEN.items():
        require(git("rev-parse", "HEAD:" + path) == expected, "frozen production blob changed: " + path)
    tracked = subprocess.check_output(["git", "diff", "HEAD", "--name-only"], cwd=ROOT, text=True)
    require(not tracked.strip(), "tracked sources changed during execution")
    return {key: os.environ[env] for key, env in
            (("source_sha", "GITHUB_SHA"), ("run_id", "GITHUB_RUN_ID"), ("attempt", "GITHUB_RUN_ATTEMPT"))}

def setup():
    sys.path.insert(0, str(LEGACY))
    identity = importlib.import_module("identity")
    identity.SCOPE = {**identity.SCOPE, "active_hosts": HOSTS, "hosts": HOSTS,
                      "sdk_source": SDK, "sdk_version": "3.42.0"}
    # The old 26-file partial admission belongs to its historical round. This
    # integration has a separate, explicit source/SDK/frozen-blob admission above.
    identity.identity = admission
    return identity

def legacy(script, args):
    setup()
    sys.argv = [str(LEGACY / (script + ".py")), *args]
    runpy.run_path(sys.argv[0], run_name="__main__")

def apple(platform, receive):
    identity = setup()
    stamp = admission()
    require(sys.platform == "darwin", "Apple runner required")
    target = "macos" if platform == "macos" else "iphonesimulator"
    sdk = ROOT / "build/raw3-ios-sdk" / target / "sdk"
    products = sdk.parent / "raw-products"
    work = ROOT / "build/dot-f03-native" / platform
    if receive:
        destination = json.loads((work / "destination.json").read_text())
        suffix = "Debug" if platform == "macos" else "Debug-iphonesimulator"
        program = work / "derived/Build/Products" / suffix / "EXReaderHost.app"
        program /= "Contents/MacOS/EXReaderHost" if platform == "macos" else "EXReaderHost"
        for phase in PHASES:
            author = ROOT / "build/f03-input/f03-author" / phase
            args = ["--host", platform, "--apple-receive", "--wire", str(author / "wire/state.json"),
                    "--expectations", str(author / "expected-groups.json"),
                    "--projection-expectations", str(author / "projection.json"),
                    "--program", str(program), "--destination", destination["destination"],
                    "--output", str(ROOT / "build/f03-receipts" / platform / (phase + ".json"))]
            if platform != "macos":
                args += ["--udid", destination["udid"]]
            legacy("build", args)
        return
    legacy("build", ["--host", platform, "--output", "build/f03-" + platform + "-build.json"])
    work.mkdir(parents=True, exist_ok=False)
    resources = work / "resources"
    run(sys.executable, "tests/apple_host/prepare_fixtures.py", "--resources", resources)
    if platform == "macos":
        destination = {"destination": "platform=macOS", "udid": "macos"}
    else:
        devices = json.loads(subprocess.check_output(["xcrun", "simctl", "list", "devices", "available", "--json"]))
        prefix = "iPhone" if platform == "iphone" else "iPad"
        runtime, device, udid = max((runtime, d["name"], d["udid"]) for runtime, rows in devices["devices"].items()
                                  for d in rows if d.get("isAvailable") and d["name"].startswith(prefix))
        subprocess.run(["xcrun", "simctl", "shutdown", udid], capture_output=True)
        run("xcrun", "simctl", "erase", udid)
        run("xcrun", "simctl", "boot", udid)
        run("xcrun", "simctl", "bootstatus", udid, "-b")
        destination = {"destination": "platform=iOS Simulator,id=" + udid, "udid": udid,
                       "runtime": runtime, "device": device}
    identity.write_json(work / "destination.json", destination)
    tests = work / "tests"
    tests.mkdir()
    shutil.copyfile(ROOT / "tests/apple_host/organization/ui/OrganizationUITests.swift", tests / "OrganizationUITests.swift")
    shutil.copyfile(LEGACY / "AppleOrganizationInteropTests.swift", tests / "AppleOrganizationInteropTests.swift")
    run("ruby", "tests/reader_team24_apple/make_project.rb", work / "project", resources, tests, "base")
    scheme = "EXReaderHost-macOS" if platform == "macos" else "EXReaderHost-iOS"
    suite = "EXReaderHostUITests-" + ("macOS" if platform == "macos" else "iOS")
    result = work / "organization.xcresult"
    args = ["xcodebuild", "test", "-project", work / "project/EXReaderHost.xcodeproj", "-scheme", scheme,
            "-destination", destination["destination"], "-derivedDataPath", work / "derived", "-resultBundlePath", result,
            "-parallel-testing-enabled", "NO", "-test-timeouts-enabled", "YES",
            "-default-test-execution-time-allowance", "300", "-maximum-test-execution-time-allowance", "600",
            "-only-testing:" + suite + "/OrganizationUITests", "EXR_SDK_DIR=" + str(sdk),
            "EXR_PRODUCTS_DIR=" + str(products), "CODE_SIGNING_ALLOWED=" + ("YES" if platform == "macos" else "NO")]
    run(*args)
    app = work / "derived/Build/Products" / ("Debug" if platform == "macos" else "Debug-iphonesimulator") / "EXReaderHost.app"
    run(sys.executable, "tests/apple_host/organization/collect.py", "--platform", platform,
        "--result", result, "--app", app, "--output", work / "validated")
    identity.write_json(work / "retained.json", {**stamp, "accepted": True,
                        "original_test_sha256": identity.digest(tests / "OrganizationUITests.swift"),
                        "complete_product_accepted": False})

def main():
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=["admit", "legacy", "apple", "apple-receive"])
    p.add_argument("args", nargs=argparse.REMAINDER)
    a = p.parse_args()
    if a.action == "admit":
        print(json.dumps(admission()))
    elif a.action == "legacy":
        legacy(a.args[0], a.args[1:])
    else:
        apple(a.args[0], a.action == "apple-receive")

if __name__ == "__main__":
    main()
