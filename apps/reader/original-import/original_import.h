/* SPDX-License-Identifier: MIT */
#ifndef READER_ORIGINAL_IMPORT_H
#define READER_ORIGINAL_IMPORT_H
#include "catalog.h"
#ifdef __cplusplus
extern "C" {
#endif
/* Single catalog owner, one import/recovery at a time. Directories must exist,
 * be absolute, private to the product and on a filesystem supporting durable
 * no-replace publication. source_name is a single portable file name.
 * The callbacks run on the caller's thread; nonzero cancellation aborts.
 * event: 1 reserved, 2 copying, 3 published. */
typedef struct {
  void *context;
  int (*cancelled)(void *);
  void (*event)(void *, int);
} reader_original_callbacks;
typedef enum { ROI_OK=0, ROI_DUPLICATE, ROI_CANCELLED, ROI_ARGUMENT, ROI_IO, ROI_CATALOG, ROI_CORRUPT, ROI_MEMORY } reader_original_status;
/* key receives txt:<sha256> (69 bytes including NUL). Metadata strings must
 * remain valid for the call. Existing catalog/SDK metadata is never replaced. */
reader_original_status reader_original_import(reader_catalog *, const char *root,
  const char *source_dir, const char *source_name, const char *title,
  const char *author, const char *sort_title, const reader_original_callbacks *, char key[69]);
/* Reconcile all interrupted staged/deleting records before accepting imports.
 * A published staged file is verified before it can become ready. */
reader_original_status reader_original_recover(reader_catalog *, const char *root);
/* Checks ready state, byte count and SHA-256. The returned absolute path is
 * valid only while the host retains exclusive ownership of the private root. */
reader_original_status reader_original_verified_path(reader_catalog *, const char *root,
  const char *key, char *path, size_t capacity);
#ifdef _WIN32
/* Returns the very handle that was hashed, opened without write or delete
 * sharing. The caller owns it and must CloseHandle after its last read. The
 * catalog owner must still serialize deletion and recovery with the reader. */
reader_original_status reader_original_verified_handle(reader_catalog *, const char *root,
  const char *key, const reader_original_callbacks *, void **handle, uint64_t *size);
#endif
#ifdef __cplusplus
}
#endif
#endif
