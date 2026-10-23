# Android host fixtures

The Android emulator walkthrough does not commit large book binaries. Fixtures are
materialized deterministically by `tools/build_android_host.py` into
`build/android-host/fixtures` and pushed to the emulator's Downloads folder:

| File | Purpose |
| --- | --- |
| Sample.epub | Three-chapter reflow sample with English and CJK text |
| Second.epub | Book switching and retry coverage |
| BigChapter.epub | Single chapter of about 2 MiB for the large-chapter path |
| Ambiguous.epub | Repeated text so a point anchor resolves as not exact |
| Sample.txt | Plain-text reflow entry |
| Sample.pdf | Copy of `tests/fixtures/pdf-public.pdf` (fixed page, per-page text) |
| Broken.epub | Malformed ZIP for the format-error path |
| TooLarge.epub | 33 MiB stored EPUB for the 32 MiB host limit |
| Large.epub | 30 MiB stored EPUB for import cancellation |

`fixtures.json` records size and SHA-256 for each file. The per-case results and
screenshots are written by the instrumented test to its external files directory and
pulled into `build/android-host/evidence/device` by the workflow. See
`docs/WP13-ANDROID.md` for the acceptance matrix and limitations.
