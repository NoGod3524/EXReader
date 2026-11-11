# Run from the repository root before the Windows release smoke test.
# The existing smoke test compiles the README consumer with cl, even when the
# engine was built with MinGW. Supply an MSVC import library for the same DLL.
$ErrorActionPreference = 'Stop'
$finder = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$installation = & $finder -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if ($LASTEXITCODE -ne 0 -or -not $installation) { throw 'MSVC x64 tools not found' }
$version = Get-ChildItem -LiteralPath (Join-Path $installation 'VC/Tools/MSVC') -Directory |
  Sort-Object Name -Descending | Select-Object -First 1
$librarian = Join-Path $version.FullName 'bin/Hostx64/x64/lib.exe'
foreach ($build in @('build/y1/baseline', 'build/y1/candidate')) {
  New-Item -ItemType Directory -Path "$build/Release" -Force | Out-Null
  & $librarian /nologo /machine:x64 /name:libexreader.dll "/def:$build/exreader.def" "/out:$build/Release/exreader.lib"
  if ($LASTEXITCODE -ne 0) { throw "Import library generation failed: $build" }
}
