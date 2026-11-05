/* SPDX-License-Identifier: MIT */
/* Installed-SDK consumer: open an installed EPUB, lay it out, render one page,
   write a PNG and prove two argument failures. No source-tree target is linked. */
#include "exr/core.h"
#include "exr/document.h"
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>

static int failures;

#define REQUIRE(condition, label) \
  do { if (!(condition)) { fprintf(stderr, "FAIL %s\n", (label)); failures++; } } while (0)

static unsigned long long file_bytes(const char *path) {
  struct stat status;
  if (stat(path, &status) != 0) return 0;
  return (unsigned long long)status.st_size;
}

int main(int argc, char **argv) {
  exr_error error = {0};
  exr_document *document = NULL;
  exr_font *font = NULL;
  exr_layout *layout = NULL;
  exr_bitmap bitmap = {0};
  exr_layout_options options = exr_layout_defaults();
  const char *text = NULL;
  size_t pages = 0, text_size = 0;
  unsigned bitmap_width = 0, bitmap_height = 0;
  unsigned long long png_bytes = 0;
  int format = -1;
  if (argc != 4) {
    fprintf(stderr, "usage: %s EPUB FONT OUT.png\n", argv[0]);
    return 2;
  }
  REQUIRE(exr_abi_version() == EXR_ABI_VERSION, "abi-version");
  REQUIRE(strcmp(exr_version(), EXR_VERSION) == 0, "release-version");
  {
    size_t probe = 99;
    uint32_t width = 99, height = 99;
    exr_bitmap image = {0};
    REQUIRE(exr_image_page_count(NULL, 0, &probe, &error) == EXR_ARGUMENT, "argument-page-count");
    REQUIRE(probe == 0, "argument-page-count-cleared");
    REQUIRE(exr_image_page_dimensions(NULL, 0, 0, &width, &height, &error) == EXR_ARGUMENT,
            "argument-page-dimensions");
    REQUIRE(width == 0 && height == 0, "argument-page-dimensions-cleared");
    REQUIRE(exr_image_decode_page(NULL, 0, 0, &image, &error) == EXR_ARGUMENT, "argument-decode");
    REQUIRE(image.pixels == NULL, "argument-decode-cleared");
  }
  REQUIRE(exr_document_open("/nonexistent/exreader-j24-missing.epub", &document, &error) != EXR_OK
          && document == NULL, "missing-file-rejected");
  REQUIRE(exr_document_open(argv[1], &document, &error) == EXR_OK && document != NULL, "open-book");
  if (document != NULL) {
    text = exr_document_text(document, &text_size);
    REQUIRE(text != NULL && text_size > 0, "extracted-text");
    format = (int)exr_document_format(document);
    REQUIRE(format == (int)EXR_EPUB, "detected-format");
    REQUIRE(exr_font_open(argv[2], &font, &error) == EXR_OK && font != NULL, "open-font");
    if (font != NULL) {
      REQUIRE(exr_layout_create(document, font, &options, &layout, &error) == EXR_OK
              && layout != NULL, "layout");
      if (layout != NULL) {
        REQUIRE(exr_layout_pages(layout, &pages) != NULL && pages > 0, "layout-pages");
        REQUIRE(exr_render_page_color(layout, font, 0, &bitmap, &error) == EXR_OK
                && bitmap.pixels != NULL, "render-page");
        REQUIRE(bitmap.width > 0 && bitmap.height > 0 && bitmap.channels == 4, "bitmap-shape");
        REQUIRE(exr_bitmap_write_png(&bitmap, argv[3], &error) == EXR_OK, "write-png");
        png_bytes = file_bytes(argv[3]);
        bitmap_width = bitmap.width;
        bitmap_height = bitmap.height;
      }
    }
  }
  exr_bitmap_free(&bitmap);
  exr_layout_free(layout);
  exr_font_free(font);
  exr_document_free(document);
  printf("{\"schema\":1,\"version\":\"%s\",\"abi\":%u,\"format\":%d,\"pages\":%zu,"
         "\"text_bytes\":%zu,\"bitmap_width\":%u,\"bitmap_height\":%u,\"png_bytes\":%llu,"
         "\"negative_checks\":4,\"failures\":%d}\n",
         exr_version(), (unsigned)exr_abi_version(), format, pages, text_size,
         bitmap_width, bitmap_height, png_bytes, failures);
  return failures == 0 ? 0 : 1;
}
