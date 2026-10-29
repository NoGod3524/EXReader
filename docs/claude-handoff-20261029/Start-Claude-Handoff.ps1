param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('C1','C2','C3')]
    [string]$Task,
    [string]$WorktreeRoot = 'C:\Users\Oscar\exreader-local-usage-20261029'
)
$ErrorActionPreference = 'Stop'
if ($env:CODEX_SANDBOX_NETWORK_DISABLED) {
    throw 'This execution environment disables network access. No Claude session has been created.'
}
if ($env:ANTHROPIC_API_KEY -or $env:ANTHROPIC_AUTH_TOKEN -or $env:ANTHROPIC_BASE_URL) {
    throw 'This launcher requires the normal Claude account login without API-key or gateway overrides.'
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
$taskDirectory = (Resolve-Path -LiteralPath (Join-Path $WorktreeRoot $Task.ToLowerInvariant())).Path
$activeSessions = & $claudeExecutable agents --json | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect existing background sessions; no duplicate dispatched.' }
$existing = $activeSessions | Where-Object { $_.cwd -eq $taskDirectory -and $_.state -in @('working','blocked','needs_input') }
if ($existing) {
    $existing | Select-Object id,name,state,cwd
    return
}
Push-Location -LiteralPath $taskDirectory
try {
    $branch = git branch --show-current
    if ($LASTEXITCODE -ne 0 -or $branch -notlike "claude/local-$($Task.ToLowerInvariant())-*") {
        throw 'The task directory must be an isolated local task branch.'
    }
    & $claudeExecutable --bg --name "EXR-local-$Task" --model claude-sonnet-5-5 --effort medium --permission-mode auto $taskText
    if ($LASTEXITCODE -ne 0) {
        throw "Claude local dispatch failed with exit code $LASTEXITCODE. Do not record this task as started."
    }
} finally {
    Pop-Location
}
