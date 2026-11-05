/* SPDX-License-Identifier: MIT */
#ifndef READER_SELECTOR_BYTES_V1_H
#define READER_SELECTOR_BYTES_V1_H
#include <stddef.h>
#if !defined(EXR_READER_PUBLIC_SELECTOR_BYTES_V1) || EXR_READER_PUBLIC_SELECTOR_BYTES_V1 != 1
#error "Use the installed raw Revisions target with public selector bytes API v1"
#endif
#define READER_REV_SELECTOR_BYTES_API_VERSION "1.0.0"
#ifdef __cplusplus
extern "C" {
#endif
typedef enum {
  READER_SELECTOR_V1_OK = 0, READER_SELECTOR_V1_ARGUMENT,
  READER_SELECTOR_V1_FORMAT, READER_SELECTOR_V1_LIMIT,
  READER_SELECTOR_V1_BUFFER, READER_SELECTOR_V1_MEMORY
} reader_selector_status_v1;
/* Pure caller-buffer codec; no store, history or allocator ownership crosses
 * this boundary. Input NULL is valid only for count zero. Optional-field
 * presence is the caller's responsibility: NULL/absent and present-empty wire
 * fields must remain distinct. Input/output must not overlap.
 *
 * output_count is required and is zero on failure except BUFFER (required
 * length). NULL output with capacity zero validates and queries the length;
 * NULL output with positive capacity is ARGUMENT. Nonnull zero-capacity output
 * succeeds for empty output, otherwise BUFFER. No implicit NUL is written.
 * Failure never partially writes output. Allocation failures are MEMORY.
 * Encode accepts arbitrary bytes. Decode requires canonical padded Base64,
 * exact declared byte count, strict UTF-8 (embedded NUL permitted), and the
 * supplied byte/scalar ceilings. Invalid UTF-8/scalar excess is FORMAT, matching
 * the existing selector wire validation; byte excess/arithmetic overflow LIMIT.
 */
reader_selector_status_v1 reader_revision_selector_encode_v1(
    const void *bytes, size_t count, char *output, size_t capacity,
    size_t *output_count);
reader_selector_status_v1 reader_revision_selector_decode_v1(
    const char *encoded, size_t encoded_count, size_t declared_bytes,
    size_t byte_limit, size_t scalar_limit, void *output, size_t capacity,
    size_t *output_count);
#ifdef __cplusplus
}
#endif
#endif
