# C lane acceptance final verification + deck-1200 31-round tiebreak, holder agy-Cacc.
# Lock discipline (2026-11-19 17:02): NO builds performed; wait for builds 0/2 BEFORE taking bench-lock;
# if a build sneaks in after acquiring bench-lock and doesn't clear in 90s, release bench-lock and retry.
# Measurement policy (2026-11-19 13:11): EXR_IDLE_GATE=off, no CPU gate, no round filtering, pre-CPU recorded only.
param(
  [string]$Repo = 'C:\Users\Oscar\Documents\Codex\EXReader-rmgradmask',
  [string]$HarnessRoot = 'C:\Users\Oscar\OneDrive\Desktop\deepseekHarness',
  [int]$TiebreakRounds = 31
)
$ErrorActionPreference = 'Stop'
$env:EXR_IDLE_GATE = 'off'
Set-Location -LiteralPath $Repo

$Holder   = 'agy-Cacc'
$Expected = 'D733D2FB4BFE98B1C0BD67F9CFA6754087BEE709DF8690837418C64D47C4F490'
$MainHash = '384B2098F283F8599418DAC5CB84CCFA2CC95A5150BDD46FD3A60FA3DC8B1051'
$FrozHash = '36821FEACB3517143F992B93BFD079E6196FF1F740849FCF9A4197461138F711'

$E = 'evidence/realmixed-gradient-mask-20261119'
$D = "$E/_work/dlls"
$P = 'evidence/dense-vector-residual-20261119/harness'
$Lock = "$HarnessRoot/ops/bench-lock.ps1"
$Gate = "$HarnessRoot/ops/build-gate.ps1"

$Cand     = 'build/perf/libexreader.dll'
$CandCopy = "$E/recovery-20261119-145608/final-recovered.dll"
$MainDll  = "$D/main-9c2443edf.dll"
$MainCopy = "$D/main-9c2443edf-copy.dll"
$FrozDll  = "$D/frozen-36821fea.dll"
$FrozCopy = "$D/frozen-36821fea-copy.dll"

$Stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$Out = "$E/agy-Cacc-verify-$Stamp"
New-Item -ItemType Directory -Path $Out, "$Out/deck-tiebreak" | Out-Null

function Require($ok, [string]$why) { if (-not $ok) { throw $why } }
function Hash([string]$p) { (Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash }
function Log([string]$msg) { Write-Host "$(Get-Date -Format HH:mm:ss) $msg" }

# --- Preflight (no lock) ---
Require ((Hash $Cand) -eq $Expected -and (Hash $CandCopy) -eq $Expected -and (Hash "$D/cand-d733.dll") -eq $Expected) 'Candidate DLL hash mismatch'
Require ((Hash $MainDll) -eq $MainHash -and (Hash $MainCopy) -eq $MainHash) 'Main 9c2443edf DLL hash mismatch'
Require ((Hash $FrozDll) -eq $FrozHash -and (Hash $FrozCopy) -eq $FrozHash) 'Frozen 36821fea DLL hash mismatch'
git diff --quiet 3cec310fa HEAD -- src tests CMakeLists.txt cmake
Require ($LASTEXITCODE -eq 0) 'Source/test tree diverged from 3cec310fa'
Log "Preflight OK. Out=$Out"

# --- Acquire bench-lock ONLY when builds == 0/2 (deadlock-free loop) ---
$LockHeld = $false
try {
  while ($true) {
    while ($true) {
      $gs = (& pwsh -NoProfile -File $Gate -Status) -join ' '
      if ($gs -match 'bench\s*:\s*FREE' -and $gs -match 'builds\s*:\s*0\s*/') { break }
      Log "Waiting (no lock held) for machine idle: $gs"
      Start-Sleep -Seconds 10
    }
    & pwsh -NoProfile -File $Lock -Holder $Holder -Wait | Out-Host
    Require ($LASTEXITCODE -eq 0) 'Failed to acquire bench-lock'
    $LockHeld = $true
    # Confirm no build raced in; wait at most 90s then yield to avoid deadlock
    $clear = $false
    for ($k = 0; $k -lt 9; $k++) {
      $gs = (& pwsh -NoProfile -File $Gate -Status) -join ' '
      if ($gs -match 'builds\s*:\s*0\s*/') { $clear = $true; break }
      Log "Post-acquire build still draining ($k/9): $gs"
      & pwsh -NoProfile -File $Lock -Holder $Holder -Heartbeat | Out-Null
      Start-Sleep -Seconds 10
    }
    if ($clear) { break }
    Log "Build did not clear within 90s; releasing bench-lock to avoid deadlock and retrying"
    & pwsh -NoProfile -File $Lock -Holder $Holder -Release | Out-Host
    $LockHeld = $false
    Start-Sleep -Seconds 15
  }

  function Beat {
    & pwsh -NoProfile -File $Lock -Holder $Holder -Heartbeat | Out-Null
    Require ($LASTEXITCODE -eq 0) 'Lost bench-lock'
    $gs = (& pwsh -NoProfile -File $Gate -Status) -join ' '
    Require ($gs -match 'builds\s*:\s*0\s*/') "Build activity detected during measurement: $gs"
  }

  # --- Step 1: Pixel parity re-check against freshly built main 9c2443edf DLL ---
  Beat
  Log "Step 1: pixels.py ($MainHash vs $Expected)"
  python -B -u "$P/pixels.py" $MainDll $Cand "$Out/pixels.json" 2>&1 | Tee-Object -FilePath "$Out/pixels.log" | Out-Host
  Require ($LASTEXITCODE -eq 0) 'pixels.py failed'
  $px = Get-Content -Raw "$Out/pixels.json" | ConvertFrom-Json
  Require ($px.a_sha256 -eq $MainHash -and $px.b_sha256 -eq $Expected) 'pixels.json hash mismatch'
  Require ($px.totals.large.pixels -eq 353143200 -and $px.totals.large.differing_pixels -eq 0) 'large pixel check failed'
  Require ($px.totals.small.pixels -eq 111897000 -and $px.totals.small.differing_pixels -eq 0) 'small pixel check failed'
  Log "Step 1 PASS: 353,143,200 large + 111,897,000 small = 465,040,200 px, 0 differing"

  # --- Step 2: Peak RSS confirmation ---
  Beat
  Log "Step 2: rss.py ($MainHash vs $Expected)"
  $rssSrc = Get-Content -Raw "$P/rss.py"
  $needle = "tmp = Path(__file__).resolve().parent/'rss-raw'; tmp.mkdir(exist_ok=True)"
  Require ($rssSrc.Contains($needle)) 'rss.py changed'
  $rssRun = "$Out/rss-run.py"
  [System.IO.File]::WriteAllText((Join-Path $Repo $rssRun), $rssSrc.Replace($needle, "tmp = out.parent/'rss-raw'; tmp.mkdir(exist_ok=True)"))
  python -B -u $rssRun $MainDll $Cand "$Out/rss.json" 2>&1 | Tee-Object -FilePath "$Out/rss.log" | Out-Host
  Require ($LASTEXITCODE -eq 0) 'rss.py failed'
  Log "Step 2 PASS: rss.json written"

  # --- Step 3: deck-1200 31-round cross-process tiebreak (2 reps x 4 arms rotated) ---
  $arms = @(
    @('cand-vs-frozen', $FrozDll, $Cand),
    @('cand-vs-main',   $MainDll, $Cand),
    @('frozen-null',    $FrozDll, $FrozCopy),
    @('main-null',      $MainDll, $MainCopy)
  )
  foreach ($rep in 0..1) {
    foreach ($j in 0..3) {
      $arm = $arms[($j + 2 * $rep) % 4]
      Beat
      $tag = "deck-1200-$($arm[0])-$rep"
      Log "Step 3: xab.py $tag ($TiebreakRounds rounds)"
      python -B -u "$E/harness/xab.py" $arm[1] $arm[2] "$Out/deck-tiebreak/$tag.json" `
        --holder $Holder --rounds $TiebreakRounds `
        --pdf tests/fixtures/pdf-ppt/deck.pdf --first 1 --last 15 --width 1200 `
        2>&1 | Out-File "$Out/deck-tiebreak/$tag.log"
      Require ($LASTEXITCODE -eq 0) "xab.py failed on $tag"
      $res = Get-Content -Raw "$Out/deck-tiebreak/$tag.json" | ConvertFrom-Json
      Log ("  $tag done: A_p50={0:0.0000} B_p50={1:0.0000} B/A={2:0.0000} sav={3:+0.00;-0.00} bf={4}/{5} cpu=[{6:0.0},{7:0.0}]" -f `
        $res.summary.A_page_p50_ms, $res.summary.B_page_p50_ms, $res.summary.ratio_B_over_A, `
        $res.summary.saving_median_ms, $res.summary.rounds_b_faster, $res.summary.rounds, `
        $res.summary.cpu_busy_pre_percent_range[0], $res.summary.cpu_busy_pre_percent_range[1])
    }
  }

  # --- Final hash verification ---
  Beat
  Require ((Hash $Cand) -eq $Expected -and (Hash $MainDll) -eq $MainHash -and (Hash $FrozDll) -eq $FrozHash) 'DLL hash changed during run'
  Log "ALL STEPS COMPLETE. OUT=$Out"
} finally {
  if ($LockHeld) {
    & pwsh -NoProfile -File $Lock -Holder $Holder -Release | Out-Host
  }
}
