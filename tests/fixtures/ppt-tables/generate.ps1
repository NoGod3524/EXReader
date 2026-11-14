# Generation tool only: Windows + installed PowerPoint; no third-party modules.
$ErrorActionPreference = 'Stop'
$directory = $PSScriptRoot
$app = New-Object -ComObject PowerPoint.Application
try {
    $app.DisplayAlerts = 1
    $deck = $app.Presentations.Add(0)
    try {
        $deck.PageSetup.SlideWidth = 720
        $deck.PageSetup.SlideHeight = 540
        $slide = $deck.Slides.Add(1, 12)
        $table = $slide.Shapes.AddTable(2, 2, 60, 80, 360, 180).Table
        $colors = @(0x332211, 0x665544, 0x998877, 0xccbbaa)
        foreach ($row in 1..2) {
            foreach ($column in 1..2) {
                $cell = $table.Cell($row, $column)
                $cell.Shape.Fill.ForeColor.RGB = $colors[($row - 1) * 2 + $column - 1]
                $cell.Shape.TextFrame.TextRange.Text = if ($row -eq 1 -and $column -eq 1) { 'A' } elseif ($row -eq 2 -and $column -eq 2) { 'B' } else { '' }
                foreach ($side in 1..4) {
                    $border = $cell.Borders.Item($side)
                    $border.ForeColor.RGB = 0x2040a0
                    $border.Weight = 3
                    $border.Visible = -1
                }
            }
        }
        $deck.SaveAs((Join-Path $directory 'plain.ppt'), 1)
        $table.Cell(1, 1).Merge($table.Cell(1, 2))
        $deck.SaveAs((Join-Path $directory 'merge.ppt'), 1)
    } finally { $deck.Close() }
    $fixtures = @()
    foreach ($case in @('plain', 'merge')) {
        $path = Join-Path $directory ($case + '.ppt')
        $saved = $app.Presentations.Open($path, -1, 0, 0)
        try {
            $slide = $saved.Slides.Item(1)
            $slide.Export((Join-Path $directory ($case + '-powerpoint.png')), 'PNG', 720, 540)
            $table = $slide.Shapes.Item(1).Table
            $fixtures += [ordered]@{
                case = $case; file = $case + '.ppt'
                sha256 = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
                reference_png = $case + '-powerpoint.png'
                rows = $table.Rows.Count; columns = $table.Columns.Count
                bbox_pt = @(60, 80, 360, 180)
                fill_rgb = @(@(17,34,51), @(68,85,102), @(119,136,153), @(170,187,204))
                border_rgb = @(160,64,32); border_width_pt = 3
                text = @('A', '', '', 'B'); horizontal_merge = ($case -eq 'merge')
            }
        } finally { $saved.Close() }
    }
    [ordered]@{ generator = 'PowerPoint COM SaveAs(format=1); reopened COM table oracle'; version = $app.Version; fixtures = $fixtures } |
        ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $directory 'manifest.json') -Encoding utf8
} finally { $app.Quit() }
