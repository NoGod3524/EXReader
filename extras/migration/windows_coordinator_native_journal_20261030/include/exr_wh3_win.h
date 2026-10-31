/* SPDX-License-Identifier: MIT */
#ifndef EXR_WH3_WIN_H
#define EXR_WH3_WIN_H
#include <windows.h>
#include <exr_wh3.h>
typedef struct { ULONGLONG volume; FILE_ID_128 file; } wh3w_identity;
typedef struct {
 void *context;
 /* enter pins a non-revocable live domain borrow until leave. These callbacks
    are an integration contract, NOT a frozen C01/production implementation. */
 int (*enter)(void *,void *,const wh_binding *,void **);
 int (*validate)(void *,void *);
 void (*poison)(void *,void *,const char *);
 void (*leave)(void *,void *);
} wh3w_domain;
enum { WH3W_PRE_BEGIN=1, WH3W_BEGIN_FLUSHED, WH3W_JOURNAL_WRITTEN,
       WH3W_JOURNAL_FLUSHED, WH3W_ACK_FLUSHED };
enum { WH3W_NO_FAULT=0, WH3W_SHORT_WRITE, WH3W_FLUSH_FAIL, WH3W_READBACK_FAIL };
/* Explicit candidate-only deterministic controls. Normal use supplies zero.
   Short write really writes a prefix; flush-fail is injected API failure,
   not evidence about physical media/power-loss durability. */
typedef struct {
 unsigned fault;
 void *context;
 void (*phase)(void *,unsigned);
} wh3w_controls;
typedef struct wh3w_store wh3w_store;
/* Existing local NTFS root, fixed journal.bin/intent.bin, all identities trusted
   by the caller's domain capability. No creation, truncation or repair. */
int wh3w_open(const wchar_t *,const wh3w_identity[3],const wh_binding *,
 const wh_gates *,const wh3w_domain *,const wh3w_controls *,wh3w_store **);
wh3_tx_status wh3w_append(void *,void *,const wh3_tip *,const char *,wh3_tip *);
/* No domain release or CLEAN transition. Poison survives only if the real
   domain integration persists it and all readers consult that gate/intent. */
void wh3w_close(wh3w_store *);
#endif
