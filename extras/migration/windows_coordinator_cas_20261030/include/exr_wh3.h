/* SPDX-License-Identifier: MIT */
#ifndef EXR_WH3_H
#define EXR_WH3_H
#include <exr_wh.h>
#define EXR_WH3_ABI 3u
typedef struct {
    char manifest_sha[65];
    size_t line_count;
    /* SHA256 of the FULL last canonical line, not the ABI2 body seal.
       At count zero this is 64 ASCII zeroes. */
    char last_line_sha[65];
} wh3_tip;
typedef enum { WH3_TX_OK=0, WH3_TX_MISMATCH=1, WH3_TX_UNCERTAIN=2 } wh3_tx_status;
/* Mandatory backend transaction contract:
 * Validate live exclusive cap, actual full journal chain and exact expected tip
 * in one protected transaction, then append, persist and independently read back.
 * MISMATCH guarantees no append; UNCERTAIN may have written. Neither permits
 * release. Count zero requires an actually empty store. Never accept a newer
 * backend tip in place of the caller's expected tip.
 * Sessions require serialized callers; the backend must serialize shared storage.
 * This facade provides no native storage, Windows locking or SDK admission.
 * A memory backend is only a contract test, not durable/native evidence. */
typedef wh3_tx_status (*wh3_transaction)(void *,void *,const wh3_tip *,
                                        const char *,wh3_tip *);
typedef struct { unsigned abi; void *context; wh3_transaction append; } wh3_backend;
typedef struct wh3_session wh3_session;
wh3_session *wh3_create(const wh_binding *,const wh_gates *,const wh_provider *,
                       const wh3_backend *);
wh_status wh3_run(wh3_session *,wh_report *);
wh_status wh3_recover(wh3_session *,const char *const *,size_t,wh_report *);
wh3_tx_status wh3_last_transaction(const wh3_session *);
/* Refusal keeps the facade, provider context and captured cap alive. */
int wh3_dispose(wh3_session *);
#endif
