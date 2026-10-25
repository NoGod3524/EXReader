/* SPDX-License-Identifier: MIT */
#ifndef READER_ORIGINAL_EXPORT_H
#define READER_ORIGINAL_EXPORT_H
#include <exr/library.h>
#ifdef __cplusplus
extern "C" {
#endif
#define ROE_VERSION "0.1.0"
#define ROE_MAX_ITEMS 100u
#define ROE_PATH_CAP 4096u
#define ROE_DEFAULT_BOOK_BYTES (UINT64_C(128)*1024*1024)
#define ROE_DEFAULT_BATCH_BYTES (UINT64_C(512)*1024*1024)
#define ROE_HARD_BATCH_BYTES (UINT64_C(1024)*1024*1024)
typedef enum { ROE_OK=0, ROE_ARGUMENT, ROE_LIMIT, ROE_OWNER, ROE_MEMORY,
  ROE_SOURCE, ROE_IO, ROE_CONFLICT, ROE_CANCELLED, ROE_PENDING, ROE_CLEANUP } roe_status;
typedef enum { ROE_HASH_NAME=0, ROE_DISPLAY_NAME=1 } roe_name_mode;
typedef struct roe_exporter roe_exporter;
/* The host's single SDK-owner gate. enter returns zero only when this worker
 * may use the borrowed library. leave cannot fail. All callbacks are noexcept.
 * They must serialize against ALL other SDK users, including direct calls.
 * The library must outlive this exporter; this module never opens/closes it. */
typedef struct { int (*enter)(void *); void (*leave)(void *); void *context; } roe_owner;
typedef struct { int64_t book_id; const char *display_name; } roe_selection;
typedef struct {
  int64_t book_id;
  roe_status status;
  exr_status sdk_status;
  int committed, created, durable, cleanup_pending;
  exr_format format;
  uint64_t bytes;
  char original_sha256[65];
  char output_path[ROE_PATH_CAP];
  char cleanup_path[ROE_PATH_CAP];
} roe_item;
typedef struct { size_t count; roe_status status; roe_item items[ROE_MAX_ITEMS]; } roe_result;
typedef enum { ROE_STAGED=1, ROE_COPYING, ROE_PUBLISHED } roe_event;
/* Called only after SDK calls return; the owner lease remains held; item is a borrowed receipt.
 * Persist STAGED/COPYING cleanup_path before returning if crash recovery is
 * required. Cancellation is checked before each <=64KiB read and publication.
 * Reentry, cross-thread use, and a second exporter for this owner are rejected.
 * The host gate must reject other direct SDK operations during callbacks. */
typedef struct {
  int (*cancelled)(void *);
  void (*progress)(void *, size_t index, roe_event, const roe_item *);
  void *context;
} roe_callbacks;
typedef struct {
  const char *directory; /* Existing absolute UTF-8 directory; no . or ..,
    symlinks/reparse components, UNC/device namespace, or aliases. Max 3500 bytes. */
  roe_name_mode naming;
  uint64_t per_book_bytes, batch_bytes; /* Zero => defaults. Book <=128MiB,
    batch <=1GiB. Entire selection preflighted before creating any file. */
  roe_callbacks callbacks;
} roe_options;
/* Owner thread is the creating thread. One exporter per borrowed library.
 * No SDK calls occur during create. No C++ exception crosses this C ABI. */
roe_status roe_create(exr_library *, const roe_owner *, roe_exporter **);
roe_status roe_destroy(roe_exporter **);
/* Synchronous; selections are explicit (1..100), never a bookshelf query as
 * selection. Owned result is returned even after partial failure. Free ONLY
 * with roe_result_free. Every item's receipt survives later failures. No batch
 * transaction: published files are never rolled back. No completion manifest,
 * shell/app invocation, network, original/notes/progress/product write occurs.
 * HASH_NAME: <SHA256>.<format>. DISPLAY_NAME: <strict ASCII slug>--<hash>.<format>.
 * Slug is 1..64 letters/digits/_/-; reserved device stems rejected. Untrusted
 * titles are never used. Duplicate means regular non-aliased existing file
 * with matching actual bytes/hash. No target is overwritten. Path strings are
 * owned inline in result; callbacks must copy their borrowed views. */
roe_status roe_run(roe_exporter *, const roe_selection *, size_t, const roe_options *, roe_result **);
void roe_result_free(roe_result *);
#ifdef __cplusplus
}
#endif
#endif
