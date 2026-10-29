/* SPDX-License-Identifier: MIT */
#include "opds_sha256_stream.h"
/* Same-owner source inclusion reuses the algorithm without a second copy or a
 * dependency on another package's private symbols. Normal OPDS is unchanged. */
#define EXREADER_OPDS_HASH_ONLY 1
#define opds_sha_init exreader_opds_hash_private_init
#define opds_sha_update exreader_opds_hash_private_update
#define opds_sha_final_hex exreader_opds_hash_private_final_hex
#include "opds_core.c"

struct opds_sha256_stream { opds_sha state; int finalized; };
opds_sha256_stream_status opds_sha256_stream_create(opds_sha256_stream **out) {
  opds_sha256_stream *c;
  if (!out) return OPDS_SHA256_STREAM_ARGUMENT;
  *out = NULL;
  c = (opds_sha256_stream *)calloc(1, sizeof *c);
  if (!c) return OPDS_SHA256_STREAM_MEMORY;
  opds_sha_init(&c->state);
  *out = c;
  return OPDS_SHA256_STREAM_OK;
}
opds_sha256_stream_status opds_sha256_stream_update(opds_sha256_stream *c,
                                                   const void *bytes, size_t size) {
  if (!c || (!bytes && size)) return OPDS_SHA256_STREAM_ARGUMENT;
  if (c->finalized) return OPDS_SHA256_STREAM_STATE;
#if SIZE_MAX > UINT64_MAX
  if (size > UINT64_MAX) return OPDS_SHA256_STREAM_ARGUMENT;
#endif
  if ((uint64_t)size > UINT64_MAX - c->state.len) return OPDS_SHA256_STREAM_ARGUMENT;
  opds_sha_update(&c->state, bytes, size);
  return OPDS_SHA256_STREAM_OK;
}
opds_sha256_stream_status opds_sha256_stream_finish_hex(opds_sha256_stream *c,
                                                       char out[65]) {
  if (!out) return OPDS_SHA256_STREAM_ARGUMENT;
  memset(out, 0, 65);
  if (!c) return OPDS_SHA256_STREAM_ARGUMENT;
  if (c->finalized) return OPDS_SHA256_STREAM_STATE;
  opds_sha_final_hex(&c->state, out);
  c->finalized = 1;
  return OPDS_SHA256_STREAM_OK;
}
void opds_sha256_stream_destroy(opds_sha256_stream **owner) {
  if (!owner) return;
  if (*owner) { memset(*owner, 0, sizeof **owner); free(*owner); }
  *owner = NULL;
}
