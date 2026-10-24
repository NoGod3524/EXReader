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
/* Same keyset contract restricted to rows with a local SDK mapping. Hosts that
 * show downloaded books use this; the global query still includes cloud-only metadata. */
int reader_catalog_local_page(reader_catalog *, const char *cursor_title, const char *cursor_key,
                              const char *query, int direction, size_t limit,
                              reader_catalog_visit, void *, reader_catalog_error *);
/* Find a stable visible key under the current filter before restoring a viewport.
 * Calls visit at most once; sets found=0 if deleted, missing or filtered out. */
int reader_catalog_find(reader_catalog *, const char *book_key, const char *query,
                        reader_catalog_visit, void *, int *found, reader_catalog_error *);

/* Read-only organization views. Mutations use the native typed command module.
 * These callbacks have the same borrowed-string/owner/no-reentry contract as books. */
typedef enum { READER_CATALOG_SHELF=0, READER_CATALOG_TAG, READER_CATALOG_SERIES } reader_catalog_group_kind;
typedef struct {
  const char *id, *name, *parent_id; /* parent_id NULL for roots, tags and series. */
  uint64_t ordinal; /* Zero for tags and series. */
  int deleted;
} reader_catalog_group_row;
typedef int (*reader_catalog_group_visit)(void *, const reader_catalog_group_row *);
typedef struct { uint64_t ordinal; const char *id; } reader_catalog_group_cursor;
typedef struct {
  const char *group_id, *book_key;
  uint64_t ordinal; /* Zero for tags. */
  int group_deleted, book_deleted;
} reader_catalog_membership_row;
typedef int (*reader_catalog_membership_visit)(void *, const reader_catalog_membership_row *);
typedef struct { reader_catalog_row book; uint64_t ordinal; } reader_catalog_group_book_row;
typedef int (*reader_catalog_group_book_visit)(void *, const reader_catalog_group_book_row *);
typedef struct { uint64_t ordinal; const char *book_key; } reader_catalog_member_cursor;

/* Finds include deleted group/book metadata for explicit restore/conflict UI.
 * Missing memberships have found=0; retained tombstone heads live in revisions.
 * No side effects, and no implicit choice of a revision head. */
int reader_catalog_group_find(reader_catalog *, reader_catalog_group_kind, const char *id,
  reader_catalog_group_visit, void *, int *found, reader_catalog_error *);
int reader_catalog_membership_find(reader_catalog *, reader_catalog_group_kind, const char *group_id,
  const char *book_key, reader_catalog_membership_visit, void *, int *found, reader_catalog_error *);
/* Visible sibling shelves ordered by (ordinal,id); NULL parent selects roots.
 * Tags/series require NULL parent and use ID order. NULL cursor starts at the
 * requested end; direction is +1/-1, limit 1..200, no OFFSET. */
int reader_catalog_groups_page(reader_catalog *, reader_catalog_group_kind, const char *parent_id,
  const reader_catalog_group_cursor *, int direction, size_t limit,
  reader_catalog_group_visit, void *, reader_catalog_error *);
/* Deleted groups across all hierarchy levels, ordered only by ID. A NULL
 * cursor starts at an end; direction +1/-1, limit 1..200. Returned parent and
 * ordinal remain available for explicit restore; no parent is restored here. */
int reader_catalog_removed_groups_page(reader_catalog *, reader_catalog_group_kind,
  const char *cursor_id, int direction, size_t limit,
  reader_catalog_group_visit, void *, reader_catalog_error *);
/* Active group members ordered by (ordinal,book_key), or book_key for tags.
 * local_only=1 selects downloaded books; 0 retains cloud-only metadata.
 * Title/author search remains a literal substring, with the existing UTF-8 rules.
 * A NULL cursor starts at an end; tags require cursor.ordinal=0. Limit 1..200. */
int reader_catalog_group_books_page(reader_catalog *, reader_catalog_group_kind, const char *group_id,
  const reader_catalog_member_cursor *, const char *query, int local_only, int direction, size_t limit,
  reader_catalog_group_book_visit, void *, reader_catalog_error *);
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
