# Full pixel parity (353,143,200 + 111,897,000) and ctest (577/577), gated to avoid interfering with any active measurement.
$ErrorActionPreference = 'Stop'
$gate = 'C:\Users\Oscar\OneDrive\Desktop\deepseekHarness\ops\build-gate.ps1'
$E = 'evidence/image-p71-100-composite-20261119'
$D = "$E/_work/dlls"
$OUT = "$E/final"
$PIXELS = 'evidence/dense-vector-residual-20261119/harness/pixels.py'

pwsh -NoProfile -File $gate -Holder agy-A -Wait
try {
  Write-Output "=== 1. Pixel Parity (465,040,200 pixels) ==="
  python -B -u $PIXELS "$D/base.dll" "$D/final.dll" "$OUT/pixels.json"
  if ($LASTEXITCODE -ne 0) { throw "pixels.py failed" }

  Write-Output "=== 2. CTest (577/577) ==="
  ctest --test-dir build/perf -j 4 --output-on-failure | Tee-Object -FilePath "$OUT/ctest.txt"
  if ($LASTEXITCODE -ne 0) { throw "ctest failed" }

  Write-Output "FINAL-VERIFY-DONE"
} finally {
  pwsh -NoProfile -File $gate -Holder agy-A -Release
}
