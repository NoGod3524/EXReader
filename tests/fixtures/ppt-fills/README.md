# PowerPoint 97–2003 fill fixtures

Run `pwsh -File tests/fixtures/ppt-fills/generate.ps1` on Windows with PowerPoint
and pywin32. The reader and CTest use only the committed artifacts and Python's
standard library. No Office process is started by a test.

The four `.ppt` files were produced by PowerPoint 16.0 COM `SaveAs(format=1)`.
The generator reopens them, records the saved shapes and theme RGB values in
`manifest.json`, and exports `*-powerpoint.png` at one pixel per point.
SHA-256 hashes bind every COM binary to its oracle data.

| Fixture | Content |
| --- | --- |
| png.ppt | Solid green 100 × 50 PNG inserted at (80,80), sized 100 × 50 pt |
| scale.ppt | The same PNG stretched to 400 × 50 pt |
| gradient.ppt | Rectangle at (80,80), 400 × 100 pt, red→blue, angle 0° |
| theme.ppt | Eight rectangles: modern accent1…6, light1/background, dark1/text |

`TwoColorGradient` resets PowerPoint's endpoint colors; the generator sets the
red and blue endpoints after calling it. Reopened COM reports stops `(red,0)`
and `(blue,1)` and angle 0°. The binary FOPT stores fillType (`0x0180`) = 7,
fillColor (`0x0181`) = `0x000000FF`, fillBackColor (`0x0183`) = `0x00FF0000`.
The M3 renderer deliberately reduces all supported gradients to horizontal
linear interpolation and reports `gradient-horizontal`.

The PNG pictures use FSP type 75 and FOPT pib (`0x0104`, fBid set) = 1.
Their BSE records are 36-byte delayed references into the CFB `Pictures` stream;
the picture has explicit noFill, which applies to the path fill and does not
disable the picture. The synthetic `blips` group independently embeds PNG and
JPEG payloads inline in BSE records, exercises all four requested record IDs,
and covers both one-UID and two-UID headers. The JPEG was generated with Windows
System.Drawing; its lossy green sample is checked with tolerance 2.

PowerPoint maps the modern theme into the legacy eight-color table. In this
fixture accent1 and accent2 remain indirect COLOR_SCHEME indices 4 and 5;
accent3…6 become literal fallback colors. Background and text use indices 0 and
1. Tests compare all eight pixels to reopened COM's master theme RGB values;
accent1 is additionally compared to the actual MainMaster ColorSchemeAtom.
The `scheme` test independently checks all eight raw legacy indices, avoiding
an assumption that legacy "Accent1" has the same index as modern accent1.

The `fallback` group checks nonexistent pib indices (including zero and
UINT32_MAX), unsupported blip types, and failed decoding. The
`gradient-fallback` group checks a missing endpoint and an explicit
fillShadeColors complex array. A following shape remains independently
renderable after each image recovery case. The `scheme` group also checks
master selection through persist/master IDs and per-slide palette overrides.
Additional samples check the nearest preceding physical master when persist
metadata is absent, ellipse clipping for gradients and image fills, horizontal
picture flips within a scaled group, separate pib/fillBlip properties, and
explicit noFill on an ordinary shape with an image fill.
