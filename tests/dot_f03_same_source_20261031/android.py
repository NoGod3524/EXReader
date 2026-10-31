"""Execute installed Android native organization suites and preserve their failure evidence."""
import argparse
import json
import shutil
from pathlib import Path
import subprocess
import sys
from identity import ROOT, identity, require, digest, same_identity, write_json

def adb(*args, timeout=120):
    return subprocess.check_output(["adb", *map(str, args)], stderr=subprocess.STDOUT, timeout=timeout)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--host-apk", type=Path, required=True)
    p.add_argument("--owner-test-apk", type=Path, required=True)
    p.add_argument("--ui-apk", type=Path, required=True)
    p.add_argument("--ui-test-apk", type=Path, required=True)
    p.add_argument("--new-ui-class", action="store_true")
    p.add_argument("--reports", type=Path, required=True)
    a = p.parse_args()
    stamp = identity()
    a.output.mkdir(parents=True, exist_ok=False)
    passed = False
    names = ("host_apk", "owner_test_apk", "ui_apk", "ui_test_apk")
    apks = {name: digest(getattr(a, name)) for name in names}
    try:
        require(a.reports.is_dir(), "original connected-test XML required")
        shutil.copytree(a.reports, a.output / "reports")
        (a.output / "apks").mkdir()
        shutil.copyfile(a.host_apk, a.output / "apks/app-debug.apk")
        for name in names:
            adb("install", "-r", "-t", getattr(a, name))
        installed = adb("shell", "pm", "path", "org.exreader.host").decode().strip()
        require(installed.startswith("package:") and "\n" not in installed, "unexpected host APK layout")
        adb("pull", installed[len("package:"):], a.output / "installed.apk")
        require(digest(a.output / "installed.apk") == apks["host_apk"], "installed host differs")
        common = []
        for key, value in stamp.items():
            common += ["-e", key, value]
        raw = adb("shell", "am", "instrument", "-w", "-r", *common,
                  "org.exreader.host.test/org.exreader.host.OrganizationTest", timeout=900)
        (a.output / "instrumentation.txt").write_bytes(raw)
        native = json.loads(adb("exec-out", "run-as", "org.exreader.host",
                                "cat", "files/organization-report.json"))
        same_identity(native, stamp)
        write_json(a.output / "device-report.json", native)
        raw = adb("shell", "am", "instrument", "-w", "-r", "-e", "phase", "seed-ui",
                  *common, "org.exreader.host.test/org.exreader.host.OrganizationTest", timeout=900)
        (a.output / "seed-ui.txt").write_bytes(raw)
        # Previous evidence is deliberately not removed: dirty runner evidence is rejected.
        selected = "OrganizationInteropTest" if a.new_ui_class else "OrganizationWalkthroughTest"
        raw = adb("shell", "am", "instrument", "-w", "-r", "-e", "disableAnalytics", "true",
                  "-e", "class", "org.exreader.host.uitest." + selected + "#organize",
                  "-e", "exr_source_sha", stamp["source_sha"], "-e", "exr_run_id", stamp["run_id"],
                  "-e", "exr_attempt", stamp["attempt"],
                  "org.exreader.host.uitest.test/androidx.test.runner.AndroidJUnitRunner", timeout=1200)
        (a.output / "ui-instrumentation.txt").write_bytes(raw)
        adb("pull", "/sdcard/Android/data/org.exreader.host.uitest/files/organization-evidence",
            a.output / "ui")
        adb("pull", "/sdcard/Android/data/org.exreader.host/files/organization-tests",
            a.output / "phases")
        require(b"FAILURES!!!" not in raw and b"OK (1 test)" in raw, "native UI suite did not pass")
        # Original all-exits checker is a separate mandatory gate once all retained reports are
        # assembled by the producer; the focused runner must not claim those absent reports.
        subprocess.run([sys.executable, str(ROOT / "tools/check_reader_organization_android.py"),
                        "--evidence", str(a.output), "--all-exits"], cwd=ROOT, check=True)
        passed = True
    finally:
        write_json(a.output / "driver-result.json",
                   {**stamp, "host": "android", "apk_sha256": apks,
                    "native_lifecycle_passed": passed, "complete_product_accepted": False,
                    "six_host_wire_verified": False,
                    "scope": "actual retained native organization lifecycle, not cross-host sync"})
if __name__ == "__main__":
    main()
