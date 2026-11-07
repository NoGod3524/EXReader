param(
  [string]$SdkBuild = 'C:/Users/Oscar/Documents/Codex/cjk-justify-20261106/build',
  [string]$Out = "$PSScriptRoot/.build-real-exe"
)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path "$PSScriptRoot/../../..").Path
New-Item -ItemType Directory -Force $Out | Out-Null
$Out = (Resolve-Path $Out).Path
function Invoke-Checked([string]$Tool, [string[]]$Arguments) {
  & $Tool @Arguments
  if ($LASTEXITCODE -ne 0) { throw "$Tool exited $LASTEXITCODE" }
}
Invoke-Checked gcc @('-std=c11','-O2','-DEXR_READER_WINDOWS_SHELL=1','-I',"$root/include",'-c',"$root/examples/reader.c",'-o',"$Out/reader.o")
Invoke-Checked g++ @('-std=c++17','-O2','-I',"$root/include",'-Wall','-Wextra','-Werror','-c',"$root/examples/windows/shell_d2d.cpp",'-o',"$Out/shell.o")
Invoke-Checked g++ @('-std=c++17','-O2','-I',"$root/include",'-c',"$root/examples/windows/shell_epub.cpp",'-o',"$Out/epub.o")
Invoke-Checked g++ @('-mwindows','-static',"$Out/reader.o","$Out/shell.o","$Out/epub.o", "$SdkBuild/libexreader.dll.a", "$SdkBuild/_deps/miniz-build/libminiz.a", "$SdkBuild/_deps/expat-build/libexpat.a", '-ld2d1','-ldwrite','-ladvapi32','-lcomdlg32','-lgdi32','-luiautomationcore','-lshell32','-luser32','-loleaut32','-lole32','-luuid','-lm','-o',"$Out/EXReader-fix.exe")
Copy-Item "$SdkBuild/libexreader.dll" "$Out/libexreader.dll"
Get-FileHash "$Out/EXReader-fix.exe","$Out/libexreader.dll"
