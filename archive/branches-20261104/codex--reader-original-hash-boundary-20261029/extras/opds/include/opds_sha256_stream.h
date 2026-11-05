/* SPDX-License-Identifier: MIT */
#ifndef OPDS_SHA256_STREAM_H
#define OPDS_SHA256_STREAM_H
#include <stddef.h>
#ifdef __cplusplus
extern "C" {
#endif
/* Independent, bounded-memory, owner-thread-only streaming SHA-256 context.
 * No concurrent mutation. Message byte count is uint64_t; overflow is rejected
 * before mutation. Final length encoding retains modulo-2^64 bit-count semantics.
 * This is a compatibility domain, not a claim of huge-message validation. */
typedef struct opds_sha256_stream opds_sha256_stream;
typedef enum opds_sha256_stream_status {
  OPDS_SHA256_STREAM_OK = 0,
  OPDS_SHA256_STREAM_ARGUMENT = 1,
  OPDS_SHA256_STREAM_MEMORY = 2,
  OPDS_SHA256_STREAM_STATE = 3
} opds_sha256_stream_status;
/* create clears *out before allocation; caller must not overwrite a live owner. */
opds_sha256_stream_status opds_sha256_stream_create(opds_sha256_stream **out);
/* NULL bytes is valid only with size zero. Rejected updates preserve state. */
opds_sha256_stream_status opds_sha256_stream_update(opds_sha256_stream *context,
                                                   const void *bytes, size_t size);
/* out must hold 65 bytes. Clears out on failure. Finalize exactly once. */
opds_sha256_stream_status opds_sha256_stream_finish_hex(opds_sha256_stream *context,
                                                       char out[65]);
/* NULL owner/context accepted. Clears *context and releases it exactly once. */
void opds_sha256_stream_destroy(opds_sha256_stream **context);
#ifdef __cplusplus
}
#endif
#endif
