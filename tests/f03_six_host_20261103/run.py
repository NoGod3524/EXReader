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
    "tests/dot_f03_same_source_20261031/build.py",
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

def android_build():
    identity = setup()
    stamp = admission()
    require(sys.platform.startswith("linux"), "Android compiler requires Linux runner")
    os.environ["ORG_GRADLE_PROJECT_exrSdkVersion"] = "3.42.0"
    builder = importlib.import_module("build")
    changes = []
    builder.build_linux_recipe("android", changes)
    # The original recipe deliberately compiles the synchronization profile.
    # Add the F03 receiver to its complete generated UI source set.
    ui = ROOT / "build/wave3/candidate/java/org/exreader/host/uitest"
    shutil.copyfile(LEGACY / "android/OrganizationInteropTest.java", ui / "OrganizationInteropTest.java")
    work = ROOT / "build/f03-android-sync"
    work.mkdir()
    staged = work / "native-tests"
    shutil.copytree(ROOT / "examples/android/app/src/androidTest/java", staged)
    overlay = ROOT / "tests/dot_f03_production_acceptance_20261102/androidTest/org/exreader/host"
    for name in ("CatalogStoreTest", "ImportMappingTest", "OrganizationTest", "OrganizationBootstrapRecoveryTest"):
        shutil.copyfile(overlay / (name + ".java"), staged / "org/exreader/host" / (name + ".java"))
    init = work / "tests.gradle"
    init.write_text("gradle.beforeProject { p -> if (p.path == ':app') { "
                    "p.pluginManager.withPlugin('com.android.application') { "
                    "p.android.sourceSets.androidTest.java.setSrcDirs([new File('" + staged.as_posix() + "')]) } } }\n")
    sdk, products = ROOT / "build/wave3/sdk-stage", ROOT / "build/wave3/stage"
    args = ["gradle", "-p", "examples/android", "--no-daemon", "--stacktrace",
            "-I", str(ROOT / "tests/reader_wave3_c11/candidate.init.gradle"), "-I", str(init),
            "-PexrSdk=" + str(sdk), "-PexrProduct=" + str(products), "-PexrSdkVersion=3.42.0"]
    for flag in ("Sync", "Search", "Navigation", "Reading", "Preferences", "SelectorBytes", "Wave3"):
        args.append("-Pexr" + flag + "=true")
    for flag in ("Wave3Prefix", "SearchPrefix", "NavigationPrefix", "PreferencesPrefix", "Dav", "Sideload"):
        args.append("-Pexr" + flag + "=" + str(products))
    identity.write_json(work / "gradle-args.json", args)
    run(*args, "-PexrTestRunner=org.exreader.host.OrganizationTest", ":app:assembleDebugAndroidTest",
        ":uitest:assembleDebugAndroidTest")
    shutil.copyfile(ROOT / "examples/android/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk",
                    work / "organization-test.apk")
    shutil.copyfile(ROOT / "examples/android/uitest/build/outputs/apk/androidTest/debug/uitest-debug-androidTest.apk",
                    ROOT / "build/wave3/artifacts/uitest-debug-androidTest.apk")
    run(*args, "-PexrTestRunner=org.exreader.host.OrganizationBootstrapRecoveryTest", ":app:assembleDebugAndroidTest")
    shutil.copyfile(ROOT / "examples/android/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk",
                    work / "recovery-test.apk")
    identity.write_json(work / "build.json", {**stamp, "sdk_version": "3.42.0", "sdk_source": SDK,
                        "operation_completed": True, "profile": "raw3-wave3-sync",
                        "program_sha256": identity.digest(ROOT / "build/wave3/artifacts/app-debug.apk"),
                        "in_memory_version_adapters": changes, "complete_product_accepted": False})

def android_retained():
    identity = setup()
    stamp = admission()
    sys.path.insert(0, str(LEGACY))
    from android import adb
    work = ROOT / "build/f03-android-sync"
    artifacts = ROOT / "build/wave3/artifacts"
    output = work / "retained"
    output.mkdir()
    adb("install", "-r", "-t", artifacts / "app-debug.apk")
    adb("install", "-r", "-t", artifacts / "organization-debug-androidTest.apk")
    run(sys.executable, "tests/reader_android_organization_sync/run.py", "--fixture",
        "build/wave3/network-fixture", "--output", str(output / "original-sync"))
    adb("install", "-r", "-t", work / "organization-test.apk")
    common = sum((["-e", key, value] for key, value in stamp.items()), [])
    raw = adb("shell", "am", "instrument", "-w", "-r", *common,
              "org.exreader.host.test/org.exreader.host.OrganizationTest", timeout=900)
    (output / "native.txt").write_bytes(raw)
    native = json.loads(adb("exec-out", "run-as", "org.exreader.host", "cat", "files/organization-report.json"))
    identity.same_identity(native, stamp)
    require(native["count"] == 8 and native["failed"] == 0 and all(r["pass"] is True for r in native["checks"]),
            "native organization cases failed or missing")
    require(b"OK (8 tests)" in raw and b"FAILURES" not in raw, "native organization instrumentation failed")
    identity.write_json(output / "native.json", native)
    raw = adb("shell", "am", "instrument", "-w", "-r", "-e", "phase", "seed-ui", *common,
              "org.exreader.host.test/org.exreader.host.OrganizationTest", timeout=900)
    (output / "seed-ui.txt").write_bytes(raw)
    require(b"EXR_ORGANIZATION_PHASE seed-ui" in raw, "original UI seed failed")
    for name in ("uitest-debug.apk", "uitest-debug-androidTest.apk"):
        adb("install", "-r", "-t", artifacts / name)
    adb("shell", "pm", "clear", "org.exreader.host.uitest")
    args = sum((["-e", "exr_" + key, value] for key, value in stamp.items()), [])
    raw = adb("shell", "am", "instrument", "-w", "-r", "-e", "disableAnalytics", "true",
              "-e", "class", "org.exreader.host.uitest.OrganizationInteropTest#organize", *args,
              "org.exreader.host.uitest.test/androidx.test.runner.AndroidJUnitRunner", timeout=1200)
    (output / "ui.txt").write_bytes(raw)
    adb("pull", "/sdcard/Android/data/org.exreader.host.uitest/files/organization-evidence", output / "ui")
    ui = json.loads((output / "ui/validation.json").read_text())
    identity.same_identity(ui, stamp)
    require(ui["passed"] == 8 and ui["failed"] == 0 and ui["skipped"] == 0 and len(ui["cases"]) == 8,
            "original organization UI cases failed or skipped")
    require(b"OK (1 test)" in raw and b"FAILURES" not in raw, "organization UI instrumentation failed")
    adb("install", "-r", "-t", work / "recovery-test.apk")
    raw = adb("shell", "am", "instrument", "-w", "-r", *common,
              "org.exreader.host.test/org.exreader.host.OrganizationBootstrapRecoveryTest", timeout=900)
    (output / "recovery.txt").write_bytes(raw)
    recovery = json.loads(adb("exec-out", "run-as", "org.exreader.host", "cat", "files/f03-bootstrap-recovery.json"))
    identity.write_json(output / "recovery.json", recovery)
    identity.same_identity(recovery, stamp)
    require(recovery["count"] == 12 and recovery["failed"] == 0 and
            all(row["passed"] is True and row["source_preserved"] is True for row in recovery["checks"]),
            "recovery cases failed or missing")
    require(b"OK (12 tests)" in raw and b"FAILURES" not in raw, "recovery instrumentation failed")
    identity.write_json(output / "result.json", {**stamp, "accepted": True, "native_checks": 8,
                        "ui_checks": 8, "recovery_checks": 12, "sync_checks": 5,
                        "program_sha256": identity.digest(artifacts / "app-debug.apk"),
                        "full_F03_accepted": False, "complete_product_accepted": False})

def main():
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=["admit", "legacy", "apple", "apple-receive", "android-build", "android-retained"])
    p.add_argument("args", nargs=argparse.REMAINDER)
    a = p.parse_args()
    if a.action == "admit":
        print(json.dumps(admission()))
    elif a.action == "legacy":
        legacy(a.args[0], a.args[1:])
    elif a.action == "android-build":
        android_build()
    elif a.action == "android-retained":
        android_retained()
    else:
        apple(a.args[0], a.action == "apple-receive")

if __name__ == "__main__":
    main()
