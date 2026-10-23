/* SPDX-License-Identifier: MIT */
#ifndef READER_CATALOG_SDK_H
#define READER_CATALOG_SDK_H
#include "catalog.h"
#include <exr/library.h>

#define READER_BOOK_KEY_CAPACITY 72
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
#endif
