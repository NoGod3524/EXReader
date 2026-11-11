/* SPDX-License-Identifier: MIT */
#include <exr/formats.h>
#include <stdio.h>

int main(void) {
  const char text[] = "Find this word, then find another word.";
  exr_document *document = NULL;
  exr_error error = {0};
  size_t start = SIZE_MAX, end = SIZE_MAX;
  exr_status status = exr_document_open_memory(EXR_TXT, text, sizeof(text) - 1,
                                               &document, &error);
  if (status == EXR_OK)
    status = exr_document_find(document, "word", 0, &start, &end, &error);
  if (status == EXR_OK) {
    if (start != SIZE_MAX) printf("UTF-8 byte range [%zu, %zu)\n", start, end);
    else puts("No match");
  } else fprintf(stderr, "%s\n", error.message);
  exr_document_free(document);
  return status == EXR_OK ? 0 : 1;
}
