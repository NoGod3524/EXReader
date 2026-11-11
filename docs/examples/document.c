/* SPDX-License-Identifier: MIT */
#include <exr/document.h>
#include <stdio.h>

int main(void) {
  const exr_node_input nodes[] = {
    {EXR_NODE_DOCUMENT, SIZE_MAX, NULL, NULL, NULL, 0},
    {EXR_NODE_CHAPTER, 0, NULL, NULL, NULL, 0},
    {EXR_NODE_PARAGRAPH, 1, NULL, NULL, NULL, 0},
    {EXR_NODE_TEXT, 2, NULL, "Hello reader.", NULL, 0}
  };
  const exr_chapter_input chapter = {"one", "one.txt", 1, 1};
  const exr_document_input input = {"Example", nodes, 4, &chapter, 1, NULL, 0};
  exr_document *document = NULL;
  exr_error error = {0};
  exr_status status = exr_document_create(&input, &document, &error);
  if (status == EXR_OK) {
    size_t size = 0;
    const char *text = exr_document_text(document, &size);
    fwrite(text, 1, size, stdout);
    putchar('\n');
  } else
    fprintf(stderr, "%s\n", error.message);
  exr_document_free(document);
  return status == EXR_OK ? 0 : 1;
}
