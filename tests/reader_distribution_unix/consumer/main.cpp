// SPDX-License-Identifier: MIT
// Installed-SDK C++ consumer: every public header in one C++11 translation unit,
// then the same open/layout path through the C ABI.
#include "exr/base.h"
#include "exr/document.h"
#include "exr/formats.h"
#include "exr/graphics.h"
#include "exr/layout.h"
#include "exr/library.h"
#include "exr/audio.h"
#include "exr/pdf.h"
#include "exr/pdf_edit.h"
#include "exr/render.h"
#include "exr/text.h"
#include "exr/textindex.h"
#include "exr/core.h"
#include "exreader.h"
#include <cstdio>
#include <cstring>

int main(int argc, char **argv) {
  int failures = 0;
  auto require = [&failures](bool condition, const char *label) {
    if (!condition) {
      std::fprintf(stderr, "FAIL %s\n", label);
      failures++;
    }
  };
  if (argc != 3) {
    std::fprintf(stderr, "usage: %s EPUB FONT\n", argv[0]);
    return 2;
  }
  require(exr_abi_version() == EXR_ABI_VERSION, "abi-version");
  require(std::strcmp(exr_version(), EXR_VERSION) == 0, "release-version");
  static_assert(sizeof(exr_error) > 0, "exr_error is complete");
  static_assert(sizeof(exr_bitmap) >= sizeof(void *) * 2, "exr_bitmap is complete");
  exr_error error = {0};
  exr_document *document = NULL;
  require(exr_document_open("/nonexistent/exreader-j24-missing.epub", &document, &error) != EXR_OK
          && document == NULL, "missing-file-rejected");
  require(exr_document_open(argv[1], &document, &error) == EXR_OK, "open-book");
  size_t pages = 0, text_size = 0;
  if (document != NULL) {
    const char *text = exr_document_text(document, &text_size);
    require(text != NULL && text_size > 0, "extracted-text");
    exr_font *font = NULL;
    require(exr_font_open(argv[2], &font, &error) == EXR_OK, "open-font");
    if (font != NULL) {
      exr_layout_options options = exr_layout_defaults();
      exr_layout *layout = NULL;
      require(exr_layout_create(document, font, &options, &layout, &error) == EXR_OK, "layout");
      if (layout != NULL) {
        require(exr_layout_pages(layout, &pages) != NULL && pages > 0, "layout-pages");
      }
      exr_layout_free(layout);
      exr_font_free(font);
    }
    exr_document_free(document);
  }
  std::printf("{\"schema\":1,\"version\":\"%s\",\"abi\":%u,\"pages\":%zu,"
              "\"text_bytes\":%zu,\"headers\":14,\"negative_checks\":1,\"failures\":%d}\n",
              exr_version(), (unsigned)exr_abi_version(), pages, text_size, failures);
  return failures == 0 ? 0 : 1;
}
