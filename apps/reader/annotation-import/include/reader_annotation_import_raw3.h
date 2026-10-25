/* SPDX-License-Identifier: MIT */
#ifndef READER_ANNOTATION_IMPORT_RAW3_H
#define READER_ANNOTATION_IMPORT_RAW3_H
#include <reader_annotation_import.h>
#include <reader_reading_state.h>
#ifdef __cplusplus
extern "C" {
#endif
#ifndef EXR_READER_SELECTOR_BYTES_CANDIDATE
#error "reader_annotation_import_raw3.h is the explicit raw0.2 family; build with EXR_READER_SELECTOR_BYTES_CANDIDATE"
#endif
#define READER_ANNOTATION_IMPORT_RAW3_VERSION "0.2.0"
#define READER_ANNOTATION_IMPORT_RAW3_FORMAT "exreader-annotation-export-raw3"

/* Explicit raw3 portable import (docs/reader-next-c06/RAW3-PORTABLE-ANNOTATIONS.md).
   Accepts only the exreader-annotation-export-raw3 format 1 file written by
   reader_annotation_export_raw3_run into a reader_revisions_open_raw_v3 store.
   The legacy importer and this one refuse each other's files and stores.

   PREVIEW is read-only: the whole file is copied once into a private anonymous
   spool and completely validated (format, hashes, wire identity, independently
   decoded location, original identity, public FOUND callback, collisions)
   without any write. COMMIT requires confirm_fingerprint == the preview's
   stats.fingerprint, re-validates the same way, and only then replays the spool
   with one public reader_revision_receive_raw_v3 per head (each its own
   transaction; cancellation or a rejected item keeps earlier commits and reports
   next_index). A validation failure, cancellation or UNRESOLVED/UNCONFIRMED
   result happens before the first receive and writes nothing.

   No ancestor is invented: only exported heads are received, keeping their IDs
   and parent IDs; the real receiving graph is reported and omitted_history
   counts source revisions that the heads-only file cannot carry. A repeated
   import is an exact duplicate (no second history row, no outbox).
   complete_product_accepted is always 0.

   FOUND: every non-delete head whose exact selector is not NULL is passed to
   resolve(); it must return 1 only for a real public SDK FOUND (reader_rs_resolve_*
   ; old offsets never break ambiguity). A typed NULL record is preserved but never
   navigable, so it is not passed to resolve(). With RESOLVE_REQUIRED a missing
   callback is ARGUMENT; RESOLVE_ALREADY_VERIFIED is the host's explicit statement
   that it verified separately: stats.found_checked stays 0.

   Borrowed store, options and strings live through the call. Run on the store
   owner worker, no reentry (refused with ARGUMENT, stats untouched). Callbacks run
   on that worker and must not call this importer or mutate/close the store. */
typedef enum {READER_AI3_PREVIEW=1,READER_AI3_COMMIT=2} reader_ai3_mode;
typedef enum {READER_AI3_RESOLVE_REQUIRED=0,READER_AI3_RESOLVE_ALREADY_VERIFIED=1} reader_ai3_resolve_policy;
typedef enum {
  READER_AI3_OK=0, READER_AI3_ARGUMENT, READER_AI3_MEMORY, READER_AI3_IO, READER_AI3_FORMAT, READER_AI3_LIMIT,
  READER_AI3_REVISION,   /* public revision API refused (also: wrong legacy/raw store, hash, collision) */
  READER_AI3_CANCELLED, READER_AI3_CALLBACK,
  READER_AI3_IDENTITY,   /* book key / original byte length differs from the target store */
  READER_AI3_UNRESOLVED, /* at least one head is not a public FOUND; nothing was written */
  READER_AI3_UNCONFIRMED /* commit without the matching preview fingerprint; nothing was written */
} reader_ai3_status;
typedef enum {
  READER_AI3_NEW=0, READER_AI3_EXACT_DUPLICATE, READER_AI3_CONFLICT, READER_AI3_MISSING_PARENT,
  READER_AI3_BLOCKED_RESTORE, READER_AI3_REJECTED
} reader_ai3_outcome;
typedef enum {
  READER_AI3_FOUND_NOT_NEEDED=0,   /* delete head */
  READER_AI3_FOUND_YES,            /* host resolve() returned 1 */
  READER_AI3_FOUND_NO,             /* host resolve() did not return 1 */
  READER_AI3_FOUND_NULL_PRESERVED, /* typed NULL exact: kept, never navigable */
  READER_AI3_FOUND_NOT_CHECKED     /* RESOLVE_ALREADY_VERIFIED */
} reader_ai3_found;
typedef struct {
  uint64_t index;
  reader_revision_info info;
  reader_revision_state graph;       /* receiving graph; zero in PREVIEW */
  reader_ai3_outcome outcome;        /* PREVIEW: NEW or EXACT_DUPLICATE (what a commit would do) */
  reader_ai3_found found;
  int committed, created, exact_duplicate, revision_code;
} reader_ai3_item;
typedef int (*reader_ai3_cancel_fn)(void *);
typedef int (*reader_ai3_item_fn)(void *,const reader_ai3_item *);
/* Borrowed record (decoded by reader_rs_decode_raw_v3). Return 1 only for a public FOUND. */
typedef int (*reader_ai3_resolve_fn)(void *,const reader_rs_record *,uint64_t index);
typedef struct {
  size_t struct_size;
  reader_revisions *revisions;       /* raw v3 store */
  const char *jsonl_path;
  const char *target_book_key;       /* host confirmed original format:sha256 */
  reader_ai3_mode mode;
  uint64_t max_input_bytes;          /* 0 = 16 MiB; hard 64 MiB */
  uint64_t confirm_fingerprint;      /* COMMIT: stats.fingerprint of the preview */
  uint64_t resume_index;             /* COMMIT: flattened head ordinal, default 0 */
  reader_ai3_resolve_policy policy;
  reader_ai3_resolve_fn resolve;
  reader_ai3_cancel_fn cancel;
  reader_ai3_item_fn item;
  void *context;
} reader_ai3_options;
typedef struct {
  uint64_t input_bytes, annotations, head_wires, omitted_history;
  uint64_t found, unresolved, null_preserved, would_create, would_duplicate;
  uint64_t created, duplicates, committed, next_index;
  uint64_t source_bytes, fingerprint;
  int validated, found_checked, complete_product_accepted;
} reader_ai3_stats;
typedef struct {
  reader_ai3_status code;
  int revision_code, rs_code, os_error;
  uint64_t line, item_index;
  char message[160];
} reader_ai3_error;
reader_ai3_status reader_annotation_import_raw3_run(const reader_ai3_options *,reader_ai3_stats *,reader_ai3_error *);
#ifdef __cplusplus
}
#endif
#endif
