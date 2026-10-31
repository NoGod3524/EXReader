# SPDX-License-Identifier: MIT
"""Actions-only F09 direct-handle control beside the frozen handle-method differential.

Runs the byte-frozen handle-diff driver (frozen eight observations plus its six array-handle
processes) unchanged, then eight control processes: compare, clone, expand and gettext on a direct
DocumentRange legacy handle per baseline/candidate host, strict S_OK with raw values kept.
No debugger, dump, memory, register or parameter reads; not full F09 acceptance.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("f09_handle_diff_driver", ROOT / "tests/reader_f09_handle_diff_20261031/run.py")
hd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hd)
avs = hd.avs
driver = hd.driver
OUT = ROOT / "build/f09-handle-control"
avs.PARENT = "6f519876e6ee3bdb1bdd25952f6733ffba994aa6"
avs.NEW_PATHS = {"tests/reader_f09_handle_control_20261031/control_probe.cpp",
                 "tests/reader_f09_handle_control_20261031/run.py",
                 ".github/workflows/dot-f09-handle-control-20261031.yml",
                 "docs/reader-total-progress/DOT_F09_HANDLE_CONTROL_20261031.md"}
avs.FROZEN = avs.FROZEN + ("tests/reader_f09_handle_diff_20261031/handle_probe.cpp",
                           "tests/reader_f09_handle_diff_20261031/run.py")
avs.OUT = OUT
hd.OUT = OUT
VARIANTS = ("compare", "clone", "expand", "gettext")

def control_observations():
    probe = OUT / "control-probe.exe"
    driver.run("cl.exe", "/nologo", "/std:c++17", "/EHsc", "/utf-8", "/DUNICODE", "/D_UNICODE",
        "/Fe:" + str(probe), "/Fo:" + str(OUT / "control-probe.obj"),
        ROOT / "tests/reader_f09_handle_control_20261031/control_probe.cpp",
        "/link", "ole32.lib", "oleaut32.lib", "user32.lib", "uiautomationcore.lib", "uuid.lib", cwd=OUT)
    reports = {}
    for variant in VARIANTS:
        for label in ("baseline", "candidate"):
            host = OUT / (label + "-package") / "EXReader" / "EXReader.exe"
            observation = label + "-control-" + variant
            directory = OUT / observation
            directory.mkdir(parents=True, exist_ok=True)
            command = list(map(str, (probe, host, directory, variant)))
            print("+ independent probe", observation, *command, flush=True)
            with (directory / "stdout.log").open("wb") as stdout, (directory / "stderr.log").open("wb") as stderr:
                process = subprocess.Popen(command, cwd=ROOT, stdout=stdout, stderr=stderr)
                process.wait()
            print((directory / "stdout.log").read_text(encoding="utf-8", errors="replace"), flush=True)
            print((directory / "stderr.log").read_text(encoding="utf-8", errors="replace"), flush=True)
            try:
                report = json.loads((directory / "report.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                report = dict(passed=False, error="probe report missing or invalid")
            report["probe_returncode"] = process.returncode
            report["passed"] = process.returncode == 0 and report.get("passed") is True
            if process.returncode != 0 and (directory / "host.pid").exists():
                pid = (directory / "host.pid").read_text().strip()
                assert pid.isdecimal() and int(pid) > 0
                cleanup = subprocess.run(["taskkill", "/PID", pid, "/T", "/F"], capture_output=True)
                report["failed_probe_host_cleanup_returncode"] = cleanup.returncode
                (directory / "cleanup.log").write_bytes(cleanup.stdout + cleanup.stderr)
            if (directory / "provider.log").exists():
                print("F09-PROVIDER", observation, (directory / "provider.log").read_text(encoding="utf-8", errors="replace"), flush=True)
            report["host_sha256"] = hashlib.sha256(host.read_bytes()).hexdigest()
            hr = report.get("method_hresult")
            print("F09-OBSERVATION", json.dumps(dict(observation=observation, variant=variant,
                returncode=process.returncode, returncode_hex="0x%08X" % (process.returncode & 0xffffffff),
                passed=report["passed"], method_returned=report.get("method_returned"),
                method_hresult_hex=None if hr is None else "0x%08X" % (hr & 0xffffffff),
                host_sha256=report["host_sha256"])), flush=True)
            (directory / "observation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
            reports[observation] = report
    (OUT / "handle-control.json").write_text(json.dumps(dict(reports=reports,
        probe_sha256=hashlib.sha256(probe.read_bytes()).hexdigest(),
        source_sha256=hashlib.sha256((ROOT / "tests/reader_f09_handle_control_20261031/control_probe.cpp").read_bytes()).hexdigest(),
        retained_failure_runs_added=[41170051294, 41170867473], diagnostic_only=True,
        formal_f09_accepted=False, screen_reader_verified=False), indent=2), encoding="utf-8")
    return reports

if __name__ == "__main__":
    driver.OUT = OUT
    driver.guard = avs.guard
    driver.crash_events = avs.crash_events
    frozen_failure = None
    try:
        driver.main()
    except AssertionError as failure:
        # Only the frozen final aggregate assertion lets the differential and control run.
        if not (OUT / "verdict.json").exists():
            raise
        frozen_failure = failure
    hd.extra_observations()
    control_observations()
    if frozen_failure is not None:
        raise frozen_failure
    sys.exit(0)
