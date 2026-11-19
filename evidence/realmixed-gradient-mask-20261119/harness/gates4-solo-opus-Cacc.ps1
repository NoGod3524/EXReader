# Process-contamination check: is the candidate slower when it is the only DLL in the process?
# Same-DLL pairs only (cand/cand-copy, frozen/frozen-copy, main/main-copy), rotated 3x per fixture so drift
# hits all three equally. Compare absolute pooled p50 across arms. 15 rounds; no CPU gate; pre-CPU recorded.
$ErrorActionPreference = 'Stop'; $env:EXR_IDLE_GATE = 'off'
Set-Location 'C:\Users\Oscar\Documents\Codex\EXReader-rmgradmask'
$H = 'opus-Cacc'; $Root = 'C:\Users\Oscar\OneDrive\Desktop\deepseekHarness'
$Lock = "$Root/ops/bench-lock.ps1"; $Gate = "$Root/ops/build-gate.ps1"
$E = 'evidence/realmixed-gradient-mask-20261119'; $D = "$E/_work/dlls"
$Out = "$E/gates4-solo-opus-Cacc-$(Get-Date -Format yyyyMMdd-HHmmss)"; New-Item -ItemType Directory $Out | Out-Null
$g = Get-Content -Raw "$E/opus-Cacc-20261119-155040/frozen-gates.json" | ConvertFrom-Json
$arms = @(@('cand', "$D/cand-d733.dll", "$D/cand-d733-copy.dll"), @('frozen', "$D/frozen-36821fea.dll", "$D/frozen-36821fea-copy.dll"),
          @('main', "$D/main-9c2443edf.dll", "$D/main-9c2443edf-copy.dll"))
& pwsh -NoProfile -File $Lock -Holder $H -Wait; if ($LASTEXITCODE) { throw 'no bench lock' }
try {
  foreach ($k in 'pptx-20-600','pptx-20-1200','word-5-1200') {
    $it = $g.items.$k
    foreach ($rep in 0..2) { foreach ($j in 0..2) { $arm = $arms[($j + $rep) % 3]
      $s = & pwsh -NoProfile -File $Gate -Status; if (-not ($s -match 'builds\s*:\s*0\s*/')) { throw "build activity: $s" }
      python -B -u "$E/../dense-vector-residual-20261119/harness/ab.py" $arm[1] $arm[2] "$Out/$k-$($arm[0])-$rep.json" --holder $H --rounds 15 --pdf $it.fixture --first $it.pages[0] --last $it.pages[1] --width $it.width 2>&1 | Out-File "$Out/$k-$($arm[0])-$rep.log"
      if ($LASTEXITCODE) { throw "ab.py failed $k $($arm[0]) $rep" }
      "$(Get-Date -Format HH:mm:ss) $k $($arm[0]) $rep done" } }
  }
} finally { & pwsh -NoProfile -File $Lock -Holder $H -Release }
"OUT $Out"
