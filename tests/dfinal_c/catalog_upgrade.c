/* SPDX-License-Identifier: MIT */
#include "catalog.h"
#include <stdio.h>
#include <string.h>

static int receive(void *context, const reader_catalog_row *row) {
  int *seen = context;
  if (strcmp(row->title, "Legacy user title") || strcmp(row->author, "Saved author") ||
      row->sdk_book_id != 42 || row->source_bytes != 23 || row->favorite != 1 || row->deleted)
    return 1;
  ++*seen;
  return 0;
}

int main(int argc, char **argv) {
  static const char key[] = "txt:0000000000000000000000000000000000000000000000000000000000000001";
  reader_catalog *catalog = NULL;
  reader_catalog_error error;
  int found = 0, seen = 0, present = 0, status;
  if (argc != 3) return 2;
  status = reader_catalog_open(argv[1], &catalog, &error);
  if (!strcmp(argv[2], "reject")) {
    if (!status || catalog) return 3;
    printf("native catalog rejected fixture: code=%d message=%s\n", status, error.message);
    return 0;
  }
  if (status) { fprintf(stderr, "catalog open: %s\n", error.message); return 4; }
  if (reader_catalog_has_local(catalog, 42, &present, &error) || !present ||
      reader_catalog_metadata(catalog, key, receive, &seen, &found, &error) || !found || seen != 1)
    return 5;
  if (reader_catalog_close(&catalog, &error) || catalog) return 6;
  puts("native catalog opened: retained metadata and SDK mapping read through public API");
  return 0;
}
