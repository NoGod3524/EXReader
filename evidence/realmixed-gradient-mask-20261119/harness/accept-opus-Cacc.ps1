# C lane (p1-21 gradient + soft mask) acceptance, holder opus-Cacc.
# Candidate: pre-built D733D2FB (not rebuilt). Control: fresh build of main 9c2443edf.
# Order: build control under build-gate -> release slot -> bench-lock -> pixels -> ctest
#        -> RSS -> p1-21 null + paired -> five frozen gates -> release lock.
# Measurement policy 2026-11-19 13:11: no CPU gate, no round filtering; pre-CPU recorded only.
param(
  [string]$Repo = 'C:\Users\Oscar\Documents\Codex\EXReader-rmgradmask',
  [string]$HarnessRoot = 'C:\Users\Oscar\OneDrive\Desktop\deepseekHarness',
  [string]$MainRev = '9c2443edf',
  [int]$Rounds = 15,
  [switch]$SkipAttribution
)
$ErrorActionPreference = 'Stop'
$env:EXR_IDLE_GATE = 'off'
Set-Location -LiteralPath $Repo
$Holder   = 'opus-Cacc'
$Expected = 'D733D2FB4BFE98B1C0BD67F9CFA6754087BEE709DF8690837418C64D47C4F490'
$OldBase  = '54E374D53FF788793AA1A7FC9D91BFC9787966088D65AC2D60CED236B127BB65'  # 2c27a907a, attribution only
$E = 'evidence/realmixed-gradient-mask-20261119'
$D = "$E/_work/dlls"
$P = 'evidence/dense-vector-residual-20261119/harness'
$Lock = "$HarnessRoot/ops/bench-lock.ps1"
$Gate = "$HarnessRoot/ops/build-gate.ps1"
$GatePath = "$HarnessRoot/projects/exreader-handoff/EXREADER-FIXTURE-GATES.json"
$Cand = 'build/perf/libexreader.dll'
$CandCopy = "$E/recovery-20261119-145608/final-recovered.dll"
$Stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$Out = "$E/opus-Cacc-$Stamp"
New-Item -ItemType Directory -Path $Out, "$Out/gates" | Out-Null

function Require($ok, [string]$why) { if (-not $ok) { throw $why } }
function Hash([string]$p) { (Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash }
function ReadJ([string]$f) { Get-Content -Raw -LiteralPath $f | ConvertFrom-Json }
function Native([string]$program, [string[]]$argv, [string]$log) {
  & $program @argv 2>&1 | Tee-Object -FilePath $log | Out-Host
  if ($LASTEXITCODE -ne 0) { throw "$program failed (exit $LASTEXITCODE); see $log" }
}
function Med([double[]]$v) { $s = $v | Sort-Object; $n = $s.Count; if ($n % 2) { $s[($n-1)/2] } else { ($s[$n/2-1] + $s[$n/2]) / 2 } }
function CpuStats($rows) {
  $c = [double[]]@($rows | ForEach-Object { $_.cpu_busy_pre_percent })
  [ordered]@{ min = ($c | Measure-Object -Minimum).Minimum; median = (Med $c); max = ($c | Measure-Object -Maximum).Maximum; per_round = $c }
}
function Beat {
  & pwsh -NoProfile -File $Lock -Holder $Holder -Heartbeat | Out-Null
  Require ($LASTEXITCODE -eq 0) 'Lost bench lock'
  $s = & pwsh -NoProfile -File $Gate -Status
  Require ($LASTEXITCODE -eq 0 -and ($s -match 'builds\s*:\s*0\s*/')) "Build activity during measurement: $s"
}
function Ab([string]$a, [string]$b, [string]$json, [string]$pdf, [int]$first, [int]$last, [int]$width) {
  Beat
  Native python @('-B','-u',"$P/ab.py",$a,$b,$json,'--holder',$Holder,'--rounds',"$Rounds",'--pdf',$pdf,'--first',"$first",'--last',"$last",'--width',"$width") ($json -replace '\.json$','.log')
  $x = ReadJ $json
  Require ($x.a_sha256 -eq (Hash $a) -and $x.b_sha256 -eq (Hash $b)) "$json DLL hash mismatch"
  Require ($x.pdf_sha256 -eq (Hash $pdf) -and $x.width -eq $width -and $x.pages[0] -eq $first -and $x.pages[1] -eq $last) "$json fixture mismatch"
  Require (@($x.rounds).Count -eq $Rounds -and @($x.mismatched_pages).Count -eq 0) "$json round count or pixel mismatch"
  for ($i = 0; $i -lt $Rounds; $i++) {
    $row = $x.rounds[$i]; $order = if (($i+1) % 2) { 'BA' } else { 'AB' }
    Require ($row.round -eq ($i+1) -and $row.start -eq $order -and $null -ne $row.cpu_busy_pre_percent) "$json bad round order / missing pre-CPU"
  }
  $x
}

$L = [System.Collections.Generic.List[string]]::new()
$Stage = 'preflight'; $Failure = $null; $GateHeld = $false; $LockHeld = $false; $hb = $null
$Results = [ordered]@{}
try {
  # ---------- preflight ----------
  Require ((Hash $Cand) -eq $Expected -and (Hash $CandCopy) -eq $Expected) 'Candidate is not D733D2FB'
  $mainSha = (git rev-parse "$MainRev^{commit}").Trim()
  Require ($LASTEXITCODE -eq 0) 'Cannot resolve main revision'
  git diff --quiet 3cec310fa HEAD -- src tests CMakeLists.txt cmake
  Require ($LASTEXITCODE -eq 0) 'Source changed after 3cec310fa; candidate build tree may be stale'
  $g = ReadJ $GatePath
  Require ($g.status -eq 'canonical' -and $g.warm_rounds -eq 15 -and $g.margin -eq 1.03 -and $g.harness -eq "$P/ab.py") 'Unrecognised frozen gate policy'
  $keys = @('pptx-20-600','pptx-20-1200','word-5-600','word-5-1200','deck-1200')
  $limits = @(0.8324975,1.6756555,2.2197015,6.9460625,9.2558375)
  for ($i = 0; $i -lt 5; $i++) {
    $row = $g.items.($keys[$i])
    Require ($null -ne $row -and [math]::Abs($row.limit_ms - $limits[$i]) -lt 1e-9 -and (Hash $row.fixture) -eq $row.sha256) "Frozen gate mismatch: $($keys[$i])"
  }
  Copy-Item -LiteralPath $GatePath -Destination "$Out/frozen-gates.json"
  $cache = Get-Content build/perf/CMakeCache.txt
  function CacheVal([string]$k) { $m = $cache | Select-String -Pattern "^$([regex]::Escape($k)):[A-Z]+=(.*)$"; if ($m) { $m.Matches[0].Groups[1].Value } }
  $cmake = CacheVal 'CMAKE_COMMAND'; $ninja = CacheVal 'CMAKE_MAKE_PROGRAM'; $cc = CacheVal 'CMAKE_C_COMPILER'; $cxx = CacheVal 'CMAKE_CXX_COMPILER'
  Require ($cmake -and $ninja -and $cc) 'Cannot read toolchain from candidate CMakeCache'
  $env:PATH = (Split-Path $cc) + ';' + $env:PATH
  $cfg = @('-G','Ninja','-DCMAKE_BUILD_TYPE=Release',"-DCMAKE_C_COMPILER=$cc","-DCMAKE_MAKE_PROGRAM=$ninja")
  if ($cxx) { $cfg += "-DCMAKE_CXX_COMPILER=$cxx" }
  foreach ($line in $cache) { if ($line -match '^(EXR_(BUILD|ENABLE)_[A-Z0-9_]+|EXR_REPRODUCIBLE|EXR_SANITIZE):BOOL=(ON|OFF)$') { $cfg += "-D$($Matches[1])=$($Matches[3])" } }
  # Offline dependency sources: reuse the candidate tree's pinned FetchContent source dirs (downloads fail TLS on this host).
  foreach ($line in $cache) { if ($line -match '^(FETCHCONTENT_SOURCE_DIR_[A-Z0-9_]+):PATH=(.+)$') { $cfg += "-D$($Matches[1])=$($Matches[2])" } }

  # ---------- build control from main (build slot only; no timing) ----------
  $Stage = 'build control'
  $Src = Join-Path $env:TEMP "opus-Cacc-main-$($mainSha.Substring(0,9))-$Stamp"
  New-Item -ItemType Directory -Path $Src | Out-Null
  git archive --format=tar -o "$Src.tar" $mainSha -- . ':(exclude)evidence'
  Require ($LASTEXITCODE -eq 0) 'git archive failed'
  tar -xf "$Src.tar" -C $Src
  Require ($LASTEXITCODE -eq 0) 'tar extract failed'
  & pwsh -NoProfile -File $Gate -Holder $Holder -Wait
  Require ($LASTEXITCODE -eq 0) 'Did not acquire build slot'
  $GateHeld = $true
  Native $cmake (@('-S',$Src,'-B',"$Src/build") + $cfg) "$Out/control-configure.log"
  Native $ninja @('-C',"$Src/build",'libexreader.dll') "$Out/control-build.log"
  & pwsh -NoProfile -File $Gate -Holder $Holder -Release
  Require ($LASTEXITCODE -eq 0) 'Build slot release failed'
  $GateHeld = $false
  $Ctl = "$D/main-$($mainSha.Substring(0,9)).dll"; $CtlCopy = "$D/main-$($mainSha.Substring(0,9))-copy.dll"
  Require (-not (Test-Path $Ctl) -and -not (Test-Path $CtlCopy)) "Control DLL path already exists: $Ctl"
  Copy-Item "$Src/build/libexreader.dll" $Ctl; Copy-Item "$Src/build/libexreader.dll" $CtlCopy
  $CtlHash = Hash $Ctl
  Require ($CtlHash -eq (Hash $CtlCopy) -and $CtlHash -ne $Expected -and $CtlHash -ne $OldBase) 'Control DLL provenance check failed'
  Set-Content "$Out/control.sha256" "$CtlHash  main $mainSha"
  $L.Add("- Control: fresh build of main ``$mainSha``, SHA-256 ``$CtlHash`` (same toolchain and EXR_* options as the candidate tree).")
  $L.Add("- Candidate: ``$Expected`` (not rebuilt). Note: candidate branch base is 2c27a907a, so it does **not** contain #271 (affine_image.c); control does.")

  # ---------- bench lock ----------
  $Stage = 'bench lock'
  & pwsh -NoProfile -File $Lock -Holder $Holder -Wait
  Require ($LASTEXITCODE -eq 0) 'Did not acquire bench lock'
  $LockHeld = $true
  $hb = Start-Job -ArgumentList $Lock, $Holder -ScriptBlock { param($lk, $h) while ($true) { & pwsh -NoProfile -File $lk -Holder $h -Heartbeat | Out-Null; Start-Sleep -Seconds 20 } }
  $deadline = (Get-Date).AddMinutes(10)
  while ($true) { $s = & pwsh -NoProfile -File $Gate -Status; if ($s -match 'builds\s*:\s*0\s*/') { break }; Require ((Get-Date) -lt $deadline) 'Build slots did not drain'; Start-Sleep 5 }

  # ---------- gate 1: pixels ----------
  $Stage = 'pixel identity'
  Beat
  Native python @('-B','-u',"$P/pixels.py",$Ctl,$Cand,"$Out/pixels.json") "$Out/pixels.log"
  $px = ReadJ "$Out/pixels.json"
  Require ($px.a_sha256 -eq $CtlHash -and $px.b_sha256 -eq $Expected) 'Pixel evidence DLL hash mismatch'
  $Results.pixels = [ordered]@{ large = $px.totals.large; small = $px.totals.small }
  $pixPass = ($px.totals.large.pixels -eq 353143200 -and $px.totals.small.pixels -eq 111897000 -and $px.totals.large.differing_pixels -eq 0 -and $px.totals.small.differing_pixels -eq 0)
  $L.Add(('- {0} pixels: large {1:N0} px / {2} differing; small {3:N0} px / {4} differing.' -f ($(if ($pixPass) {'PASS'} else {'FAIL'})), $px.totals.large.pixels, $px.totals.large.differing_pixels, $px.totals.small.pixels, $px.totals.small.differing_pixels))
  foreach ($c in $px.cells) { $L.Add(('  - {0}@{1}: {2} pages, {3:N0} px, {4} differing, mismatched pages [{5}]' -f $c.pdf, $c.width, $c.pages, $c.pixels, $c.differing_pixels, ($c.mismatched_pages -join ','))) }
  Require $pixPass 'Pixel identity failed'

  # ---------- ctest confirmation ----------
  $Stage = 'CTest'
  Beat
  $ctestExe = Join-Path (Split-Path $cmake) 'ctest.exe'
  & $ctestExe --test-dir build/perf --parallel 4 --output-on-failure > "$Out/ctest.txt" 2>&1
  $ct = Get-Content -Raw "$Out/ctest.txt"
  Require ((Hash $Cand) -eq $Expected) 'Candidate DLL changed during CTest'
  $ctPass = $ct -match '100% tests passed,?\s*(0 tests failed )?out of 577'
  $L.Add("- $(if ($ctPass) {'PASS'} else {'FAIL'}) CTest re-run: " + (($ct -split "`n" | Select-String 'tests passed|Total Test time' | ForEach-Object { $_.Line.Trim() }) -join '; '))
  Require $ctPass 'CTest not 577/577'

  # ---------- gate 2: RSS ----------
  $Stage = 'RSS'
  Beat
  $rssSrc = Get-Content -Raw "$P/rss.py"
  $needle = "tmp = Path(__file__).resolve().parent/'rss-raw'; tmp.mkdir(exist_ok=True)"
  Require ($rssSrc.Contains($needle)) 'RSS harness changed'
  $rssRun = "$E/harness/rss-opus-Cacc-$Stamp.py"
  [System.IO.File]::WriteAllText((Join-Path $Repo $rssRun), $rssSrc.Replace($needle, "tmp = out.parent/'rss-raw'; tmp.mkdir(exist_ok=True)"))
  Native python @('-B','-u',$rssRun,$Ctl,$Cand,"$Out/rss.json") "$Out/rss.log"
  $rr = ReadJ "$Out/rss.json"
  Require ($rr.dll_sha256.A -eq $CtlHash -and $rr.dll_sha256.B -eq $Expected) 'RSS DLL hash mismatch'
  $rssPass = $true; $Results.rss = [ordered]@{}
  foreach ($name in 'image-heavy-100','real-mixed-120','vector-heavy-100') {
    $smp = @($rr.working_sets.$name); Require ($smp.Count -eq 3) "Missing RSS samples for $name"
    $a = Med ([double[]]$smp.A); $b = Med ([double[]]$smp.B); $dl = 100.0 * ($b / $a - 1)
    $Results.rss[$name] = [ordered]@{ control_median_bytes = $a; candidate_median_bytes = $b; delta_pct = $dl }
    $ok = $dl -le 10; if (-not $ok) { $rssPass = $false }
    $L.Add(('- {0} RSS {1}: control {2:N1} MiB, candidate {3:N1} MiB, {4:+0.00;-0.00}% (cap +10%).' -f ($(if ($ok) {'PASS'} else {'FAIL'})), $name, ($a/1MB), ($b/1MB), $dl))
  }
  Require $rssPass 'RSS above +10%'

  # ---------- gate 3a: p1-21 paired ----------
  $Stage = 'p1-21 paired'
  $pdf = 'tests/fixtures/pdf-large/real-mixed-120.pdf'
  $null0 = Ab $Ctl $CtlCopy "$Out/p121-null.json" $pdf 1 21 1200
  $trial = Ab $Ctl $Cand "$Out/p121-candidate.json" $pdf 1 21 1200
  $attr = $null
  if (-not $SkipAttribution) { $attr = Ab "$D/base.dll" $Cand "$Out/p121-attribution-oldbase.json" $pdf 1 21 1200 }
  $ns = [double]$null0.summary.saving_median_ms; $ts = [double]$trial.summary.saving_median_ms
  $p121 = [ordered]@{
    fixture = $pdf; pages = @(1,21); width = 1200; rounds = $Rounds; order = $trial.order
    policy = 'no CPU gate; no rounds dropped; pre-CPU recorded only'
    control_dll = $CtlHash; candidate_dll = $Expected
    null_control = [ordered]@{ summary = $null0.summary; pre_cpu = (CpuStats $null0.rounds); per_round_saving_ms = @($null0.rounds.saving_ms) }
    candidate    = [ordered]@{ summary = $trial.summary; pre_cpu = (CpuStats $trial.rounds); per_round_saving_ms = @($trial.rounds.saving_ms) }
    criterion = 'candidate median paired saving > 0 and > |null-control median|; candidate faster in a majority of rounds (null max |A-B| reported for context)'
  }
  if ($attr) { $p121.attribution_vs_2c27a907a = [ordered]@{ note = 'supplementary only, not used for verdict'; summary = $attr.summary; pre_cpu = (CpuStats $attr.rounds); per_round_saving_ms = @($attr.rounds.saving_ms) } }
  $nullSpread = [math]::Max([math]::Abs([double]$null0.summary.saving_min_ms), [math]::Abs([double]$null0.summary.saving_max_ms))
  $p121Pass = ($ts -gt [math]::Abs($ns) -and $ts -gt 0 -and $trial.summary.rounds_b_faster -gt ($Rounds / 2))
  $p121.verdict = if ($p121Pass) { 'PASS' } else { 'FAIL' }
  $p121.null_max_abs_saving_ms = $nullSpread
  $p121 | ConvertTo-Json -Depth 8 | Set-Content "$Out/p121.json" -Encoding utf8
  $Results.p121 = $p121
  $L.Add(('- {0} p1-21 (real-mixed-120@1200, {1} rounds): candidate median saving {2:+0.000;-0.000} ms (A {3:0.0} -> B {4:0.0} ms/round), range [{5:0.000}, {6:0.000}], {7}/{1} faster; null median {8:+0.000;-0.000} ms, range [{9:0.000}, {10:0.000}].' -f ($(if ($p121Pass) {'PASS'} else {'FAIL'})), $Rounds, $ts, $trial.summary.A_median_ms, $trial.summary.B_median_ms, $trial.summary.saving_min_ms, $trial.summary.saving_max_ms, $trial.summary.rounds_b_faster, $ns, $null0.summary.saving_min_ms, $null0.summary.saving_max_ms))
  $pairs = [System.Collections.Generic.List[object]]::new()
  $pairs.Add(@('null', $null0)); $pairs.Add(@('candidate', $trial))
  if ($attr) { $pairs.Add(@('attribution-vs-2c27a907a', $attr)) }
  foreach ($pair in $pairs) {
    $cs = CpuStats $pair[1].rounds
    $L.Add(('  - {0} pre-CPU %: min {1:0.0} / median {2:0.0} / max {3:0.0}; per round [{4}]' -f $pair[0], $cs.min, $cs.median, $cs.max, (($cs.per_round | ForEach-Object { '{0:0.0}' -f $_ }) -join ', ')))
    $L.Add(('  - {0} per-round A-B ms: [{1}]' -f $pair[0], ((@($pair[1].rounds.saving_ms) | ForEach-Object { '{0:+0.00;-0.00}' -f $_ }) -join ', ')))
    $hi = @($pair[1].rounds | Where-Object { $_.cpu_busy_pre_percent -gt [math]::Max(25, 2 * $cs.median) })
    if ($hi.Count) { $L.Add(('  - {0}: rounds with noticeably high pre-CPU (kept in statistics): {1}' -f $pair[0], (($hi | ForEach-Object { "r$($_.round)=$('{0:0.0}' -f $_.cpu_busy_pre_percent)%" }) -join ', '))) }
  }
  if ($attr) { $L.Add(('  - Supplementary attribution vs old base 2c27a907a (C change alone, no #271): median saving {0:+0.000;-0.000} ms, {1}/{2} faster. Not used for verdict.' -f $attr.summary.saving_median_ms, $attr.summary.rounds_b_faster, $Rounds)) }

  # ---------- gate 3b: five frozen fixture gates ----------
  $Stage = 'fixture gates'
  $gatePass = $true; $Results.gates = [ordered]@{}
  foreach ($k in $keys) {
    $lim = $g.items.$k
    $x = Ab $Ctl $Cand "$Out/gates/$k.json" $lim.fixture $lim.pages[0] $lim.pages[1] $lim.width
    $b50 = [double]$x.summary.B_page_p50_ms; $a50 = [double]$x.summary.A_page_p50_ms
    $ok = $b50 -gt 0 -and $b50 -le $lim.limit_ms; if (-not $ok) { $gatePass = $false }
    $cs = CpuStats $x.rounds
    $Results.gates[$k] = [ordered]@{ candidate_p50_ms = $b50; control_p50_ms = $a50; ratio_cand_over_ctrl = $b50 / $a50; baseline_ms = $lim.baseline_ms; limit_ms = $lim.limit_ms; pass = $ok; pre_cpu = $cs }
    $L.Add(('- {0} {1}: candidate p50 {2:0.00000} ms/page vs limit {3:0.0000000} (baseline {4:0.00000}); control {5:0.00000}, cand/ctrl {6:0.0000}; pre-CPU min/med/max {7:0.0}/{8:0.0}/{9:0.0}%.' -f ($(if ($ok) {'PASS'} else {'FAIL'})), $k, $b50, $lim.limit_ms, $lim.baseline_ms, $a50, ($b50/$a50), $cs.min, $cs.median, $cs.max))
  }
  Require $p121Pass 'p1-21 paired gain not established'
  Require $gatePass 'Frozen fixture gate(s) missed'
  Beat
  Require ((Hash $Cand) -eq $Expected -and (Hash $Ctl) -eq $CtlHash) 'DLL changed during run'
} catch {
  $Failure = "$Stage : $($_.Exception.Message)"
} finally {
  if ($hb) { Stop-Job $hb -ErrorAction SilentlyContinue; Remove-Job $hb -Force -ErrorAction SilentlyContinue }
  if ($GateHeld) { & pwsh -NoProfile -File $Gate -Holder $Holder -Release; if ($LASTEXITCODE -ne 0) { $Failure = "$Failure; build slot release failed" } }
  if ($LockHeld) { & pwsh -NoProfile -File $Lock -Holder $Holder -Release; if ($LASTEXITCODE -ne 0) { $Failure = "$Failure; bench release failed" } }
  $Results.failure = $Failure
  $Results | ConvertTo-Json -Depth 10 | Set-Content "$Out/summary.json" -Encoding utf8
  $verdict = if ($Failure) { "FAIL / incomplete: $Failure" } else { 'PASS: all three gates passed (no push / PR performed by this script).' }
  $body = @('# C lane (p1-21 gradient + soft mask) acceptance - opus-Cacc', '', "**Verdict: $verdict**", '', "Run directory: ``$Out``", '') + $L
  Set-Content "$Out/RUN.md" -Value $body -Encoding utf8
}
if ($Failure) { throw $Failure }
