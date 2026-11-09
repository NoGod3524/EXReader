/* SPDX-License-Identifier: MIT */
#include <exr/formats.h>
#include <stdio.h>

int main(void) {
  const char text[] = "Keep this sentence.";
  exr_document *document = NULL;
  exr_anchor anchor = {0};
  exr_text_annotation input = {0}, restored = {0};
  exr_anchor_match match = {0};
  char *json = NULL;
  size_t size = 0;
  exr_error error = {0};
  exr_status status = exr_document_open_memory(EXR_TXT, text, sizeof(text) - 1,
                                               &document, &error);
  if (status == EXR_OK)
    status = exr_anchor_create(document, 0, sizeof(text) - 1, &anchor, &error);
  input.id = "urn:example:note:1";
  input.source = "urn:example:book:1";
  input.text = "My comment";
  input.anchor = anchor; /* Borrowed shallow copy for export only. */
  if (status == EXR_OK) status = exr_text_annotation_export(&input, &json, &size, &error);
  if (status == EXR_OK) status = exr_text_annotation_import(json, size, &restored, &error);
  if (status == EXR_OK) status = exr_anchor_resolve(document, &restored.anchor, &match, &error);
  if (status == EXR_OK && match.state == EXR_ANCHOR_FOUND)
    printf("restored [%zu, %zu), JSON bytes=%zu\n", match.start, match.end, size);
  else {
    fprintf(stderr, "%s\n", status == EXR_OK ? "Anchor was not uniquely resolved" : error.message);
    if (status == EXR_OK) status = EXR_FORMAT;
  }
  exr_text_annotation_free(&restored);
  exr_free(json);
  exr_anchor_free(&anchor);
  exr_document_free(document);
  return status == EXR_OK ? 0 : 1;
}
