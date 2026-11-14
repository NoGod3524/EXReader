# PowerPoint 97–2003 shape fixtures

Run `python tests/fixtures/ppt-shapes/generate.py` on Windows with PowerPoint
and pywin32. Generation uses `PowerPoint.Application` COM,
`Presentations.Add(WithWindow=0)`, and `SaveAs(format=1)`. The committed files
were generated with PowerPoint 16.0. Reader tests consume these files without
invoking Office or importing pywin32.

The generator reopens every saved `.ppt` to collect PowerPoint's dimensions,
shape coordinates, solid fill and line colors, and line widths in
`manifest.json`. `*-powerpoint.png` are PowerPoint's own exports at one pixel
per point. The manifest also includes hashes and interior pixel samples.

| File | Contents | Page size (pt) |
| --- | --- | --- |
| red-rect.ppt | One red rectangle | 720 × 540 |
| blue-circle.ppt | One blue circle, with a white corner sample | 720 × 540 |
| overlap.ppt | Red rectangle behind a green rectangle | 720 × 540 |
| group.ppt | Two rectangles in a translated, nonuniformly scaled group | 720 × 540 |
| standard.ppt | RGB (17, 83, 211) rectangle, 6pt green line, unfilled rectangle | 720 × 540 (4:3) |
| wide.ppt | RGB (17, 83, 211) ellipse, 6pt green line, unfilled rectangle | 960 × 540 (16:9) |

`colorref` is COM's numeric `0x00BBGGRR` value. Red is `0x000000FF`, blue is
`0x00FF0000`, and the asymmetric color is `0x00D35311`; their expected RGB
values appear independently in `rgb` and `samples`.

The group starts with children at `(40,30,80,60)` and `(140,90,60,40)` pt.
Its child coordinate bounds are `(40,30)` to `(200,130)` pt. The saved group
has offset `(180,135)` and extent `(360,200)` pt, giving scale `(2.25,2)`.
PowerPoint reports the saved children at `(180,135,180,120)` and
`(405,255,135,80)` pt. These are absolute page coordinates, so pixel bounds
can be compared directly at one pixel per point.

Actual records in `group.ppt` use Slide `0x03EE`, PPDrawing `0x040C`,
OfficeArtSpgrContainer `0xF003`, SpContainer `0xF004`, FSPGR `0xF009`, FSP
`0xF00A`, FOPT `0xF00B`, ChildAnchor `0xF00F`, and ClientAnchor `0xF010`.
The group FSPGR bounds are `[508000,381000,2540000,1651000]` in the child
coordinate system. Its ClientAnchor contains signed 16-bit values in the
order `top,left,right,bottom`: `[1080,1440,4320,2680]`, measured in master
units (8 per point). ChildAnchor contains signed 32-bit
`left,top,right,bottom`: the red child is
`[508000,381000,1524000,1143000]`, and the blue child is
`[1778000,1143000,2540000,1651000]`.

All 14 manifest samples were checked against the committed PowerPoint PNG
exports and matched the exact expected RGB values.
