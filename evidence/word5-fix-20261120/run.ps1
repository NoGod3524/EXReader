param([ValidateSet('build','test','bench')][string]$Mode,[string]$Run='final')
$ErrorActionPreference='Stop'
$repo=(Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$openperf=(Resolve-Path (Join-Path $repo '../EXReader-openperf')).Path
$ops='C:/Users/Oscar/OneDrive/Desktop/deepseekHarness/ops'
$gate=Join-Path $ops 'build-gate.ps1'
$lock=Join-Path $ops 'bench-lock.ps1'
$holder='codex-word5-fix'
$raw=Join-Path $PSScriptRoot "raw/$Run"
New-Item -ItemType Directory -Force $raw | Out-Null
$log=Join-Path $raw 'locks.txt'
function Log([string]$msg) { "$(Get-Date -Format o) $msg" | Tee-Object -FilePath $log -Append }
function Locked-Command([string]$tool,[string[]]$params) {
    $result=& pwsh -NoProfile -File $tool @params
    Log ($result -join ' ')
    if($LASTEXITCODE -ne 0){throw "Lock command failed $params"}
}
function Slots {
    & pwsh -NoProfile -File $gate -Status | Out-Null
    Get-ChildItem $ops -Force -Filter '.build.*' | ForEach-Object Name
}
function Run-Bench([string]$name,[string[]]$cmd) {
    Locked-Command $lock @('-Holder',$holder,'-Heartbeat')
    $slots=@(Slots)
    if($slots.Count){throw "Unexpected build slots $slots"}
    Log "Starting $name with zero build slots and EXR_IDLE_GATE=$env:EXR_IDLE_GATE"
    & $cmd[0] @($cmd | Select-Object -Skip 1) 2>&1 | Tee-Object -FilePath (Join-Path $raw "$name.txt")
    if($LASTEXITCODE -ne 0){throw "$name failed ($LASTEXITCODE)"}
}
Set-Location $repo
if($Mode -eq 'build') {
    Locked-Command $gate @('-Holder',$holder,'-Wait','-TimeoutSeconds','14400')
    try {
        Log 'Release build, build/vhslides, parallel 4'
        cmake --build build/vhslides --parallel 4 *> (Join-Path $raw 'build.txt')
        if($LASTEXITCODE -ne 0){throw 'Build failed'}
    } finally {Locked-Command $gate @('-Holder',$holder,'-Release')}
    return
}
$env:EXR_IDLE_GATE='off'
while($true) {
    if(@(Slots).Count){Start-Sleep -Seconds 5;continue}
    Locked-Command $lock @('-Holder',$holder,'-Wait','-TimeoutSeconds','14400')
    if(!@(Slots).Count){break}
    Locked-Command $lock @('-Holder',$holder,'-Release')
}
try {
    if($Mode -eq 'test') {
        Run-Bench 'ctest' @('ctest','--test-dir','build/vhslides','--parallel','6','--output-on-failure')
    } else {
        $dll=(Resolve-Path 'build/vhslides/libexreader.dll').Path
        $nullDll=Join-Path (Split-Path $dll) 'word5-identical-copy.dll'
        Copy-Item -LiteralPath $dll -Destination $nullDll -Force
        $pdfjs=(Resolve-Path '../pdfjs-bench2/node_modules/pdfjs-dist').Path
        $fixture=(Resolve-Path 'tests/fixtures/pdf-hybrid-real/word-5.pdf').Path
        foreach($width in 600,1200,2400) {
            $sweep=@('python','-B',"$openperf/tools/render_vs_pdfjs.py",'--library',$dll,'--null-library',$nullDll,'--pdfjs-root',$pdfjs,'--case',"word-5=$fixture",'--width',"$width",'--rounds','12','--out',"$raw/paired-$width.json")
            if($Run -eq 'reverse') { $sweep+='--reverse-start' }
            Run-Bench "paired-$width" $sweep
        }
        if($Run -eq 'final') {
            Run-Bench 'pixels' @('python','-B',"$PSScriptRoot/validate.py",'pixels',"$openperf/build/perf/libexreader.dll",$dll,$raw)
            Run-Bench 'rss' @('python','-B',"$PSScriptRoot/validate.py",'rss',"$openperf/build/perf/libexreader.dll",$dll,$raw)
        }
    }
} finally {Locked-Command $lock @('-Holder',$holder,'-Release')}
