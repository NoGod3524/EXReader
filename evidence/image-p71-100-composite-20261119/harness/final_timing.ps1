# Final production timed acceptance suite under 2026-11-19 measurement policy.
$ErrorActionPreference = 'Stop'
$env:EXR_IDLE_GATE = 'off'
$E = 'evidence/image-p71-100-composite-20261119'
$D = "$E/_work/dlls"
$OUT = "$E/final"
New-Item -ItemType Directory -Force -Path $OUT | Out-Null
$AB = 'evidence/dense-vector-residual-20261119/harness/ab.py'
$RSS = 'evidence/dense-vector-residual-20261119/harness/rss.py'
$LOCK = 'C:\Users\Oscar\OneDrive\Desktop\deepseekHarness\ops\bench-lock.ps1'

pwsh -NoProfile -File $LOCK -Holder agy-A -Wait
try {
  $opsDir = Split-Path $LOCK
  $waitStart = Get-Date
  while ($true) {
    $builds = @(Get-ChildItem $opsDir -Force -ErrorAction SilentlyContinue | Where-Object { $_.Name -match '^\.build\.' })
    if ($builds.Count -eq 0) { break }
    if (((Get-Date) - $waitStart).TotalSeconds -gt 180) { Write-Output "WARN build slots still present after 180s: $($builds.Name -join ',')"; break }
    Write-Output "DRAIN waiting for in-flight builds: $($builds.Name -join ',')"
    pwsh -NoProfile -File $LOCK -Holder agy-A -Heartbeat | Out-Null
    Start-Sleep -Seconds 2
  }

  Write-Output "=== 1. Same-DLL Null Control (p71-100 @1200, 15 rounds) ==="
  python -B -u $AB "$D/base.dll" "$D/base-copy.dll" "$OUT/control-null.json" --rounds 15 --pdf tests/fixtures/pdf-large/image-heavy-100.pdf --first 71 --last 100 --width 1200 --holder agy-A
  if ($LASTEXITCODE -ne 0) { throw "control-null failed" }

  Write-Output "=== 2. Primary Production A/B (p71-100 @1200, 15 rounds) ==="
  python -B -u $AB "$D/base.dll" "$D/final.dll" "$OUT/p71-100.json" --rounds 15 --pdf tests/fixtures/pdf-large/image-heavy-100.pdf --first 71 --last 100 --width 1200 --holder agy-A
  if ($LASTEXITCODE -ne 0) { throw "p71-100 failed" }

  Write-Output "=== 3. Whole-document image-heavy-100 (p1-100 @1200, 11 rounds) ==="
  python -B -u $AB "$D/base.dll" "$D/final.dll" "$OUT/image-heavy-100.json" --rounds 11 --pdf tests/fixtures/pdf-large/image-heavy-100.pdf --first 1 --last 100 --width 1200 --holder agy-A
  if ($LASTEXITCODE -ne 0) { throw "image-heavy-100 failed" }

  Write-Output "=== 4. Whole-document real-mixed-120 (p1-120 @1200, 11 rounds) ==="
  python -B -u $AB "$D/base.dll" "$D/final.dll" "$OUT/real-mixed-120.json" --rounds 11 --pdf tests/fixtures/pdf-large/real-mixed-120.pdf --first 1 --last 120 --width 1200 --holder agy-A
  if ($LASTEXITCODE -ne 0) { throw "real-mixed-120 failed" }

  Write-Output "=== 5. Whole-document vector-heavy-100 (p1-100 @1200, 11 rounds) ==="
  python -B -u $AB "$D/base.dll" "$D/final.dll" "$OUT/vector-heavy-100.json" --rounds 11 --pdf tests/fixtures/pdf-large/vector-heavy-100.pdf --first 1 --last 100 --width 1200 --holder agy-A
  if ($LASTEXITCODE -ne 0) { throw "vector-heavy-100 failed" }

  Write-Output "=== 6. Small-Fixture Gates (EXREADER-FIXTURE-GATES.md, 15 rounds each) ==="
  $gates = @(
    @{ name='gate-pptx-20-600';  pdf='tests/fixtures/pdf-hybrid-real/pptx-20.pdf'; last=20; width=600  },
    @{ name='gate-pptx-20-1200'; pdf='tests/fixtures/pdf-hybrid-real/pptx-20.pdf'; last=20; width=1200 },
    @{ name='gate-word-5-600';   pdf='tests/fixtures/pdf-hybrid-real/word-5.pdf';  last=5;  width=600  },
    @{ name='gate-word-5-1200';  pdf='tests/fixtures/pdf-hybrid-real/word-5.pdf';  last=5;  width=1200 },
    @{ name='gate-deck-1200';    pdf='tests/fixtures/pdf-ppt/deck.pdf';            last=15; width=1200 }
  )
  foreach ($g in $gates) {
    Write-Output "--- $($g.name) ---"
    python -B -u $AB "$D/base.dll" "$D/final.dll" "$OUT/$($g.name).json" --rounds 15 --pdf $g.pdf --first 1 --last $g.last --width $g.width --holder agy-A
    if ($LASTEXITCODE -ne 0) { throw "$($g.name) failed" }
  }

  Write-Output "=== 7. Peak RSS (AB, BA, AB fresh processes) ==="
  pwsh -NoProfile -File $LOCK -Holder agy-A -Heartbeat | Out-Null
  python -B -u $RSS "$D/base.dll" "$D/final.dll" "$OUT/rss.json"
  if ($LASTEXITCODE -ne 0) { throw "rss failed" }

  Write-Output "FINAL-TIMING-DONE"
} finally {
  pwsh -NoProfile -File $LOCK -Holder agy-A -Release
}
