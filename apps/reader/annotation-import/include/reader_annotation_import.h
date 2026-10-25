/* SPDX-License-Identifier: MIT */
#ifndef READER_ANNOTATION_IMPORT_H
#define READER_ANNOTATION_IMPORT_H
#include <reader_revisions.h>
#ifdef __cplusplus
extern "C" {
#endif
#define READER_ANNOTATION_IMPORT_VERSION "0.1.0"
#define READER_ANNOTATION_IMPORT_DEFAULT_MAX_BYTES ((uint64_t)16u<<20)
#define READER_ANNOTATION_IMPORT_HARD_MAX_BYTES ((uint64_t)64u<<20)
#define READER_ANNOTATION_IMPORT_MAX_ITEMS 65536u
/* Only unchanged G05 0.1.0 JSONL v1, including its field order. No Markdown,
   book parser, SQL, projection, clock selection, SDK notes or progress writes.
   All bytes are copied from ONE regular-file handle into a private anonymous
   spool, bounded before validation. The spool is completely validated before
   ANY receive, then replayed without reopening the source. Memory holds one
   wire (<= public 1 MiB limit) plus <=65536 32-byte revision IDs.

   Every receive is its own public revision transaction. Cancellation never
   rolls back earlier commits. Retry the same file from zero (exact duplicates
   do not requeue history/outbox), or use next_index with the SAME input/store.
   resume_index does not authenticate another file: host must retain its input.
   Returned stats describe this invocation, not earlier calls. A rejected file
   has validated=0, next_index=0 and no item callbacks/commits.

   G05 exports HEADS ONLY: non-head ancestor wires cannot be recovered. Import
   preserves exact heads, IDs, parent IDs and payload, and reports the REAL
   receiving graph. It never recreates a missing ancestor or imports advisory
   book_title/graph counters as new entities. omitted_history reports this gap;
   complete_product_accepted is ALWAYS zero. Host UI is outside this package.

   Borrowed store, options and UTF-8 strings live through run. Run on the store
   owner worker, no concurrent close and no reentry. Callbacks execute on that
   worker outside revision callbacks; do not call this importer or mutate/close
   its store. Exceptions from host callbacks are caught as CALLBACK failures.
   A refused reentry leaves stats untouched. No exceptions cross the C ABI. */
typedef enum {
  READER_AI_OK=0, READER_AI_ARGUMENT, READER_AI_MEMORY, READER_AI_IO,
  READER_AI_FORMAT, READER_AI_LIMIT, READER_AI_REVISION, READER_AI_CANCELLED,
  READER_AI_CALLBACK
} reader_annotation_import_status;
typedef enum {
  READER_AI_NEW=0, READER_AI_EXACT_DUPLICATE, READER_AI_CONFLICT,
  READER_AI_MISSING_PARENT, READER_AI_BLOCKED_RESTORE, READER_AI_REJECTED
} reader_annotation_import_outcome;
typedef struct {
  uint64_t index;
  reader_revision_info info;
  reader_revision_state graph;
  reader_annotation_import_outcome outcome;
  int committed, created, exact_duplicate, revision_code;
} reader_annotation_import_item;
typedef int (*reader_annotation_import_cancel_fn)(void *);
/* Nonzero stops AFTER this item. Item and strings are borrowed until return. */
typedef int (*reader_annotation_import_item_fn)(void *,const reader_annotation_import_item *);
/* Advisory exporter fields are delivered intact, NEVER written as invented
   entities. annotation_id==NULL is the header (book_title may be NULL); other
   records expose the original source graph/selection, not receiving state.
   Called only after whole-file preflight; nonzero cancels before that record. */
typedef struct {
  const char *book_title, *annotation_id, *entity_key, *selection;
  reader_revision_state graph;
  int tombstone;
} reader_annotation_import_metadata;
typedef int (*reader_annotation_import_metadata_fn)(void *,const reader_annotation_import_metadata *);
typedef struct {
  size_t struct_size;
  reader_revisions *revisions;
  const char *jsonl_path;
  const char *target_book_key; /* host confirmed original format:sha256, NOT SDK ID */
  uint64_t max_input_bytes;    /* 0=16 MiB; hard64 MiB */
  uint64_t resume_index;       /* flattened head ordinal, default0 */
  reader_annotation_import_cancel_fn cancel;
  reader_annotation_import_item_fn item;
  reader_annotation_import_metadata_fn metadata;
  void *context;
} reader_annotation_import_options;
typedef struct {
  uint64_t input_bytes, annotations, head_wires, omitted_history;
  uint64_t created, duplicates, committed, next_index;
  int validated, complete_product_accepted;
} reader_annotation_import_stats;
typedef struct {
  reader_annotation_import_status code;
  int revision_code, os_error;
  uint64_t line, item_index;
  char message[160];
} reader_annotation_import_error;
reader_annotation_import_status reader_annotation_import_run(const reader_annotation_import_options *,
  reader_annotation_import_stats *,reader_annotation_import_error *);
#ifdef __cplusplus
}
#endif
#endif
