# SPDX-License-Identifier: MIT
param()
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$outDir = Join-Path ([IO.Path]::GetTempPath()) 'exreader-l04-clipboard'
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
Push-Location $root
try {
    foreach ($name in @('check_shell_docedit_clipboard', 'check_shell_docedit_clipboard_win')) {
        $exe = Join-Path $outDir ($name + '.exe')
        & gcc -std=c11 -Wall -Wextra -Werror -DEXR_STATIC -Iinclude "examples/windows/$name.c" src/docx_edit.c -o $exe
        if ($LASTEXITCODE -ne 0) { throw "Compilation failed: $name" }
        & $exe
        if ($LASTEXITCODE -ne 0) { throw "Acceptance failed: $name" }
    }
    & gcc -std=c11 -fsyntax-only -DEXR_READER_WINDOWS_SHELL -Iinclude examples/windows/check_shell_docedit_clipboard_host.c
    if ($LASTEXITCODE -ne 0) { throw 'Actual host syntax check failed' }
    Write-Host 'PASS actual Windows host syntax check'
    & git apply --check examples/windows/shell_docedit_clipboard_wiring.patch
    if ($LASTEXITCODE -ne 0) { throw 'Wiring patch check failed' }
    Write-Host 'PASS two-line wiring patch applies cleanly (not applied)'
} finally { Pop-Location }
