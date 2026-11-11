/* SPDX-License-Identifier: MIT */
#if defined(_MSC_VER) && !defined(_CRT_SECURE_NO_WARNINGS)
#define _CRT_SECURE_NO_WARNINGS
#endif
#include <exr/core.h>
#include <stdio.h>

int main(int argc, char **argv) {
  exr_document *document = NULL;
  exr_publication *publication = NULL;
  exr_font *font = NULL;
  exr_layout *layout = NULL;
  exr_bitmap bitmap = {0};
  exr_error error = {0};
  const exr_toc_entry *toc = NULL;
  size_t pages = 0, toc_count = 0;
  FILE *output = NULL;
  const char *path = argc == 4 ? argv[3] : "page-1.pgm";
  int result = 1;
  if (argc < 3 || argc > 4) {
    fprintf(stderr, "usage: %s book.epub font.ttf [page-1.pgm]\n", argv[0]);
    return 2;
  }
  if (exr_document_open(argv[1], &document, &error) != EXR_OK)
    goto done;
  if (exr_document_format(document) != EXR_EPUB) {
    fprintf(stderr, "Expected an EPUB document\n");
    goto done;
  }
  if (exr_publication_open(argv[1], &publication, &error) != EXR_OK ||
      exr_publication_toc(publication, &toc, &toc_count, &error) != EXR_OK ||
      exr_font_open(argv[2], &font, &error) != EXR_OK ||
      exr_layout_create(document, font, NULL, &layout, &error) != EXR_OK)
    goto done;
  exr_layout_pages(layout, &pages);
  if (exr_render_page(layout, exr_layout_font(layout), 0, &bitmap, &error) != EXR_OK)
    goto done;
  printf("Title: %s\nPages: %zu\nTOC entries: %zu\n",
         exr_document_title(document), pages, toc_count);
  output = fopen(path, "wb");
  if (!output) { perror(path); goto done; }
  if (fprintf(output, "P5\n%u %u\n255\n", bitmap.width, bitmap.height) < 0)
    goto write_error;
  for (uint32_t y = 0; y < bitmap.height; ++y)
    if (fwrite(bitmap.pixels + (size_t)y * bitmap.stride, 1, bitmap.width, output)
        != bitmap.width)
      goto write_error;
  if (fclose(output) != 0) { output = NULL; perror(path); goto done; }
  output = NULL;
  printf("Output: %s (%u x %u, PGM)\n", path, bitmap.width, bitmap.height);
  result = 0;
  goto done;
write_error:
  perror(path);
done:
  if (error.code != EXR_OK) fprintf(stderr, "%s\n", error.message);
  if (output) fclose(output);
  exr_bitmap_free(&bitmap);
  exr_layout_free(layout);
  exr_font_free(font);
  exr_publication_free(publication);
  exr_document_free(document);
  return result;
}
