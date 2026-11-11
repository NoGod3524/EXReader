/* SPDX-License-Identifier: MIT */
#include <exr/formats.h>
#include <exr/layout.h>
#include <stdio.h>

int main(int argc, char **argv) {
  const char text[] = "A page is laid out only when the host requests it.";
  exr_document *document = NULL;
  exr_font *font = NULL;
  exr_pager *pager = NULL;
  const exr_layout *page = NULL;
  exr_error error = {0};
  exr_status status;
  if (argc != 2) { fprintf(stderr, "usage: pagination font.ttf\n"); return 2; }
  status = exr_document_open_memory(EXR_TXT, text, sizeof(text) - 1, &document, &error);
  if (status == EXR_OK) status = exr_font_open(argv[1], &font, &error);
  if (status == EXR_OK) status = exr_pager_create(document, font, NULL, &pager, &error);
  if (status == EXR_OK) status = exr_pager_set_cache(pager, 3, 8u * 1024u * 1024u, &error);
  if (status == EXR_OK) status = exr_pager_get(pager, 0, &page, &error);
  if (status == EXR_OK)
    printf("cached=%zu, scanned=%zu UTF-8 bytes\n",
           exr_pager_cached_count(pager), exr_pager_position(pager));
  else
    fprintf(stderr, "%s\n", error.message);
  /* page is borrowed from pager; do not call layout_free(page). */
  exr_pager_free(pager);
  exr_font_free(font);
  exr_document_free(document);
  return status == EXR_OK ? 0 : 1;
}
