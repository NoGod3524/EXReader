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
 /* Optional paired hooks retain domain storage while a journal is open. */
 int (*retain)(void *);
 void (*release)(void *);
} wh3w_domain;
enum { WH3W_PRE_BEGIN=1, WH3W_BEGIN_FLUSHED, WH3W_JOURNAL_WRITTEN,
       WH3W_JOURNAL_FLUSHED, WH3W_ACK_FLUSHED,
       WH3W_BEGIN_PARTIAL, WH3W_JOURNAL_HEADER_PARTIAL,
       WH3W_JOURNAL_BODY_PARTIAL, WH3W_ACK_PARTIAL, WH3W_ACK_WRITTEN,
       WH3W_PINNED_BASE=100 };
enum { WH3W_NO_FAULT=0, WH3W_SHORT_WRITE, WH3W_FLUSH_FAIL, WH3W_READBACK_FAIL };
/* Explicit candidate-only deterministic controls. Normal use supplies zero.
   Short write really writes a prefix; flush-fail is injected API failure,
   not evidence about physical media/power-loss durability. */
typedef struct {
 unsigned fault;
 unsigned fault_phase; /* zero means the first eligible operation */
 void *context;
 void (*phase)(void *,unsigned);
} wh3w_controls;
typedef struct wh3w_store wh3w_store;
/* Existing local NTFS root, fixed journal.bin/intent.bin, all identities trusted
   by the caller's domain capability. No creation, truncation, bootstrap or repair. Both files are validated on open. */
int wh3w_open(const wchar_t *,const wh3w_identity[3],const wh_binding *,
 const wh_gates *,const wh3w_domain *,const wh3w_controls *,wh3w_store **);
wh3_tx_status wh3w_append(void *,void *,const wh3_tip *,const char *,wh3_tip *);
/* Read the current fully acknowledged pair without mutation or authority
   upgrade. Recovery must bind the returned tip to independently trusted
   transaction metadata, then request an exact fresh resume capability. */
int wh3w_read(wh3w_store *,char (*lines)[EXR_WH_LINE_MAX],size_t capacity,
 size_t *count,wh3_tip *tip);
/* No domain release or CLEAN transition. Poison survives only if the real
   domain integration persists it and all readers consult that gate/intent. */
void wh3w_close(wh3w_store *);
/* Persistent admission: explicitly enrolled, trusted native objects only.
   Shared holders require CLEAN and the exact independently supplied generation AND record seal.
   Owner begin persists PENDING before issuing the opaque mutation capability.
   No API initializes missing files, silently adopts a newer generation, or
   clears PENDING on close. The caller owns registry provenance and publication
   proof; neither a digest string nor a journal alone establishes that proof. */
typedef struct wh3wg_gate wh3wg_gate;
typedef struct { uint64_t generation; char seal[65]; } wh3wg_grant;
enum { WH3WG_SHARED=1, WH3WG_OWNER=2, WH3WG_ENROLL=3, WH3WG_RECOVER=4 };
enum { WH3WG_BEGIN_WRITTEN=201, WH3WG_BEGIN_DURABLE=202,
       WH3WG_CLEAN_WRITTEN=203, WH3WG_CLEAN_DURABLE=204 };
int wh3wg_open(const wchar_t *,const wh3w_identity[2],const char domain[49],
 const wh3wg_grant *trusted,unsigned mode,const wh3w_controls *,wh3wg_gate **);
/* ENROLL requires an existing, exactly identified, empty admission.bin.
   Only an independently established bootstrap authority may call it. */
int wh3wg_enroll(wh3wg_gate *,wh3wg_grant *);
int wh3wg_begin(wh3wg_gate *,const wh_binding *,const wh_gates *,
 const wh3_tip *,void **capability);
void wh3wg_domain(wh3wg_gate *,wh3w_domain *);
int wh3wg_check(wh3wg_gate *);
uint64_t wh3wg_generation(const wh3wg_gate *);
int wh3wg_clean(wh3wg_gate *,wh3wg_grant *);
/* Recovery grants a fresh capability only for the exact complete on-disk tip. */
int wh3wg_resume(wh3wg_gate *,const wh_binding *,const wh_gates *,
 wh3w_store *,const wh3_tip *,void **capability);
/* prove must independently establish actual publication/abort and terminal
   workers for this exact tip. The returned generation becomes registry input
   only on success. A failed/unknown finish cannot advance trusted admission. */
int wh3wg_finish(wh3wg_gate *,void *capability,wh3w_store *,const wh3_tip *,
 int (*prove)(void *,const wh3_tip *),void *context,wh3wg_grant *grant);
/* Refuses while any journal borrow is live; never writes CLEAN. */
int wh3wg_close(wh3wg_gate *);

/* Explicit lost-finish recovery: verify the exact terminal tip and actual
   publication again before issuing the already-written grant. No auto-upgrade. */
int wh3wg_reconcile(wh3wg_gate *,wh3w_store *,const wh3_tip *,
 int (*prove)(void *,const wh3_tip *),void *context,wh3wg_grant *);

/* Windows application registry adapter. Ordinary open reads the current-user
   protected registry and never enrolls. Enrollment is an explicit operation on
   an existing target and three empty native files, with independent clean-state
   proof while exclusively held. Registry aliases, permissive ACLs and
   noncanonical bindings refuse. Each record binds the actual target FileID.
   The trust boundary is the current user and SYSTEM; hostile same-user code
   with registry write rights is not isolated by this application protocol. */
typedef struct wh3wr_registration wh3wr_registration;
int wh3wr_enroll(const wchar_t *library,const wchar_t *root,
 int (*prove_initial)(void *,const wchar_t *),void *context);
/* Enrollment intent is durably recorded before the first native gate record.
   Recovery accepts only its independently computed initial grant and exact
   object identities, then repeats initial-state proof. Ordinary open never
   calls either enrollment API. Torn or replaced objects remain refused. */
enum { WH3WR_ENROLL_RESERVED=500, WH3WR_ENROLL_INTENT=501, WH3WR_ENROLL_GATE=502,
       WH3WR_ENROLL_PROVED=503, WH3WR_ENROLL_BOUND=504 };
int wh3wr_enroll_controlled(const wchar_t *library,const wchar_t *root,
 int (*prove_initial)(void *,const wchar_t *),void *context,const wh3w_controls *);
/* Explicit user command only: create a new domain root and all three objects,
   or validate the already existing empty set. Existing incomplete roots are
   never filled in. create_library uses CREATE_NEW and never overwrites. */
int wh3wr_enroll_created(const wchar_t *library,const wchar_t *root,int create_library,
 int (*prove_initial)(void *,const wchar_t *),void *context);
int wh3wr_recover_enrollment(const wchar_t *library,
 int (*prove_initial)(void *,const wchar_t *),void *context);
int wh3wr_open(const wchar_t *library,unsigned mode,const wh3w_controls *,
 wh3wr_registration **);
int wh3wr_check(wh3wr_registration *);
/* Per-native-domain immutable input and verified-stage records, held in the
   protected registry. Unknown writes cannot issue success or authorize publish.
   Only explicit owner/recovery callers may read them; bytes are still subject
   to the production provider's canonical schema and semantic validation. */
enum { WH3WR_INPUT=1, WH3WR_PREPARED=2 };
/* Explicit clean-state checkpoint; preserves prior roots and registry values.
   Ordinary opens refuse during its durable intent. A retry never adopts an
   incompletely created root and independently proves the current target again. */
enum { WH3WR_EPOCH_INTENT=700, WH3WR_EPOCH_OBJECTS, WH3WR_EPOCH_READY,
       WH3WR_EPOCH_BOUND, WH3WR_EPOCH_RETIRED };
int wh3wr_next_epoch(const wchar_t *library,int (*prove)(void *,const wchar_t *),
 void *context,const wh3w_controls *);
int wh3wr_transaction_write(wh3wr_registration *,unsigned phase,const void *,size_t);
int wh3wr_transaction_read(wh3wr_registration *,unsigned phase,void *,size_t,size_t *);

int wh3wr_journal(wh3wr_registration *,const wh_binding *,const wh_gates *,
 const wh3w_controls *,wh3w_store **);
int wh3wr_begin(wh3wr_registration *,const wh_binding *,const wh_gates *,
 const wh3_tip *,void **capability);
int wh3wr_resume(wh3wr_registration *,const wh_binding *,const wh_gates *,
 wh3w_store *,const wh3_tip *,void **capability);
/* Drops only the owner's target pin, after durable PENDING. Parent namespace,
   gate and registry remain held. Reacquire the actual published target before
   committing a new trusted binding. Readers cannot invoke this transition. */
int wh3wr_prepare_publish(wh3wr_registration *);
/* Same-parent, handle-bound publication preserves the old target at a fresh
   retained leaf. The caller supplies the independently verified stage FileID.
   Every directory pin stays live and keeps denying write/delete opens.
   MISMATCH performs no namespace mutation; UNCERTAIN poisons this holder and
   requires fresh recovery. This operation does not write the terminal journal
   or advance admission. Call finish only after independent publication proof. */
wh3_tx_status wh3wr_publish(wh3wr_registration *,const wchar_t *stage_leaf,
 const wh3w_identity *stage_identity,const wchar_t *retained_leaf);
int wh3wr_finish(wh3wr_registration *,wh3w_store *,const wh3_tip *,
 int (*prove)(void *,const wh3_tip *),void *context);
/* Refuses while a journal retains the gate. Caller closes all SDK borrowers
   before releasing a shared registration. Pending never becomes clean here. */
int wh3wr_close(wh3wr_registration *);

#endif
