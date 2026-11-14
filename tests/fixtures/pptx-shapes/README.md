# PPTX M2 shape fixtures

Run `python tests/fixtures/pptx-shapes/generate.py` with python-pptx 1.0.2 to
regenerate the six original decks, or add `--check` to verify their bytes and
manifest. ZIP entries use deterministic timestamps, permissions and ordering.

The first five slides are 960 × 540 pt (16:9); `standard.pptx` is 720 × 540 pt
(4:3). Every shape has explicit sRGB fill and no outline. The group has two
offset rectangles and a 2 × 1.5 group scale; its off and chOff differ.

`manifest.json` records dimensions, colors, preset geometries and absolute
bounds obtained by reopening each deck with python-pptx and composing the
reported group coordinate transforms. The ctypes acceptance test needs only
Python's standard library and the committed decks. It samples interior pixels,
checks shape silhouettes and compares rendered color bounds against the oracle.
Additional in-memory XML mutations exercise quarter rotations, flips, nested
groups, zero child extents, solid outlines, default theme colors, malformed
transforms/colors, unknown presets, skipped media, shape limits and group depth.
