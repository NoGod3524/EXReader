/* SPDX-License-Identifier: MIT */
#ifndef READER_REVISIONS_H
#define READER_REVISIONS_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
#define READER_REVISIONS_VERSION "0.2.0"
#define READER_REVISION_MAX_BYTES ((size_t)1048576)
#define READER_REVISION_MAX_PARENTS ((size_t)32)
#define READER_REVISION_MAX_ENTITY_HISTORY ((size_t)4096)
typedef enum {
  READER_REV_OK=0, READER_REV_ARGUMENT, READER_REV_MEMORY, READER_REV_DATABASE,
  READER_REV_FORMAT, READER_REV_LIMIT, READER_REV_HASH, READER_REV_COLLISION,
  READER_REV_MISSING_PARENT, READER_REV_CYCLE, READER_REV_UNSAFE,
  READER_REV_OWNER, READER_REV_NOT_FOUND
} reader_revision_status;
typedef struct { reader_revision_status code; int sqlite_code; char message[160]; } reader_revision_error;
typedef struct reader_revisions reader_revisions;
typedef struct {
  char revision_id[33], entity_kind[16], entity_key[257], operation[8], location_kind[16], sha256[65];
  size_t bytes, parent_count;
  char book_key[73]; /* Empty for shelf/tag/series; global original identity otherwise. */
  uint64_t source_bytes; /* Known only on a non-delete book revision, never inferred as zero. */
} reader_revision_info;
typedef struct {
  size_t revisions, heads, missing_parents, foreign_parents;
  int projection_safe, deleted, requires_restore;
} reader_revision_state;
typedef struct {
  char revision_id[33], operation[8], sha256[65];
  int complete, requires_restore;
} reader_revision_head;
typedef struct {
  reader_revision_info info;
  const char *wire; /* Borrowed during callback; exact original UTF-8 bytes. */
  int64_t queue_id, attempts;
  const char *last_error; /* Fixed module status token, never a supplied URL/secret. */
} reader_revision_outbox_row;
typedef int (*reader_revision_head_fn)(void *,const reader_revision_head *);
typedef int (*reader_revision_outbox_fn)(void *,const reader_revision_outbox_row *);
/* One existing product schema1 catalog; this is never the SDK library.
   Calls and close use the creating host worker, without callback reentry.
   An empty database is initialized with the unchanged product migration.
   The module uses one already-installed product SQLite, not a system fallback. */
reader_revision_status reader_revisions_open(const char *utf8_path,reader_revisions **,reader_revision_error *);
reader_revision_status reader_revisions_close(reader_revisions **,reader_revision_error *);
reader_revision_status reader_revision_new_id(char out[33],reader_revision_error *);
/* v1 strict JSON, at most 1 MiB/32 parents/32 levels/20000 values. Optional
   expected_sha256 verifies exact transport bytes; output never canonicalizes.
   Duplicate keys, malformed UTF-8, unknown fields and SDK-local IDs are refused. */
reader_revision_status reader_revision_validate(reader_revisions *,const void *,size_t,
  const char *expected_sha256,reader_revision_info *,reader_revision_error *);
/* Local history+outbox is one transaction. No projection/SDK write occurs.
   Local parents must already exist and belong to the entity. Remote missing
   parents are retained and recomputed when their revisions later arrive.
   Exact same ID/bytes is a no-op, including after ack/remote receive; it does
   not requeue. Same ID/different bytes is COLLISION. Never chooses by clock.
   created is set only after commit; all failed commits leave it zero. */
reader_revision_status reader_revision_local(reader_revisions *,const void *,size_t,
  reader_revision_info *,int *created,reader_revision_error *);
reader_revision_status reader_revision_receive(reader_revisions *,const void *,size_t,
  const char *expected_sha256,reader_revision_info *,int *created,reader_revision_error *);
/* Copies exact retained bytes after revalidating columns/hash. Release with
   reader_revision_bytes_free. */
reader_revision_status reader_revision_get(reader_revisions *,const char *revision_id,
  char **wire,size_t *bytes,reader_revision_info *,reader_revision_error *);
void reader_revision_bytes_free(void *);
/* Complete graph, bounded to 4096 revisions per entity; no history pruning.
   Every concurrent head remains visible. Missing/foreign parents, an implicit
   put after delete, or restore without a directly named delete block automatic
   projection. A safe unique complete head does not authorize SDK navigation:
   its selector still requires the existing public resolve result FOUND. */
reader_revision_status reader_revision_heads(reader_revisions *,const char *entity_kind,
  const char *entity_key,reader_revision_head_fn,void *,reader_revision_state *,reader_revision_error *);
/* Revalidates retained book history and returns its immutable original byte
   length. Missing non-delete metadata is NOT_FOUND; conflicts are refused. */
reader_revision_status reader_revision_book_identity(reader_revisions *,const char *book_key,
  uint64_t *source_bytes,reader_revision_error *);
/* Read first 1..100 pending entries, not a persistent monotonic queue cursor.
   Copy rows before calling ack/retry; callback reentry is rejected. */
reader_revision_status reader_revision_outbox(reader_revisions *,size_t limit,
  reader_revision_outbox_fn,void *,reader_revision_error *);
reader_revision_status reader_revision_retry(reader_revisions *,const char *revision_id,
  reader_revision_status redacted_reason,reader_revision_error *);
/* Host calls only after remote byte/hash verification. Ack compares the
   retained SHA, removes only the outbox row, and never deletes history. */
reader_revision_status reader_revision_ack(reader_revisions *,const char *revision_id,
  const char *expected_sha256,reader_revision_error *);
#ifdef __cplusplus
}
#endif
#endif
