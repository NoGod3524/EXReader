/* SPDX-License-Identifier: MIT */
#ifndef READER_DESKTOP_METADATA_H
#define READER_DESKTOP_METADATA_H
#include <reader_commands.h>
#ifdef __cplusplus
extern "C" {
#endif
#ifdef EXR_READER_METADATA_RAW3
#define READER_METADATA_VERSION "0.2.0"
#else
#define READER_METADATA_VERSION "0.1.0"
#endif
#define READER_METADATA_PENDING_MAX_BYTES ((size_t)131072)
typedef struct reader_metadata_owner reader_metadata_owner;
typedef struct reader_metadata_snapshot reader_metadata_snapshot;
typedef enum { READER_METADATA_OK=0, READER_METADATA_NO_PENDING,
  READER_METADATA_NEEDS_BOOTSTRAP, READER_METADATA_CONFLICT,
  READER_METADATA_PENDING, READER_METADATA_IO, READER_METADATA_ARGUMENT,
  READER_METADATA_OWNER, READER_METADATA_REVISION,
  READER_METADATA_COMMITTED_PENDING_CLEAR } reader_metadata_status;
typedef enum { READER_METADATA_BOOK=0, READER_METADATA_GROUP,
  READER_METADATA_MEMBERSHIP } reader_metadata_entity;
typedef struct {
  reader_metadata_status code;
  reader_command_error command;
  char message[160];
} reader_metadata_error;
typedef struct {
  reader_command_result command;
  int committed, pending;
} reader_metadata_result;
typedef struct {
  reader_metadata_entity entity;
  const char *entity_key;
  int present, deleted, needs_bootstrap, dependency_deleted;
  reader_revision_state graph;
  const char *const *heads;
  size_t head_count;
  reader_book_command book;
  reader_group_command group;
  reader_membership_command membership;
} reader_metadata_view;
typedef struct {
  const char *format, *source_sha256;
  uint64_t source_bytes;
} reader_metadata_verified_source;
/* Product schema1 only. The creating host worker owns both native handles;
 * open/calls/close cannot cross threads or reenter. A lifetime sidecar lock
 * excludes another metadata owner. No SDK handle or local book ID is accepted.
 * pending_path is a private file in the existing host profile directory. */
reader_metadata_status reader_metadata_open(const char *product_path,const char *pending_path,
  reader_metadata_owner **,reader_metadata_error *);
#ifdef EXR_READER_METADATA_RAW3
/* Opt-in package only. Opens the matching raw-capability revision/command
 * family. Typed metadata and private pending bytes keep their original schema;
 * metadata operations do not produce or reinterpret reading selectors. */
reader_metadata_status reader_metadata_open_raw_v3(const char *product_path,const char *pending_path,
  reader_metadata_owner **,reader_metadata_error *);
#endif
reader_metadata_status reader_metadata_close(reader_metadata_owner **,reader_metadata_error *);
/* Preparation copies metadata and the COMPLETE observed head set. A conflict
 * or NEEDS_BOOTSTRAP may also return a snapshot, for explicit host presentation.
 * No automatic conflict resolution or original-source verification occurs. */
reader_metadata_status reader_metadata_prepare_book(reader_metadata_owner *,const char *book_key,
  reader_metadata_snapshot **,reader_metadata_error *);
reader_metadata_status reader_metadata_prepare_group(reader_metadata_owner *,reader_group_kind,
  const char *id,reader_metadata_snapshot **,reader_metadata_error *);
reader_metadata_status reader_metadata_prepare_membership(reader_metadata_owner *,reader_group_kind,
  const char *group_id,const char *book_key,reader_metadata_snapshot **,reader_metadata_error *);
const reader_metadata_view *reader_metadata_snapshot_view(reader_metadata_snapshot *);
void reader_metadata_snapshot_free(reader_metadata_snapshot *);
/* A single immutable pending intent; staging never changes product metadata.
 * IDs, original expected heads and ALL typed fields are durably stored before
 * any producer runs. Staging refuses to replace an existing pending intent.
 * Input identity must match the prepared snapshot. New groups use an empty ID.
 * The host supplies strict UTF-8 (reader_command_utf16 at Windows boundaries).
 * An existing verified book history is required for ordinary book edits. */
reader_metadata_status reader_metadata_stage_book(reader_metadata_owner *,const reader_metadata_snapshot *,
  const reader_book_command *,reader_metadata_result *,reader_metadata_error *);
/* Explicit user resolution only: all complete concurrent heads are retained as
 * parents of a new typed book revision. Ordinary staging remains conflict-safe.
 * A later changed head set is still rejected atomically by finish_pending. */
reader_metadata_status reader_metadata_stage_book_resolution(reader_metadata_owner *,const reader_metadata_snapshot *,
  const reader_book_command *,reader_metadata_result *,reader_metadata_error *);
reader_metadata_status reader_metadata_stage_group(reader_metadata_owner *,const reader_metadata_snapshot *,
  const reader_group_command *,reader_metadata_result *,reader_metadata_error *);
reader_metadata_status reader_metadata_stage_membership(reader_metadata_owner *,const reader_metadata_snapshot *,
  const reader_membership_command *,reader_metadata_result *,reader_metadata_error *);
/* Explicit legacy bootstrap: the host first verifies exact original bytes via
 * the public SDK. This command preserves the snapshot's product title, author,
 * favorite and NFC sort title rather than importing stale SDK metadata. */
reader_metadata_status reader_metadata_stage_bootstrap(reader_metadata_owner *,const reader_metadata_snapshot *,
  const reader_metadata_verified_source *,reader_metadata_result *,reader_metadata_error *);
/* apply keeps the durable intent after commit, including exact old-ID no-ops.
 * finish first applies/verifies that SAME intent, then removes the sidecar.
 * A crash between commit and finish is safe: reopen and replay unchanged.
 * A failed cleanup reports COMMITTED_PENDING_CLEAR with committed=1.
 * There is no cancellation result after a committed product transaction. */
reader_metadata_status reader_metadata_apply_pending(reader_metadata_owner *,reader_metadata_result *,reader_metadata_error *);
reader_metadata_status reader_metadata_finish_pending(reader_metadata_owner *,reader_metadata_result *,reader_metadata_error *);
/* Inspect assigned IDs without submitting. Abandon only an intent whose ID
 * has no retained revision; a committed intent must be replayed/finished. */
reader_metadata_status reader_metadata_pending(reader_metadata_owner *,reader_metadata_result *,reader_metadata_error *);
reader_metadata_status reader_metadata_abandon_pending(reader_metadata_owner *,reader_metadata_error *);
#ifdef __cplusplus
}
#endif
#endif
