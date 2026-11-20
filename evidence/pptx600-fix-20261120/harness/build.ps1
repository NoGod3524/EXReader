# Configure (once) and build build/p600 inside a shared build slot.
# Usage: pwsh -File build.ps1 [-Target exreader] [-Configure]
param([string]$Target = 'exreader', [switch]$Configure, [string]$Holder = 'codex-P600f')
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
$ops = Join-Path $env:USERPROFILE 'OneDrive/Desktop/deepseekHarness/ops'
$gate = Join-Path $ops 'build-gate.ps1'
$bin = 'C:/Users/Oscar/AppData/Local/Microsoft/WinGet/Packages/BrechtSanders.WinLibs.POSIX.UCRT_Microsoft.Winget.Source_8wekyb3d8bbwe/mingw64/bin'
$env:Path = "$bin;$env:Path"
$build = Join-Path $root 'build/p600'
$deps = 'C:/Users/Oscar/exr-deps-cache'
& $gate -Holder $Holder -Wait -TimeoutSeconds 7200
if ($LASTEXITCODE) { throw 'no build slot' }
try {
  if ($Configure -or -not (Test-Path (Join-Path $build 'CMakeCache.txt'))) {
    $flags = 'EXPAT','FREETYPE','LCMS','LIBTIFF','LIBWEBP','MBEDTLS','MINIMP3','MINIZ','OPENJPEG','SQLITE','STB','ZLIB' |
      ForEach-Object { "-DFETCHCONTENT_SOURCE_DIR_$_=$deps/$($_.ToLowerInvariant())-src" }
    cmake -S $root -B $build -G Ninja -DCMAKE_BUILD_TYPE=Release "-DCMAKE_C_COMPILER=$bin/gcc.exe" "-DCMAKE_CXX_COMPILER=$bin/g++.exe" "-DCMAKE_MAKE_PROGRAM=$bin/ninja.exe" -DEXR_ENABLE_IMAGE_AVIF=OFF -DEXR_ENABLE_AAC=OFF @flags
    if ($LASTEXITCODE) { throw "configure failed $LASTEXITCODE" }
  }
  if ($Target -eq 'all') { cmake --build $build --parallel 6 } else { cmake --build $build --parallel 6 --target $Target }
  if ($LASTEXITCODE) { throw "build failed $LASTEXITCODE" }
} finally {
  & $gate -Holder $Holder -Release | Out-Null
}
