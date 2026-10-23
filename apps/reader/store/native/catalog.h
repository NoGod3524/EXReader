/* SPDX-License-Identifier: MIT */
#ifndef READER_CATALOG_H
#define READER_CATALOG_H
#include <stddef.h>
#include <stdint.h>

/* Product metadata, independent of the SDK database and ABI. All calls use
 * the creating host worker. UTF-8 paths/text; return zero on success. */
typedef struct reader_catalog reader_catalog;
typedef struct { int code; char message[256]; } reader_catalog_error;
typedef struct {
  const char *format, *sha256, *title, *author, *sort_title, *location_kind;
  uint64_t source_bytes;
  int64_t sdk_book_id;
  int favorite;
} reader_catalog_book;
typedef struct {
  const char *book_key, *title, *format, *sort_title, *location_kind;
  uint64_t source_bytes;
  int64_t sdk_book_id; /* Zero if no local SDK mapping exists. */
  int favorite;
} reader_catalog_row;
/* Row strings are borrowed for this call only. Copy them before returning.
 * Return nonzero to stop delivery. No reentry on this catalog. */
typedef int (*reader_catalog_visit)(void *, const reader_catalog_row *);

int reader_catalog_open(const char *path, reader_catalog **out, reader_catalog_error *error);
int reader_catalog_close(reader_catalog **catalog, reader_catalog_error *error);
/* The host verifies the original SDK bytes before attach and supplies NFC
 * sort_title. Attach preserves existing metadata/history and selects the
 * lowest historical SDK ID for duplicates, together with its real mode. */
int reader_catalog_attach(reader_catalog *, const reader_catalog_book *, reader_catalog_error *);
int reader_catalog_has_local(reader_catalog *, int64_t id, int *present, reader_catalog_error *);
int reader_catalog_remove_local(reader_catalog *, int64_t id, reader_catalog_error *);
/* Both cursor strings NULL selects the first page. Otherwise use the last
 * delivered (sort_title, book_key). Limit is 1..200. Deleted books stay hidden. */
int reader_catalog_page(reader_catalog *, const char *after_title, const char *after_key,
                        size_t limit, reader_catalog_visit, void *, reader_catalog_error *);
const char *reader_catalog_migration(size_t *bytes);
#endif
