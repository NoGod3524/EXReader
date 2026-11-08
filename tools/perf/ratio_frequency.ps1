param([Parameter(Mandatory)][string]$Output,
      [Parameter(Mandatory)][string]$Build,
      [int]$Cpu = 3, [ValidateRange(1,100)][int]$CpuMax = 50)
$ErrorActionPreference = 'Stop'
if ((Test-Path -LiteralPath $Output) -or (Test-Path -LiteralPath "$Output-frequency-power-original.json")) {
    throw 'Refusing to overwrite a frequency experiment'
}
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
$original | ConvertTo-Json | Set-Content "$Output-frequency-power-original.json" -Encoding utf8
try {
    foreach ($pair in @(@('PROCTHROTTLEMIN',$CpuMax), @('PROCTHROTTLEMAX',$CpuMax), @('PERFBOOSTMODE',0))) {
        powercfg /setacvalueindex SCHEME_CURRENT SUB_PROCESSOR $pair[0] $pair[1]
        if ($LASTEXITCODE) { throw "Cannot set $($pair[0])" }
    }
    powercfg /setactive SCHEME_CURRENT
    if ($LASTEXITCODE) { throw 'Cannot activate frequency limit' }
    @{requested_min_pct=$CpuMax; requested_max_pct=$CpuMax; boost=0; cpu=$Cpu} |
        ConvertTo-Json | Set-Content "$Output-frequency-request.json" -Encoding utf8
    & "$PSScriptRoot/preflight.ps1" -Output "$Output-frequency-preflight.json" -Seconds 3
    $env:E1_CPU = [string]$Cpu
    $env:E1_PRIORITY = 'high'
    & "$Build/perf-reference.exe" *> "$Output-reference-pilot.json"
    if ($LASTEXITCODE) { throw 'Frequency pilot failed' }
    & "$PSScriptRoot/preflight.ps1" -Output "$Output-frequency-postflight.json" -Seconds 3
} finally {
    foreach ($setting in $settings) {
        powercfg /setacvalueindex SCHEME_CURRENT SUB_PROCESSOR $setting $original[$setting]
        if ($LASTEXITCODE) { throw "RESTORE FAILED: $setting" }
    }
    powercfg /setactive SCHEME_CURRENT
    if ($LASTEXITCODE) { throw 'RESTORE FAILED: activate policy' }
    $restored = Read-Policy
    $restored | ConvertTo-Json | Set-Content "$Output-frequency-power-restored.json" -Encoding utf8
    foreach ($setting in $settings) {
        if ($restored[$setting] -ne $original[$setting]) { throw "RESTORE MISMATCH: $setting" }
    }
}
