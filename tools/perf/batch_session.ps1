param(
    [Parameter(Mandatory)][string]$Binary,
    [Parameter(Mandatory)][string]$Book,
    [Parameter(Mandatory)][string]$Font,
    [Parameter(Mandatory)][string]$Output,
    [ValidateRange(0,63)][int]$Cpu = 3,
    [ValidateSet(5)][int]$Runs = 5,
    [ValidateRange(1,10000)][int]$Turns = 20,
    [ValidateRange(1,100000)][int]$Warmup = 21,
    [string]$Reference
)
$ErrorActionPreference = 'Stop'
if (Test-Path -LiteralPath $Output) { throw 'Refusing to overwrite session evidence' }
$Binary = (Resolve-Path -LiteralPath $Binary).Path
$Book = (Resolve-Path -LiteralPath $Book).Path
$Font = (Resolve-Path -LiteralPath $Font).Path
if ($Reference) { $Reference = (Resolve-Path -LiteralPath $Reference).Path }

if (-not ('ExrBatchPower' -as [type])) {
    Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class ExrBatchPower {
    [StructLayout(LayoutKind.Sequential)]
    public struct Status {
        public byte ACLineStatus, BatteryFlag, BatteryLifePercent, SystemStatusFlag;
        public uint BatteryLifeTime, BatteryFullLifeTime;
    }
    [DllImport("kernel32.dll", SetLastError=true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static extern bool GetSystemPowerStatus(out Status status);
}
'@
}
$power = New-Object ExrBatchPower+Status
if (-not [ExrBatchPower]::GetSystemPowerStatus([ref]$power) -or $power.ACLineStatus -ne 1) {
    throw 'An AC-powered machine is required before changing the temporary AC policy'
}
New-Item -ItemType Directory -Path $Output | Out-Null
$Output = (Resolve-Path -LiteralPath $Output).Path
$settings = @('PROCTHROTTLEMIN', 'PROCTHROTTLEMAX', 'PERFBOOSTMODE')
function Invoke-PowerCfg([string[]]$PowerArgs) {
    $text = & powercfg @PowerArgs 2>&1 | Out-String
    $code = $LASTEXITCODE
    "[$([DateTime]::UtcNow.ToString('o'))] powercfg $($PowerArgs -join ' ') exit=$code`n$text" |
        Add-Content -LiteralPath "$Output/powercfg.txt" -Encoding utf8
    if ($code) { throw "powercfg failed ($code): $($PowerArgs -join ' ')" }
    return $text
}
function Get-ActiveScheme {
    $text = Invoke-PowerCfg -PowerArgs @('/getactivescheme')
    $match = [regex]::Match($text, '[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}')
    if (-not $match.Success) { throw 'Cannot parse active power scheme GUID' }
    return $match.Value.ToLowerInvariant()
}
function Read-AcPolicy([string]$Scheme) {
    $values = @{}
    foreach ($setting in $settings) {
        $text = Invoke-PowerCfg -PowerArgs @('/qh', $Scheme, 'SUB_PROCESSOR', $setting)
        $indices = [regex]::Matches($text, '0x([0-9a-fA-F]{8})')
        if ($indices.Count -lt 2) { throw "Cannot parse AC/DC indices for $setting" }
        $values[$setting] = [Convert]::ToInt32($indices[$indices.Count - 2].Groups[1].Value, 16)
    }
    return $values
}
function Capture-Batch([string]$Name, [string]$Exe, [int]$Pages) {
    if (-not [ExrBatchPower]::GetSystemPowerStatus([ref]$power) -or $power.ACLineStatus -ne 1) {
        throw 'AC power disconnected during the benchmark session'
    }
    & $Exe $Book $Font --runs $Runs --turns $Turns --warmup $Pages --cpu $Cpu --high-priority `
        --json "$Output/$Name.json" *> "$Output/$Name.txt"
    $code = $LASTEXITCODE
    if ($code) { throw "$Name benchmark exited $code; raw output retained" }
    $data = Get-Content -LiteralPath "$Output/$Name.json" -Raw | ConvertFrom-Json
    if ($data.runs -ne $Runs -or $data.batches.Count -ne $Runs -or
        @($data.batches | Where-Object { $_.samples.Count -ne $Turns }).Count) {
        throw "$Name benchmark produced an incomplete batch"
    }
}

$scheme = Get-ActiveScheme
$original = Read-AcPolicy $scheme
@{scheme=$scheme; ac_line_status=$power.ACLineStatus; ac=$original} |
    ConvertTo-Json -Depth 4 | Set-Content -LiteralPath "$Output/power-original.json" -Encoding utf8
@{binary=$Binary; reference=$Reference; book=$Book; font=$Font; cpu=$Cpu; runs=$Runs; turns=$Turns;
  warmup=$Warmup; policy=@{PROCTHROTTLEMIN=100; PROCTHROTTLEMAX=100; PERFBOOSTMODE=0}; retries=0} |
    ConvertTo-Json -Depth 4 | Set-Content -LiteralPath "$Output/session.json" -Encoding utf8
$failure = $null
try {
    if ((Get-ActiveScheme) -ne $scheme) { throw 'Active power scheme changed before policy application' }
    foreach ($pair in @(@('PROCTHROTTLEMIN',100), @('PROCTHROTTLEMAX',100), @('PERFBOOSTMODE',0))) {
        $null = Invoke-PowerCfg -PowerArgs @('/setacvalueindex', $scheme, 'SUB_PROCESSOR', $pair[0], [string]$pair[1])
    }
    $null = Invoke-PowerCfg -PowerArgs @('/setactive', $scheme)
    $applied = Read-AcPolicy $scheme
    if ($applied.PROCTHROTTLEMIN -ne 100 -or $applied.PROCTHROTTLEMAX -ne 100 -or $applied.PERFBOOSTMODE -ne 0) {
        throw 'Temporary processor policy did not read back correctly'
    }
    $applied | ConvertTo-Json | Set-Content -LiteralPath "$Output/power-applied.json" -Encoding utf8
    & "$PSScriptRoot/preflight.ps1" -Output "$Output/preflight.json" -Seconds 3
    if ($Reference) { Capture-Batch 'reference' $Reference 0 }
    Capture-Batch 'cold' $Binary 0
    Capture-Batch 'warm' $Binary $Warmup
} catch {
    $failure = $_
    $_ | Out-String | Set-Content -LiteralPath "$Output/failure.txt" -Encoding utf8
} finally {
    # Restore before optional telemetry: CIM providers can take minutes to reply.
    $restoreErrors = @()
    foreach ($setting in $settings) {
        try { $null = Invoke-PowerCfg -PowerArgs @('/setacvalueindex', $scheme, 'SUB_PROCESSOR', $setting, [string]$original[$setting]) }
        catch { $restoreErrors += $_.Exception.Message }
    }
    try { $null = Invoke-PowerCfg -PowerArgs @('/setactive', $scheme) }
    catch { $restoreErrors += $_.Exception.Message }
    $restored = $null; $active = $null
    try {
        $restored = Read-AcPolicy $scheme
        $active = Get-ActiveScheme
        foreach ($setting in $settings) {
            if ($restored[$setting] -ne $original[$setting]) { $restoreErrors += "RESTORE MISMATCH: $setting" }
        }
        if ($active -ne $scheme) { $restoreErrors += 'RESTORE MISMATCH: active scheme GUID' }
    } catch { $restoreErrors += $_.Exception.Message }
    @{scheme=$scheme; active_scheme=$active; ac=$restored; verified=($restoreErrors.Count -eq 0); errors=$restoreErrors} |
        ConvertTo-Json -Depth 4 | Set-Content -LiteralPath "$Output/power-restored.json" -Encoding utf8
    if ($restoreErrors.Count) { throw "Power restoration failed: $($restoreErrors -join '; '); see power-original.json" }
    try { & "$PSScriptRoot/preflight.ps1" -Output "$Output/postflight.json" -Seconds 3 }
    catch { $_ | Out-String | Set-Content -LiteralPath "$Output/postflight-error.txt" -Encoding utf8 }
}
if ($failure) { throw $failure }
