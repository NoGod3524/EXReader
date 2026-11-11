# dispatch.ps1 v3 — 自动发现 codex / claude 可执行文件（版本目录会变）
param(
  [Parameter(Mandatory)][ValidateSet('codex','claude')][string]$Engine,
  [Parameter(Mandatory)][string]$Worktree,
  [string]$Prompt,
  [string]$PromptFile,
  [string]$Out,
  [string]$AddDir,
  [string]$CodexModel = 'gpt-6.1-sol',
  [string]$CodexEffort = 'medium',
  [string]$Model = 'claude-sonnet-5-5',
  [string]$Effort = 'medium',
  [switch]$Permissive,
  [switch]$DryRun
)

$ErrorActionPreference = 'Stop'

function Find-Codex {
  $root = Join-Path $env:LOCALAPPDATA 'OpenAI\Codex\bin'
  Get-ChildItem $root -Directory -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending |
    ForEach-Object { Join-Path $_.FullName 'codex.exe' } |
    Where-Object { Test-Path $_ } | Select-Object -First 1
}
function Find-Claude {
  $root = Join-Path $env:LOCALAPPDATA 'Claude-Data\claude_pzs8sxrjxfjjc\claude-code'
  Get-ChildItem $root -Recurse -Filter 'claude.exe' -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1 -ExpandProperty FullName
}

if (-not (Test-Path $Worktree)) { throw "worktree not found: $Worktree" }
if ($PromptFile) {
  if (-not (Test-Path $PromptFile)) { throw "prompt file not found: $PromptFile" }
  $Prompt = Get-Content $PromptFile -Raw -Encoding UTF8
}
if (-not $Prompt) { throw "need -Prompt or -PromptFile" }

# 工作树独占闸门：同一工作树同时只允许一个 agent（两个会话会互相覆盖验收脚本/产物）
$leaf = Split-Path $Worktree -Leaf; $wtPath = ($Worktree -replace "\\","/")
$busy = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
  Where-Object {
    $_.Name -match '^(codex|claude)\.exe$' -and $_.CommandLine -and
    $_.ProcessId -ne $PID -and $_.CommandLine -notmatch 'Get-CimInstance' -and
    $_.CommandLine -replace "\\","/" -match [regex]::Escape($wtPath)
  }
if ($busy) {
  $ids = ($busy | ForEach-Object { "$($_.ProcessId):$($_.Name)" }) -join ', '
  throw "工作树 $leaf 已有 agent 在跑（$ids）。同一工作树禁止并发；等它结束，或换工作树。"
}

if ($Engine -eq 'codex') {
  $exe = Find-Codex
  if (-not $exe) { throw "codex.exe not found" }
  $argv = @('exec', '-C', $Worktree, '-m', $CodexModel, '-c', ('model_reasoning_effort="' + $CodexEffort + '"'), '--skip-git-repo-check')
  # Automated runs must never take the owner's mouse or keyboard:
  # computer-use / unified-computer-use / browser plugins and the Tinysky CUA pipe
  # are switched off for every dispatched agent.
  $argv += @(
    '-c', 'plugins."computer-use@openai-bundled".enabled=false',
    '-c', 'plugins."unified-computer-use@openai-bundled".enabled=false',
    '-c', 'plugins."browser@openai-bundled".enabled=false',
    '-c', 'mcp_servers.node_repl.env.BROWSER_USE_TINYSKY_ENABLED="0"',
    '-c', 'mcp_servers.node_repl.env.SKY_CUA_NATIVE_PIPE="0"'
  )
  if ($Out) { $argv += @('-o', $Out) }
  $argv += $Prompt
} else {
  $exe = Find-Claude
  if (-not $exe) { throw "claude.exe not found" }
  # 成本闸门：Claude 会话并发上限（每个新会话都要重读仓库，并行越多越贵）
  $running = (Get-CimInstance Win32_Process -Filter "Name='claude.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match 'claude-code' } | Measure-Object).Count
  $limit = 8
  if ($running -ge $limit) {
    throw "claude 并发会话已达上限 $limit（当前 $running）。等现有会话结束再派；或改用 -Engine codex。"
  }
  $argv = @('--print', '--model', $Model, '--effort', $Effort, '--no-chrome',
    '--disallowedTools', 'computer', 'mcp__windows-mcp__*', 'mcp__windows_mcp__*',
    'mcp__computer-use__*', 'mcp__computer_use__*',
    'mcp__unified-computer-use__*', 'mcp__unified_computer_use__*',
    'mcp__browser__*', 'mcp__node_repl__*')
  if ($Permissive) { $argv += @('--permission-mode', 'bypassPermissions') }
  if ($AddDir) {
    foreach ($d in ($AddDir -split ';')) { if ($d.Trim()) { $argv += @('--add-dir', $d.Trim()) } }
  }
  # 用 `--` 结束 --add-dir 的可变参数，再把 prompt 作为位置参数传入；
  # Start-Process 无法给子进程喂 stdin，所以这里不能走原来的管道方式。
  $argv += @('--', $Prompt)
}

if ($DryRun) {
  "engine : $Engine"
  "exe    : $exe"
  "cwd    : $Worktree"
  "argv   : " + ($argv -join ' ')
  return
}

# Background-first launch:
#  - hidden window, BelowNormal priority, restricted CPU affinity so a build never takes the
#    desk back while the owner is using the machine
#  - CMAKE_BUILD_PARALLEL_LEVEL / MAKEFLAGS cap the agent's own build parallelism
$affinityCores = if ($env:DSH_AGENT_CORES) { [int]$env:DSH_AGENT_CORES } else { 4 }
$priority      = if ($env:DSH_AGENT_PRIORITY) { $env:DSH_AGENT_PRIORITY } else { 'BelowNormal' }
$buildJobs     = if ($env:DSH_AGENT_BUILD_JOBS) { $env:DSH_AGENT_BUILD_JOBS } else { '4' }
$env:CMAKE_BUILD_PARALLEL_LEVEL = $buildJobs
$env:MAKEFLAGS = "-j$buildJobs"
$env:NINJAFLAGS = "-j$buildJobs"

$stdoutCapture = [IO.Path]::GetTempFileName()
$stderrCapture = [IO.Path]::GetTempFileName()
Push-Location $Worktree
try {
  # Start-Process flattens an argument array into one command line, so every
  # argument has to be quoted the way the Windows CRT parser expects.
  function ConvertTo-ArgLine([string]$value) {
    if ($value -match '^[A-Za-z0-9_\-./:=@\\]+$') { return $value }
    $escaped = [regex]::Replace($value, '(\\*)"', '$1$1\"')
    $escaped = [regex]::Replace($escaped, '(\\+)\z', '$1$1')
    return '"' + $escaped + '"'
  }
  $argLine = ($argv | ForEach-Object { ConvertTo-ArgLine $_ }) -join ' '
  $startArgs = @{
    FilePath = $exe; ArgumentList = $argLine; WorkingDirectory = $Worktree
    WindowStyle = 'Hidden'; PassThru = $true
    RedirectStandardOutput = $stdoutCapture; RedirectStandardError = $stderrCapture
  }
  if ($Out -and $Engine -eq 'claude') { $startArgs.RedirectStandardOutput = $Out }
  $proc = Start-Process @startArgs
  try {
    $proc.PriorityClass = $priority
    if ($affinityCores -gt 0 -and $affinityCores -lt [Environment]::ProcessorCount) {
      $cpuCount = [Environment]::ProcessorCount
      $mask = [int64]0
      for ($i = $cpuCount - $affinityCores; $i -lt $cpuCount; $i++) { $mask = $mask -bor ([int64]1 -shl $i) }
      $proc.ProcessorAffinity = [IntPtr]$mask
    }
  } catch { "affinity/priority not applied: $($_.Exception.Message)" }
  $proc.WaitForExit()
  $code = $proc.ExitCode
  $outputPath = if ($Out -and $Engine -eq 'claude') { $Out } else { $stdoutCapture }
  $resultText = Get-Content -LiteralPath $outputPath -Raw -Encoding UTF8
  $errorText = Get-Content -LiteralPath $stderrCapture -Raw -Encoding UTF8
} finally {
  Pop-Location
  Remove-Item -LiteralPath $stdoutCapture, $stderrCapture -ErrorAction SilentlyContinue
}

$resultText
if ($errorText) { [Console]::Error.Write($errorText) }
"exit=$code"
exit $code
