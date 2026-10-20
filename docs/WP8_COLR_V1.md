# WP8: COLR v1 paint support

This page freezes the COLR v1 subset implemented by EXReader's built-in
renderer. It is a package status document; the SDK version and component
versions are assigned by the mainline integrator. ABI epoch 1 and library
schema 6 are unchanged.

## Entry points and precedence

- `exr_font_color_info_get()` reports the intrinsic colour source of one
  glyph (`EXR_FONT_COLOR_NONE`, `..._COLR_V0`, `..._COLR_V1`, `..._SVG`),
  whether the COLR table carries a variation store, and the optional COLR v1
  clip box in 1000-em units. The output record is size-tagged; unknown
  trailing bytes must be zero and are rejected.
- Rendering precedence inside the built-in raster: sbix/CBDT strike image,
  then COLR v1, then SVG font document, then COLR v0 layers, then the outline.
  Fonts that provide both COLR v1 and an SVG description render COLR v1.
- Only palette 0 is used by the built-in renderer. The text foreground colour
  supplies palette index 0xffff and multiplies the final glyph alpha once.
  `exr_font_color_layers()` keeps its existing COLR v0 contract and is not
  used for COLR v1 glyphs.

## Paint type matrix

"Positive" names the regression scene in `native-font-color-v1`; every scene
is an original fixture glyph in `tests/fixtures/fonts/colrv1.ttf`.

| COLR v1 format | Status | Notes | Positive scene |
| --- | --- | --- | --- |
| PaintColrLayers (1) | supported | back-to-front, source-over | `layers`, `layers_overlap` |
| PaintSolid (2) | supported | CPAL entry or 0xffff foreground; CPAL alpha × stop alpha | `solid`, `solid_fg`, `solid_half` |
| PaintVarSolid (3) | supported | resolved by FreeType at the face's design coordinates | `var_solid` (variable fixture) |
| PaintLinearGradient (4) | supported | p0→p1 colour axis; p2 rotates/shears the basis | `linear`, `linear_p2`, `linear_shear` |
| PaintVarLinearGradient (5) | supported | geometry/colour deltas resolved by FreeType | variable fixture |
| PaintRadialGradient (6) | supported | two-circle (c0,r0)-(c1,r1) parameterisation | `radial`, `radial_offset` |
| PaintVarRadialGradient (7) | supported | resolved by FreeType | variable fixture |
| PaintSweepGradient (8) | supported | angles measured CCW from +x in font space with the 180° encoding bias; pad/repeat/reflect | `sweep` |
| PaintVarSweepGradient (9) | supported | resolved by FreeType | variable fixture |
| PaintGlyph (10) | supported | non-zero clipped glyph contour; empty contour paints nothing | `solid`, all gradient scenes |
| PaintColrGlyph (11) | supported | nested base glyph; recursion capped and cycles rejected | `colr_glyph`, `cycle` (reject) |
| PaintTransform (12) | supported | Affine2x3, layout `x'=xx·x+xy·y+dx`, `y'=yx·x+yy·y+dy` | `transform` |
| PaintVarTransform (13) | supported | resolved by FreeType | variable fixture |
| PaintTranslate (14) | supported | font-unit translation | `translate` |
| PaintVarTranslate (15) | supported | resolved by FreeType | variable fixture |
| PaintScale (16) | supported | about the origin | `scale` |
| PaintVarScale (17) | supported | resolved by FreeType | variable fixture |
| PaintScaleAroundCenter (18) | supported | centre in font units | `scale_center` |
| PaintVarScaleAroundCenter (19) | supported | resolved by FreeType | variable fixture |
| PaintScaleUniform (20) | supported | FreeType exposes it as `FT_COLR_PAINTFORMAT_SCALE` with equal axes | `scale_uniform` |
| PaintVarScaleUniform (21) | supported | resolved by FreeType | variable fixture |
| PaintScaleUniformAroundCenter (22) | supported | as format 20 plus centre | `scale_center` |
| PaintVarScaleUniformAroundCenter (23) | supported | resolved by FreeType | variable fixture |
| PaintRotate (24) | supported | CCW in font coordinates | `rotate` |
| PaintVarRotate (25) | supported | resolved by FreeType | variable fixture |
| PaintRotateAroundCenter (26) | supported | pivot in font units | `rotate_center`, `rotate_half` |
| PaintVarRotateAroundCenter (27) | supported | resolved by FreeType | variable fixture |
| PaintSkew (28) | supported | counter-clockwise in font space: `x'=x−tan(xAngle)·y`, `y'=y+tan(yAngle)·x` | `skew`, `skew_y` |
| PaintVarSkew (29) | supported | resolved by FreeType | variable fixture |
| PaintSkewAroundCenter (30) | supported | pivot in font units | `skew` |
| PaintVarSkewAroundCenter (31) | supported | resolved by FreeType | variable fixture |
| PaintComposite (32) | partial | 16 modes supported, 12 Porter-Duff operators rejected | `composite_*` |

FreeType normalises the centre/uniform variants into formats 16, 24 and 28;
EXReader therefore sees one structure per transform family and applies the
centre when it is present. Unknown or unsupported FreeType paint formats
return `EXR_UNSUPPORTED`.

## Composite modes

Supported (source painted over the backdrop with the corresponding
ISO 32000 / CSS compositing formula): SRC_OVER, SCREEN, OVERLAY, DARKEN,
LIGHTEN, COLOR_DODGE, COLOR_BURN, HARD_LIGHT, SOFT_LIGHT, DIFFERENCE,
EXCLUSION, MULTIPLY, HSL_HUE, HSL_SATURATION, HSL_COLOR, HSL_LUMINOSITY.
SRC_OVER is the plain source-over path; the others use a non-isolated canvas
group whose commit applies the blend mode.

Rejected with `EXR_UNSUPPORTED`: CLEAR, SRC, DEST, DEST_OVER, SRC_IN,
DEST_IN, SRC_OUT, DEST_OUT, SRC_ATOP, DEST_ATOP, XOR, PLUS. These need
per-pixel Porter-Duff semantics outside the canvas blend set. The two
negative scenes are `composite_src` and `composite_clear`.

## Colour and gradients

- Colour stops are clamped to [0,1], must be non-decreasing, and are limited
  to 256 per colour line. Interpolation happens in premultiplied sRGB and the
  result is returned as straight sRGB; stop alpha multiplies the CPAL alpha.
- Extend modes PAD, REPEAT and REFLECT are implemented for all three gradient
  kinds. Linear gradients with `p2 == p0` project onto the p0→p1 axis;
  otherwise the affine basis (p0,p1,p2) is inverted.
- Radial gradients solve the two-circle quadratic. Degenerate radii and
  coincident circles fall back to a linear solve or t = 0. The root with the
  smaller magnitude is used and the extend mode is applied afterwards.
- Sweep gradients use `atan2(fontY-cy, fontX-cx)` measured CCW from +x with
  the 180° bias of the encoded angles. The exact centre is a singular point;
  the reference renderer also reports a position-dependent value there, so
  the comparison excludes that pixel.
- The text foreground alpha is applied once when the completed glyph surface
  is composited into the page. CPAL, stop and paint alphas are applied inside
  the surface. Palette index 0xffff uses the foreground RGB and the stop
  alpha, matching the COLR v0 rule.

## Variable behaviour

FreeType resolves `PaintVar*` values and `VarColorLine`/colour-stop deltas
against the face's active design coordinates (set through
`exr_font_create_variable`). EXReader adds no interpolation of its own.
`exr_font_color_info_get().variable` is set when the COLR v1 header has a
non-zero variation index map or item variation store. The variable fixture
uses a `PaintVarSolid` alpha delta: alpha is 0.25 at wght=400 and 0.75 at
wght=900; both are asserted by `native-font-color-v1`.

## Limits, cancellation and ownership

| Limit | Value | Failure |
| --- | --- | --- |
| Paint graph depth | 64 | `EXR_LIMIT` |
| Nodes per glyph and pass | 4096 | `EXR_LIMIT` |
| Colour stops per gradient | 256 | `EXR_LIMIT` |
| Nested `PaintColrGlyph` recursion | 16 | `EXR_LIMIT` |
| Cyclic `PaintColrGlyph` | detected | `EXR_FONT` |
| Glyph surface | 8192 px per side, 8 Mi pixels | `EXR_LIMIT` |
| Shared raster work | 256 MiB units per page | `EXR_LIMIT` |
| Cancellation | polled per 64 nodes, per outline block and per canvas row | `EXR_CANCELLED` |

The paint graph is validated once before any surface is allocated; malformed
palette indices, stop offsets, negative radii, missing nested glyphs and
unsupported composites fail during that pass. A failed render returns a zero
`exr_color_surface` and no bitmap; a successful one owns straight RGBA
pixels that the caller releases with `exr_bitmap_free()`.

The drawable region is the explicit COLR v1 clip box when present, otherwise
the union of every paint glyph's transformed control box. Every leaf paint is
clipped to a glyph contour, so this union is a conservative superset of the
painted pixels; no visible content is cropped. Transformed glyph bounds that
exceed the per-glyph surface limits are rejected rather than silently clipped.

## Verification

- `native-font-color-v1`: palette/foreground, all paint families, transforms,
  gradients, composites, variable instance, orientation/sideways clipping,
  decoration, failures (`cycle`, `palette_oob`, `deep`, `many`,
  `composite_src`, `composite_clear`), cancellation, pager/layout/hit
  identity. 167 assertions.
- `native-font-color`: existing COLR v0/sbix/CBDT/cmap14 regression.
- `tools/generate_colrv1_test_fonts.py` builds `colrv1.ttf` and
  `colrv1-var.ttf`; hashes are recorded in
  `docs/validation/wp8-colrv1.json`.
- The independent reference is Google Chrome 152 (Skia) at a fixed font size;
  see `docs/validation/wp8-reference.json` and
  `tools/check_color_font_reference.py`.

## Host example

```c
exr_font_color_info info = {0};
info.struct_size = sizeof(info);
if (exr_font_color_info_get(font, 0, glyph, &info, NULL, &error) == EXR_OK &&
    info.kind == EXR_FONT_COLOR_COLR_V1) {
  /* exr_render_page_color() uses the built-in COLR v1 painter. */
}
```

A host renderer that wants its own COLR v1 traversal can read the raw font
through `exr_font_source()` and use `info.clip_box` for allocation. The SDK
does not expose the paint graph itself.
