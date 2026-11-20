param(
  [string]$FinalDll = 'evidence/realmixed-gradient-mask-20261119/_work/dlls/final-recovered.dll',
  [string]$Repo = 'C:\Users\Oscar\Documents\Codex\EXReader-rmgradmask',
  [string]$HarnessRoot = 'C:\Users\Oscar\OneDrive\Desktop\deepseekHarness'
)
$ErrorActionPreference = 'Stop'
$env:EXR_IDLE_GATE = 'off'
Set-Location -LiteralPath $Repo
$E = 'evidence/realmixed-gradient-mask-20261119'
$D = "$E/_work/dlls"
$P = 'evidence/dense-vector-residual-20261119/harness'
$Lock = "$HarnessRoot/ops/bench-lock.ps1"
$BuildGate = "$HarnessRoot/ops/build-gate.ps1"
$GatePath = "$HarnessRoot/projects/exreader-handoff/EXREADER-FIXTURE-GATES.json"
$Holder = 'dot-C-D733-accept'
$Expected = 'D733D2FB4BFE98B1C0BD67F9CFA6754087BEE709DF8690837418C64D47C4F490'
$BaseHash = '54E374D53FF788793AA1A7FC9D91BFC9787966088D65AC2D60CED236B127BB65'
$Out = "$E/recovered-d733-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
$Report = "$E/REPORT.md"
if (Test-Path -LiteralPath $Report) { throw "Existing REPORT.md will not be overwritten." }
if (Test-Path -LiteralPath $Out) { throw "Existing run directory: $Out" }
New-Item -ItemType Directory -Path $Out | Out-Null
$Lines = [System.Collections.Generic.List[string]]::new()
$Held = $false
$Stage = 'preflight'
$Failure = $null
$Lines.Add('# C lane: exact-D733 recovery acceptance')
$Lines.Add('')
$Lines.Add("Run output: $Out")
$Lines.Add("Candidate SHA-256: $Expected")
$Lines.Add("Base SHA-256: $BaseHash")
function Require($ok,[string]$why) { if (-not $ok) { throw $why } }
function Hash([string]$p) { (Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash }
function Native([string]$program,[string[]]$argv,[string]$log) {
  & $program @argv 2>&1 | Tee-Object -FilePath $log | Out-Host
  if ($LASTEXITCODE -ne 0) { throw "$program failed (exit $LASTEXITCODE); see $log" }
}
function Beat {
  & pwsh -NoProfile -File $Lock -Holder $Holder -Heartbeat | Out-Null
  Require ($LASTEXITCODE -eq 0) 'Lost bench lock'
  $s = & pwsh -NoProfile -File $BuildGate -Status
  Require ($LASTEXITCODE -eq 0 -and ($s -match 'builds\s*:\s*0\s*/')) "Build activity or status failure: $s"
}
function ReadJ([string]$f) { Get-Content -Raw -LiteralPath $f | ConvertFrom-Json }
function Ab([string]$a,[string]$b,[string]$tag,[int]$rounds,[string]$pdf,[int]$first,[int]$last,[int]$width) {
  Beat
  $j = "$Out/$tag.json"
  Native python @('-B','-u',"$P/ab.py",$a,$b,$j,'--holder',$Holder,'--rounds',"$rounds",'--pdf',$pdf,'--first',"$first",'--last',"$last",'--width',"$width") "$Out/$tag.log"
  $x = ReadJ $j
  Require ($x.a_sha256 -eq (Hash $a) -and $x.b_sha256 -eq (Hash $b)) "$tag hash mismatch"
  Require ($x.pdf_sha256 -eq (Hash $pdf) -and $x.width -eq $width -and $x.pages[0] -eq $first -and $x.pages[1] -eq $last) "$tag fixture mismatch"
  Require (@($x.rounds).Count -eq $rounds -and $x.summary.rounds -eq $rounds -and @($x.mismatched_pages).Count -eq 0) "$tag invalid rounds/pixel equivalence"
  for ($i=0; $i -lt $rounds; $i++) {
    $row=$x.rounds[$i]
    $order=if (($i+1)%2) {'BA'} else {'AB'}
    Require ($row.round -eq ($i+1) -and $row.start -eq $order -and $null -ne $row.cpu_busy_pre_percent -and $row.cpu_busy_pre_percent -ge 0 -and $row.cpu_busy_pre_percent -le 100) "$tag invalid round order/pre-CPU"
  }
  $x
}
try {
  Require ((Hash $FinalDll) -eq $Expected) 'Recovered DLL does not match exact D733 pin'
  Require ((Hash "$D/base.dll") -eq $BaseHash -and (Hash "$D/base-copy.dll") -eq $BaseHash) 'Base/control provenance mismatch'
  Require ((Hash 'build/perf/libexreader.dll') -eq $Expected) 'CTest build tree DLL does not match the tested candidate'
  $g=ReadJ $GatePath
  Require ($g.status -eq 'canonical' -and $g.warm_rounds -eq 15 -and $g.margin -eq 1.03 -and $g.harness -eq "$P/ab.py") 'Unrecognized frozen gate policy'
  $keys=@('pptx-20-600','pptx-20-1200','word-5-600','word-5-1200','deck-1200')
  $limits=@(0.8324975,1.6756555,2.2197015,6.9460625,9.2558375)
  Require (@($g.items.PSObject.Properties).Count -eq 5) 'Unexpected frozen gate count'
  for ($i=0; $i -lt $keys.Count; $i++) {
    $row=$g.items.($keys[$i])
    Require ($null -ne $row -and [math]::Abs($row.limit_ms-$limits[$i]) -lt 1e-10 -and (Hash $row.fixture) -eq $row.sha256) "Frozen gate fixture/limit mismatch: $($keys[$i])"
  }
  Copy-Item -LiteralPath $GatePath -Destination "$Out/frozen-gates.json"
  $Stage = 'bench lock'
  & pwsh -NoProfile -File $Lock -Holder $Holder -Wait
  Require ($LASTEXITCODE -eq 0) 'Did not acquire bench lock'
  $Held = $true
  $gateDeadline = (Get-Date).AddMinutes(5)
  do {
    & pwsh -NoProfile -File $Lock -Holder $Holder -Heartbeat | Out-Null
    Require ($LASTEXITCODE -eq 0) 'Lost bench lock before testing'
    $status = & pwsh -NoProfile -File $BuildGate -Status
    Require ($LASTEXITCODE -eq 0) 'Build status failed'
    if ($status -match 'builds\s*:\s*0\s*/') { break }
    Require ((Get-Date) -lt $gateDeadline) 'Build slots did not clear'
    Start-Sleep -Seconds 2
  } while ($true)
  $Stage = 'pixel equivalence'
  Beat
  Native python @('-B','-u',"$P/pixels.py","$D/base.dll",$FinalDll,"$Out/pixels.json") "$Out/pixels.log"
  $x = ReadJ "$Out/pixels.json"
  Require ($x.a_sha256 -eq $BaseHash -and $x.b_sha256 -eq $Expected) 'Pixel evidence DLL hash mismatch'
  Require ($x.totals.large.pixels -eq 353143200 -and $x.totals.small.pixels -eq 111897000 -and $x.totals.large.differing_pixels -eq 0 -and $x.totals.small.differing_pixels -eq 0) 'Pixel coverage or parity failed'
  $Lines.Add('- PASS pixel parity: 353,143,200 large + 111,897,000 small, zero differing pixels.')
  $Stage = 'CTest'
  Beat
  Require ((Hash 'build/perf/libexreader.dll') -eq $Expected) 'CTest build DLL changed'
  Native ctest @('--test-dir','build/perf','--parallel','4','--output-on-failure') "$Out/ctest.txt"
  $ct=Get-Content -Raw -LiteralPath "$Out/ctest.txt"
  Require ($ct -match '100% tests passed,\s*0 tests failed out of 577|100% tests passed out of 577') 'Expected all 577 tests to pass'
  Require ((Hash 'build/perf/libexreader.dll') -eq $Expected) 'CTest build DLL changed'
  $Lines.Add('- PASS CTest: 577/577.')
  $Stage = 'RSS'
  Beat
  $rssSrc = Get-Content -Raw -LiteralPath "$P/rss.py"
  $needle = "tmp = Path(__file__).resolve().parent/'rss-raw'; tmp.mkdir(exist_ok=True)"
  Require ($rssSrc.Contains($needle)) 'RSS harness changed'
  $rssRun = "$E/harness/rss-d733-$((Split-Path $Out -Leaf)).py"
  [System.IO.File]::WriteAllText((Join-Path $Repo $rssRun), $rssSrc.Replace($needle, "tmp = out.parent/'rss-raw'; tmp.mkdir(exist_ok=True)"))
  Native python @('-B','-u',$rssRun,"$D/base.dll",$FinalDll,"$Out/rss.json") "$Out/rss.log"
  $rr=ReadJ "$Out/rss.json"
  Require ($rr.dll_sha256.A -eq $BaseHash -and $rr.dll_sha256.B -eq $Expected) 'RSS evidence DLL hash mismatch'
  foreach ($name in 'image-heavy-100','real-mixed-120','vector-heavy-100') {
    $samples=@($rr.working_sets.$name)
    Require ($samples.Count -eq 3 -and @($samples | Where-Object { $_.A -le 0 -or $_.B -le 0 }).Count -eq 0) "Missing RSS samples for $name"
    $a=($samples.A | Sort-Object)[1]; $b=($samples.B | Sort-Object)[1]
    $delta=100.0*($b/$a-1)
    $Lines.Add(('- RSS {0}: {1:+0.00;-0.00;0.00}% (median peak working set, cap +10%).' -f $name,$delta))
    Require ($delta -le 10) "RSS above +10% for $name"
  }
  $Stage = 'p1–21 paired acceptance'
  $pdf='tests/fixtures/pdf-large/real-mixed-120.pdf'
  $control=Ab "$D/base.dll" "$D/base-copy.dll" 'control-p1-21' 15 $pdf 1 21 1200
  $trial=Ab "$D/base.dll" $FinalDll 'candidate-p1-21' 15 $pdf 1 21 1200
  $cs=[double]$control.summary.saving_median_ms
  $ts=[double]$trial.summary.saving_median_ms
  $Lines.Add(('- p1–21 same-DLL control: median {0:+0.000;-0.000;0.000} ms, range [{1:0.000}, {2:0.000}] ms (15 rounds).' -f $cs,$control.summary.saving_min_ms,$control.summary.saving_max_ms))
  $Lines.Add(('- p1–21 candidate: median paired saving {0:+0.000;-0.000;0.000} ms, range [{1:0.000}, {2:0.000}] ms, {3}/15 faster. Per-round pre-CPU in both JSONs.' -f $ts,$trial.summary.saving_min_ms,$trial.summary.saving_max_ms,$trial.summary.rounds_b_faster))
  Require ($ts -gt [math]::Abs($cs) -and $trial.summary.rounds_b_faster -gt 7) 'Positive paired gain not established above the control median'
  $Stage = 'absolute frozen fixture gates'
  $failed=[System.Collections.Generic.List[string]]::new()
  foreach ($name in $keys) {
    $limit=$g.items.$name
    $x=Ab "$D/base.dll" $FinalDll "gate-$name" 15 $limit.fixture $limit.pages[0] $limit.pages[1] $limit.width
    $p50=$x.summary.B_page_p50_ms
    Require ($null -ne $p50 -and $p50 -gt 0) "No valid p50 for $name"
    $pass=$p50 -le $limit.limit_ms
    $verdict=if($pass){'PASS'}else{'FAIL'}
    $Lines.Add(('- {0} {1}: candidate {2:0.0000000} vs frozen {3:0.0000000} ms/page.' -f $verdict,$name,$p50,$limit.limit_ms))
    if (-not $pass) { $failed.Add($name) }
  }
  Require ($failed.Count -eq 0) "Frozen thresholds missed: $($failed -join ', ')"
  Beat
  Require ((Hash $FinalDll) -eq $Expected -and (Hash 'build/perf/libexreader.dll') -eq $Expected) 'Candidate/build hash changed during run'
} catch {
  $Failure = "$Stage : $($_.Exception.Message)"
} finally {
  if ($Held) {
    & pwsh -NoProfile -File $Lock -Holder $Holder -Release
    if ($LASTEXITCODE -ne 0) { $Failure = "$Failure; bench release failed" }
  }
  $verdict=if($Failure){"FAIL / incomplete: $Failure"}else{'PASS: all ordered checks passed; no PR or merge performed.'}
  $body = @($Lines[0], '', "**Verdict: $verdict**", '') + @($Lines | Select-Object -Skip 1)
  Set-Content -LiteralPath "$Out/REPORT.md" -Value $body -Encoding utf8
  if (-not (Test-Path -LiteralPath $Report)) { Copy-Item -LiteralPath "$Out/REPORT.md" -Destination $Report }
}
if ($Failure) { throw $Failure }