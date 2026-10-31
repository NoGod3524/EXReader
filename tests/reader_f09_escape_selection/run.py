# SPDX-License-Identifier: MIT
"""Actions-only native baseline/candidate event regression; not full F09 acceptance."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
ROOT = Path(__file__).resolve().parents[2]
BASE = "8f8acf3234cba747165f001c0c96efe1b911e6ad"
OUT = ROOT / "build/f09-escape"
OLD = '''        case VK_ESCAPE:
          selection_clear();
          set_status(L"已清除选择。");
          return 0;'''
NEW = '''        case VK_ESCAPE: {
          int selection_changed = g.selection.active;
          selection_clear();
          if (selection_changed) host_a11y_page_changed(1);
          set_status(L"已清除选择。");
          return 0;
        }'''
def run(*argv, cwd=ROOT):
    print("+", *map(str, argv), flush=True)
    subprocess.run(list(map(str, argv)), cwd=cwd, check=True)
def guard():
    assert os.environ.get("GITHUB_ACTIONS") == "true", "Actions only"
    actual = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    assert actual == os.environ["GITHUB_SHA"]
    before = subprocess.check_output(["git", "show", BASE + ":examples/reader.c"], cwd=ROOT).decode()
    assert before.count(OLD) == 1
    assert (ROOT / "examples/reader.c").read_text(encoding="utf-8") == before.replace(OLD, NEW, 1)
    allowed = {"examples/reader.c", "tests/reader_f09_escape_selection/probe.cs",
               "tests/reader_f09_escape_selection/run.py", ".github/workflows/reader-f09-escape-selection.yml"}
    changed = set(subprocess.check_output(["git", "diff", "--name-only", BASE, "HEAD"], cwd=ROOT, text=True).splitlines())
    assert changed == allowed, changed
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "source.json").write_text(json.dumps(dict(source=actual, base=BASE,
        run=os.environ["GITHUB_RUN_ID"], attempt=os.environ["GITHUB_RUN_ATTEMPT"],
        formal_f09_accepted=False, screen_reader_verified=False), indent=2))
def main():
    guard()
    sdk = OUT / "sdk"
    run("cmake", "--preset", "reading-library", "-B", OUT / "sdk-build", "-DCMAKE_INSTALL_PREFIX=" + str(sdk))
    run("cmake", "--build", OUT / "sdk-build", "--parallel", "4")
    run("cmake", "--install", OUT / "sdk-build")
    baseline = OUT / "baseline-source"
    run("git", "worktree", "add", "--detach", baseline, BASE)
    packages = {}
    for label, source in (("baseline", baseline), ("candidate", ROOT)):
        build = OUT / (label + "-build")
        run("cmake", "-S", source / "apps/reader/desktop", "-B", build, "-G", "Ninja",
            "-DCMAKE_BUILD_TYPE=Release", "-DEXR_SDK=" + str(sdk), "-DEXR_SDK_VERSION=3.42.0")
        run("cmake", "--build", build, "--target", "EXReaderProduct", "--parallel", "4")
        package = OUT / (label + "-package")
        run(sys.executable, source / "tools/build_windows_host.py", "--sdk", sdk,
            "--binary", build / "EXReaderProduct.exe", "--output", package, "--static-reading", cwd=source)
        preserved = json.loads((package / "report.json").read_text())
        assert preserved["passed"] is True and preserved["checks"] >= 26, preserved
        packages[label] = package / "EXReader" / "EXReader.exe"
    framework = Path(os.environ["WINDIR"]) / "Microsoft.NET/Framework64/v4.0.30319"
    probe = OUT / "probe.exe"
    run(framework / "csc.exe", "/nologo", "/target:exe", "/out:" + str(probe),
        "/r:" + str(framework / "WPF/UIAutomationClient.dll"),
        "/r:" + str(framework / "WPF/UIAutomationTypes.dll"),
        "/r:" + str(framework / "WPF/WindowsBase.dll"),
        "/r:" + str(framework / "System.Web.Extensions.dll"),
        ROOT / "tests/reader_f09_escape_selection/probe.cs")
    reports = {}
    for label, expectation in (("baseline", "absent"), ("candidate", "present")):
        directory = OUT / label
        directory.mkdir(parents=True, exist_ok=True)
        command = list(map(str, (probe, packages[label], directory, expectation)))
        print("+ independent probe", label, *command, flush=True)
        with (directory / "stdout.log").open("wb") as stdout, (directory / "stderr.log").open("wb") as stderr:
            result = subprocess.run(command, cwd=ROOT, stdout=stdout, stderr=stderr)
        print((directory / "stdout.log").read_text(encoding="utf-8", errors="replace"), flush=True)
        print((directory / "stderr.log").read_text(encoding="utf-8", errors="replace"), flush=True)
        report_file = directory / "report.json"
        try:
            report = json.loads(report_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            report = dict(passed=False, error="probe report missing or invalid")
        report["probe_returncode"] = result.returncode
        report["passed"] = result.returncode == 0 and report.get("passed") is True
        # A native crash bypasses the C# finally. Clean only this probe's newly launched host.
        if result.returncode != 0 and (directory / "host.pid").exists():
            pid = (directory / "host.pid").read_text().strip()
            assert pid.isdecimal() and int(pid) > 0
            cleanup = subprocess.run(["taskkill", "/PID", pid, "/T", "/F"], capture_output=True)
            report["failed_probe_host_cleanup_returncode"] = cleanup.returncode
            (directory / "cleanup.log").write_bytes(cleanup.stdout + cleanup.stderr)
        reports[label] = report
        (directory / "observation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    passed = all(r["passed"] for r in reports.values())
    (OUT / "verdict.json").write_text(json.dumps(dict(passed=passed, reports=reports,
        retained_failure_run=41152293447, diagnostic_only=True,
        hashes={k: hashlib.sha256(v.read_bytes()).hexdigest() for k,v in packages.items()},
        formal_f09_accepted=False, screen_reader_verified=False), indent=2))
    assert passed, "one or both independent native observations failed; retained as failure"
if __name__ == "__main__":
    main()
