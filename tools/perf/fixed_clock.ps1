param([Parameter(Mandatory)][string]$Output, [int]$Cpu = 2, [int]$Runs = 5,
    [string]$Build = 'evidence/perf-gate-20261107/build',
    [string]$Font = 'C:/Users/Oscar/exr-deps/reader-font/Reader.otf',
    [double]$IdleCpuMax = 5, [double]$IdleTimeout = 15)
$ErrorActionPreference = 'Stop'
if (Test-Path -LiteralPath $Output) { throw 'Refusing to overwrite a session' }
$settings = @('PROCTHROTTLEMIN', 'PROCTHROTTLEMAX', 'PERFBOOSTMODE')
$original = @{}
foreach ($setting in $settings) {
    $query = powercfg /qh SCHEME_CURRENT SUB_PROCESSOR $setting | Out-String
    if ($LASTEXITCODE) { throw "Cannot read $setting" }
    $indices = [regex]::Matches($query, '0x([0-9a-fA-F]{8})')
    if ($indices.Count -lt 2) { throw "Cannot parse AC/DC indices for $setting" }
    $original[$setting] = [Convert]::ToInt32($indices[$indices.Count-2].Groups[1].Value, 16)
}
$sessionParent = Split-Path -Parent $Output
$sessionName = Split-Path -Leaf $Output
$original | ConvertTo-Json | Set-Content "$sessionParent/$sessionName-power-original.json" -Encoding utf8
try {
    foreach ($pair in @(@('PROCTHROTTLEMIN',100), @('PROCTHROTTLEMAX',100), @('PERFBOOSTMODE',0))) {
        powercfg /setacvalueindex SCHEME_CURRENT SUB_PROCESSOR $pair[0] $pair[1]
        if ($LASTEXITCODE) { throw "Cannot set $($pair[0])" }
    }
    powercfg /setactive SCHEME_CURRENT
    if ($LASTEXITCODE) { throw 'Cannot activate fixed-clock settings' }
    & "$PSScriptRoot/preflight.ps1" -Output "$sessionParent/$sessionName-preflight.json"
    python "$PSScriptRoot/gate_capture.py" --binary "$Build/e1-probe.exe" --build $Build --font $Font --output $Output --runs $Runs --max-batches 1 --interval 1 --cpu $Cpu --priority high --idle-cpu-max $IdleCpuMax --idle-timeout $IdleTimeout
    $captureExit = $LASTEXITCODE
    & "$PSScriptRoot/preflight.ps1" -Output "$sessionParent/$sessionName-postflight.json" -Seconds 3
} finally {
    foreach ($setting in $settings) {
        powercfg /setacvalueindex SCHEME_CURRENT SUB_PROCESSOR $setting $original[$setting]
        if ($LASTEXITCODE) { throw "RESTORE FAILED: $setting; use saved power-original.json" }
    }
    powercfg /setactive SCHEME_CURRENT
    if ($LASTEXITCODE) { throw 'RESTORE FAILED: activate saved scheme' }
    $restored = @{}
    foreach ($setting in $settings) {
        $query = powercfg /qh SCHEME_CURRENT SUB_PROCESSOR $setting | Out-String
        if ($LASTEXITCODE) { throw "Cannot verify restored $setting" }
        $indices = [regex]::Matches($query, '0x([0-9a-fA-F]{8})')
        $restored[$setting] = [Convert]::ToInt32($indices[$indices.Count-2].Groups[1].Value, 16)
        if ($restored[$setting] -ne $original[$setting]) { throw "RESTORE MISMATCH: $setting" }
    }
    $restored | ConvertTo-Json | Set-Content "$sessionParent/$sessionName-power-restored.json" -Encoding utf8
}
exit $captureExit
