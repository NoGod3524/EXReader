# reader_ocr_overlay — temporary OCR text snapshot for one rendered page

Turns one **rendered fixed page** into a session-local OCR text/region snapshot and
maps every recognized box back to page coordinates. It is a reader aid for scanned
pages, not a text layer: nothing is written to the SDK notes, library, reading
progress or the original file, and no permanent reading anchor is produced.

* Public C ABI; the only header a consumer needs is `reader_ocr_overlay.h`.
* Installs as an independent CMake package `EXReaderOCROverlay 0.1.0`.
* Backed by the separate optional adapter `extras/ocr` (Tesseract); not part of the
  default reading profile and never enabled implicitly.

## Contract

| Item | Behaviour |
| --- | --- |
| Input | an `exr_fixed_document` page rendered at `scale`, or a host bitmap that matches `exr_viewport_create` at that scale |
| Output | owned `reader_ocr_overlay`: line and word records, UTF-8 text, page-space quads, Tesseract confidence 0..100 |
| Labels | `source` is always `tesseract-ocr`; `native_text` and `permanent_anchor` are always `0` |
| Ownership | bitmaps and geometry are borrowed for the call; the snapshot owns every string and record and outlives bitmap, document and engine |
| Threads | the engine is bound to its opening thread; a foreign-thread call returns `THREAD` and changes nothing |
| Reentry | a call from inside a control/still-current callback of the same engine returns `BUSY` |
| Commit | a snapshot exists only on `OK`; otherwise `*out` stays NULL with no partial records |
| Cancellation | cooperative: `exr_control.cancelled` during render/recognition plus one final poll before commit |
| Deadline | `timeout_ms` covers render and recognition as elapsed time; model load is outside it |
| Hard caps | 64 Mpx / 20 000 records / 4 MiB snapshot / 300 s / scale <= 16; defaults 16 Mpx / 5 000 / 1 MiB / 30 s |
| Rotation | the raster is orientation-corrected by `(720 - geometry.rotation - content_rotation) % 360` degrees clockwise |
| Staleness | `check_current` compares page id, geometry, scale and optionally bitmap size + pixel hash; `still_current` guards the commit |

`reader_ocr_overlay_to_fixed_text` copies one level into an SDK `exr_fixed_text` for
session-local find/select/hit. That text must not be persisted as an anchor: OCR
text is a temporary projection of pixels, not the book's own text.

## Limits and deliberate gaps

* Recognition quality is Tesseract's on the rendered raster; confidence is a
  Tesseract score, not a calibrated probability.
* `pixel_quad` follows the adapter's bounding-box convention, so a rotated raster can
  differ from the unrotated one by about one page unit at the far edge.
* Not a hard CPU/RSS cap: the deadline is cooperative. Isolate the backend in a
  process when a hard cap is required.
* Model files, their licences and their identity are the host's to ship and register;
  this package bundles no traineddata and no font.
* Windows and mobile hosts are not exercised by this package's CI (Linux and macOS
  only); the component is portable C++17 but those hosts stay unaccepted until they
  run their own probe.
* No network path, no private SDK SQL, no server, no WebView and no plugin framework.

## Build and consume

```
cmake -S apps/reader/ocr-overlay -B build/overlay -DCMAKE_PREFIX_PATH="$SDK;$OCR" -DCMAKE_INSTALL_PREFIX="$PREFIX"
cmake --build build/overlay && cmake --install build/overlay
```

```cmake
find_package(EXReaderOCROverlay 0.1.0 EXACT CONFIG REQUIRED)
target_link_libraries(app PRIVATE EXReaderOCROverlay::reader_ocr_overlay)
```

See `docs/READER-OCR-OVERLAY.md` for the acceptance evidence and reproduction.
