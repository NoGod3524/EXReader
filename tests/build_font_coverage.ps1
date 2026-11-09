param([string]$Build = 'build')
$ErrorActionPreference = 'Stop'
$cache = @{}
Get-Content (Join-Path $Build 'CMakeCache.txt') | ForEach-Object {
    if ($_ -match '^([^:#]+):[^=]+=(.*)$') { $cache[$Matches[1]] = $Matches[2] }
}
$output = Join-Path $Build 'font_coverage_ft.dll'
& $cache['CMAKE_C_COMPILER'] -shared -O2 -Wall -Wextra -Wpedantic -Werror `
    -I (Join-Path $cache['freetype_SOURCE_DIR'] 'include') `
    -I (Join-Path $cache['freetype_BINARY_DIR'] 'include') `
    (Join-Path $PSScriptRoot 'font_coverage_ft.c') `
    (Join-Path $cache['freetype_BINARY_DIR'] 'libfreetype.a') -o $output
if ($LASTEXITCODE) { throw 'FreeType acceptance bridge build failed' }
Write-Output $output
