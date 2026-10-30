/* SPDX-License-Identifier: MIT
 * Full-width (49-byte) logical snapshot / import / recovery coordinator.
 * It orchestrates provider steps only. Admission/reopen leases (C01), exclusive
 * publication and rename custody (native publisher) and the native observer are
 * supplied through the provider; missing pieces make wc_run return WC_PENDING
 * before any mutation. WC_COMPLETED is never produced by this module alone. */
#ifndef EXR_WC_H
#define EXR_WC_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
#define EXR_WC_ABI 1u
#define EXR_WC_ID_BYTES 49u    /* volume64 + FileID128: 48 lowercase hex + NUL */
#define EXR_WC_SHA_BYTES 65u
#define EXR_WC_MAX_RECORDS 4096u
#define EXR_WC_PATH_MAX 512u
#define EXR_WC_LINE_MAX 448u

typedef enum {
  WC_COMPLETED = 0,   /* published, verified, lease released */
  WC_PENDING,         /* provider function or gate evidence missing; nothing ran */
  WC_REFUSED,         /* invalid input/binding or admission refused; nothing published */
  WC_ROLLED_BACK,     /* staged data discarded, lease released */
  WC_UNCERTAIN,       /* effect cannot be proven either way; everything retained */
  WC_LEASE_RETAINED,  /* terminal data state reached but lease release failed */
  WC_INTERNAL
} wc_status;
const char *wc_status_name(wc_status status);

/* Every field is bound into the journal: source commit, Actions run/attempt,
   artifact SHA256, platform, SDK identity and provider identity SHA256. */
typedef struct {
  char source[41], run[21], attempt[8], artifact[65], platform[32], sdk[64], provider[65];
} wc_binding;
int wc_binding_valid(const wc_binding *binding);
int wc_binding_digest(const wc_binding *binding, char out[EXR_WC_SHA_BYTES]);

typedef struct {
  char id[EXR_WC_ID_BYTES];       /* full source file identity */
  char path[EXR_WC_PATH_MAX];     /* relative, '/' separated, UTF-8 */
  uint64_t size;
  char sha[EXR_WC_SHA_BYTES];     /* SHA256 of content */
} wc_record;
/* Strictly path-sorted, unique, canonical relative paths, valid ids/hashes. */
int wc_snapshot_valid(const wc_record *rows, size_t count);
int wc_snapshot_digest(const wc_binding *binding, const wc_record *rows, size_t count,
                       char out[EXR_WC_SHA_BYTES]);           /* includes ids */
int wc_content_digest(const wc_record *rows, size_t count,
                      char out[EXR_WC_SHA_BYTES]);            /* path+size+sha only */
void wc_sha256_hex(const void *data, size_t size, char out[EXR_WC_SHA_BYTES]);

/* Gate evidence: empty string = absent (pending), otherwise 64 lowercase hex
   naming the Actions artifact/evidence digest of that separately owned piece. */
typedef struct {
  char admission[65];   /* C01 shared admission/reopen lease */
  char publisher[65];   /* native exclusive publication/rename custody */
  char recovery[65];    /* native recovery engine */
  char observer[65];    /* native observer */
  char fault[65];       /* P0 fault acceptance */
} wc_gates;

typedef int (*wc_sink)(void *context, const char *line);   /* 0 = durably appended */

typedef struct {
  wc_status status;
  char phase[16];
  char pending[256];
  char lease[EXR_WC_ID_BYTES], staged[EXR_WC_ID_BYTES];
  char snapshot_digest[EXR_WC_SHA_BYTES], content_digest[EXR_WC_SHA_BYTES];
  unsigned records, seq;
  char detail[160];
} wc_report;

struct wc_provider;
wc_status wc_run(const wc_binding *binding, const wc_gates *gates,
                 const struct wc_provider *provider, wc_sink sink, void *sink_context,
                 wc_report *report);
/* Resume from an existing journal (hash chained, same binding). Never guesses:
   undecidable states return WC_UNCERTAIN and mutate nothing. */
wc_status wc_recover(const wc_binding *binding, const wc_gates *gates,
                     const struct wc_provider *provider, const char *const *lines, size_t count,
                     wc_sink sink, void *sink_context, wc_report *report);
int wc_journal_check(const wc_binding *binding, const char *const *lines, size_t count,
                     char *why, size_t why_size);
#ifdef __cplusplus
}
#endif
#endif
