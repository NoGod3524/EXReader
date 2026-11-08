param(
  [Parameter(Mandatory=$true)][string]$SdkBuild,
  [Parameter(Mandatory=$true)][string]$Output
)
$ErrorActionPreference = 'Stop'
$SdkBuild = (Resolve-Path -LiteralPath $SdkBuild).Path
New-Item -ItemType Directory -Force $Output | Out-Null
$Output = (Resolve-Path -LiteralPath $Output).Path
function Compile([string]$Compiler, [string[]]$Arguments) {
  Write-Output "$Compiler $($Arguments -join ' ')"
  & $Compiler @Arguments
  if ($LASTEXITCODE -ne 0) { throw "$Compiler exited $LASTEXITCODE" }
}
Push-Location (Join-Path $PSScriptRoot '../../..')
try {
  $common = @('-O2', '-Wall', '-Wextra', '-Werror', '-DEXR_READER_WINDOWS_SHELL=1',
    '-I', 'include', '-I', 'examples', '-I', 'examples/windows')
  Compile gcc ($common + @('-c', 'examples/reader.c', '-o', "$Output/reader.o"))
  foreach ($source in @('shell_d2d', 'shell_epub')) {
    Compile g++ ($common + @('-std=c++17', '-c', "examples/windows/$source.cpp", '-o', "$Output/$source.o"))
  }
  $libraries = @("-L$SdkBuild", '-lexreader', "$SdkBuild/_deps/expat-build/libexpat.a",
    "$SdkBuild/_deps/miniz-build/libminiz.a", '-ld2d1', '-ldwrite', '-lgdi32', '-lcomdlg32',
    '-lshell32', '-lole32', '-loleaut32', '-luuid', '-luiautomationcore', '-lm')
  $shell = @("$Output/shell_d2d.o", "$Output/shell_epub.o")
  Compile g++ (@("$Output/reader.o") + $shell + @('-o', "$Output/EXReader.exe") + $libraries)
  foreach ($artifact in @('font-test.exe', 'font_bridge.dll')) {
    $flags = if ($artifact.EndsWith('.dll')) { @('-shared') } else { @() }
    Compile gcc ($common + $flags + @('examples/windows/check_typography_font.c') + $shell +
      @('-o', "$Output/$artifact", '-lstdc++') + $libraries)
  }
  Copy-Item -LiteralPath "$SdkBuild/libexreader.dll" -Destination $Output
} finally {
  Pop-Location
}
