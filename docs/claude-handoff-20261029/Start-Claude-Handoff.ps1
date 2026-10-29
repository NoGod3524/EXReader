param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('C1','C2','C3')]
    [string]$Task
)
$ErrorActionPreference = 'Stop'
if ($env:CODEX_SANDBOX_NETWORK_DISABLED) {
    throw 'This execution environment disables network access. No Claude session has been created. Use an authorized backend environment with Anthropic access.'
}
$claudeExecutable = Join-Path $env:USERPROFILE '.local\bin\claude.exe'
if (-not (Test-Path -LiteralPath $claudeExecutable)) {
    $claudeExecutable = (Get-Command claude -ErrorAction Stop).Source
}
$taskFiles = @{
    C1 = 'C1-android-installed-sync.txt'
    C2 = 'C2-product-performance.txt'
    C3 = 'C3-delivery-licenses.txt'
}
$taskPath = Join-Path $PSScriptRoot $taskFiles[$Task]
$taskText = [System.IO.File]::ReadAllText($taskPath)
& $claudeExecutable --model sonnet --effort medium --cloud $taskText
if ($LASTEXITCODE -ne 0) {
    throw "Claude cloud dispatch failed with exit code $LASTEXITCODE. Do not record this task as submitted."
}
