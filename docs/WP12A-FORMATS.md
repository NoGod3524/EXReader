# WP12a CBZ image formats and frame/page rules

This document freezes the WP12a CBZ image scope. It is additive to the existing
CBZ reader; natural sorting, ComicInfo metadata, fixed-page IDs and PNG/JPEG
pixel output are unchanged for single-page files.

## Supported formats

| Format | Build option | Default | Pages | Notes |
| --- | --- | --- | --- | --- |
| PNG | always built | ON | 1 | Existing path, byte-identical pixels |
| JPEG | always built | ON | 1 | Existing path, including CMYK JPEG through the PDF adapter |
| BMP | always built | ON | 1 | Uncompressed/indexed/RLE BMP through the pinned stb_image; 32-bit BITMAPV4 alpha masks preserve alpha |
| GIF | always built | ON | 1..4096 | All frames in source order; GIF disposal is composited by stb_image; transparency index preserves alpha |
| WebP | `EXR_ENABLE_IMAGE_WEBP` | ON | 1..4096 | Lossy/lossless still and animated WebP through libwebp/demux |
| TIFF | `EXR_ENABLE_IMAGE_TIFF` | ON | 1..4096 | Baseline/Deflate/LZW/PackBits strips and tiles, palette/alpha/16-bit via libtiff |
| AVIF | `EXR_ENABLE_IMAGE_AVIF` | ON | 1..4096 | 8/10/12-bit still, grid and image sequences through libavif + libaom |

A disabled optional codec keeps its public entry points. Probes and decodes for
that format return `EXR_UNSUPPORTED`; they never silently skip a page. Builds
with all three options OFF still compile, install and run the rest of the SDK.

## Candidate selection and page order

1. An archive member is a page candidate only when its extension is one of
   `.png .jpg .jpeg .gif .webp .bmp .avif .tif .tiff`. Other members are ignored
   exactly as before; `ComicInfo.xml` is handled separately.
2. The decoder sniffs the bytes and does not trust the extension. A candidate
   extension with damaged or unsupported content is an `EXR_FORMAT` error, not
   a dropped page. A .webp member containing valid PNG bytes is accepted as PNG
   (the extension is only the candidate filter).
3. Members are ordered by the existing natural comparator (digit runs compared
   numerically, ASCII case folded, full byte comparison as the tie-break).
4. Each candidate expands into its frames in source order, frame 0 first. The
   final directory order is: natural member order, then ascending frame index
   within that member.
5. Page IDs are stable:
   - single-page image: the member path, unchanged;
   - multi-page image frame 0: the member path;
   - frame N (N > 0): `<member>#N`.
   Duplicate IDs (including a literal file whose name already ends in a matching
   `#N`) are rejected. No frame is renumbered or reordered.
6. Limits: one image may contribute at most 4,096 frames; the whole archive may
   contain at most 10,000 pages after expansion and at most 10,000 members.
   Exceeding either limit returns `EXR_LIMIT`; it is not truncated.

Frame/page selection is available through:

```c
size_t pages = 0;
exr_image_page_count(bytes, size, &pages, &error);
uint32_t width, height;
exr_image_page_dimensions(bytes, size, page, &width, &height, &error);
exr_bitmap rgba = {0};
exr_image_decode_page(bytes, size, page, &rgba, &error); /* page 0 is exr_image_decode() */
exr_bitmap_free(&rgba);
```

The fixed CBZ reader uses the same page index. `exr_fixed_pages()` returns the
expanded directory; `exr_fixed_render(doc, page, ...)` decodes exactly that
frame. There is no implicit "first frame only" mode and no silent frame drop.

## Budgets and failure classes

| Budget | Value | Applied |
| --- | --- | --- |
| Encoded bytes per CBZ member | 32 MiB | open/render |
| Header bytes read for PNG/JPEG/BMP | 1 MiB | open |
| Header bytes read for GIF/WebP/TIFF/AVIF | full member (≤32 MiB) | open |
| Aggregate header work | 96 MiB | open |
| Width/height | 8192 each | probe and decode |
| Pixels per page | 16,777,216 | probe and decode |
| Expanded RGBA per decode | 256 MiB | decode |
| Expanded GIF frame array | 96 MiB | before decode |
| stb_image working allocations | 128 MiB | PNG/JPEG/BMP/GIF |
| Pages per image / archive | 4,096 / 10,000 | open/probe |

Failure classes are distinct: `EXR_FORMAT` = damaged/unknown input,
`EXR_LIMIT` = a declared budget, `EXR_UNSUPPORTED` = codec disabled at build
time, `EXR_CANCELLED` = control callback, `EXR_IO` = archive source read
failure, `EXR_MEMORY` = allocation failure. Every failed decode zeroes its
output bitmap. Cancellation is checked before/after member reads, per decoded
GIF row and per animation frame.

## Codec dependencies

All archives are pinned by SHA-256 in `cmake/deps.cmake`; license texts are
installed under `share/exreader/licenses`.

| Component | Version / commit | SHA-256 | License | Use |
| --- | --- | --- | --- | --- |
| stb_image | `2c980bb59875b0d32144a71867fbdebb2f77cd20` | `9a955b1b49a4410088a2e0ee2a9c057c3c907d0c1d75454144cb980aca0ba515` | MIT or public domain | PNG/JPEG/BMP/GIF |
| libwebp | 1.5.0 | `668c9aba45565e24c27e17f7aaf7060a399f7f31dba6c97a044e1feacb930f37` | BSD-3-Clause | WebP still/animation |
| zlib | 1.3.1 | `17e88863f3600672ab49182f217281b6fc4d3c762bde361935e436a95214d05c` | zlib | TIFF Deflate |
| libtiff | 4.7.0 | `8f568a0dfac2e514074b04d7368c22e8afc1009af29780762a2536fd4d111e16` | libtiff (BSD-style) | TIFF |
| libaom | 3.15.2, `af3dc9aadc793c1b00edc003e3fc19a44fdeb574` (mirror of the official tag) | `a606215ed62ee1aaffc1360867c637b0ccafbc1a0c1c8430e2412257b8baa62a` | BSD-2-Clause + AOM patent license | AV1 decoder for AVIF |
| libavif | 1.2.0 | `2182f4900d1a9617cee89746922a58dd825f2a3547f23907b8d78dc3685f7d8c` | BSD-2-Clause | AVIF container/color conversion |

libaom's CMake requires Perl for its RTCD/version generation. The configure
step searches `PATH`, then Git for Windows' `usr/bin/perl.exe` on Windows. If
Perl is unavailable, configure fails with an explicit instruction to install
Perl or pass `-DEXR_ENABLE_IMAGE_AVIF=OFF`. libaom appends its warning flags to
the directory `CMAKE_*_FLAGS`; `cmake/deps.cmake` snapshots and restores
EXReader's flags so third-party warnings do not become EXReader warnings.

## Verification

Fixtures are generated by `tools/generate_image_format_fixtures.py`
(Pillow development tool only, never linked). The committed files are original
patterns under `tests/fixtures/images` with MIT provenance and SHA-256 values in
`MANIFEST.json`. Regressions:

- `native-image-formats`: 11 matrix cases per format (color, alpha, checker,
  odd/1x1/255x1/1x255 sizes, gray, palette, transparent, gradient), animation
  pages 0..3, transparent GIF and 32-bit BMP alpha, truncated/bad-magic/huge/
  expansion/33 MiB rejection and page-index bounds (956 checks).
- `native-cbz-formats`: one archive mixing PNG/GIF/WebP/BMP/multi-page TIFF/
  AVIF/JPEG, asserting the expanded directory order, IDs, geometry, per-frame
  pixels, ComicInfo title and damaged-content rejection.
- `native-cbz`: existing natural sorting, ComicInfo, duplicate path, CRC,
  library import/dedup/backup and cancellation regressions.
