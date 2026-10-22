# WP11 optional OCR adapter

This is the recognition and coordinate adapter subpackage, not the complete WP11 exit. It does not write PDF text layers, replace native text, integrate search/selection/annotation, or alter ABI1/schema6. The default SDK build does not compile or distribute Tesseract or language models.

## Consumption

Build and install the ordinary EXReader 3.40.0 SDK first. Configure `extras/ocr` separately with `CMAKE_PREFIX_PATH` pointing at that installed SDK. The optional build requires C++17, pkg-config, and Tesseract 5 development files. Install it into a separate prefix. An application then uses `find_package(EXReaderOCR CONFIG REQUIRED)` and links `EXReader::exreader_ocr`; both prefixes must be in `CMAKE_PREFIX_PATH`. `tests/ocr` is an installed consumer, not an in-tree linkage shortcut.

The C interface in `extras/ocr/exr_ocr.h` consumes the existing public `exr_bitmap`, `exr_control`, and page transform conventions. `exr_fixed_render` provides a gray/RGBA bitmap. Pass the corresponding `exr_viewport.inverse` as `pixel_to_page`; callers rendering a cropped raster compose the crop translation into that inverse first. No private SDK object is inspected.

`exr_ocr_open` loads caller-selected model files into one serial, nonreentrant context. `exr_ocr_recognize` borrows the bitmap for the synchronous call, composites RGBA against white, applies an explicit clockwise orientation correction, and returns owned UTF-8 text slices with line/word/symbol confidence and quadrilaterals. Confidence is Tesseract's 0–100 score. Quad order follows the normalized text image TL/TR/BR/BL; its coordinates are transformed back into the original input raster and original page. Orientation is supplied by the caller; this adapter does not perform automatic OSD.

Each record references its own text slice in the result arena; the arena contains line, word and symbol representations. Concatenating the entire arena would duplicate text. Select the required record level. `exr_ocr_result_free` frees both arenas; free an owned result before reusing its output struct. Every failed recognition leaves a zero result. Contexts remain reusable after cancellation or a limit return.

## Budgets and cancellation

Defaults admit 16 million pixels, at most 100,000 records, and at most 4 MiB of final record-plus-text payload including the text terminator. One gray raster copy is used for rotation and alpha composition. Maximum pixels is checked before allocation. Every input row and every output record polls cancellation/deadline; recognition uses the Tesseract monitor. The 30-second default deadline is elapsed time, not process CPU. Model loading occurs in `open`, outside that recognition deadline.

These limits do not impose a hard RSS ceiling on Tesseract's internal workspace or transient UTF-8 allocation. The deadline is cooperative, not a process termination guarantee. Hosts needing a hard process memory/time limit must isolate the optional backend. No claim of hard CPU metering is made by this subpackage, and none of its measurements count toward the separate WP16 campaign.

## Frozen cloud acceptance

Only `.github/workflows/wp11-ocr.yml` builds and executes this subpackage. It installs the unchanged lightweight SDK, installs the OCR adapter separately, builds a fresh installed consumer, then measures 30 original digitally rendered 300 dpi pages: ten English, ten Chinese and ten mixed pages, including supplied 0/90/180/270-degree orientations. This is clean digital print, not a claim of scanned-page or handwriting accuracy.

The text, font selection, page geometry and rendering procedure live in `tests/ocr/generate.py`. The cloud artifact freezes every input raster, per-character reference boxes, font bytes/licenses, pinned model bytes/licenses, program/library hashes, package versions, per-page raw records and measurement JSON. Models use `tesseract-ocr/tessdata_fast` commit `87416418657359cb625c412a48b6e1d6d41c29bd`, `eng` and `chi_sim`, Apache-2.0. Fonts are DejaVu Sans and Noto Sans CJK, with their redistribution notices copied into the same artifact. Distribution of the adapter alone does not include these models or fonts.

CER uses NFC code points after whitespace removal. WER uses whitespace-delimited words; Chinese WER is consequently a line/token diagnostic, not linguistic segmentation. Character coordinate error is reported only for correctly aligned characters, comparing maximum box-edge difference against rendered font ink bounds. Recognition box error and exact affine roundtrip error are separate metrics. English CER must be <=3%, Chinese <=5%; mixed results are reported independently. No tolerance is widened on failure. Both Release and ASan/UBSan wrapper jobs must pass. The system Tesseract library is not rebuilt with sanitizers, so this is adapter instrumentation, not a sanitizer claim about all backend internals.

Eleven consumer contracts cover pixel/output/item limits, invalid rotation/transform/stride, pre-cancel, recognition-phase cancel, deadline, reuse after failure and RGBA input. Every failed call is checked for empty output. The current acceptance state and exact remaining WP11 dependencies are recorded in `docs/validation/wp11-ocr-adapter.json`.
