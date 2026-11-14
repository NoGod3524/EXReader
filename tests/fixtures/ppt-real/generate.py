#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Author real binary .ppt fixtures using installed Windows PowerPoint COM.

Generation is manual and requires PowerPoint. --check is portable, uses only
stored manifests and hashes, and never launches PowerPoint or regenerates files.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import zlib

HERE = Path(__file__).resolve().parent
WHITE = [255, 255, 255]
BLUE, ORANGE, GREEN = [36, 90, 129], [217, 123, 40], [76, 130, 80]


def text(name, value, box, size=24, **extra):
    return dict(kind='text', name=name, text=value, box=box, size=size, **extra)


def solid(name, box, color, geometry='rect'):
    return dict(kind='solid', name=name, box=box, fill=color, geometry=geometry)


def region(shape):
    x, y, w, h = shape['box']
    return dict(name=shape['name'], bounds=[x, y, x+w, y+h],
                geometry=shape.get('geometry', 'line' if shape['kind'] == 'line' else 'rect'), fill=shape.get('fill'),
                text=bool(shape.get('text')), stroke=shape.get('stroke', 0),
                **({'image': True} if shape['kind'] == 'picture' else {}))


def samples(points=()):
    """Twelve authored stable points; color selection never reads engine pixels."""
    result = [[x, y, *rgb] for x, y, rgb in points]
    for x, y in ((12, 12), (354, 12), (708, 12), (12, 390), (354, 390),
                 (708, 390), (12, 200), (708, 200), (180, 390),
                 (540, 390), (180, 12), (540, 12)):
        if len(result) == 12:
            break
        result.append([x, y, *WHITE])
    assert len(result) == 12 and len({tuple(p[:2]) for p in result}) == 12
    return result


def cases():
    title = [text('Title', 'A practical roadmap', [72, 160, 576, 90], 36, bold=True)]
    result = {
        'title': dict(features=['text', 'title', '16:9'], width=720, height=405,
                      pages=[dict(shapes=title, samples=samples())]),
        'bullets': dict(features=['text', 'bullets', 'levels-0-1-2', '16:9'], width=720, height=405,
                        pages=[dict(shapes=[text('Title', 'From fieldwork to findings', [42, 28, 636, 60], 30, bold=True),
                                           text('Three-level list', 'Collect source material\nInterview the team\nRecord open questions\nCompare the evidence\nPublish conclusions',
                                                [60, 115, 600, 250], 23, levels=[1, 2, 3, 1, 2])], samples=samples())]),
        'image-text': dict(features=['text', 'png', 'image-stretch', '16:9'], width=720, height=405,
                           pages=[dict(shapes=[text('Title', 'A landscape in context', [42, 28, 636, 60], 30, bold=True),
                                              dict(kind='picture', name='Original illustration', box=[42, 120, 270, 180], fill=BLUE),
                                              text('Notes', 'Observation notes\nCompare the ridge\nand the lowlands.', [360, 126, 318, 180], 24)],
                                       samples=samples([(70, 140, BLUE), (280, 140, ORANGE),
                                                        (70, 275, GREEN), (280, 275, [38, 156, 168])]))]),
    }
    for name, chinese, merged in (('merged-table', False, True), ('chinese', True, False)):
        title_value = '研究进展与下一步计划' if chinese else 'Programme delivery'
        shapes = [text('Title', title_value, [42, 24, 636, 60], 30, bold=True, chinese=chinese)]
        if chinese:
            shapes.append(text('Body', '数据采集已经完成，团队正在整理分析结果。', [42, 87, 636, 44], 22, chinese=True))
        rows = [['区域', '项目', '状态'], ['北部', '采样', '完成'], ['南部', '分析', '进行中']] if chinese else [
            ['Delivery programme', '', 'Status'], ['Regional teams', 'Collection', 'Complete'], ['', 'Analysis', 'Active']]
        table = dict(kind='table', name='Delivery table', box=[60, 148, 600, 210], rows=rows,
                     colors=[[218, 231, 239], [238, 244, 247], [228, 238, 227]], chinese=chinese, merged=merged)
        shapes.append(table)
        colors = table['colors']
        result[name] = dict(features=['text', 'cjk-title', 'cjk-body', 'cjk-table', 'table', '16:9'] if chinese else [
            'text', 'table', 'horizontal-merge', 'vertical-merge', 'cell-borders', '16:9'], width=720, height=405,
            pages=[dict(shapes=shapes, samples=samples([(70, 206, colors[0]), (650, 206, colors[0]),
                                                       (650, 276, colors[1]), (650, 348, colors[2])]))])
    result['standard-4x3'] = dict(features=['text', 'rect', 'ellipse', 'line', 'outline-only', '4:3'], width=720, height=540,
        pages=[dict(shapes=[text('Title', 'Space for ideas', [42, 28, 636, 60], 30, bold=True),
                           text('Body', 'Review, discuss, decide', [42, 104, 636, 60], 24),
                           solid('Blue rectangle', [60, 210, 250, 190], BLUE),
                           solid('Orange ellipse', [400, 210, 250, 190], ORANGE, 'ellipse'),
                           dict(kind='line', name='Border-only line', box=[60, 425, 590, 0], stroke=3),
                           dict(kind='outline', name='Border-only rectangle', box=[60, 450, 590, 50], stroke=3)],
                    samples=samples([(70, 220, BLUE), (180, 300, BLUE), (300, 390, BLUE),
                                     (525, 225, ORANGE), (525, 300, ORANGE), (525, 385, ORANGE)]))])
    result['wide-16x9'] = dict(features=['text', 'title', '20-slides', '16:9'], width=720, height=405,
                               benchmark=True, benchmark_baseline='title',
                               pages=[dict(shapes=title, samples=samples()) for _ in range(20)])
    group_shapes = [solid('Grouped rectangle', [80, 142, 220, 170], BLUE),
                    text('Grouped label', 'Planning', [96, 175, 190, 65], 27, bold=True),
                    dict(kind='group', name='Inner group', scale=1.08, shapes=[
                        solid('Nested ellipse', [360, 153, 125, 125], GREEN, 'ellipse'),
                        solid('Nested triangle', [525, 153, 125, 125], ORANGE, 'triangle')])]
    result['nested-groups'] = dict(features=['text', 'grpSp', 'nested-grpSp', 'group-scale', 'rect', 'ellipse', 'triangle', '16:9'], width=720, height=405,
        pages=[dict(shapes=[text('Title', 'A programme has connected parts', [42, 28, 636, 60], 30, bold=True),
                           dict(kind='group', name='Outer group', shapes=group_shapes),
                           text('Caption', 'Nested groups retain their own coordinates.', [60, 335, 600, 44], 22)],
                    samples=samples([(90, 150, BLUE), (290, 300, BLUE),
                                     (422, 215, GREEN), (422, 170, GREEN),
                                     (606, 180, ORANGE), (587, 258, ORANGE)]))])
    return result


def flatten(shapes):
    for shape in shapes:
        if shape['kind'] == 'group':
            yield from flatten(shape['shapes'])
        elif shape['kind'] == 'table':
            x, y, w, h = shape['box']
            for r, row in enumerate(shape['rows']):
                for c, value in enumerate(row):
                    if shape['merged'] and (r, c) in ((0, 1), (2, 0)):
                        continue
                    cw = 2*w/3 if shape['merged'] and (r, c) == (0, 0) else w/3
                    ch = 2*h/3 if shape['merged'] and (r, c) == (1, 0) else h/3
                    yield dict(kind='solid', name=f'Table cell {r+1},{c+1}',
                               box=[x+c*w/3, y+r*h/3, cw, ch],
                               fill=shape['colors'][r], text=value, stroke=1)
        else:
            yield shape


def illustration():
    width, height = 240, 160
    colors = (BLUE, ORANGE, GREEN, [38, 156, 168])
    raw = b''.join(b'\x00'+b''.join(bytes(colors[(y >= height//2)*2+(x >= width//2)])
                                   for x in range(width)) for y in range(height))
    def chunk(tag, payload):
        return struct.pack('>I', len(payload))+tag+payload+struct.pack('>I', zlib.crc32(tag+payload) & 0xffffffff)
    return (b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))+
            chunk(b'IDAT', zlib.compress(raw, 0))+chunk(b'IEND', b''))


POWERSHELL = r'''
param([string]$Spec, [string]$Output, [string]$Report)
$ErrorActionPreference = 'Stop'
$cases = Get-Content -LiteralPath $Spec -Raw -Encoding UTF8 | ConvertFrom-Json
function Color($rgb) { return [int]$rgb[0] + ([int]$rgb[1] -shl 8) + ([int]$rgb[2] -shl 16) }
function Format-Text($shape, $item) {
    $frame = $shape.TextFrame
    if (-not $item.cell) {
        $frame.AutoSize = 0
        $frame.WordWrap = -1
        $frame.MarginLeft = 6; $frame.MarginRight = 6
        $frame.MarginTop = 4; $frame.MarginBottom = 4
        $frame.VerticalAnchor = 1
    }
    $range = $frame.TextRange
    $range.Text = $item.text.Replace("`n", "`r")
    $range.Font.Name = if ($item.chinese) { 'Microsoft YaHei' } else { 'Arial' }
    $range.Font.Size = $item.size
    $range.Font.Bold = if ($item.bold) { -1 } else { 0 }
    $range.Font.Color.RGB = 0x302820
    $range.ParagraphFormat.SpaceBefore = 0
    $range.ParagraphFormat.SpaceAfter = 4
    if ($item.levels) {
        for ($i = 1; $i -le $item.levels.Count; $i++) {
            $paragraph = $range.Paragraphs($i, 1)
            $paragraph.IndentLevel = $item.levels[$i-1]
            $paragraph.ParagraphFormat.Bullet.Visible = -1
            $paragraph.ParagraphFormat.Bullet.Character = 8226
        }
    }
}
function Add-Items($slide, $items, $directory) {
    $names = @()
    foreach ($item in $items) {
        $box = $item.box
        switch ($item.kind) {
            'text' {
                $shape = $slide.Shapes.AddTextbox(1, $box[0], $box[1], $box[2], $box[3])
                $shape.Fill.Visible = 0; $shape.Line.Visible = 0
                Format-Text $shape $item
            }
            'solid' {
                $type = switch ($item.geometry) { 'ellipse' { 9 } 'triangle' { 7 } default { 1 } }
                $shape = $slide.Shapes.AddShape($type, $box[0], $box[1], $box[2], $box[3])
                $shape.Fill.Solid(); $shape.Fill.ForeColor.RGB = Color $item.fill
                $shape.Line.Visible = 0
            }
            'line' {
                $shape = $slide.Shapes.AddLine($box[0], $box[1], ($box[0]+$box[2]), ($box[1]+$box[3]))
                $shape.Line.ForeColor.RGB = 0x302820; $shape.Line.Weight = $item.stroke
            }
            'outline' {
                $shape = $slide.Shapes.AddShape(1, $box[0], $box[1], $box[2], $box[3])
                $shape.Fill.Visible = 0
                $shape.Line.Visible = -1; $shape.Line.ForeColor.RGB = 0x302820; $shape.Line.Weight = $item.stroke
            }
            'picture' {
                $shape = $slide.Shapes.AddPicture((Join-Path $directory 'source.png'), 0, -1, $box[0], $box[1], $box[2], $box[3])
                $shape.Line.Visible = 0
            }
            'table' {
                $shape = $slide.Shapes.AddTable(3, 3, $box[0], $box[1], $box[2], $box[3])
                $table = $shape.Table
                for ($r = 1; $r -le 3; $r++) {
                    for ($c = 1; $c -le 3; $c++) {
                        $cell = $table.Cell($r, $c)
                        $cell.Shape.Fill.Solid(); $cell.Shape.Fill.ForeColor.RGB = Color $item.colors[$r-1]
                        $cellItem = [pscustomobject]@{ text=$item.rows[$r-1][$c-1]; size=20; chinese=$item.chinese; bold=($r -eq 1); cell=$true }
                        Format-Text $cell.Shape $cellItem
                        foreach ($side in 1..4) {
                            $border = $cell.Borders.Item($side)
                            $border.ForeColor.RGB = 0x8a7148; $border.Weight = 1; $border.Visible = -1
                        }
                    }
                }
                if ($item.merged) {
                    $table.Cell(1, 1).Merge($table.Cell(1, 2))
                    $table.Cell(2, 1).Merge($table.Cell(3, 1))
                }
            }
            'group' {
                $children = @(Add-Items $slide $item.shapes $directory)
                $shape = $slide.Shapes.Range([object[]]$children).Group()
                if ($item.scale) {
                    $shape.ScaleWidth($item.scale, 0, 0)
                    $shape.ScaleHeight($item.scale, 0, 0)
                }
            }
            default { throw "Unknown shape $($item.kind)" }
        }
        $shape.Name = $item.name
        $names += $shape.Name
    }
    return $names
}
function Get-Bounds($shape, $prefix) {
    if ($shape.Type -eq 6) {
        for ($i=1; $i -le $shape.GroupItems.Count; $i++) { Get-Bounds $shape.GroupItems.Item($i) $prefix }
    } elseif ($shape.HasTable -eq -1) {
        for ($r=1; $r -le 3; $r++) {
            for ($c=1; $c -le 3; $c++) {
                $cell = $shape.Table.Cell($r,$c).Shape
                [ordered]@{ name="Table cell $r,$c"; bounds=@($cell.Left,$cell.Top,($cell.Left+$cell.Width),($cell.Top+$cell.Height)) }
            }
        }
    } else {
        [ordered]@{ name=$shape.Name; bounds=@($shape.Left,$shape.Top,($shape.Left+$shape.Width),($shape.Top+$shape.Height)) }
    }
}
$app = New-Object -ComObject PowerPoint.Application
$results = @()
try {
    $app.DisplayAlerts = 1
    foreach ($entry in $cases) {
        $directory = Join-Path $Output $entry.name
        $deck = $app.Presentations.Add(0)
        try {
            $deck.PageSetup.SlideWidth = $entry.width
            $deck.PageSetup.SlideHeight = $entry.height
            foreach ($page in $entry.pages) {
                $slide = $deck.Slides.Add(($deck.Slides.Count+1), 12)
                $slide.FollowMasterBackground = 0
                $slide.Background.Fill.Solid(); $slide.Background.Fill.ForeColor.RGB = 0xffffff
                $null = Add-Items $slide $page.shapes $directory
            }
            $path = Join-Path $directory ($entry.name+'.ppt')
            $deck.SaveAs($path, 1)
        } finally { $deck.Close() }
        $saved = $app.Presentations.Open($path, -1, 0, 0)
        try {
            $saved.Slides.Item(1).Export((Join-Path $directory 'powerpoint.png'), 'PNG', $entry.width, $entry.height)
            $geometry = @()
            for ($p=1; $p -le $saved.Slides.Count; $p++) {
                $slide = $saved.Slides.Item($p)
                $bounds = @()
                for ($i=1; $i -le $slide.Shapes.Count; $i++) { $bounds += Get-Bounds $slide.Shapes.Item($i) '' }
                $geometry += ,$bounds
            }
            $results += [ordered]@{ name=$entry.name; slides=$saved.Slides.Count;
                width=$saved.PageSetup.SlideWidth; height=$saved.PageSetup.SlideHeight; version=$app.Version; geometry=$geometry }
            Write-Host "$($entry.name): source=powerpoint-com slides=$($saved.Slides.Count) version=$($app.Version)"
        } finally { $saved.Close() }
    }
    $results | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $Report -Encoding UTF8
} finally { $app.Quit() }
'''


def digest(path):
    data = path.read_bytes()
    return dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())


def stored_png(path):
    """Preserve PowerPoint's PNG pixels and metadata, store IDAT without compression."""
    data = path.read_bytes()
    assert data[:8] == b'\x89PNG\r\n\x1a\n'
    chunks, compressed, offset = [], bytearray(), 8
    while offset < len(data):
        size = struct.unpack_from('>I', data, offset)[0]
        tag, payload = data[offset+4:offset+8], data[offset+8:offset+8+size]
        assert zlib.crc32(tag+payload) & 0xffffffff == struct.unpack_from('>I', data, offset+8+size)[0]
        if tag == b'IDAT':
            compressed.extend(payload)
            if not chunks or chunks[-1][0] != b'IDAT':
                chunks.append((tag, None))
        else:
            chunks.append((tag, payload))
        offset += size+12
    stored = zlib.compress(zlib.decompress(compressed), 0)
    output = bytearray(data[:8])
    for tag, payload in chunks:
        payload = stored if tag == b'IDAT' else payload
        output.extend(struct.pack('>I', len(payload))+tag+payload+struct.pack('>I', zlib.crc32(tag+payload) & 0xffffffff))
    path.write_bytes(output)


def write_json(path, content):
    path.write_text(json.dumps(content, ensure_ascii=False, indent=2)+'\n', encoding='utf-8', newline='\n')


def summary():
    entries = []
    for path in sorted(HERE.glob('*/manifest.json')):
        entry = json.loads(path.read_text(encoding='utf-8'))
        entry['file'] = (path.parent / entry['file']).relative_to(HERE).as_posix()
        # Asset paths in the summary are also relative to the corpus root.
        for asset in entry.get('assets', []):
            asset['file'] = (path.parent / asset['file']).relative_to(HERE).as_posix()
        entries.append(entry)
    return entries


def check():
    expected_names = set(cases()) | {'bad-truncated', 'bad-header'}
    entries = summary()
    assert {Path(e['file']).stem for e in entries} == expected_names, 'corpus membership differs'
    assert json.loads((HERE/'manifest.json').read_text(encoding='utf-8')) == entries, 'summary manifest differs'
    for entry in entries:
        for item in [entry, *entry.get('assets', [])]:
            path = HERE/item['file']
            assert path.is_file(), f'missing fixture: {path}'
            assert digest(path) == {key: item[key] for key in ('bytes', 'sha256')}, f'hash/size mismatch: {path}'
        print(f'{entry["file"]}: slides={entry["slides"]} source={entry["source"]} bytes={entry["bytes"]} sha256={entry["sha256"]} ok')
    print(f'manifest.json: {len(entries)} files, {sum(e["slides"] for e in entries)} valid slides; check=ok')


def generate():
    authored = cases()
    for name in authored:
        (HERE/name).mkdir(parents=True, exist_ok=True)
    (HERE/'image-text/source.png').write_bytes(illustration())
    with tempfile.TemporaryDirectory(prefix='exreader-ppt-com-') as temp:
        temporary = Path(temp)
        spec = temporary/'spec.json'
        write_json(spec, [dict(name=name, **deck) for name, deck in authored.items()])
        script = temporary/'generate.ps1'
        script.write_text(POWERSHELL, encoding='utf-16')
        report = temporary/'report.json'
        subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                        '-File', str(script), '-Spec', str(spec), '-Output', str(HERE), '-Report', str(report)], check=True)
        reports = {entry['name']: entry for entry in json.loads(report.read_text(encoding='utf-8-sig'))}
    for name, deck in authored.items():
        report = reports[name]
        assert report['slides'] == len(deck['pages']), f'{name}: PowerPoint slide count differs'
        assert report['width'] == deck['width'] and report['height'] == deck['height']
        stored_png(HERE/name/'powerpoint.png')
        assets = [dict(file='powerpoint.png', **digest(HERE/name/'powerpoint.png'))]
        if name == 'image-text':
            assets.append(dict(file='source.png', **digest(HERE/name/'source.png')))
        oracle_slides = []
        for page, actual in zip(deck['pages'], report['geometry']):
            bounds = {shape['name']: shape['bounds'] for shape in actual}
            regions = [region(s) for s in flatten(page['shapes'])]
            for item in regions:
                item['bounds'] = bounds[item['name']]
            oracle_slides.append(dict(regions=regions, samples=page['samples'],
                                      text_content=[s['text'] for s in flatten(page['shapes']) if s.get('text')]))
        entry = dict(file=name+'.ppt', slides=report['slides'], features=deck['features'],
                     source='powerpoint-com', generated_by='generate.py', license='MIT',
                     powerpoint_version=report['version'], powerpoint_reported_slides=report['slides'],
                     **digest(HERE/name/(name+'.ppt')), assets=assets,
                     oracle=dict(width=deck['width'], height=deck['height'], background=WHITE,
                                 slides=oracle_slides))
        for key in ('benchmark', 'benchmark_baseline'):
            if key in deck:
                entry[key] = deck[key]
        write_json(HERE/name/'manifest.json', entry)
    title = (HERE/'title/title.ppt').read_bytes()
    for name, data, feature in (('bad-truncated', title[:len(title)//2], 'truncated-cfb'),
                                ('bad-header', b'BROKEN!!'+title[8:], 'corrupt-cfb-header')):
        folder = HERE/name
        folder.mkdir(parents=True, exist_ok=True)
        target = folder/(name+'.ppt')
        target.write_bytes(data)
        write_json(folder/'manifest.json', dict(file=target.name, slides=0, features=[feature],
                   source='powerpoint-com', generated_by='generate.py', license='MIT',
                   derived_from='title/title.ppt', expected_status=5, expected_error='EXR_FORMAT', **digest(target)))
    write_json(HERE/'manifest.json', summary())
    check()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='check stored files, sizes and SHA-256; no COM')
    args = parser.parse_args()
    check() if args.check else generate()
