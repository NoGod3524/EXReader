# Office and pywin32 are fixture-generation tools only.
$ErrorActionPreference = 'Stop'
python (Join-Path $PSScriptRoot 'generate.py')
if ($LASTEXITCODE -ne 0) { throw 'PowerPoint fixture generation failed' }
Add-Type -AssemblyName System.Drawing
$bitmap = [System.Drawing.Bitmap]::new((Join-Path $PSScriptRoot 'green-100x50.png'))
try {
    $bitmap.Save((Join-Path $PSScriptRoot 'green-100x50.jpg'), [System.Drawing.Imaging.ImageFormat]::Jpeg)
} finally {
    $bitmap.Dispose()
}
