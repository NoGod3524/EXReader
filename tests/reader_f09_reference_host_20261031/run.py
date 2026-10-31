# SPDX-License-Identifier: MIT
"""Actions-only F09 Microsoft RichEdit reference-host comparison.

Runs the byte-frozen handle-control driver unchanged (frozen eight observations, six array-handle
and eight direct-handle processes against the EXReader hosts), then drives a test-only Microsoft
RichEdit reference host with the same already-built consumer binaries. Crash versus no crash on
the same array-to-legacy-handle route decides whether the fault follows the provider.
No debugger, dump, memory, register or parameter reads; not full F09 acceptance.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("f09_handle_control_driver", ROOT / "tests/reader_f09_handle_control_20261031/run.py")
hc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hc)
hd = hc.hd
avs = hc.avs
driver = hc.driver
OUT = ROOT / "build/f09-reference-host"
avs.PARENT = "15ea33d9e914e8b353f0d6ec5c31b021cfaa04a4"
avs.NEW_PATHS = {"tests/reader_f09_reference_host_20261031/reference_host.cpp",
                 "tests/reader_f09_reference_host_20261031/run.py",
                 ".github/workflows/dot-f09-reference-host-20261031.yml",
                 "docs/reader-total-progress/DOT_F09_REFERENCE_HOST_20261031.md"}
avs.FROZEN = avs.FROZEN + ("tests/reader_f09_handle_control_20261031/control_probe.cpp",
                           "tests/reader_f09_handle_control_20261031/run.py")
avs.OUT = OUT
hd.OUT = OUT
hc.OUT = OUT
# (observation, consumer binary, third argument). Selection-event and Escape assertions are
# EXReader-specific; for RichEdit the comparison is the exit code and the last stage reached.
REFERENCE = [("reference-managed", "probe.exe", "absent"),
             ("reference-native", "native-probe.exe", "absent"),
             ("reference-legacy", "legacy-probe.exe", "absent"),
             ("reference-visible", "visible-probe.exe", "absent")]
REFERENCE += [("reference-handle-" + v, "handle-probe.exe", v) for v in hd.VARIANTS]
REFERENCE += [("reference-control-" + v, "control-probe.exe", v) for v in hc.VARIANTS]

def reference_observations():
    folder = OUT / "reference"
    folder.mkdir(parents=True, exist_ok=True)
    host = folder / "reference-host.exe"
    driver.run("cl.exe", "/nologo", "/std:c++17", "/EHsc", "/utf-8", "/DUNICODE", "/D_UNICODE",
        "/Fe:" + str(host), "/Fo:" + str(folder / "reference-host.obj"),
        ROOT / "tests/reader_f09_reference_host_20261031/reference_host.cpp",
        "/link", "/SUBSYSTEM:WINDOWS", "user32.lib", cwd=folder)
    reports = {}
    for observation, binary, argument in REFERENCE:
        directory = OUT / observation
        directory.mkdir(parents=True, exist_ok=True)
        command = list(map(str, (OUT / binary, host, directory, argument)))
        print("+ independent probe", observation, *command, flush=True)
        with (directory / "stdout.log").open("wb") as stdout, (directory / "stderr.log").open("wb") as stderr:
            process = subprocess.Popen(command, cwd=ROOT, stdout=stdout, stderr=stderr)
            process.wait()
        out_text = (directory / "stdout.log").read_text(encoding="utf-8", errors="replace")
        print(out_text, flush=True)
        print((directory / "stderr.log").read_text(encoding="utf-8", errors="replace"), flush=True)
        try:
            report = json.loads((directory / "report.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            report = dict(passed=False, error="probe report missing or invalid")
        report["probe_returncode"] = process.returncode
        report["passed"] = process.returncode == 0 and report.get("passed") is True
        stages = [line for line in out_text.splitlines() if line.startswith(("F09-NATIVE", "F09-STAGE"))]
        # F09-STAGE <name>; F09-NATIVE <utc> pid=<n> <name>.
        if not stages:
            report["last_stage"] = None
        elif stages[-1].startswith("F09-STAGE"):
            report["last_stage"] = stages[-1].split(" ", 1)[-1]
        else:
            report["last_stage"] = stages[-1].split(" ", 3)[-1]
        if process.returncode != 0 and (directory / "host.pid").exists():
            pid = (directory / "host.pid").read_text().strip()
            assert pid.isdecimal() and int(pid) > 0
            cleanup = subprocess.run(["taskkill", "/PID", pid, "/T", "/F"], capture_output=True)
            report["failed_probe_host_cleanup_returncode"] = cleanup.returncode
            (directory / "cleanup.log").write_bytes(cleanup.stdout + cleanup.stderr)
        hr = report.get("method_hresult")
        print("F09-OBSERVATION", json.dumps(dict(observation=observation, consumer=binary, argument=argument,
            returncode=process.returncode, returncode_hex="0x%08X" % (process.returncode & 0xffffffff),
            passed=report["passed"], last_stage=report["last_stage"],
            method_hresult_hex=None if hr is None else "0x%08X" % (hr & 0xffffffff))), flush=True)
        (directory / "observation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        reports[observation] = report
    (OUT / "reference-host.json").write_text(json.dumps(dict(reports=reports,
        host_sha256=hashlib.sha256(host.read_bytes()).hexdigest(),
        source_sha256=hashlib.sha256((ROOT / "tests/reader_f09_reference_host_20261031/reference_host.cpp").read_bytes()).hexdigest(),
        consumers={b: hashlib.sha256((OUT / b).read_bytes()).hexdigest() for b in sorted({r[1] for r in REFERENCE})},
        retained_failure_runs_added=[41170051294, 41170867473, 41171939136], diagnostic_only=True,
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
        # Only the frozen final aggregate assertion lets the later comparisons run.
        if not (OUT / "verdict.json").exists():
            raise
        frozen_failure = failure
    hd.extra_observations()
    hc.control_observations()
    reference_observations()
    if frozen_failure is not None:
        raise frozen_failure
    sys.exit(0)
