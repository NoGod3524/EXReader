# Upstream font color presentation

This is the byte-for-byte `features/steps/test_files/font-color.pptx` from
python-pptx commit `278b47b1dedd5b46ee84c286e77cdfb0bf4594be`. It is an independent
upstream integration presentation, last modified by Steve Canny in PowerPoint
on 2013-11-10. It has five text boxes: default text color, direct RGB, theme
accent1, accent4 with `lumMod=75000`, and accent1 with `lumMod=60000` /
`lumOff=40000`. No slides or package parts were rewritten.

`LICENSE` is the upstream MIT license. `UPSTREAM-MANIFEST.in` explicitly includes
`features/**` in the same licensed source distribution. The creator and last
modifier in `docProps/core.xml` are `python-pptx` and Steve Canny, matching the
upstream project and copyright holder; there are no embedded third-party images.
The fixed source URL, license URL, original metadata, size, and SHA-256 are in
`manifest.json`.

The unmodified M5 engine opens this file with status 0 and reports only
`font fallback=+mn-lt`, which is the permitted host font warning. Text boxes are
transparent: their layout frames are larger than the glyph ink bounding boxes.
The matrix must report that geometry/ink distinction faithfully.
