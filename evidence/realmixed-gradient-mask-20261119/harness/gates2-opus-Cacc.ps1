# Five frozen fixture gates, same-session calibration. No builds, no CPU gate; pre-CPU recorded only.
# Per fixture, four paired ab.py runs (15 warm rounds each, AB/BA alternating per page, flipped per round):
#   cand-vs-main   A=main 9c2443edf (384B2098)  B=candidate D733D2FB   (brief's cand/ctrl ratio)
#   cand-vs-frozen A=frozen 36821FEA (gate DLL) B=candidate D733D2FB   (limit = 1.03 x frozen, re-measured now)
#   frozen-null    A=frozen  B=frozen copy     (noise floor + today's absolute frozen p50)
#   main-null      A=main    B=main copy       (noise floor)
$ErrorActionPreference = 'Stop'; $env:EXR_IDLE_GATE = 'off'
Set-Location 'C:\Users\Oscar\Documents\Codex\EXReader-rmgradmask'
$H = 'opus-Cacc'; $Root = 'C:\Users\Oscar\OneDrive\Desktop\deepseekHarness'
$Lock = "$Root/ops/bench-lock.ps1"; $Gate = "$Root/ops/build-gate.ps1"
$E = 'evidence/realmixed-gradient-mask-20261119'; $D = "$E/_work/dlls"; $C = 'build/perf/libexreader.dll'
$Out = "$E/gates2-opus-Cacc-$(Get-Date -Format yyyyMMdd-HHmmss)"; New-Item -ItemType Directory $Out | Out-Null
$g = Get-Content -Raw "$E/opus-Cacc-20261119-155040/frozen-gates.json" | ConvertFrom-Json
$arms = @(@('cand-vs-main', "$D/main-9c2443edf.dll", $C), @('cand-vs-frozen', "$D/frozen-36821fea.dll", $C),
          @('frozen-null', "$D/frozen-36821fea.dll", "$D/frozen-36821fea-copy.dll"), @('main-null', "$D/main-9c2443edf.dll", "$D/main-9c2443edf-copy.dll"))
& pwsh -NoProfile -File $Lock -Holder $H -Wait; if ($LASTEXITCODE) { throw 'no bench lock' }
try {
  foreach ($k in 'pptx-20-600','pptx-20-1200','word-5-600','word-5-1200','deck-1200') {
    $it = $g.items.$k
    foreach ($arm in $arms) {
      $s = & pwsh -NoProfile -File $Gate -Status; if (-not ($s -match 'builds\s*:\s*0\s*/')) { throw "build activity: $s" }
      python -B -u "$E/../dense-vector-residual-20261119/harness/ab.py" $arm[1] $arm[2] "$Out/$k-$($arm[0]).json" --holder $H --rounds 15 --pdf $it.fixture --first $it.pages[0] --last $it.pages[1] --width $it.width 2>&1 | Out-File "$Out/$k-$($arm[0]).log"
      if ($LASTEXITCODE) { throw "ab.py failed $k $($arm[0])" }
      "$(Get-Date -Format HH:mm:ss) $k $($arm[0]) done"
    }
  }
} finally { & pwsh -NoProfile -File $Lock -Holder $H -Release }
"OUT $Out"
