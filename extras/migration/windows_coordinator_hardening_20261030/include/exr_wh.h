/* SPDX-License-Identifier: MIT */
#ifndef EXR_WH_H
#define EXR_WH_H
#include <stddef.h>
#include <stdint.h>
#define EXR_WH_ABI 2u
#define EXR_WH_ID_BYTES 49u
#define EXR_WH_SHA_BYTES 65u
#define EXR_WH_MAX_RECORDS 4096u
#define EXR_WH_PATH_MAX 512u
#define EXR_WH_LINE_MAX 2048u
#define EXR_WH_MAX_JOURNAL 256u
typedef enum {WH_COMPLETED=0,WH_PENDING,WH_REFUSED,WH_ROLLED_BACK,
 WH_UNCERTAIN,WH_LEASE_RETAINED,WH_INTERNAL} wh_status;
typedef struct {char source[41],run[21],attempt[8],artifact[65],platform[32],sdk[64],provider[65];} wh_binding;
typedef struct {char admission[65],publisher[65],recovery[65],observer[65],fault[65];} wh_gates;
typedef struct {char id[49],path[512];uint64_t size;char sha[65];} wh_record;
int wh_binding_valid(const wh_binding *);
int wh_binding_digest(const wh_binding *,char[65]);
int wh_snapshot_valid(const wh_record *,size_t);
int wh_snapshot_digest(const wh_binding *,const wh_record *,size_t,char[65]);
int wh_content_digest(const wh_record *,size_t,char[65]);
void wh_sha256_hex(const void *,size_t,char[65]);
const char *wh_status_name(wh_status);
typedef enum {WH_STEP_OK=0,WH_STEP_FAILED=1,WH_STEP_UNCERTAIN=2} wh_step;
typedef enum {WH_PUB_NO=0,WH_PUB_YES=1,WH_PUB_UNKNOWN=2} wh_pub;
/* Private provider contract, NOT a native provider or SDK admission.
 * Every non-admission call receives a newly acquired opaque live capability.
 * FAILED admission: no capability/effect; UNCERTAIN: retain all ownership.
 * Reacquire must obtain fresh exclusive custody, verify generation/PENDING,
 * complete manifest and actual namespaces. Historical ID is NEVER authority.
 * Inspect YES proves current publication+logical content and worker terminal;
 * NO proves no publication/unknown worker and all staging absent or identified
 * by staged ID. Any ambiguity must return UNCERTAIN/UNKNOWN.
 * Release non-OK MUST preserve the capability/evidence; OK alone disposes it.
 * Never infer a live capability from a 49-byte identity string. */
typedef struct {
 unsigned abi;const char *identity_sha;void *context;
 wh_step (*acquire)(void *,const wh_binding *,const wh_gates *,void **,char[49]);
 wh_step (*reacquire)(void *,const wh_binding *,const wh_gates *,const char *,void **,char[49]);
 wh_step (*check)(void *,void *);
 wh_step (*snapshot)(void *,void *,wh_record *,size_t,size_t *);
 wh_step (*import_rows)(void *,void *,const wh_record *,size_t,char[49]);
 wh_step (*verify)(void *,void *,const char *,const wh_record *,size_t);
 wh_step (*publish)(void *,void *,const char *,wh_pub *);
 wh_step (*inspect)(void *,void *,const char *,const char *,wh_pub *);
 wh_step (*discard)(void *,void *,const char *);
 wh_step (*release)(void *,void *);
} wh_provider;
/* Return zero ONLY after durable append AND independent readback verification.
 * Any nonzero permanently poisons this session, even if a later append could
 * succeed. No callbacks or releases follow that failure. */
typedef int (*wh_append_verify)(void *,const char *);
typedef struct wh_session wh_session;
typedef struct {wh_status status;unsigned seq;int live_lease,poisoned;
 char lease[49],staged[49],snapshot[65],content[65],detail[128];} wh_report;
int wh_manifest(const wh_binding *,const wh_gates *,char out[EXR_WH_LINE_MAX]);
int wh_journal_check(const wh_binding *,const wh_gates *,const char *const *,size_t);
wh_session *wh_create(const wh_binding *,const wh_gates *,const wh_provider *,wh_append_verify,void *);
wh_status wh_run(wh_session *,wh_report *);
wh_status wh_recover(wh_session *,const char *const *,size_t,wh_report *);
/* Refuses to free a live capability or poisoned session. No reset/force-close.
 * Process-lifetime retention is intentional until an external qualified owner
 * handles recovery. This package does not implement that owner. */
int wh_dispose(wh_session *);
#endif
