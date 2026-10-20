# WP8: SVG font support

This page freezes the SVG-in-OpenType subset implemented by EXReader's
built-in renderer. The SDK version and component versions are assigned by the
mainline integrator; ABI epoch 1 and library schema 6 are unchanged. No new
runtime dependency is introduced: SVG documents are parsed by a bounded
in-tree XML/path reader and gzip documents reuse the bundled miniz.

## Table format

| Item | Supported | Notes |
| --- | --- | --- |
| SVG table version | 0 | other versions are `EXR_FONT` |
| Document records | 1..4096 | sorted, non-overlapping glyph ranges, bounds checked |
| Document size | ≤ 4 MiB after decompression | `EXR_LIMIT` |
| Table size | ≤ 8 MiB | `EXR_LIMIT` |
| gzip documents | yes | fixed output size from the gzip trailer, bounded by 4 MiB |
| Shared documents | yes | glyph selected by `id="glyph<gid>"` per the OT-SVG use rule |

A glyph with an SVG document is reported by
`exr_font_color_info_get()` as `EXR_FONT_COLOR_SVG` unless a COLR v1 paint is
also present (COLR v1 wins). If the document has no element with the
`glyph<gid>` identifier, the whole document root is rendered.

## Coordinate system

The OT-SVG default applies: y grows downward, the origin is the glyph origin
on the baseline, and user units are font design units. With a root
`viewBox` the viewport is the em square and maps as
`x_dev=(x_u-minX)·size/vbWidth`,
`y_dev=(y_u-minY)·size/vbHeight - size`. Without `viewBox` the mapping is
`x_dev=x_u·size/upem`, `y_dev=y_u·size/upem`.

`width`/`height` on the root are accepted only when they equal the designed
em size; other viewport scalings are rejected. `preserveAspectRatio` is
accepted only as `none` (the exact, non-letterboxed mapping above). The ink
bounding box of the parsed geometry is the rendered region; the em viewport
is not clipped, so ink outside the em square is still painted up to the
region limits.

## Element matrix

| Element | Status | Notes |
| --- | --- | --- |
| `svg` | supported | one root, optional viewBox/width/height |
| `g` | supported | inherited presentation attributes and group opacity |
| `defs` | supported | parsed but not painted; may hold `id` glyph elements |
| `path` | supported | M/L/H/V/C/S/Q/T/A/Z, absolute and relative, implicit repeats |
| `rect` | supported | x/y/width/height; rounded corners rejected |
| `circle` | supported | cx/cy/r |
| `ellipse` | supported | cx/cy/rx/ry |
| `line` | supported | stroke only |
| `polyline` | supported | open run of points |
| `polygon` | supported | closed run of points |
| `image`, `use`, `text`, `style`, `script`, `a`, `switch`, `symbol`, `marker`, `mask`, `clipPath`, `filter`, `pattern`, `linearGradient`, `radialGradient`, animation and foreign content | rejected | `EXR_UNSUPPORTED`; external references never resolve |

Namespaced prefixed element names are rejected. Attributes in a namespace
(for example `xmlns:xlink`) are ignored unless their name is in the rejected
presentation list.

## Attribute and paint subset

| Attribute | Status | Notes |
| --- | --- | --- |
| `fill`, `stroke` | supported | `none`, `#rgb`, `#rrggbb`, `rgb()` (integer or percent), `currentColor`, small named set |
| `fill-opacity`, `stroke-opacity` | supported | 0..1 or percent |
| `fill-rule` | supported | nonzero, evenodd |
| `opacity` | supported | element/group opacity via an isolated canvas layer |
| `stroke-width` | supported | non-negative |
| `stroke-linecap`, `stroke-linejoin`, `stroke-miterlimit` | supported | butt/round/square; miter/round/bevel; ≥1 |
| `transform` | supported | matrix, translate, scale, rotate, skewX, skewY (composed left to right) |
| `color` | supported | supplies `currentColor` |
| `display`, `visibility` | supported | `none`/`hidden` skip the subtree |
| `style`, `class`-driven CSS, `mask`, `clip-path`, `filter`, `marker-*`, `stroke-dasharray`, `stroke-dashoffset`, `paint-order`, `vector-effect` | rejected | an unsupported presentation attribute is an error, not silently ignored |
| `rx`/`ry` on `rect` | rejected | rounded rectangles are not painted as sharp rectangles |

Paint servers (`url(#...)`) are rejected. External URLs, `file:` references,
scripts, DTDs, CDATA sections and non-predefined entities are rejected before
any drawing. Only the five predefined XML entities and numeric character
references are decoded.

## Limits and failure ownership

| Limit | Value | Failure |
| --- | --- | --- |
| Elements per document | 2048 | `EXR_LIMIT` |
| Nesting depth | 32 | `EXR_LIMIT` |
| Attributes per element | 24 | `EXR_LIMIT` |
| Attribute bytes per document | 256 KiB | `EXR_LIMIT` |
| Path segments per document | 65536 | `EXR_LIMIT` |
| Rendered region | 8192 px per side, 8 Mi pixels | `EXR_LIMIT` |
| Work | shared 256 MiB raster units | `EXR_LIMIT` |
| Cancellation | per element, per 256 path segments and per canvas row | `EXR_CANCELLED` |

Parsing is two-pass (validate/measure, then paint). Malformed XML, mismatched
end tags, unquoted attributes, invalid UTF-8, numeric-reference overflow and
unsupported elements fail before a canvas is created. A failed render frees
the parsed document and returns a zero `exr_color_surface`; no partial bitmap
escapes. The returned surface is straight RGBA and is released by the caller
with `exr_bitmap_free()`.

## Verification

- `native-font-svg`: 26 positive documents (shapes, paths/arcs, transforms,
  viewBox scaling, opacity, currentColor, defs, gzip, shared-document `id`
  selection) and 15 rejection documents with exact status assertions, plus
  cancellation, alpha/sideways and layout/hit identity. 159 assertions.
- `tests/fixtures/fonts/svgfont.ttf` is built by
  `tools/generate_svg_test_fonts.py`; its SHA-256 is recorded in
  `docs/validation/wp8-svg.json`.
- Independent reference: Google Chrome 152 (Skia) rendering each document at
  a fixed size; see `docs/validation/wp8-reference.json`.

## Host example

```c
exr_font_color_info info = {0};
info.struct_size = sizeof(info);
if (exr_font_color_info_get(font, 0, glyph, &info, NULL, &error) == EXR_OK &&
    info.kind == EXR_FONT_COLOR_SVG) {
  /* exr_render_page_color() paints the frozen SVG subset. */
}
```

Hosts that need full SVG can read the font bytes with `exr_font_source()` and
run their own isolated SVG engine; no document bytes or parser objects are
retained by the SDK after a render.
