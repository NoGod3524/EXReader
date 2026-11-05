/* SPDX-License-Identifier: MIT
 * Private observation protocol. Never a COMMIT or reopen receipt. */
#ifndef LM_WE_PROTOCOL_H
#define LM_WE_PROTOCOL_H
#include "lm_recovery_win32_platform.h"
#include "lm.h"
#ifndef LM_WE_SOURCE
#error LM_WE_SOURCE must bind the configured source
#endif
#define LM_WE_LIMIT (64u*1024u*1024u)
typedef struct {
 char magic[16],source[41],nonce[33],root[49],parent[49],target[49],worker_sha[65];
} lm_we_request;
typedef struct {
 lm_we_request request;
 char target_sha[65];
 unsigned long long bytes;
 unsigned observed;
} lm_we_response;
int lm_we_hash(HANDLE h,char sha[65],wr_identity *identity,wr_error *e);
int lm_we_request_valid(const lm_we_request *r);
#endif
