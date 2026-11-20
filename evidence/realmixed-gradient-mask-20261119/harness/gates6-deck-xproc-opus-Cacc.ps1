# Tiebreak: deck@1200 cand/frozen was 0.968 (ab.py), 1.0385 and 1.007 (xab.py). Cross-process xab.py, 31 rounds, 2 reps x 4 arms rotated.
# No builds; no CPU gate; pre-CPU recorded only.
$ErrorActionPreference = 'Stop'; $env:EXR_IDLE_GATE = 'off'
Set-Location 'C:\Users\Oscar\Documents\Codex\EXReader-rmgradmask'
$H = 'opus-Cacc'; $Root = 'C:\Users\Oscar\OneDrive\Desktop\deepseekHarness'
$Lock = "$Root/ops/bench-lock.ps1"; $Gate = "$Root/ops/build-gate.ps1"
$E = 'evidence/realmixed-gradient-mask-20261119'; $D = "$E/_work/dlls"
$Out = "$E/gates6-deck-xproc-opus-Cacc-$(Get-Date -Format yyyyMMdd-HHmmss)"; New-Item -ItemType Directory $Out | Out-Null
$g = Get-Content -Raw "$E/opus-Cacc-20261119-155040/frozen-gates.json" | ConvertFrom-Json
$arms = @(@('cand-vs-main', "$D/main-9c2443edf.dll", "$D/cand-d733.dll"), @('cand-vs-frozen', "$D/frozen-36821fea.dll", "$D/cand-d733.dll"),
          @('main-null', "$D/main-9c2443edf.dll", "$D/main-9c2443edf-copy.dll"), @('frozen-null', "$D/frozen-36821fea.dll", "$D/frozen-36821fea-copy.dll"))
& pwsh -NoProfile -File $Lock -Holder $H -Wait; if ($LASTEXITCODE) { throw 'no bench lock' }
try {
  foreach ($rep in 0..1) { foreach ($k in 'deck-1200') {
    $it = $g.items.$k
    foreach ($j in 0..3) { $arm = $arms[($j + 2*$rep) % 4]
      # bench lock held => new builds BLOCKED; wait for in-flight ones to drain before timing (never time during a build)
      while ($true) { $s = & pwsh -NoProfile -File $Gate -Status; if ($s -match 'builds\s*:\s*0\s*/') { break }; "$(Get-Date -Format HH:mm:ss) waiting for build drain: $s"; & pwsh -NoProfile -File $Lock -Holder $H -Heartbeat | Out-Null; Start-Sleep 15 }
      python -B -u "$E/harness/xab.py" $arm[1] $arm[2] "$Out/$k-$($arm[0])-$rep.json" --holder $H --rounds 31 --pdf $it.fixture --first $it.pages[0] --last $it.pages[1] --width $it.width 2>&1 | Out-File "$Out/$k-$($arm[0])-$rep.log"
      if ($LASTEXITCODE) { throw "xab.py failed $k $($arm[0]) $rep" }
      "$(Get-Date -Format HH:mm:ss) $k $($arm[0]) $rep done" }
  } }
} finally { & pwsh -NoProfile -File $Lock -Holder $H -Release }
"OUT $Out"
