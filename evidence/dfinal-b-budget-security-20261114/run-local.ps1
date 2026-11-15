param([ValidateSet('configure','build','ctest','new-checks','prepush','ci-hygiene')][string]$Step)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
Set-Location -LiteralPath $root
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
if ($Step -in @('configure','build')) {
    $vs = & "${env:ProgramFiles(x86)}/Microsoft Visual Studio/Installer/vswhere.exe" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
    $wrapper = Join-Path $root 'build/final-b-vcvars.bat'
    Set-Content -LiteralPath $wrapper ('@call "' + $vs + '/VC/Auxiliary/Build/vcvars64.bat" >nul' + "`r`n@set")
    & cmd.exe /d /c $wrapper | ForEach-Object {
        if ($_ -match '^(PATH|INCLUDE|LIB|LIBPATH)=(.*)$') {
            [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2], 'Process')
        }
    }
}
switch ($Step) {
    configure {
        # Preserve the full profile and cached dependency locations used in the prior audited run.
        $command = (Get-Content -LiteralPath 'evidence/dfinal-b-followup-20261114/configure-exit.json' -Raw | ConvertFrom-Json).command
    }
    build { $command = @('cmake','--build','build/audit-msvc','--parallel','8') }
    ctest { $command = @('ctest','--test-dir','build/audit-msvc','--parallel','4','--output-on-failure','--no-tests=error','-E','sdk-release|sdk-doc-coverage','--output-junit',(Join-Path $PSScriptRoot 'ctest.xml')) }
    new-checks { $command = @('ctest','--test-dir','build/audit-msvc','--no-tests=error','-V','-R','windows-(privacy-cleanup|a11y-(control|shell)|render-budget-report|selection-(render-budget|sync|keyboard|dictionary-storage))') }
    prepush { $command = @('pwsh','-NoProfile','-File','C:/Users/Oscar/OneDrive/Desktop/deepseekHarness/ops/prepush-check.ps1','-Worktree',$root) }
    ci-hygiene { $command = @('python','tools/check_ci_hygiene.py','--base','e2d6f4d0aa58ea03135f3af1a7d4b9626190fa08') }
}
$start = [DateTime]::UtcNow.ToString('o')
$exe, $arguments = $command
& $exe @arguments *> (Join-Path $PSScriptRoot ($Step + '.txt'))
$result = $LASTEXITCODE
@{command=$command;exit=$result;started_utc=$start;completed_utc=[DateTime]::UtcNow.ToString('o');source=(& git rev-parse HEAD)} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $PSScriptRoot ($Step + '-exit.json')) -Encoding utf8
Get-Content -LiteralPath (Join-Path $PSScriptRoot ($Step + '.txt')) -Tail 12
exit $result
