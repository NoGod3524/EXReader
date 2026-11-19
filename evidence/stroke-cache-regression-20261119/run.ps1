# Stroke-cache regression orchestration (holder opus-Breg). Pixel/status evidence only; no timing.
#   -Phase build  : build-gate -Wait; build B DLL + test (build/perf); build C DLL (9c2443edf) once; compile render_abc for both; -Release
#   -Phase run    : run the unit test and the A/A2/B/C renders for -Label, then compare
#   -Phase ctest  : build-gate -Wait; full ctest in build/perf; -Release   (held so nobody times while 578 tests run)
param([Parameter(Mandatory=$true)][ValidateSet('build','run','ctest')][string] $Phase,
      [Parameter(Mandatory=$true)][string] $Label, [switch] $TestOnly)
$ErrorActionPreference = 'Stop'
$holder = 'opus-Breg'
$gate = 'C:\Users\Oscar\OneDrive\Desktop\deepseekHarness\ops\build-gate.ps1'
$repo = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../..')).Path
$ev = $PSScriptRoot
$perf = Join-Path $repo 'build/perf'
$baseRoot = Join-Path $repo 'build/base-9c2443edf'
$baseSrc = Join-Path $baseRoot 'src'
$baseBuild = Join-Path $baseRoot 'build'
$cache = Get-Content -LiteralPath (Join-Path $perf 'CMakeCache.txt')
function CacheValue($name) { (($cache | Where-Object { $_ -match "^${name}:[^=]*=" } | Select-Object -First 1) -split '=',2)[1] }
$gcc = CacheValue 'CMAKE_C_COMPILER'
$cmake = CacheValue 'CMAKE_COMMAND'
$ninja = CacheValue 'CMAKE_MAKE_PROGRAM'
$python = CacheValue '_Python3_EXECUTABLE'
$env:Path = "$(Split-Path -Parent $gcc);$env:Path"
$out = Join-Path $ev $Label
$null = New-Item -ItemType Directory -Force -Path $out
function Log($m) { $s = "[$(Get-Date -Format 'HH:mm:ss')] $m"; Write-Output $s; Add-Content -LiteralPath (Join-Path $out 'run.log') -Value $s }
function Native { param([string]$Exe, [string[]]$Arguments, [string]$LogFile)
  & $Exe @Arguments *>> $LogFile; if ($LASTEXITCODE -ne 0) { throw "$Exe failed ($LASTEXITCODE); see $LogFile" } }
function Gate($action) {
  $p = @{ Holder = $holder }; $p[$action.TrimStart('-')] = $true
  & $gate @p; if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) { throw "build-gate $action failed ($LASTEXITCODE)" } }
function CompileRender($buildDir, $dest) {
  $null = New-Item -ItemType Directory -Force -Path $dest
  Copy-Item -LiteralPath (Join-Path $buildDir 'libexreader.dll') -Destination $dest -Force
  Native $gcc @('-std=c11','-O2','-Wall','-Wextra',"-I$(Join-Path $buildDir 'generated/include')","-I$(Join-Path $repo 'include')",
    (Join-Path $ev 'render_abc.c'),(Join-Path $buildDir 'libexreader.dll.a'),'-o',(Join-Path $dest 'render_abc.exe')) (Join-Path $out 'build.log')
  "$((Get-FileHash -LiteralPath (Join-Path $dest 'libexreader.dll')).Hash)  $(Join-Path $dest 'libexreader.dll')" | Add-Content -LiteralPath (Join-Path $out 'dll-sha256.txt')
}

if ($Phase -eq 'build') {
  Log "build-gate -Wait"; Gate '-Wait'
  try {
    Log "B: build/perf exreader + exreader-stroke-cache-key-test (source $(git -C $repo rev-parse --short HEAD) + worktree diff)"
    git -C $repo diff -- src CMakeLists.txt > (Join-Path $out 'worktree.diff')
    Native $cmake @('--build',$perf,'--target','exreader','exreader-stroke-cache-key-test') (Join-Path $out 'build.log')
    if (-not (Test-Path -LiteralPath (Join-Path $baseBuild 'libexreader.dll'))) {
      Log "C: configure + build 9c2443edf library only"
      $null = New-Item -ItemType Directory -Force -Path $baseSrc
      $zip = Join-Path $baseRoot 'src.zip'
      git -C $repo archive --format=zip -o $zip 9c2443edf; if ($LASTEXITCODE) { throw 'git archive failed' }
      Expand-Archive -LiteralPath $zip -DestinationPath $baseSrc -Force
      $defs = @('-G','Ninja','-S',$baseSrc,'-B',$baseBuild,'-DCMAKE_BUILD_TYPE=Release',"-DCMAKE_C_COMPILER=$gcc","-DCMAKE_MAKE_PROGRAM=$ninja",
                '-DEXR_BUILD_TESTS=OFF','-DFETCHCONTENT_FULLY_DISCONNECTED=ON')
      $defs += $cache | Where-Object { $_ -match '^FETCHCONTENT_SOURCE_DIR_[A-Z0-9_]+:PATH=' } | ForEach-Object { $k,$v = $_ -split '=',2; "-D$(($k -split ':')[0])=$v" }
      Native $cmake $defs (Join-Path $out 'build.log')
      Native $cmake @('--build',$baseBuild,'--target','exreader') (Join-Path $out 'build.log')
    }
    Log "compile render_abc against B and C DLLs"
    CompileRender $perf (Join-Path $out 'bin-B')
    CompileRender $baseBuild (Join-Path $out 'bin-C')
  } finally { Log "build-gate -Release"; Gate '-Release' }
}

if ($Phase -eq 'run') {
  $fx = Join-Path $ev 'fixtures'
  if (-not (Test-Path -LiteralPath $fx)) { Native $python @('-I',(Join-Path $ev 'gen_fixtures.py'),$fx) (Join-Path $out 'fixtures.log') }
  Get-ChildItem -LiteralPath $fx -Filter *.pdf | ForEach-Object { "$((Get-FileHash -LiteralPath $_.FullName).Hash)  $($_.Name)" } | Set-Content -LiteralPath (Join-Path $out 'fixtures-sha256.txt')
  Log "unit test (B DLL)"
  $env:Path = "$perf;$env:Path"
  & (Join-Path $perf 'exreader-stroke-cache-key-test.exe') *> (Join-Path $out 'unit-test.txt'); $code = $LASTEXITCODE
  Add-Content -LiteralPath (Join-Path $out 'unit-test.txt') -Value "exit=$code"; Log "unit test exit=$code"
  if ($TestOnly) { Get-Content -LiteralPath (Join-Path $out 'unit-test.txt'); return }
  $raw = Join-Path $out 'raw'; $null = New-Item -ItemType Directory -Force -Path $raw
  $arms = @(@{n='A';bin='bin-B';mode='nocache'},@{n='A2';bin='bin-B';mode='nocache'},@{n='B';bin='bin-B';mode='cache'},@{n='C';bin='bin-C';mode='cache'})
  foreach ($pdf in Get-ChildItem -LiteralPath $fx -Filter *.pdf | Sort-Object Name) {
    foreach ($a in $arms) {
      $exe = Join-Path (Join-Path $out $a.bin) 'render_abc.exe'
      $stem = Join-Path $raw "$($pdf.BaseName).$($a.n)"
      & $exe $pdf.FullName "$stem.rgba" $a.mode > "$stem.txt"; if ($LASTEXITCODE) { throw "render $($pdf.Name) $($a.n) failed ($LASTEXITCODE)" }
    }
    Log "rendered $($pdf.Name)"
  }
  Native $python @('-I',(Join-Path $ev 'compare_abc.py'),$raw,$Label) (Join-Path $out 'compare.log')
  Copy-Item -LiteralPath (Join-Path $raw "compare-$Label.md") -Destination $out -Force
  Get-ChildItem -LiteralPath $raw -Filter *.rgba | Remove-Item -Force   # keep metadata + hashes, drop 4.3 MB dumps
  Get-Content -LiteralPath (Join-Path $out "compare-$Label.md")
}

if ($Phase -eq 'ctest') {
  Log "build-gate -Wait (ctest)"; Gate '-Wait'
  try {
    Native $cmake @('--build',$perf) (Join-Path $out 'build.log')
    $ctest = Join-Path (Split-Path -Parent $cmake) 'ctest.exe'
    & $ctest --test-dir $perf -j 4 --output-on-failure *> (Join-Path $out 'ctest.txt'); $code = $LASTEXITCODE
    Log "ctest exit=$code"; Get-Content -LiteralPath (Join-Path $out 'ctest.txt') -Tail 15
  } finally { Log "build-gate -Release"; Gate '-Release' }
}
