/* SPDX-License-Identifier: MIT */
/* Shared by the installed desktop consumer and the Android JNI probe. Secret
   values arrive from the job harness and are never written to any output. */
#ifndef EXR_CREDENTIALS_SUITE_H
#define EXR_CREDENTIALS_SUITE_H
#include <stddef.h>
#include <stdint.h>
#include "exr_credentials.h"

enum { SUITE_ACCOUNTS = 6, SUITE_SECRETS = 8 };
typedef struct {
  char name[16];
  uint8_t bytes[EXR_CREDENTIALS_SECRET_MAX + 1];
  size_t length;
} suite_secret;
typedef struct {
  char ns[EXR_CREDENTIALS_NAMESPACE_MAX + 1], ns2[EXR_CREDENTIALS_NAMESPACE_MAX + 1];
  /* a, b, c, d: functional; r: reopen; p: unavailable probe. */
  char account[SUITE_ACCOUNTS][EXR_CREDENTIALS_ACCOUNT_ID_LENGTH + 1];
  suite_secret secret[SUITE_SECRETS];
} suite_input;
typedef void (*suite_emit)(void *context, const char *line);

/* Parses "namespace|namespace2 <value>", "account <a|b|c|d|r|p> <uuid>" and
   "secret <name> <hex>" lines. Returns 0 on success. */
int suite_parse(const char *text, suite_input *input);
/* phase: suite, reopen, seed, unavailable or cleanup. Returns failed checks,
   or -1 for an unknown phase. */
int suite_run(const char *phase, const suite_input *input, suite_emit emit, void *context);
void suite_wipe(suite_input *input);
#endif
