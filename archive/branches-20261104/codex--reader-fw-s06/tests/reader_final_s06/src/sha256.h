/* SPDX-License-Identifier: MIT */
#ifndef S06_SHA256_H
#define S06_SHA256_H
#include <stddef.h>
#include <stdint.h>

/* Minimal streaming SHA-256 so the acceptance probe can hash originals
   without adding a dependency to the installed SDK or module packages. */
typedef struct {
  uint32_t state[8];
  uint64_t bytes;
  unsigned char block[64];
  size_t used;
} s06_sha256;

void s06_sha256_init(s06_sha256 *hash);
void s06_sha256_update(s06_sha256 *hash, const void *data, size_t size);
void s06_sha256_finish(s06_sha256 *hash, unsigned char digest[32]);
void s06_sha256_hex(const unsigned char digest[32], char out[65]);

#endif
