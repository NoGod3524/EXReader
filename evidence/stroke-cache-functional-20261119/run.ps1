param([Parameter(Mandatory=$true)][string] $CandidateDllSha256,[string] $BuildDir)
$ErrorActionPreference='Stop'
$repo=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../..')).Path
if (-not $BuildDir) { $BuildDir=Join-Path $repo 'build/perf' }
$BuildDir=(Resolve-Path -LiteralPath $BuildDir).Path
& git -C $repo diff --quiet 1beab649c -- src include CMakeLists.txt cmake
if ($LASTEXITCODE -ne 0) { throw 'Source/header/build inputs differ from 1beab649c.' }
$line=Get-Content -LiteralPath (Join-Path $BuildDir 'CMakeCache.txt') | Where-Object { $_ -match '^CMAKE_C_COMPILER:[^=]*=' } | Select-Object -First 1
if (-not $line) { throw 'Configured C compiler missing.' }
$gcc=($line -split '=',2)[1]
$dll=Join-Path $BuildDir 'libexreader.dll'
$sha=(Get-FileHash -LiteralPath $dll).Hash
if ($CandidateDllSha256 -notmatch '^[0-9a-fA-F]{64}$' -or $sha -ne $CandidateDllSha256) { throw 'Candidate DLL hash mismatch.' }
$run=Join-Path $PSScriptRoot ("run-" + [Guid]::NewGuid().ToString('N'))
$null=New-Item -ItemType Directory -Path $run
$exe=Join-Path $run 'stroke_cache.exe'
$runtime=Join-Path $run 'libexreader.dll'
Copy-Item -LiteralPath $dll -Destination $runtime
if ((Get-FileHash -LiteralPath $runtime).Hash -ne $sha) { throw 'Runtime DLL copy hash mismatch.' }
$src=Join-Path $PSScriptRoot 'stroke_cache.c'
$head=& git -C $repo rev-parse HEAD
Write-Output "source_reference=1beab649c worktree_HEAD=$head candidate_DLL_SHA256=$sha functional_source_SHA256=$((Get-FileHash -LiteralPath $src).Hash)"
$args=@('-std=c11','-O2','-Wall','-Wextra',"-I$(Join-Path $BuildDir 'generated/include')","-I$(Join-Path $repo 'include')","-I$(Join-Path $repo 'src')",$src,(Join-Path $BuildDir 'libexreader.dll.a'),'-o',$exe)
$oldPath=$env:Path
try {
  $env:Path="$(Split-Path -Parent $gcc);$BuildDir;$oldPath"
  & $gcc @args
  if ($LASTEXITCODE -ne 0) { throw "Standalone compilation failed ($LASTEXITCODE)." }
  & $exe
  if ($LASTEXITCODE -ne 0) { throw "Stroke cache regression failed ($LASTEXITCODE)." }
} finally { $env:Path=$oldPath }
