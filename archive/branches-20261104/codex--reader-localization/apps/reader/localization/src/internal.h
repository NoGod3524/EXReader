/* SPDX-License-Identifier: MIT */
#ifndef READER_LOCALIZATION_INTERNAL_H
#define READER_LOCALIZATION_INTERNAL_H

#include "reader_localization.h"

#include <stddef.h>
#include <stdint.h>

/* Shipped message count. The catalog table asserts it and the digest uses it
   for its fixed-order index array. */
#define RL_MESSAGE_COUNT 62u

#define RL_LOCALE_COUNT 2u

/* One locale-independent catalog message. kinds has exactly one character per
   slot, in slot order: 's' string, 'd' signed decimal, 'u' unsigned decimal.
   kinds is "" for a message without placeholders. */
typedef struct {
  const char *id;
  const char *group;
  const char *kinds;
} rl_message;

extern const rl_message rl_messages[];
extern const size_t rl_message_count;
/* Parallel to rl_messages. NULL marks a shipped row that is absent for that
   locale; the renderer then falls back to en-US and reports it. The shipped
   catalog has no NULL row in either locale (checked in Actions), so a NULL can
   only appear through the test-hook build. */
extern const char *const rl_zh_templates[];
extern const char *const rl_en_templates[];

size_t rl_slot_count(const char *kinds);
/* Copies the byte length when a NUL appears within 'limit' bytes; returns 1 on
   success and 0 when the string is longer than the limit. */
int rl_strlen_bounded(const char *text, size_t limit, size_t *length);
int rl_utf8_valid(const char *text, size_t length);

/* Streaming SHA-256 used only for the catalog digest. */
typedef struct {
  uint32_t state[8];
  uint64_t bits;
  unsigned char block[64];
  size_t used;
} rl_sha256;

void rl_sha256_init(rl_sha256 *hash);
void rl_sha256_update(rl_sha256 *hash, const void *data, size_t length);
void rl_sha256_update_string(rl_sha256 *hash, const char *text);
void rl_sha256_final(rl_sha256 *hash, unsigned char out[32]);

#endif
