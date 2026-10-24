/* SPDX-License-Identifier: MIT */
#ifndef READER_CATALOG_H
#define READER_CATALOG_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

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
  const char *author;
  int deleted; /* Populated by metadata lookup; shelf queries remain active only. */
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
/* direction +1: ascending rows after cursor; -1: descending rows before it.
 * Both cursor strings NULL starts at that end. Search is a literal substring
 * of title/author (SQLite ASCII case-insensitive; Unicode bytes otherwise exact).
 * NULL or empty query selects all. Limit remains 1..200, including filtered rows.
 * Reverse pages are delivered in descending order; the host reverses them for
 * an ascending UI. No OFFSET or unbounded row materialization is used. */
int reader_catalog_query_page(reader_catalog *, const char *cursor_title, const char *cursor_key,
                              const char *query, int direction, size_t limit,
                              reader_catalog_visit, void *, reader_catalog_error *);
/* Find a stable visible key under the current filter before restoring a viewport.
 * Calls visit at most once; sets found=0 if deleted, missing or filtered out. */
int reader_catalog_find(reader_catalog *, const char *book_key, const char *query,
                        reader_catalog_visit, void *, int *found, reader_catalog_error *);
/* Same bounded keyset implementation, restricted to local mappings. The host
 * supplies NFC and NFD query forms; sort_title uses NFC and author uses both.
 * inclusive applies only to the ascending restore cursor. Limit stays 1..200. */
int reader_catalog_local_canonical_page(reader_catalog *,const char *cursor_title,const char *cursor_key,
  const char *nfc,const char *nfd,int direction,int inclusive,size_t limit,
  reader_catalog_visit,void *,reader_catalog_error *);
/* At most one active mapped row. sdk_id>0 selects that ID (title must be NULL),
 * otherwise exact_title is required. No unbounded host-side scans. */
int reader_catalog_local_lookup(reader_catalog *,int64_t sdk_id,const char *exact_title,
  reader_catalog_visit,void *,int *found,reader_catalog_error *);
/* Current product fields including soft deletion, without requiring local map.
 * Used only after the host has verified the public SDK retained original. */
int reader_catalog_metadata(reader_catalog *,const char *book_key,
  reader_catalog_visit,void *,int *found,reader_catalog_error *);
const char *reader_catalog_migration(size_t *bytes);
#ifdef __cplusplus
}
#endif
#endif
