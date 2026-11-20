$ErrorActionPreference = 'Stop'
Set-Location C:\Users\Oscar\Documents\Codex\EXReader-dvpath
$env:EXR_IDLE_GATE = 'off'
$E = 'evidence\dense-vector-path-residual-20261119'
$W = "$E\harness"
$D = "$E\_work\dlls"
$F = 'tests\fixtures'
$lock = 'C:\Users\Oscar\OneDrive\Desktop\deepseekHarness\ops\bench-lock.ps1'
$gate = 'C:\Users\Oscar\OneDrive\Desktop\deepseekHarness\ops\build-gate.ps1'
$holder = 'agy-B'

function Heartbeat { pwsh -NoProfile -File $lock -Holder $holder -Heartbeat | Out-Null }

pwsh -NoProfile -File $lock -Holder $holder -Wait
try {
  while (-not ((pwsh -NoProfile -File $gate -Status) -match '^builds\s*:\s*0\s*/')) {
    Heartbeat
    Start-Sleep -Seconds 2
  }
  New-Item -ItemType Directory -Force -Path "$E\paired" | Out-Null

  # 1. Same-DLL empty control (noise floor) and Production A/B on p66-100 (15 rounds each)
  python -B -u "$W\ab.py" "$D\main.dll" "$D\main-copy.dll" "$E\control-1200.json" --rounds 15 --holder $holder
  if ($LASTEXITCODE -ne 0) { throw "control-1200 failed" }
  python -B -u "$W\ab.py" "$D\main.dll" "$D\final.dll" "$E\dense-1200.json" --rounds 15 --holder $holder
  if ($LASTEXITCODE -ne 0) { throw "dense-1200 failed" }

  # 2. Three-arm with PDF.js on p66-100 (15 rounds)
  python -B -u "$W\ab.py" "$D\main.dll" "$D\final.dll" "$E\dense-vs-pdfjs-1200.json" --rounds 15 --holder $holder --pdfjs-root ..\pdfjs-bench2
  if ($LASTEXITCODE -ne 0) { throw "dense-vs-pdfjs-1200 failed" }

  # 3. Whole-document paired A/B (11 rounds each; covers all cohorts)
  foreach ($item in @(
    @('vector-heavy-100', 100),
    @('real-mixed-120', 120),
    @('image-heavy-100', 100)
  )) {
    $name = $item[0]; $last = $item[1]
    python -B -u "$W\ab.py" "$D\main.dll" "$D\final.dll" "$E\paired\$name-1200.json" --rounds 11 --holder $holder --pdf "$F\pdf-large\$name.pdf" --first 1 --last $last
    if ($LASTEXITCODE -ne 0) { throw "$name failed" }
  }

  # 4. All 5 small-fixture gates (EXREADER-FIXTURE-GATES.md: 15 rounds each)
  foreach ($cell in @(
    @('pdf-hybrid-real\pptx-20.pdf', 'pptx-20', 600, 20),
    @('pdf-hybrid-real\pptx-20.pdf', 'pptx-20', 1200, 20),
    @('pdf-hybrid-real\word-5.pdf', 'word-5', 600, 5),
    @('pdf-hybrid-real\word-5.pdf', 'word-5', 1200, 5),
    @('pdf-ppt\deck.pdf', 'deck', 1200, 15)
  )) {
    Heartbeat
    python -B -u "$W\ab.py" "$D\main.dll" "$D\final.dll" "$E\paired\$($cell[1])-$($cell[2]).json" --rounds 15 --holder $holder --pdf "$F\$($cell[0])" --first 1 --last $cell[3] --width $cell[2]
    if ($LASTEXITCODE -ne 0) { throw "small fixture $($cell[1])-$($cell[2]) failed" }
  }

  # 5. Full pixel parity (353,143,200 + 111,897,000)
  Heartbeat
  python -B -u "$W\pixels.py" "$D\main.dll" "$D\final.dll" "$E\pixels.json"
  if ($LASTEXITCODE -ne 0) { throw "pixels.py failed" }

  # 6. Peak RSS (AB, BA, AB on all 3 large fixtures)
  Heartbeat
  python -B -u "$W\rss.py" "$D\main.dll" "$D\final.dll" "$E\rss.json"
  if ($LASTEXITCODE -ne 0) { throw "rss.py failed" }

  # 7. Full CTest (577/577)
  Heartbeat
  $ErrorActionPreference = 'Continue'
  ctest --test-dir build\perf --parallel 4 --output-on-failure 2>&1 | Out-File -FilePath "$E\ctest.txt" -Encoding UTF8
  $ctestCode = $LASTEXITCODE
  $ErrorActionPreference = 'Stop'
  Get-Content "$E\ctest.txt" -Tail 10
  if ($ctestCode -ne 0) { throw "ctest failed with $ctestCode" }
  Heartbeat
  Write-Output 'ACCEPT-DONE'
} finally {
  pwsh -NoProfile -File $lock -Holder $holder -Release
}
