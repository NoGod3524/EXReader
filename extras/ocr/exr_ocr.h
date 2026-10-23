/* SPDX-License-Identifier: MIT */
#ifndef EXR_OCR_H
#define EXR_OCR_H
#include <exr/base.h>
#ifdef __cplusplus
extern "C" {
#endif
/* Separate optional adapter, outside SDK ABI1. Never bundled with default SDK. */
typedef struct exr_ocr exr_ocr;
typedef struct {
  size_t max_pixels, max_output_bytes, max_items;
  unsigned timeout_ms, dpi, clockwise; /* Known correction: 0/90/180/270, no OSD. */
  double pixel_to_page[6]; /* Input bitmap -> original page; use viewport.inverse. */
  exr_control control;
} exr_ocr_options;
typedef struct {
  size_t text_offset, text_bytes;
  unsigned level; /* 1=line, 2=word, 3=symbol. UTF-8 offsets into result.text. */
  float confidence; /* Tesseract 0..100; not calibrated probability. */
  double pixel_quad[8], page_quad[8]; /* TL,TR,BR,BL in normalized reading order. */
} exr_ocr_item;
typedef struct { char *text; size_t text_bytes; exr_ocr_item *items; size_t count; } exr_ocr_result;
/* Serial/nonreentrant context. Model loading is outside recognition timeout. */
exr_status exr_ocr_open(const char *tessdata, const char *languages, exr_ocr **out, exr_error *error);
void exr_ocr_close(exr_ocr *ocr);
void exr_ocr_options_default(exr_ocr_options *options);
/* Borrowed gray/RGBA pixels, synchronous. RGBA is composited against white.
   Failure zeroes out; call result_free before reusing an owned result.
   Pixel limit bounds input admission/copy, output limit includes records+text.
   Deadline/cancel is cooperative Tesseract monitoring, not a hard RSS/CPU cap. */
exr_status exr_ocr_recognize(exr_ocr *ocr, const exr_bitmap *bitmap,
  const exr_ocr_options *options, exr_ocr_result *out, exr_error *error);
void exr_ocr_result_free(exr_ocr_result *result);
#ifdef __cplusplus
}
#endif
#endif
