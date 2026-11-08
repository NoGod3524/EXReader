param([Parameter(Mandatory)][string]$Output, [int]$Seconds = 10)
$ErrorActionPreference = 'Stop'
if (Test-Path -LiteralPath $Output) { throw 'Refusing to overwrite preflight evidence' }
$computer = Get-CimInstance Win32_ComputerSystem
$thermal = $null
$thermalError = $null
try { $thermal = @(Get-CimInstance -Namespace root/wmi -ClassName MSAcpi_ThermalZoneTemperature | Select-Object CurrentTemperature,InstanceName) }
catch { $thermalError = $_.Exception.Message }
$samples = @()
for ($i = 0; $i -lt $Seconds; $i++) {
    $before = @{}
    Get-Process | ForEach-Object { $before[$_.Id] = $_.CPU }
    $start = [DateTime]::UtcNow
    Start-Sleep -Seconds 1
    $elapsed = ([DateTime]::UtcNow - $start).TotalSeconds
    $processes = @(Get-Process | ForEach-Object {
        if ($before.ContainsKey($_.Id) -and $null -ne $_.CPU) {
            [PSCustomObject]@{name=$_.Name; pid=$_.Id; cpu_seconds=($_.CPU-$before[$_.Id]); one_core_pct=100*($_.CPU-$before[$_.Id])/$elapsed}
        }
    } | Sort-Object cpu_seconds -Descending | Select-Object -First 8)
    $counters = @(Get-CimInstance Win32_PerfFormattedData_Counters_ProcessorInformation |
        Select-Object Name,ProcessorFrequency,PercentofMaximumFrequency,PercentProcessorPerformance,PerformanceLimitFlags,PercentProcessorTime)
    $samples += @{utc=[DateTime]::UtcNow.ToString('o'); processes=$processes; counters=$counters}
}
@{
    advisory=$true; accepted=$false; utc=[DateTime]::UtcNow.ToString('o')
    cpu=@(Get-CimInstance Win32_Processor | Select-Object Name,NumberOfCores,NumberOfLogicalProcessors,MaxClockSpeed)
    system=@{manufacturer=$computer.Manufacturer; model=$computer.Model; hypervisor_present=$computer.HypervisorPresent; memory_bytes=$computer.TotalPhysicalMemory}
    active_scheme=(powercfg /getactivescheme | Out-String)
    processor_policy=(powercfg /qh SCHEME_CURRENT SUB_PROCESSOR | Out-String)
    thermal=$thermal; thermal_error=$thermalError
    thermal_interpretation='PerformanceLimitFlags are supplementary counters; unavailable temperature means thermal throttling cannot be ruled out.'
    samples=$samples
} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $Output -Encoding utf8
