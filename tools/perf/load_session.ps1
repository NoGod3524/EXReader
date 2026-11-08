param([Parameter(Mandatory)][string]$Output,
      [Parameter(Mandatory)][string]$Build,
      [Parameter(Mandatory)][string]$Font,
      [ValidateSet('diagnostic','sandwich')][string]$Mode = 'sandwich',
      [int]$Runs = 5, [int]$Cpu = 3)
$ErrorActionPreference = 'Stop'
if (Test-Path -LiteralPath $Output) { throw 'Refusing to overwrite session evidence' }
New-Item -ItemType Directory -Path $Output | Out-Null
$progressFile = Join-Path (Split-Path $Output) 'PERF3-OUT.txt'
$settings = @('PROCTHROTTLEMIN','PROCTHROTTLEMAX','PERFBOOSTMODE')
function Read-Policy {
    $values = @{}
    foreach ($setting in $settings) {
        $query = powercfg /qh SCHEME_CURRENT SUB_PROCESSOR $setting | Out-String
        if ($LASTEXITCODE) { throw "Cannot read $setting" }
        $indices = [regex]::Matches($query,'0x([0-9a-fA-F]{8})')
        if ($indices.Count -lt 2) { throw "Cannot parse $setting" }
        $values[$setting] = [Convert]::ToInt32($indices[$indices.Count-2].Groups[1].Value,16)
    }
    return $values
}
$original = Read-Policy
$original | ConvertTo-Json | Set-Content "$Output/power-original.json" -Encoding utf8
try {
    foreach ($pair in @(@('PROCTHROTTLEMIN',100),@('PROCTHROTTLEMAX',100),@('PERFBOOSTMODE',0))) {
        powercfg /setacvalueindex SCHEME_CURRENT SUB_PROCESSOR $pair[0] $pair[1]
        if ($LASTEXITCODE) { throw "Cannot set $($pair[0])" }
    }
    powercfg /setactive SCHEME_CURRENT
    if ($LASTEXITCODE) { throw 'Cannot activate policy' }
    & "$PSScriptRoot/preflight.ps1" -Output "$Output/preflight.json" -Seconds 3 -SkipPowerDump
    foreach ($level in @(@('none',0),@('medium',1),@('high',3))) {
        $name = $level[0]
        python -X utf8 "$PSScriptRoot/load_capture.py" capture --build $Build --font $Font --output "$Output/$name" --cpu $Cpu --runs $Runs --stress-workers $level[1] --load-mode $Mode *> "$Output/$name-console.txt"
        if ($LASTEXITCODE) { throw "$name capture failed; all attempted raw files retained" }
        Add-Content $progressFile "Step $Mode/$name complete: $Runs runs x 19 books x 16 sequential pages; workers=$($level[1]), raw retained."
        if ($Mode -eq 'sandwich' -and $name -eq 'none') {
            python -X utf8 "$PSScriptRoot/load_capture.py" freeze "$Output/none" "$Output/policy.json" *> "$Output/freeze-console.txt"
            Add-Content $progressFile "Froze thresholds BEFORE pressure candidates; eligibility exit=$LASTEXITCODE."
        } elseif ($Mode -eq 'sandwich') {
            python -X utf8 "$PSScriptRoot/load_capture.py" check "$Output/policy.json" "$Output/$name" "$Output/$name-check.json" *> "$Output/$name-check-console.txt"
            Add-Content $progressFile "Independent $name gate check exit=$LASTEXITCODE (advisory)."
        }
    }
    & "$PSScriptRoot/preflight.ps1" -Output "$Output/postflight.json" -Seconds 3 -SkipPowerDump
} finally {
    foreach ($setting in $settings) {
        powercfg /setacvalueindex SCHEME_CURRENT SUB_PROCESSOR $setting $original[$setting]
        if ($LASTEXITCODE) { throw "RESTORE FAILED: $setting" }
    }
    powercfg /setactive SCHEME_CURRENT
    if ($LASTEXITCODE) { throw 'RESTORE FAILED: activate scheme' }
    $restored = Read-Policy
    $restored | ConvertTo-Json | Set-Content "$Output/power-restored.json" -Encoding utf8
    foreach ($setting in $settings) {
        if ($restored[$setting] -ne $original[$setting]) { throw "RESTORE MISMATCH: $setting" }
    }
    Add-Content $progressFile "Step $Mode session: power policy restored and read back."
}
