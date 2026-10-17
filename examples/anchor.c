/* SPDX-License-Identifier: GPL-3.0-only */
#include <exreader.h>
#include <stdio.h>
#include <string.h>

int main(void) {
  const char before[] = "A chapter begins. Keep this sentence. The chapter ends.";
  const char after[] = "An inserted preface. A chapter begins. Keep this sentence. The chapter ends.";
  const char quote[] = "Keep this sentence.";
  exr_document *doc = NULL;
  exr_anchor anchor = {0};
  exr_text_annotation input={0},received={0};
  char *json=NULL; size_t json_size=0;
  exr_anchor_match match;
  exr_error error = {0};
  exr_status status;
  size_t start = (size_t)(strstr(before, quote) - before);
  status = exr_document_open_memory(EXR_TXT, before, sizeof(before) - 1, &doc, &error);
  if (status == EXR_OK)
    status = exr_anchor_create(doc, start, start + sizeof(quote) - 1, &anchor, &error);
  input.id="urn:example:annotation"; input.source="urn:example:chapter";
  input.text="A comment that travels with the quote"; input.anchor=anchor;
  if(status==EXR_OK) status=exr_text_annotation_export(&input,&json,&json_size,&error);
  if(status==EXR_OK) status=exr_text_annotation_import(json,json_size,&received,&error);
  exr_document_free(doc);
  doc = NULL;
  if (status == EXR_OK)
    status = exr_document_open_memory(EXR_TXT, after, sizeof(after) - 1, &doc, &error);
  if (status == EXR_OK)
    status = exr_anchor_resolve(doc, &received.anchor, &match, &error);
  if (status == EXR_OK &&
      (match.state != EXR_ANCHOR_FOUND || match.start != (size_t)(strstr(after, quote) - after))) {
    fprintf(stderr, "Could not uniquely relocate the saved annotation\n");
    status = EXR_FORMAT;
  }
  if (status == EXR_OK)
    printf("EXReader C %s: annotation moved from %zu to %zu\n", exr_version(), start, match.start);
  else
    fprintf(stderr, "%s\n", error.message);
  exr_document_free(doc);
  exr_anchor_free(&anchor);
  exr_text_annotation_free(&received); exr_free(json);
  return status == EXR_OK ? 0 : 1;
}
