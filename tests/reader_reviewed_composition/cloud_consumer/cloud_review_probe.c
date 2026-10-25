/* SPDX-License-Identifier: MIT
 * Same reviewed allocation fault injection and unchanged original cases.
 * The original's four-parent include accidentally resolved via its old SDK
 * installation depth. Three parents is the actual repository source root. */
#include <stdlib.h>
static unsigned long review_allocations;
static int review_fail(void) {
  const char *text = getenv("READER_CLOUD_FAIL_ALLOC");
  review_allocations++;
  return text && strtoul(text, NULL, 10) == review_allocations;
}
static void *review_malloc(size_t size) {
  return review_fail() ? NULL : malloc(size);
}
static void *review_calloc(size_t count, size_t size) {
  return review_fail() ? NULL : calloc(count, size);
}
#define malloc review_malloc
#define calloc review_calloc
#include "../../../apps/reader/cloud-import/src/cloud_import.c"
#undef malloc
#undef calloc
#define READER_CLOUD_REVIEW_INJECTED 1
#include "../../reader_webdav_import/consumer/cloud_probe.c"
