# SPDX-License-Identifier: MIT
"""Actions-only F09 rerun of the frozen visible-range driver with a corrected crash-event collector.

Only the guard, output directory and Windows event collection differ. The eight observations,
26-check suites, assertions and timeouts are the byte-frozen visible-range driver's own.
No debugger, no dump, no memory, register or parameter reads; not full F09 acceptance.
"""
import base64
import importlib.util
import json
import os
from pathlib import Path
import subprocess
ROOT = Path(__file__).resolve().parents[2]
PARENT = "068bf454388b2576883ef8b8f60f80be878faf58"
VISIBLE = ROOT / "tests/reader_f09_visible_range_20261031/run.py"
spec = importlib.util.spec_from_file_location("f09_visible_driver", VISIBLE)
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)
OUT = ROOT / "build/f09-av-stack"
NEW_PATHS = {"tests/reader_f09_av_stack_20261031/run.py",
             ".github/workflows/dot-f09-av-stack-20261031.yml",
             "docs/reader-total-progress/DOT_F09_AV_STACK_20261031.md"}
FROZEN = ("examples/reader.c", "apps/reader/desktop/windows_accessibility.inc",
          "tests/reader_f09_escape_selection/probe.cs",
          "tests/reader_f09_escape_selection/provider_diagnostics.inc",
          "tests/reader_f09_consumer_compare/native_probe.cpp",
          "tests/reader_f09_legacy_uia/legacy_probe.cpp",
          "tests/reader_f09_legacy_uia/run.py",
          "tests/reader_f09_visible_range_20261031/visible_probe.cpp",
          "tests/reader_f09_visible_range_20261031/run.py")
def git(*argv):
    return subprocess.check_output(["git", *argv], cwd=ROOT, text=True).strip()
def guard():
    assert os.environ.get("GITHUB_ACTIONS") == "true", "Actions only"
    actual = git("rev-parse", "HEAD")
    assert actual == os.environ["GITHUB_SHA"]
    delta = set(git("diff", "--name-only", PARENT, "HEAD").splitlines())
    assert delta == NEW_PATHS, delta
    for frozen in FROZEN:
        assert git("hash-object", "--path=" + frozen, frozen) == git("rev-parse", PARENT + ":" + frozen), frozen
    # reader.c is byte-frozen to PARENT, whose run fb3e95ac already asserted the two routing hunks over BASE.
    before = subprocess.check_output(["git", "show", driver.BASE + ":examples/reader.c"], cwd=ROOT).decode()
    assert before.count(driver.OLD) == 1
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "source.json").write_text(json.dumps(dict(source=actual, parent=PARENT, base=driver.BASE,
        run=os.environ["GITHUB_RUN_ID"], attempt=os.environ["GITHUB_RUN_ATTEMPT"],
        retained_failure_runs=[41152293447, 41155749004, 41156727928, 41157569248, 41159097889,
                               41159620416, 41160570582, 41161587756, 41162331946, 41165411704],
        debugger=False, dump=False, formal_f09_accepted=False, screen_reader_verified=False), indent=2))

EVENTS = r"""
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=New-Object System.Text.UTF8Encoding($false)
$start=[DateTime]::Parse('__START__').ToUniversalTime()
$ids=@(__IDS__)
$apps=@('probe.exe','native-probe.exe','legacy-probe.exe','visible-probe.exe','EXReader.exe')
$named1000=@('AppName','AppVersion','AppTimeStamp','ModuleName','ModuleVersion','ModuleTimeStamp','ExceptionCode','FaultingOffset','ProcessId')
$wer=$null
try{$wer=[string](Get-Service -Name WerSvc).Status}catch{$wer='query-failed:'+$_.Exception.GetType().FullName}
$crash=@();$report=@();$errors=@();$polls=0
$deadline=(Get-Date).AddSeconds(30)
do{
  $polls++;$crash=@();$report=@()
  try{
    $events=Get-WinEvent -FilterHashtable @{LogName='Application';Id=@(1000,1001);StartTime=$start}
    foreach($event in $events){
      $values=@($event.Properties|ForEach-Object{[string]$_.Value})
      if($event.Id -eq 1000){
        $data=@{};for($i=0;$i -lt $named1000.Count -and $i -lt $values.Count;$i++){$data[$named1000[$i]]=$values[$i]}
        $raw=$data['ProcessId'];$pidNumber=0
        if($raw -match '^0x'){$pidNumber=[Convert]::ToInt32($raw.Substring(2),16)}elseif($raw -match '^\d+$'){$pidNumber=[int]$raw}
        if($ids -contains $pidNumber){
          $crash+=@{pid=$pidNumber;utc=$event.TimeCreated.ToUniversalTime().ToString('o');provider=$event.ProviderName;
                    app=$data['AppName'];module=$data['ModuleName'];module_version=$data['ModuleVersion'];
                    exception_code=$data['ExceptionCode'];fault_offset=$data['FaultingOffset']}
        }
      } elseif($event.Id -eq 1001 -and $values.Count -ge 13 -and $values[2] -eq 'APPCRASH' -and $apps -contains $values[5]){
        # WER bucket parameters P1,P4,P5,P7,P8 only: app, module, module version, code, offset.
        $report+=@{utc=$event.TimeCreated.ToUniversalTime().ToString('o');provider=$event.ProviderName;event_type=$values[2];
                   app=$values[5];module=$values[8];module_version=$values[9];exception_code=$values[11];fault_offset=$values[12]}
      }
    }
  }catch{$errors+=@{poll=$polls;error_type=$_.Exception.GetType().FullName;error=$_.Exception.Message}}
  if($crash.Count -gt 0){break}
  Start-Sleep -Milliseconds 1000
}while((Get-Date) -lt $deadline)
@{application_error_1000=$crash;wer_1001=$report;query_errors=$errors;polls=$polls;
  found=($crash.Count -gt 0);wer_service=$wer;window_start=$start.ToString('o');
  window_end=(Get-Date).ToUniversalTime().ToString('o')}|ConvertTo-Json -Depth 6
"""
def crash_events(directory, pids, started):
    # Named event fields only; never event Message, dumps, memory, registers or book text.
    script = EVENTS.replace("__START__", started).replace("__IDS__", ",".join(str(p) for p in pids))
    result = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand",
        base64.b64encode(script.encode("utf-16-le")).decode("ascii")], capture_output=True)
    (directory / "windows-events.json").write_bytes(result.stdout)
    (directory / "windows-events-collector.json").write_text(json.dumps(dict(returncode=result.returncode,
        pids=pids, stderr=result.stderr.decode("utf-8", errors="replace")), indent=2), encoding="utf-8")
    print("F09-EVENTS", json.dumps(dict(directory=directory.name, pids=pids, collector_returncode=result.returncode)),
          result.stdout.decode("utf-8", errors="replace"), flush=True)

if __name__ == "__main__":
    driver.OUT = OUT
    driver.guard = guard
    driver.crash_events = crash_events
    driver.main()
