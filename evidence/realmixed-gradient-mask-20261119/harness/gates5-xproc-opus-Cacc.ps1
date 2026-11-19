# Cross-process paired gates (xab.py: one worker process per DLL), five frozen fixtures, 2 reps x 4 arms,
# arm order rotated per rep. 15 warm rounds. No builds; no CPU gate; pre-CPU recorded only.
$ErrorActionPreference = 'Stop'; $env:EXR_IDLE_GATE = 'off'
Set-Location 'C:\Users\Oscar\Documents\Codex\EXReader-rmgradmask'
$H = 'opus-Cacc'; $Root = 'C:\Users\Oscar\OneDrive\Desktop\deepseekHarness'
$Lock = "$Root/ops/bench-lock.ps1"; $Gate = "$Root/ops/build-gate.ps1"
$E = 'evidence/realmixed-gradient-mask-20261119'; $D = "$E/_work/dlls"
$Out = "$E/gates5-xproc-opus-Cacc-$(Get-Date -Format yyyyMMdd-HHmmss)"; New-Item -ItemType Directory $Out | Out-Null
$g = Get-Content -Raw "$E/opus-Cacc-20261119-155040/frozen-gates.json" | ConvertFrom-Json
$arms = @(@('cand-vs-main', "$D/main-9c2443edf.dll", "$D/cand-d733.dll"), @('cand-vs-frozen', "$D/frozen-36821fea.dll", "$D/cand-d733.dll"),
          @('main-null', "$D/main-9c2443edf.dll", "$D/main-9c2443edf-copy.dll"), @('frozen-null', "$D/frozen-36821fea.dll", "$D/frozen-36821fea-copy.dll"))
& pwsh -NoProfile -File $Lock -Holder $H -Wait; if ($LASTEXITCODE) { throw 'no bench lock' }
try {
  foreach ($rep in 0..1) { foreach ($k in 'pptx-20-600','pptx-20-1200','word-5-600','word-5-1200','deck-1200') {
    $it = $g.items.$k
    foreach ($j in 0..3) { $arm = $arms[($j + 2*$rep) % 4]
      # bench lock held => new builds BLOCKED; wait for in-flight ones to drain before timing (never time during a build)
      while ($true) { $s = & pwsh -NoProfile -File $Gate -Status; if ($s -match 'builds\s*:\s*0\s*/') { break }; "$(Get-Date -Format HH:mm:ss) waiting for build drain: $s"; & pwsh -NoProfile -File $Lock -Holder $H -Heartbeat | Out-Null; Start-Sleep 15 }
      python -B -u "$E/harness/xab.py" $arm[1] $arm[2] "$Out/$k-$($arm[0])-$rep.json" --holder $H --rounds 15 --pdf $it.fixture --first $it.pages[0] --last $it.pages[1] --width $it.width 2>&1 | Out-File "$Out/$k-$($arm[0])-$rep.log"
      if ($LASTEXITCODE) { throw "xab.py failed $k $($arm[0]) $rep" }
      "$(Get-Date -Format HH:mm:ss) $k $($arm[0]) $rep done" }
  } }
} finally { & pwsh -NoProfile -File $Lock -Holder $H -Release }
"OUT $Out"
