# Gate calibration (diagnostic only, candidate NOT re-measured): same-DLL runs on the five
# frozen fixtures for (a) the frozen-gate DLL 36821FEA (how the limits were derived) and
# (b) the main control (null floor for cand/ctrl ratio). No CPU gate; pre-CPU recorded only.
$ErrorActionPreference = 'Stop'; $env:EXR_IDLE_GATE = 'off'
Set-Location 'C:\Users\Oscar\Documents\Codex\EXReader-rmgradmask'
$H = 'opus-Cacc'; $Root = 'C:\Users\Oscar\OneDrive\Desktop\deepseekHarness'
$Lock = "$Root/ops/bench-lock.ps1"; $Gate = "$Root/ops/build-gate.ps1"
$E = 'evidence/realmixed-gradient-mask-20261119'; $D = "$E/_work/dlls"; $Out = "$E/opus-Cacc-calib-$(Get-Date -Format yyyyMMdd-HHmmss)"
New-Item -ItemType Directory $Out | Out-Null
$g = Get-Content -Raw "$Root/projects/exreader-handoff/EXREADER-FIXTURE-GATES.json" | ConvertFrom-Json
& pwsh -NoProfile -File $Lock -Holder $H -Wait; if ($LASTEXITCODE) { throw 'no bench lock' }
try {
  foreach ($arm in @(@('frozen', "$D/frozen-36821fea.dll", "$D/frozen-36821fea-copy.dll"), @('main-null', "$D/main-9c2443edf.dll", "$D/main-9c2443edf-copy.dll"))) {
    foreach ($k in 'pptx-20-600','pptx-20-1200','word-5-600','word-5-1200','deck-1200') {
      $s = & pwsh -NoProfile -File $Gate -Status; if (-not ($s -match 'builds\s*:\s*0\s*/')) { throw "build activity: $s" }
      $it = $g.items.$k
      python -B -u evidence/dense-vector-residual-20261119/harness/ab.py $arm[1] $arm[2] "$Out/$($arm[0])-$k.json" --holder $H --rounds 15 --pdf $it.fixture --first $it.pages[0] --last $it.pages[1] --width $it.width 2>&1 | Out-File "$Out/$($arm[0])-$k.log"
      if ($LASTEXITCODE) { throw "ab.py failed $($arm[0]) $k" }
      "$($arm[0]) $k done"
    }
  }
} finally { & pwsh -NoProfile -File $Lock -Holder $H -Release }
"OUT $Out"
