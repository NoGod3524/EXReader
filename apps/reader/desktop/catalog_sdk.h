/* SPDX-License-Identifier: MIT */
#ifndef READER_CATALOG_SDK_H
#define READER_CATALOG_SDK_H
#include "catalog.h"
#include <exr/library.h>
#ifdef __cplusplus
extern "C" {
#endif

#define READER_BOOK_KEY_CAPACITY 72
/* Hash a borrowed immutable source in 64 KiB blocks. Short reads are accepted;
 * cancellation and read failure clear both outputs. Does not release source. */
exr_status reader_catalog_source_identity(const exr_source *, const exr_control *,
  char sha256[65], uint64_t *bytes, exr_error *);
/* Verify source identity again before bootstrapping a legacy product revision.
 * Read-only, public SDK source only, 64 KiB blocks. Outputs clear on failure. */
exr_status reader_catalog_sdk_original_identity(exr_library *, int64_t id,
  const exr_control *, char sha256[65], uint64_t *bytes, exr_error *);
/* Existing host worker only. Reads/releases the public original source in
 * 64 KiB chunks and obtains the real EPUB mode through epub_info_get.
 * Product writes never roll back or delete an already committed SDK book.
 * key may be NULL; otherwise provide READER_BOOK_KEY_CAPACITY bytes. */
exr_status reader_catalog_sdk_attach(reader_catalog *, exr_library *, const exr_book *,
  const exr_control *, char *key, exr_error *);
/* Reuse the caller's single public books() result. Continue independent
 * per-book repair failures; report their count and first error. Cancellation
 * is checked around each publication. An in-flight product transaction may
 * finish (including its existing <=5s writer wait); retain committed rows,
 * then return CANCELLED before beginning another book. */
exr_status reader_catalog_sdk_repair(reader_catalog *, exr_library *, const exr_book *,
  size_t count, const exr_control *, size_t *failed, exr_error *);
#ifdef __cplusplus
}
#endif
#endif
