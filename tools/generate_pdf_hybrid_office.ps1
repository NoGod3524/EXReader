$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$out = Join-Path $root 'build/pdf-hybrid-office'
New-Item -ItemType Directory -Force $out | Out-Null
Add-Type -AssemblyName System.Drawing
$bitmap = New-Object System.Drawing.Bitmap 640,480
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$graphics.Clear([System.Drawing.Color]::White)
$graphics.FillRectangle([System.Drawing.Brushes]::Blue,40,40,300,200)
$graphics.FillEllipse([System.Drawing.Brushes]::Orange,240,180,300,240)
$image = Join-Path $out 'scan.bmp'
$bitmap.Save($image)
$graphics.Dispose(); $bitmap.Dispose()
$ppt = New-Object -ComObject PowerPoint.Application
try {
  foreach ($spec in @(@('pptx-1',1),@('pptx-20',20),@('chinese',1),@('image-only',1))) {
    $deck = $ppt.Presentations.Add(0)
    try {
      for ($i=1; $i -le $spec[1]; $i++) {
        $slide = $deck.Slides.Add($i,12)
        if ($spec[0] -eq 'image-only') {
          $null = $slide.Shapes.AddPicture($image,0,-1,20,20,640,480)
        } else {
          $shape = $slide.Shapes.AddTextbox(1,40,40,600,150)
          $shape.TextFrame.TextRange.Text = if ($spec[0] -eq 'chinese') { '中文交叉引用测试：表格、图片与页面渲染。' } else { "Hybrid PDF acceptance page $i" }
          $shape.TextFrame.TextRange.Font.Name = if ($spec[0] -eq 'chinese') { 'Microsoft YaHei' } else { 'Arial' }
          $shape.TextFrame.TextRange.Font.Size = 28
          $shape = $slide.Shapes.AddShape(1,60,230,400,160)
          $shape.Fill.ForeColor.RGB = 16744448
        }
      }
      $deck.SaveAs((Join-Path $out ($spec[0]+'.pptx')),24)
      $deck.SaveAs((Join-Path $out ($spec[0]+'.pdf')),32)
      Write-Output "$($spec[0]) producer=PowerPoint pages=$($deck.Slides.Count)"
    } finally { $deck.Close() }
  }
} finally { $ppt.Quit() }
$word = New-Object -ComObject Word.Application
$word.Visible = $false
try {
  $doc = $word.Documents.Add()
  try {
    for ($i=1; $i -le 5; $i++) {
      $range = $doc.Range($doc.Content.End-1,$doc.Content.End-1)
      $range.InsertAfter("Hybrid Word acceptance page $i`r")
      $range = $doc.Range($doc.Content.End-1,$doc.Content.End-1)
      $table = $doc.Tables.Add($range,3,3)
      $table.Borders.Enable = 1
      for ($r=1; $r -le 3; $r++) { for ($c=1; $c -le 3; $c++) { $table.Cell($r,$c).Range.Text = "R$r C$c" } }
      $range = $doc.Range($doc.Content.End-1,$doc.Content.End-1)
      $range.InsertParagraphAfter()
      $range = $doc.Range($doc.Content.End-1,$doc.Content.End-1)
      $pic = $doc.InlineShapes.AddPicture($image,$false,$true,$range)
      $pic.Width = 200; $pic.Height = 150
      if ($i -lt 5) { $range = $doc.Range($doc.Content.End-1,$doc.Content.End-1); $range.InsertBreak(7) }
    }
    $doc.ExportAsFixedFormat((Join-Path $out 'word-5.pdf'),17)
    Write-Output "word-5 producer=Word pages=$($doc.ComputeStatistics(2))"
  } finally { $doc.Close(0) }
} finally { $word.Quit() }
$excel = New-Object -ComObject Excel.Application
$excel.Visible=$false; $excel.DisplayAlerts=$false
try {
  $book=$excel.Workbooks.Add()
  try {
    $sheet=$book.Worksheets.Item(1)
    for ($r=1; $r -le 20; $r++) { for ($c=1; $c -le 5; $c++) { $sheet.Cells.Item($r,$c)="Row $r Col $c" } }
    $sheet.Range('A1:E20').Borders.LineStyle=1
    $sheet.Columns.AutoFit() | Out-Null
    $sheet.PageSetup.Zoom=$false; $sheet.PageSetup.FitToPagesWide=1; $sheet.PageSetup.FitToPagesTall=1
    $sheet.ExportAsFixedFormat(0,(Join-Path $out 'excel-1.pdf'))
    Write-Output 'excel-1 producer=Excel pages=1'
  } finally { $book.Close($false) }
} finally { $excel.Quit() }
