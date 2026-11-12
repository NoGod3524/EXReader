param([string]$SdkBuild='build/tts', [string]$Output='build/tts-host')
$ErrorActionPreference='Stop'
$SdkBuild=(Resolve-Path -LiteralPath $SdkBuild).Path
New-Item -ItemType Directory -Force $Output | Out-Null
$Output=(Resolve-Path -LiteralPath $Output).Path
function Compile([string]$Compiler,[string[]]$Arguments) {
  & $Compiler @Arguments
  if($LASTEXITCODE -ne 0) {throw "$Compiler exited $LASTEXITCODE"}
}
$flags=@('-O2','-Wall','-Wextra','-Werror','-DEXR_READER_WINDOWS_SHELL=1','-I','include')
Compile gcc ($flags+@('-std=c11','-c','examples/reader.c','-o',"$Output/reader.o"))
foreach($unit in @('shell_d2d','shell_epub','shell_speech')) {
  Compile g++ ($flags+@('-std=c++17','-c',"examples/windows/$unit.cpp",'-o',"$Output/$unit.o"))
}
Compile g++ @('-static',"$Output/reader.o","$Output/shell_d2d.o","$Output/shell_epub.o","$Output/shell_speech.o",
  "$SdkBuild/libexreader.dll.a","$SdkBuild/_deps/miniz-build/libminiz.a","$SdkBuild/_deps/expat-build/libexpat.a",
  '-ld2d1','-ldwrite','-ladvapi32','-lcomdlg32','-lgdi32','-luiautomationcore','-lshell32','-luser32','-loleaut32','-lole32','-luuid','-lwinhttp','-lcrypt32','-lws2_32','-lm','-o',"$Output/EXReader.exe")
Copy-Item -LiteralPath "$SdkBuild/libexreader.dll" -Destination $Output
Get-FileHash "$Output/EXReader.exe","$Output/libexreader.dll"
