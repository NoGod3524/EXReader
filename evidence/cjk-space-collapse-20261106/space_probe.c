/* Dump the SDK projection, never XHTML source whitespace. Output stays local. */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>

int main(int argc, char **argv) {
  exr_publication *pub = NULL;
  exr_error error = {0};
  size_t count;
  if (argc != 3) return 2;
  if (exr_publication_open(argv[1], &pub, &error)) return 1;
  exr_publication_parts(pub, &count);
  for (size_t part = 0; part < count; part++) {
    exr_document *doc = NULL;
    char path[4096];
    size_t size, blocks;
    FILE *out;
    if (exr_publication_load(pub, part, &doc, &error)) return 1;
    const char *text = exr_document_text(doc, &size);
    const exr_block *b = exr_document_blocks(doc, &blocks);
    snprintf(path, sizeof(path), "%s/part-%02zu.txt", argv[2], part);
    out = fopen(path, "wb");
    if (!out || fwrite(text, 1, size, out) != size) return 1;
    fclose(out);
    snprintf(path, sizeof(path), "%s/body-%02zu.txt", argv[2], part);
    out = fopen(path, "wb");
    if (!out) return 1;
    for (size_t i = 0; i < blocks; i++) if (!b[i].heading) {
      if (fwrite(text+b[i].start, 1, b[i].end-b[i].start, out) != b[i].end-b[i].start ||
          fputc('\n', out) == EOF) return 1;
    }
    fclose(out);
    exr_document_free(doc);
  }
  exr_publication_free(pub);
  printf("parts=%zu\n", count);
  return 0;
}
