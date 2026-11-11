# Test scheduling for this Windows checkout; no test limits are changed.
param(
  [string]$Build = 'build/y1/candidate',
  [string]$Log = 'evidence/y1-api-20261110/candidate-ctest-priority.txt'
)
$ErrorActionPreference = 'Stop'
[System.Diagnostics.Process]::GetCurrentProcess().PriorityClass = 'AboveNormal'
$stdout = Join-Path (Resolve-Path $Build) 'ctest-priority-stdout.txt'
$stderr = Join-Path (Resolve-Path $Build) 'ctest-priority-stderr.txt'
$run = Start-Process -FilePath (Get-Command ctest).Source -WindowStyle Hidden -PassThru `
  -ArgumentList @('--test-dir', $Build, '--output-on-failure', '-j', '4', '--output-log', $Log) `
  -RedirectStandardOutput $stdout -RedirectStandardError $stderr
Write-Output "CTest PID $($run.Id): AboveNormal scheduling for this task's process tree"
while (-not $run.HasExited) {
  $processes = Get-CimInstance Win32_Process
  $ids = [System.Collections.Generic.HashSet[int]]::new()
  [void]$ids.Add($run.Id)
  do {
    $added = $false
    foreach ($process in $processes) {
      if ($ids.Contains([int]$process.ParentProcessId) -and $ids.Add([int]$process.ProcessId)) { $added = $true }
    }
  } while ($added)
  foreach ($taskProcessId in $ids) {
    try { (Get-Process -Id $taskProcessId -ErrorAction Stop).PriorityClass = 'AboveNormal' } catch { }
  }
  Start-Sleep -Milliseconds 250
}
$run.WaitForExit()
Get-Content -LiteralPath $stdout -Tail 20
Get-Content -LiteralPath $stderr
exit $run.ExitCode
