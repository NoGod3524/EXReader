/* SPDX-License-Identifier: MIT */
#include "opds_sdk.h"
#include "exreader.h"
#include <stdio.h>
#include <string.h>

opds_status opds_sdk_read_title(const char *path, char *title, size_t cap, size_t *parts_out,
                                char *detail, size_t detail_cap) {
  exr_publication *pub = NULL;
  exr_document *doc = NULL;
  exr_error error;
  size_t parts = 0, text_size = 0;
  const char *t;
  opds_status result = OPDS_UNREADABLE;
  memset(&error, 0, sizeof error);
  if (exr_publication_open(path, &pub, &error) != EXR_OK) {
    snprintf(detail, detail_cap, "SDK open failed: %s", error.message);
    return OPDS_UNREADABLE;
  }
  (void)exr_publication_parts(pub, &parts);
  if (!parts) { snprintf(detail, detail_cap, "publication has no readable parts"); goto done; }
  if (exr_publication_load(pub, 0, &doc, &error) != EXR_OK) {
    snprintf(detail, detail_cap, "SDK load failed: %s", error.message);
    goto done;
  }
  (void)exr_document_text(doc, &text_size);
  t = exr_publication_title(pub);
  snprintf(title, cap, "%s", t ? t : "");
  if (parts_out) *parts_out = parts;
  snprintf(detail, detail_cap, "parts=%zu first_part_text_bytes=%zu", parts, text_size);
  result = OPDS_OK;
done:
  exr_document_free(doc);
  exr_publication_free(pub);
  return result;
}

opds_status opds_sdk_verify(void *context, const char *path, const char *media_type, char *detail, size_t cap) {
  char title[256];
  (void)context;
  if (media_type && !strcmp(media_type, "application/epub+zip"))
    return opds_sdk_read_title(path, title, sizeof title, NULL, detail, cap);
  snprintf(detail, cap, "no SDK verification offered for %s", media_type && *media_type ? media_type : "unknown type");
  return OPDS_UNSUPPORTED;
}
