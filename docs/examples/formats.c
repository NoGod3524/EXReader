/* SPDX-License-Identifier: MIT */
#include <exr/formats.h>
#include <stdio.h>

int main(void) {
  const char html[] = "<html><body><h1>Chapter</h1><p>Hello.</p></body></html>";
  exr_document *document = NULL;
  exr_error error = {0};
  exr_status status = exr_document_open_memory(EXR_HTML, html, sizeof(html) - 1,
                                               &document, &error);
  if (status == EXR_OK)
    printf("format=%d\n", (int)exr_document_format(document));
  else
    fprintf(stderr, "%s\n", error.message);
  exr_document_free(document);
  return status == EXR_OK ? 0 : 1;
}
