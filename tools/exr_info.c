/* SPDX-License-Identifier: MIT */
#include <exr/core.h>
#include <stdio.h>
#include <string.h>

int main(int argc, char **argv) {
  static const char *const formats[] = {
    "custom", "TXT", "HTML", "FB2", "EPUB", "DOCX", "RTF", "MOBI", "PDF", "CBZ"
  };
  exr_document *document = NULL;
  exr_publication *publication = NULL;
  exr_font *font = NULL;
  exr_layout *layout = NULL;
  exr_error error = {0};
  const exr_toc_entry *toc = NULL;
  size_t pages = 0, toc_count = 0;
  exr_format format;
  int result = 1;
  if (argc == 2 && !strcmp(argv[1], "--version")) {
    printf("EXReader %s\n", exr_version());
    return 0;
  }
  if (argc != 3) {
    fprintf(stderr, "usage: %s book font.ttf\n       %s --version\n"
                    "Reflow formats: EPUB, TXT, HTML, FB2, DOCX, RTF, MOBI/KF8.\n",
            argv[0], argv[0]);
    return 2;
  }
  if (exr_document_open(argv[1], &document, &error) != EXR_OK)
    goto done;
  format = exr_document_format(document);
  if (format == EXR_EPUB || format == EXR_MOBI || format == EXR_FB2) {
    if (exr_publication_open(argv[1], &publication, &error) != EXR_OK ||
        exr_publication_toc(publication, &toc, &toc_count, &error) != EXR_OK)
      goto done;
  }
  if (exr_font_open(argv[2], &font, &error) != EXR_OK ||
      exr_layout_create(document, font, NULL, &layout, &error) != EXR_OK)
    goto done;
  exr_layout_pages(layout, &pages);
  printf("Version: %s\nFormat: %s\nTitle: %s\nPages: %zu\nTOC entries: %zu\n",
         exr_version(), (unsigned)format < sizeof(formats) / sizeof(*formats)
           ? formats[format] : "unknown",
         exr_document_title(document), pages, toc_count);
  result = 0;
done:
  if (error.code != EXR_OK) fprintf(stderr, "%s\n", error.message);
  exr_layout_free(layout);
  exr_font_free(font);
  exr_publication_free(publication);
  exr_document_free(document);
  return result;
}
