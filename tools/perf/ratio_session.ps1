param([Parameter(Mandatory)][string]$Output,
      [Parameter(Mandatory)][string]$Build,
      [Parameter(Mandatory)][string]$Font, [int]$Cpu = 3)
$ErrorActionPreference = 'Stop'
$settings = @('PROCTHROTTLEMIN', 'PROCTHROTTLEMAX', 'PERFBOOSTMODE')
function Read-Policy {
    $values = @{}
    foreach ($setting in $settings) {
        $query = powercfg /qh SCHEME_CURRENT SUB_PROCESSOR $setting | Out-String
        if ($LASTEXITCODE) { throw "Cannot read $setting" }
        $indices = [regex]::Matches($query, '0x([0-9a-fA-F]{8})')
        if ($indices.Count -lt 2) { throw "Cannot parse $setting" }
        $values[$setting] = [Convert]::ToInt32($indices[$indices.Count-2].Groups[1].Value, 16)
    }
    return $values
}
$original = Read-Policy
$original | ConvertTo-Json | Set-Content "$Output/power-original.json" -Encoding utf8
try {
    foreach ($pair in @(@('PROCTHROTTLEMIN',100), @('PROCTHROTTLEMAX',100), @('PERFBOOSTMODE',0))) {
        powercfg /setacvalueindex SCHEME_CURRENT SUB_PROCESSOR $pair[0] $pair[1]
        if ($LASTEXITCODE) { throw "Cannot set $($pair[0])" }
    }
    powercfg /setactive SCHEME_CURRENT
    if ($LASTEXITCODE) { throw 'Cannot activate policy' }
    & "$PSScriptRoot/preflight.ps1" -Output "$Output/preflight.json" -Seconds 10
    python -X utf8 "$PSScriptRoot/ratio_capture.py" capture --build $Build --font $Font --output "$Output/normal" --cpu $Cpu *> "$Output/normal-console.txt"
    if ($LASTEXITCODE) { throw 'Normal capture failed; raw files retained' }
    Add-Content "$Output/PERF2-OUT.txt" 'Step B: completed five normal runs, 19 books x 16 turns per run; all raw measurements retained.'
    python -X utf8 "$PSScriptRoot/ratio_capture.py" freeze "$Output/normal" "$Output/ratio-policy.json" *> "$Output/freeze-console.txt"
    Add-Content "$Output/PERF2-OUT.txt" "Step C: froze ratio tiers before loaded candidate; eligibility exit code $LASTEXITCODE. No thresholds adjusted to candidate."
    python -X utf8 "$PSScriptRoot/ratio_capture.py" capture --build $Build --font $Font --output "$Output/loaded" --cpu $Cpu --stress *> "$Output/loaded-console.txt"
    if ($LASTEXITCODE) { throw 'Loaded capture failed; raw files retained' }
    Add-Content "$Output/PERF2-OUT.txt" 'Step C: completed five loaded runs with one equal-priority busy worker on the same logical CPU; worker stopped by finally.'
    python -X utf8 "$PSScriptRoot/ratio_capture.py" check "$Output/ratio-policy.json" "$Output/loaded" "$Output/loaded-check.json" *> "$Output/check-console.txt"
    Add-Content "$Output/PERF2-OUT.txt" "Step C: independent loaded candidate audit exit code $LASTEXITCODE (E3 remains advisory)."
    & "$PSScriptRoot/preflight.ps1" -Output "$Output/postflight.json" -Seconds 3
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
    Add-Content "$Output/PERF2-OUT.txt" 'Power policy restored and read back successfully.'
}
