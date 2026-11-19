# Clean locked comparison of v4 candidates + pure Site 3 isolation on image-heavy-100 p71-100 @1200.
$ErrorActionPreference = 'Stop'
$env:EXR_IDLE_GATE = 'off'
$E = 'evidence/image-p71-100-composite-20261119'
$D = "$E/_work/dlls"
$OUT = "$E/clean"
New-Item -ItemType Directory -Force -Path $OUT | Out-Null
$AB = 'evidence/dense-vector-residual-20261119/harness/ab.py'
$LOCK = 'C:\Users\Oscar\OneDrive\Desktop\deepseekHarness\ops\bench-lock.ps1'
$PDF = 'tests/fixtures/pdf-large/image-heavy-100.pdf'

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
  $runs = @(
    @{ name = 'v4-control-null'; dll = "$D/relink-base-copy.dll"; rounds = 15 },
    @{ name = 'v4-cand-site3';   dll = "$D/cand-site3.dll";       rounds = 15 },
    @{ name = 'v4-simple';       dll = "$D/v4-simple.dll";        rounds = 15 },
    @{ name = 'v4-uniform';      dll = "$D/v4-uniform.dll";       rounds = 15 },
    @{ name = 'v4-uniform-s3';   dll = "$D/v4-uniform-s3.dll";    rounds = 15 }
  )
  foreach ($r in $runs) {
    Write-Output "=== RUN $($r.name) (rounds=$($r.rounds)) ==="
    python -B -u $AB "$D/relink-base.dll" $r.dll "$OUT/$($r.name).json" --rounds $r.rounds --pdf $PDF --first 71 --last 100 --width 1200 --holder agy-A
    if ($LASTEXITCODE -ne 0) { throw "ab.py failed on $($r.name)" }
  }
  Write-Output "CLEAN-V4-DONE"
} finally {
  pwsh -NoProfile -File $LOCK -Holder agy-A -Release
}
