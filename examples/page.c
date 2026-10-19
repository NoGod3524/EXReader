/* SPDX-License-Identifier: MIT */
#include <exreader.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>

static int index_value(const char *text, size_t *out) {
  char *end;
  unsigned long long value;
  if (!text[0] || text[0] == '-' || text[0] == '+')
    return 0;
  errno = 0;
  value = strtoull(text, &end, 10);
  if (errno || *end || value > SIZE_MAX)
    return 0;
  *out = (size_t)value;
  return 1;
}
static int example_main(int argc, char **argv) {
  exr_publication *publication = NULL;
  exr_document *doc = NULL;
  exr_font *font = NULL;
  exr_pager *pager = NULL;
  const exr_layout *page = NULL;
  exr_bitmap bitmap = {0};
  exr_error error = {0};
  exr_status status;
  size_t index = 0, part = 0, text_size;
  if (argc < 4 || argc > 6 || (argc >= 5 && !index_value(argv[4], &index)) ||
      (argc == 6 && !index_value(argv[5], &part))) {
    fprintf(stderr, "usage: exreader-page-example book.epub font.ttf output.png [page] [part]\n");
    return 2;
  }
  status = exr_publication_open(argv[1], &publication, &error);
  if (status == EXR_OK)
    status = exr_publication_load(publication, part, &doc, &error);
  exr_publication_free(publication);
  if (status == EXR_OK)
    status = exr_font_open(argv[2], &font, &error);
  if (status == EXR_OK)
    status = exr_pager_create(doc, font, NULL, &pager, &error);
  if (status == EXR_OK)
    status = exr_pager_set_cache(pager, 3, (size_t)8 * 1024 * 1024, &error);
  if (status == EXR_OK)
    status = exr_pager_get(pager, index, &page, &error);
  if (status == EXR_OK)
    status = exr_render_page_color(page, font, 0, &bitmap, &error);
  if (status == EXR_OK)
    status = exr_bitmap_write_png(&bitmap, argv[3], &error);
  if (status == EXR_OK) {
    exr_document_text(doc, &text_size);
    printf("EXReader C %s: part %zu page %zu; scanned %zu/%zu UTF-8 bytes; "
           "%zu cached pages, %zu payload bytes\n", exr_version(), part, index,
           exr_pager_position(pager), text_size, exr_pager_cached_count(pager),
           exr_pager_cached_bytes(pager));
  } else
    fprintf(stderr, "%s\n", error.message);
  exr_bitmap_free(&bitmap);
  exr_pager_free(pager);
  exr_font_free(font);
  exr_document_free(doc);
  return status == EXR_OK ? 0 : 1;
}
#include "entry.h"
