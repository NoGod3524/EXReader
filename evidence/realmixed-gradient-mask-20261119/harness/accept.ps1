$ErrorActionPreference = 'Stop'
$E = 'evidence\realmixed-gradient-mask-20261119'
$D = "$E\_work\dlls"
$AB = 'evidence\dense-vector-residual-20261119\harness\ab.py'
$LOCK = 'C:\Users\Oscar\OneDrive\Desktop\deepseekHarness\ops\bench-lock.ps1'
$GATE = 'C:\Users\Oscar\OneDrive\Desktop\deepseekHarness\ops\build-gate.ps1'
$F = 'tests\fixtures'
$env:EXR_IDLE_GATE = 'off'
New-Item -ItemType Directory -Force -Path "$E\raw" | Out-Null

function Run-Ab([string]$a, [string]$b, [string]$out, [string[]]$extra) {
  & pwsh -NoProfile -File $LOCK -Holder agy-C -Heartbeat | Out-Null
  Write-Output "=== RUN $out ==="
  & python -B -u $AB $a $b $out --holder agy-C @extra
  if ($LASTEXITCODE -ne 0) { throw "ab.py failed for $out ($LASTEXITCODE)" }
}

& pwsh -NoProfile -File $LOCK -Holder agy-C -Wait
try {
  while ((& pwsh -NoProfile -File $GATE -Status | Select-String 'builds : 0 /') -eq $null) {
    & pwsh -NoProfile -File $LOCK -Holder agy-C -Heartbeat | Out-Null
    Start-Sleep -Milliseconds 800
  }
  Run-Ab "$D\base.dll" "$D\base-copy.dll" "$E\raw\control-final-p1-21.json" @('--rounds','15','--pdf',"$F\pdf-large\real-mixed-120.pdf",'--first','1','--last','21')
  Run-Ab "$D\base.dll" "$D\cand_axial_v2.dll" "$E\raw\pilot-axial-p1-21.json" @('--rounds','11','--pdf',"$F\pdf-large\real-mixed-120.pdf",'--first','1','--last','21')
  Run-Ab "$D\base.dll" "$D\final.dll" "$E\raw\final-p1-21.json" @('--rounds','15','--pdf',"$F\pdf-large\real-mixed-120.pdf",'--first','1','--last','21')

  Run-Ab "$D\base.dll" "$D\final.dll" "$E\raw\real-mixed-120-1200.json" @('--rounds','11','--pdf',"$F\pdf-large\real-mixed-120.pdf",'--first','1','--last','120')
  Run-Ab "$D\base.dll" "$D\final.dll" "$E\raw\image-heavy-100-1200.json" @('--rounds','11','--pdf',"$F\pdf-large\image-heavy-100.pdf",'--first','1','--last','100')
  Run-Ab "$D\base.dll" "$D\final.dll" "$E\raw\vector-heavy-100-1200.json" @('--rounds','11','--pdf',"$F\pdf-large\vector-heavy-100.pdf",'--first','1','--last','100')

  Run-Ab "$D\base.dll" "$D\final.dll" "$E\raw\gate-pptx-20-600.json" @('--rounds','15','--pdf',"$F\pdf-hybrid-real\pptx-20.pdf",'--first','1','--last','20','--width','600')
  Run-Ab "$D\base.dll" "$D\final.dll" "$E\raw\gate-pptx-20-1200.json" @('--rounds','15','--pdf',"$F\pdf-hybrid-real\pptx-20.pdf",'--first','1','--last','20','--width','1200')
  Run-Ab "$D\base.dll" "$D\final.dll" "$E\raw\gate-word-5-600.json" @('--rounds','15','--pdf',"$F\pdf-hybrid-real\word-5.pdf",'--first','1','--last','5','--width','600')
  Run-Ab "$D\base.dll" "$D\final.dll" "$E\raw\gate-word-5-1200.json" @('--rounds','15','--pdf',"$F\pdf-hybrid-real\word-5.pdf",'--first','1','--last','5','--width','1200')
  Run-Ab "$D\base.dll" "$D\final.dll" "$E\raw\gate-deck-1200.json" @('--rounds','15','--pdf',"$F\pdf-ppt\deck.pdf",'--first','1','--last','15','--width','1200')

  Write-Output 'ACCEPT-SWEEP-DONE'
} finally {
  & pwsh -NoProfile -File $LOCK -Holder agy-C -Release
}
