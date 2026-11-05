# Independent integration entry; original guard/main remain frozen, not invoked.
import hashlib,json,os,subprocess,sys,importlib.util
from pathlib import Path
from datetime import datetime,timezone
from guard import guard as integration_guard
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location("frozen_f09",ROOT/"tests/reader_f09_escape_routing/run.py")
original=importlib.util.module_from_spec(spec);spec.loader.exec_module(original)
BASE=original.BASE
OUT=original.OUT
run=original.run
diagnostic_overlay=original.diagnostic_overlay
crash_events=original.crash_events
def integrated_main():
    integration_guard()
    OUT.mkdir(parents=True,exist_ok=True)
    prefix=OUT/"original-hash"
    run("cmake","-S",ROOT/"extras/opds","-B",OUT/"hash-build","-G","Ninja","-DCMAKE_BUILD_TYPE=Release","-DEXREADER_OPDS_HASH_ONLY=ON","-DCMAKE_INSTALL_PREFIX="+prefix.resolve().as_posix())
    run("cmake","--build",OUT/"hash-build","--parallel","4")
    run("cmake","--install",OUT/"hash-build")
    os.environ["EXREADER_ORIGINAL_HASH_PREFIX"]=prefix.resolve().as_posix()
    sdk = OUT / "sdk"
    run("cmake", "--preset", "reading-library", "-B", OUT / "sdk-build", "-DCMAKE_INSTALL_PREFIX=" + str(sdk))
    run("cmake", "--build", OUT / "sdk-build", "--parallel", "4")
    run("cmake", "--install", OUT / "sdk-build")
    baseline = OUT / "baseline-source"
    run("git", "worktree", "add", "--detach", baseline, BASE)
    candidate = OUT / "candidate-source"
    run("git", "worktree", "add", "--detach", candidate, os.environ["GITHUB_SHA"])
    packages = {}
    overlays = {}
    for label, source in (("baseline", baseline), ("candidate", candidate)):
        overlays[label] = diagnostic_overlay(source)
        build = OUT / (label + "-build")
        run("cmake", "-S", source / "apps/reader/desktop", "-B", build, "-G", "Ninja",
            "-DCMAKE_BUILD_TYPE=Release", "-DEXR_SDK=" + str(sdk), "-DEXR_SDK_VERSION=3.42.0",
            "-DCMAKE_C_FLAGS=-DEXR_F09_DIAGNOSTICS=1")
        run("cmake", "--build", build, "--target", "EXReaderProduct", "--parallel", "4")
        package = OUT / (label + "-package")
        run(sys.executable, source / "tools/build_windows_host.py", "--sdk", sdk,
            "--binary", build / "EXReaderProduct.exe", "--output", package, "--static-reading", cwd=source)
        preserved = json.loads((package / "report.json").read_text())
        assert preserved["passed"] is True and preserved["checks"] >= 26, preserved
        packages[label] = package / "EXReader" / "EXReader.exe"
    assert overlays["baseline"] == overlays["candidate"], "provider overlays must be identical"
    (OUT / "diagnostic-overlay.json").write_text(json.dumps(overlays, indent=2), encoding="utf-8")
    framework = Path(os.environ["WINDIR"]) / "Microsoft.NET/Framework64/v4.0.30319"
    probe = OUT / "probe.exe"
    run(framework / "csc.exe", "/nologo", "/target:exe", "/out:" + str(probe),
        "/r:" + str(framework / "WPF/UIAutomationClient.dll"),
        "/r:" + str(framework / "WPF/UIAutomationTypes.dll"),
        "/r:" + str(framework / "WPF/WindowsBase.dll"),
        "/r:" + str(framework / "System.Web.Extensions.dll"),
        ROOT / "tests/reader_f09_escape_selection/probe.cs")
    native = OUT / "native-probe.exe"
    run("cl.exe","/nologo","/std:c++17","/EHsc","/utf-8","/DUNICODE","/D_UNICODE",
        "/Fe:"+str(native),"/Fo:"+str(OUT/"native-probe.obj"),
        ROOT/"tests/reader_f09_consumer_compare/native_probe.cpp",
        "/link","ole32.lib","oleaut32.lib","user32.lib","uiautomationcore.lib","uuid.lib",cwd=OUT)
    probes = {"managed":probe,"native":native}
    (OUT/"consumers.json").write_text(json.dumps({
        k:dict(binary_sha256=hashlib.sha256(v.read_bytes()).hexdigest(),
               source_sha256=hashlib.sha256((ROOT/("tests/reader_f09_escape_selection/probe.cs" if k=="managed" else "tests/reader_f09_consumer_compare/native_probe.cpp")).read_bytes()).hexdigest())
        for k,v in probes.items()},indent=2))
    reports = {}
    observations = [(label+"-"+consumer,label,expectation,consumer)
        for consumer in ("managed","native")
        for label,expectation in (("baseline","absent"),("candidate","present"))]
    for observation, label, expectation, consumer in observations:
        directory = OUT / observation
        directory.mkdir(parents=True, exist_ok=True)
        command = list(map(str, (probes[consumer], packages[label], directory, expectation)))
        print("+ independent probe", observation, *command, flush=True)
        started = datetime.now(timezone.utc).isoformat()
        with (directory / "stdout.log").open("wb") as stdout, (directory / "stderr.log").open("wb") as stderr:
            process = subprocess.Popen(command, cwd=ROOT, stdout=stdout, stderr=stderr)
            process.wait()
        result = process
        pids = [process.pid]
        if (directory / "host.pid").exists():
            pids.append(int((directory / "host.pid").read_text().strip()))
        if result.returncode != 0:
            crash_events(directory, pids, started)
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
        if (directory / "provider.log").exists():
            print("F09-PROVIDER", observation, (directory / "provider.log").read_text(encoding="utf-8", errors="replace"), flush=True)
        report["consumer"] = consumer
        report["host_sha256"] = hashlib.sha256(packages[label].read_bytes()).hexdigest()
        reports[observation] = report
        (directory / "observation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    assert len(reports) == 4
    passed = all(r["passed"] for r in reports.values())
    (OUT / "verdict.json").write_text(json.dumps(dict(passed=passed, reports=reports,
        retained_failure_runs=[41152293447,41155749004,41156727928,41157569248,41159097889,41159620416], diagnostic_only=True, overlays=overlays,
        hashes={k: hashlib.sha256(v.read_bytes()).hexdigest() for k,v in packages.items()},
        formal_f09_accepted=False, screen_reader_verified=False), indent=2))
    assert passed, "one or more of four independent consumer observations failed; native cannot override managed"

if __name__=="__main__":integrated_main()
