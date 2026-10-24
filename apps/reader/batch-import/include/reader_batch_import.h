/* SPDX-License-Identifier: MIT */
#ifndef READER_BATCH_IMPORT_H
#define READER_BATCH_IMPORT_H
#include <stddef.h>
#include <stdint.h>
#include <exr/library.h>
#include <exr_sideload.h>
#ifdef __cplusplus
extern "C" {
#endif

#define READER_BATCH_IMPORT_VERSION "0.1.0"
#define READER_BATCH_MAX_BATCH 100u
#define READER_BATCH_MAX_DEPTH 16u
#define READER_BATCH_MAX_DIRECTORIES 10000u
#define READER_BATCH_MAX_CANDIDATES 10000u
#define READER_BATCH_MAX_PATH_BYTES 32768u
#define READER_BATCH_MAX_PENDING_BYTES (8u * 1024u * 1024u)
#define READER_BATCH_DEFAULT_BATCH 32u
#define READER_BATCH_DEFAULT_DEPTH 8u
#define READER_BATCH_DEFAULT_DIRECTORIES 4096u
#define READER_BATCH_DEFAULT_CANDIDATES 4096u
#define READER_BATCH_DEFAULT_PATH_BYTES 4096u
#define READER_BATCH_DEFAULT_PENDING_BYTES (1u * 1024u * 1024u)

/* This package has two independent synchronous phases and creates no thread,
   watcher or resident task. Enumeration may run on an ordinary I/O worker.
   Import borrows one exr_library and must run serially on its SDK owner.
   Both phases observe the caller's exr_control cancellation callback between
   bounded units of work; neither callback may destroy an active object. */
typedef enum {
  READER_BATCH_OK = 0,
  READER_BATCH_CANCELLED,
  READER_BATCH_ARGUMENT,
  READER_BATCH_MEMORY,
  READER_BATCH_IO,
  READER_BATCH_ENCODING,
  READER_BATCH_INTERNAL
} reader_batch_status;

typedef struct {
  reader_batch_status code;
  /* Underlying public SDK/OS status when code reports a lower-level failure.
     EXR_OK when the batch status itself carries the only detail. */
  exr_status status_code;
  char message[192];
} reader_batch_error;

/* Recursive traversal is opt-in. A zero limit selects its default; a nonzero
   value may only lower the published hard maximum, and a larger value is
   rejected with READER_BATCH_ARGUMENT. max_depth is ignored (forced to zero)
   unless recursive is nonzero. max_pending_bytes bounds paths retained by the
   enumerator; the caller-owned batch is separately bounded by batch_size and
   max_path_bytes. */
typedef struct {
  size_t struct_size;
  /* UTF-8 directory selected by the user. Symbolic links/junctions at the
     root are rejected; the selected directory is canonicalized once. */
  const char *root;
  int recursive;
  size_t max_depth;
  size_t max_directories;
  size_t max_candidates;
  size_t max_path_bytes;
  size_t max_pending_bytes;
  size_t batch_size; /* 1..READER_BATCH_MAX_BATCH */
  exr_control control;
} reader_batch_scan_options;

/* One extension-filtered candidate. path/relative_path are owned by the
   candidate and released by reader_batch_candidates_free. format is only an
   extension hint; import validates the real bytes through EXReaderSideload.
   size_hint is the size observed during enumeration and is never trusted for
   import. relative_path uses '/' on every platform. */
typedef struct {
  size_t struct_size;
  char *path;
  size_t path_bytes;
  char *relative_path;
  size_t relative_bytes;
  exr_format format;
  uint64_t size_hint;
} reader_batch_candidate;

typedef struct reader_batch_enumerator reader_batch_enumerator;

void reader_batch_scan_options_init(reader_batch_scan_options *options);
/* Canonicalizes the root and retains only the directory stack, never the whole
   tree. Root/open failures are reported here; a directory removed or made
   unreadable after open ends the scan with truncated=1. */
reader_batch_status reader_batch_enumerate_open(const reader_batch_scan_options *options,
  reader_batch_enumerator **out, reader_batch_error *error);
/* Produces at most batch_size candidates. complete=1 only after a normal end
   with no bound or unreadable entry; truncated=1 means the scan stopped or
   omitted entries and must not be reported as a complete scan. If both flags
   are zero, call again. On error/cancel no partial batch is returned.
   Reader loops until complete || truncated. */
reader_batch_status reader_batch_enumerate_next(reader_batch_enumerator *enumerator,
  reader_batch_candidate **items, size_t *count, int *complete, int *truncated,
  reader_batch_error *error);
void reader_batch_enumerate_close(reader_batch_enumerator *enumerator);
void reader_batch_candidates_free(reader_batch_candidate *items, size_t count);

typedef struct {
  size_t struct_size;
  const char *path;  /* UTF-8; reopened and revalidated at import time */
  /* Optional UTF-8 title. NULL/empty lets the SDK use embedded metadata. */
  const char *title;
  exr_format format; /* extension candidate; the SDK still validates bytes */
} reader_batch_item;

typedef enum {
  READER_BATCH_ITEM_NOT_ATTEMPTED = 0,
  READER_BATCH_ITEM_IMPORTED,   /* committed new SDK row: created=1 */
  READER_BATCH_ITEM_DUPLICATE,  /* committed exact duplicate: created=0 */
  READER_BATCH_ITEM_FAILED,     /* not committed */
  READER_BATCH_ITEM_CANCELLED   /* not committed, or later batch work stopped */
} reader_batch_item_status;

typedef struct reader_batch_result {
  size_t struct_size;
  reader_batch_item_status status;
  /* Borrowed from the matching input item; valid while that array lives. */
  const char *path;
  exr_format format;
  int committed; /* 1 only after EXReaderSideload returned a committed result */
  int created;   /* 1 only for a new SDK row; 0 for an exact duplicate */
  int64_t book_id;
  exr_status status_code; /* staging/SDK detail for FAILED or CANCELLED */
  char message[192];
} reader_batch_result;

/* Called on the importing thread after the SDK import for that item returned
   and before the next item starts. It is never called while EXReaderSideload
   is running. result is borrowed and must not be retained. The callback must
   not call back into this batch or into the same library; product catalog
   mapping is the host's later transaction, not part of this module. */
typedef void (*reader_batch_result_callback)(void *context, size_t index,
  const reader_batch_result *result);

typedef struct {
  size_t struct_size;
  /* Existing app-private directory for one temporary stable file per item.
     Required. PDF and every other format are copied here before the SDK
     opens them, so a post-enumeration change cannot alter an in-flight read. */
  const char *staging_dir;
  /* Zero selects the format's 32 MiB reflow / 128 MiB streaming ceiling.
     Nonzero may only lower it. */
  uint64_t max_input_bytes;
  exr_control control;
  reader_batch_result_callback on_result;
  void *on_result_context;
} reader_batch_import_options;

void reader_batch_import_options_init(reader_batch_import_options *options);
/* Imports 1..READER_BATCH_MAX_BATCH items serially through the installed
   EXReaderSideload. Per-item failures do not abort later items. Cancellation
   prevents later uncommitted imports; every committed result is still
   returned. On return each results[i] is terminal except after an aggregate
   argument/memory error. Paths/titles are borrowed only for the call.
   Returns READER_BATCH_OK when every item reached a terminal result (some may
   be FAILED), or READER_BATCH_CANCELLED when later items were stopped. */
reader_batch_status reader_batch_import(exr_library *library,
  const reader_batch_item *items, size_t count,
  const reader_batch_import_options *options,
  reader_batch_result **results, size_t *result_count, reader_batch_error *error);
void reader_batch_results_free(reader_batch_result *results, size_t count);

const char *reader_batch_status_name(reader_batch_status status);
const char *reader_batch_item_status_name(reader_batch_item_status status);
const char *reader_batch_format_name(exr_format format);
#ifdef __cplusplus
}
#endif
#endif
