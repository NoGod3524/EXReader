/* SPDX-License-Identifier: MIT */
/* C11 consumer of the installed public header. It needs no OCR model, no font and
   no document: it checks the exported ABI surface and the documented failure paths
   a host sees before a page is ever recognized. */
#include <reader_ocr_overlay.h>
#include <stdio.h>
#include <string.h>

static int failures = 0;
static void expect(const char *name, int ok) {
  if (!ok) { failures++; printf("c-consumer FAIL %s\n", name); }
}

int main(void) {
  reader_ocr_overlay_options options;
  reader_ocr_overlay_error error;
  reader_ocr_engine *engine = (reader_ocr_engine *)1;
  reader_ocr_overlay *overlay = (reader_ocr_overlay *)1;
  exr_fixed_text *fixed = (exr_fixed_text *)1;
  memset(&error, 0, sizeof(error));
  reader_ocr_overlay_options_default(&options);
  expect("version", strcmp(reader_ocr_overlay_version(), READER_OCR_OVERLAY_VERSION) == 0);
  expect("options default", options.struct_size == sizeof(options) && options.scale == 1.0 &&
    options.base_dpi == 300 && options.timeout_ms == 30000 && options.max_pixels == 16000000 &&
    options.max_items == 5000 && options.max_snapshot_bytes == (1u << 20) && options.min_confidence == 0.0f);
  expect("open rejects empty directory", reader_ocr_engine_open("", "eng", &engine, &error) == READER_OCR_OVERLAY_ARGUMENT && !engine);
  expect("open rejects empty language", reader_ocr_engine_open("models", "", &engine, &error) == READER_OCR_OVERLAY_ARGUMENT && !engine);
  expect("open reports a missing model", reader_ocr_engine_open("no-such-ocr-model-directory", "eng", &engine, &error) == READER_OCR_OVERLAY_MODEL_MISSING && !engine);
  expect("error message is terminated", error.message[sizeof(error.message) - 1] == 0 && strlen(error.message) > 0);
  expect("options copy is reloadable", (reader_ocr_overlay_options_default(&options), options.timeout_ms == 30000));
  expect("close accepts NULL", reader_ocr_engine_close(NULL, &error) == READER_OCR_OVERLAY_OK);
  reader_ocr_overlay_free(NULL);
  expect("info is NULL for NULL snapshot", reader_ocr_overlay_get_info(NULL) == NULL);
  {
    size_t count = 1, bytes = 1;
    expect("items are NULL for NULL snapshot", reader_ocr_overlay_items(NULL, &count) == NULL && count == 0);
    expect("text is empty for NULL snapshot", reader_ocr_overlay_text(NULL, &bytes) != NULL && bytes == 0);
    expect("check_current needs a snapshot", reader_ocr_overlay_check_current(NULL, "p", NULL, 1.0, NULL, &error) == READER_OCR_OVERLAY_ARGUMENT);
    expect("fixed text needs a snapshot", reader_ocr_overlay_to_fixed_text(NULL, READER_OCR_LINE, NULL, &fixed, &error) == READER_OCR_OVERLAY_ARGUMENT && !fixed);
    expect("status codes are stable", READER_OCR_OVERLAY_OK == 0 && READER_OCR_OVERLAY_ARGUMENT == 1 &&
      READER_OCR_OVERLAY_THREAD == 11 && READER_OCR_LINE == 1 && READER_OCR_WORD == 2);
  }
  printf("c-consumer %s failures=%d\n", reader_ocr_overlay_version(), failures);
  return failures == 0 ? 0 : 1;
}
