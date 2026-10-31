/* SPDX-License-Identifier: MIT */
#ifndef EXR_WH3_REPAIR_H
#define EXR_WH3_REPAIR_H
#include <exr_wh3_win.h>
/* Observational evidence, not a recovery capability. Allocate this large output
   on the heap. The caller already holds exclusive native custody and checks
   both handles against independently trusted identities and directory pins. */
typedef struct {
 wh3w_identity journal_identity,intent_identity;
 uint64_t journal_bytes,intent_bytes,journal_keep_bytes,intent_keep_bytes;
 char journal_sha256[65],intent_sha256[65];
 size_t count;wh3_tip tip;int unack_tail;
 char lines[EXR_WH_MAX_JOURNAL][EXR_WH_LINE_MAX];
} wh3r_scan;
/* Reads actual bytes twice, checks identity/size again, and observes every full
   ACK. At most one legal interrupted append suffix, plus the native poison
   byte, may follow the last ACK. Contradictory complete records refuse.
   No write, truncation, bootstrap, capability issuance or CLEAN transition.
   The file cursors move; the native objects and their bytes do not.
   Failure clears all output. Admission-file evidence belongs to the caller. */
int wh3r_scan_ack(HANDLE journal,HANDLE intent,const wh_binding *,
 const wh_gates *,wh3r_scan *);
/* The ack input must be a fresh successful observation made under the same
   exclusive custody. This helper accepts only an initial per-domain I0 grant
   and at most one B1/C1 cycle. It plans a canonical target; it writes nothing. */
#define WH3R_GATE_RECORD_BYTES 344u
typedef struct {
 wh3w_identity identity;uint64_t bytes;char sha256[65];uint64_t gate_keep_bytes;
 unsigned char target[3u*WH3R_GATE_RECORD_BYTES];
 size_t target_bytes;int needs_write,complete_clean;
} wh3r_gate_scan;
int wh3r_scan_gate(HANDLE admission,const char domain[49],const wh3wg_grant *,
 const wh_binding *,const wh_gates *,const wh3r_scan *,wh3r_gate_scan *);
#endif
