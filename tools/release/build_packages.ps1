# SPDX-License-Identifier: MIT
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)][string]$BuildDir,
    [string]$OutputDir = (Join-Path $PSScriptRoot '../../dist'),
    [string]$Configuration = 'Release',
    [string]$Python = 'python'
)
$ErrorActionPreference = 'Stop'
& $Python (Join-Path $PSScriptRoot 'build_packages.py') --build-dir $BuildDir --output-dir $OutputDir --config $Configuration
if ($LASTEXITCODE -ne 0) { throw "SDK packaging failed with exit code $LASTEXITCODE" }
