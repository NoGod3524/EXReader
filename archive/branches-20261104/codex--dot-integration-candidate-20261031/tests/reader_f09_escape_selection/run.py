# SPDX-License-Identifier: MIT
"""Actions-only native baseline/candidate event regression; not full F09 acceptance."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone
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
               "tests/reader_f09_escape_selection/run.py", ".github/workflows/reader-f09-escape-selection.yml",
               "tests/reader_f09_escape_selection/provider_diagnostics.inc",
               "docs/reader-total-progress/DOT_F09_NATIVE_DIAGNOSTIC_20261031.md"}
    changed = set(subprocess.check_output(["git", "diff", "--name-only", BASE, "HEAD"], cwd=ROOT, text=True).splitlines())
    assert changed == allowed, changed
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "source.json").write_text(json.dumps(dict(source=actual, base=BASE,
        run=os.environ["GITHUB_RUN_ID"], attempt=os.environ["GITHUB_RUN_ATTEMPT"],
        formal_f09_accepted=False, screen_reader_verified=False), indent=2))

def diagnostic_overlay(source):
    target = source / "apps/reader/desktop/windows_accessibility.inc"
    original_bytes = target.read_bytes()
    overlay_bytes = (ROOT / "tests/reader_f09_escape_selection/provider_diagnostics.inc").read_bytes()
    original = original_bytes.decode("utf-8").replace("\r\n", "\n")
    overlay = overlay_bytes.decode("utf-8").replace("\r\n", "\n")
    anchor = "/* Private interface id:"
    assert original.count(anchor) == 1
    content = original.replace(anchor, overlay + "\n" + anchor, 1)
    entry = """static HRESULT STDMETHODCALLTYPE host_a11y_range_text(ITextRangeProvider *self, int max, BSTR *out) {
  host_a11y_range *range = (host_a11y_range *)self;
  const host_a11y_snapshot *snapshot = range->snapshot;
  int from, to, at, count;
"""
    assert content.count(entry) == 1
    traced_entry = entry.replace("  const host_a11y_snapshot *snapshot = range->snapshot;", '  F09_TRACE(NULL,"entry-before-dereference",max,S_OK);\n  const host_a11y_snapshot *snapshot = range->snapshot;')
    content = content.replace(entry, traced_entry + '  F09_TRACE(range,"metadata",max,S_OK);\n', 1)
    old = """  *out = SysAllocStringLen(snapshot->text + from, (UINT)(to - from));
  return *out ? S_OK : E_OUTOFMEMORY;
}"""
    new = """  *out = SysAllocStringLen(snapshot->text + from, (UINT)(to - from));
  F09_TRACE(range,"return",max,*out ? S_OK : E_OUTOFMEMORY);
  return *out ? S_OK : E_OUTOFMEMORY;
}"""
    assert content.count(old) == 1
    content = content.replace(old, new, 1)
    # Observe real ownership calls only: no extra QI/AddRef/Release for diagnosis.
    patches = [
        ('static HRESULT STDMETHODCALLTYPE host_a11y_range_query(ITextRangeProvider *self, REFIID id, void **out) {\n',
         'static HRESULT STDMETHODCALLTYPE host_a11y_range_query(ITextRangeProvider *self, REFIID id, void **out) {\n'
         '  F09_TRACE((host_a11y_range*)self,IsEqualIID(id,&IID_IUnknown)?"qi-iunknown":IsEqualIID(id,&IID_ITextRangeProvider)?"qi-text-range":IsEqualIID(id,&host_a11y_range_iid)?"qi-private":"qi-other",0,S_OK);\n'),
        ('  return (ULONG)InterlockedIncrement(&range->refs);\n',
         '  LONG incremented=InterlockedIncrement(&range->refs);\n'
         '  F09_TRACE(range,"addref",incremented,S_OK);\n'
         '  return (ULONG)incremented;\n'),
        ('  left = InterlockedDecrement(&range->refs);\n',
         '  F09_TRACE(range,"release-before",0,S_OK);\n'
         '  left = InterlockedDecrement(&range->refs);\n'
         '  F09_COUNT(range,left);\n'),
        ('  range->end = end;\n  return range;\n',
         '  range->end = end;\n  F09_TRACE(range,"created",0,S_OK);\n  return range;\n'),
        ('  slot[0] = &range->iface;\n  SafeArrayUnaccessData(array);\n  *out = array;\n',
         '  slot[0] = &range->iface;\n  SafeArrayUnaccessData(array);\n  F09_ARRAY(array,range);\n  *out = array;\n')
    ]
    for before, after in patches:
        assert content.count(before) == 1, before
        content = content.replace(before, after, 1)
    target.write_text(content, encoding="utf-8")
    return dict(original_sha256=hashlib.sha256(original_bytes).hexdigest(),
                compiled_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                overlay_sha256=hashlib.sha256(overlay_bytes).hexdigest(),
                macro="EXR_F09_DIAGNOSTICS=1", test_overlay=True)

def crash_events(directory, pids, started):
    # Event IDs/fields only; never Message, credential material, or memory dump.
    ids = ",".join(str(p) for p in pids)
    script = r"""
$ErrorActionPreference='Stop'
$start=[DateTime]::Parse('__START__').ToUniversalTime()
$end=[DateTime]::Parse('__END__').ToUniversalTime()
$ids=@(__IDS__)
$rows=@()
try {
  $events=Get-WinEvent -FilterHashtable @{LogName='Application';Id=1000;StartTime=$start;EndTime=$end}
  foreach($event in $events){
    $xml=[xml]$event.ToXml();$data=@{}
    foreach($item in $xml.Event.EventData.Data){$data[[string]$item.Name]=[string]$item.'#text'}
    $raw=$data['ProcessId'];$pidNumber=0
    if($raw -match '^0x'){$pidNumber=[Convert]::ToInt32($raw.Substring(2),16)}
    elseif($raw){$pidNumber=[int]$raw}
    if($ids -contains $pidNumber){
      $rows+=@{pid=$pidNumber;utc=$event.TimeCreated.ToUniversalTime().ToString('o');
               app=$data['AppName'];module=$data['ModuleName'];exception_code=$data['ExceptionCode'];fault_offset=$data['FaultingOffset']}
    }
  }
  @{events=$rows;available=$true;missing=($rows.Count -eq 0)}|ConvertTo-Json -Depth 5
} catch { @{events=@();available=$false;error_type=$_.Exception.GetType().FullName}|ConvertTo-Json }
""".replace("__START__", started).replace("__END__", datetime.now(timezone.utc).isoformat()).replace("__IDS__", ids)
    result = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], capture_output=True)
    (directory / "windows-events.json").write_bytes(result.stdout)
    print("F09-EVENTS", result.stdout.decode("utf-8", errors="replace"), flush=True)

def main():
    guard()
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
    reports = {}
    for label, expectation in (("baseline", "absent"), ("candidate", "present")):
        directory = OUT / label
        directory.mkdir(parents=True, exist_ok=True)
        command = list(map(str, (probe, packages[label], directory, expectation)))
        print("+ independent probe", label, *command, flush=True)
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
            print("F09-PROVIDER", label, (directory / "provider.log").read_text(encoding="utf-8", errors="replace"), flush=True)
        reports[label] = report
        (directory / "observation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    passed = all(r["passed"] for r in reports.values())
    (OUT / "verdict.json").write_text(json.dumps(dict(passed=passed, reports=reports,
        retained_failure_runs=[41152293447,41155749004], diagnostic_only=True, overlays=overlays,
        hashes={k: hashlib.sha256(v.read_bytes()).hexdigest() for k,v in packages.items()},
        formal_f09_accepted=False, screen_reader_verified=False), indent=2))
    assert passed, "one or both independent native observations failed; retained as failure"
if __name__ == "__main__":
    main()
