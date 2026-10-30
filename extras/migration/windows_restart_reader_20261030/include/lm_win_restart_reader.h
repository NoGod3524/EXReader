/* SPDX-License-Identifier: MIT */
#ifndef LM_WIN_RESTART_READER_H
#define LM_WIN_RESTART_READER_H
#include <lm_recovery_win32_record.h>
#include <lm_win_lease.h>
typedef struct lm_rr lm_rr;
typedef enum { LM_RR_REFUSED=0,LM_RR_RESERVED=1,LM_RR_PREFIX=2,
 LM_RR_COMPLETE_EVIDENCE=3,LM_RR_NAMESPACE_CONFLICT=4 } lm_rr_class;
typedef struct {
 lm_rr_class classification;unsigned valid_records,slots;
 int pending,published;uint64_t generation;
 wr_identity target,records[32];
} lm_rr_result;
/* Caller supplies independently trusted binding, NOT data inferred from slots.
 * expected is codec-valid ordinal zero. lease_identity identifies the SAME C01
 * exclusion domain used by the dead owner; mapping is an integration precondition.
 *
 * The pinned C01 provider is frozen elsewhere in the repository and is not
 * modified by this adapter. Two of its weaknesses are contained here:
 *  - it opens the lease file with OPEN_ALWAYS, so a deleted or truncated lease
 *    would be silently re-created/re-initialised;
 *  - it caches generation/pending at acquire and its own check re-verifies only
 *    the 64-byte identity header.
 * Therefore the reader qualifies the lease namespace itself, before any lease
 * handle exists: the lease directory and the exactly-80-byte lease file are
 * pinned with deny-delete sharing, the 64-byte header must be bound to this
 * identity, the on-disk generation must equal expected_generation, and PENDING
 * must already be set. Every later check re-reads the whole 80-byte region from
 * disk under a reader-owned shared byte-range window over [0,80), which is
 * disjoint from the provider's own 4096/4097 admission locks, and refuses on any
 * drift between disk, the retained value and the provider cache.
 * Distinct refusal reasons: restart-lease-dir, restart-lease-dir-kind,
 * restart-lease-missing, restart-lease-empty, restart-lease-size,
 * restart-lease-kind, restart-lease-header, restart-lease-identity,
 * restart-lease-generation, restart-lease-pending, restart-lease-window,
 * restart-lease-disk-drift, restart-lease-cache-drift, restart-lease-state.
 * A failed wr_prepare releases every pin it already held before returning.
 * Byte-range locks cannot stop SetEndOfFile or memory-mapped writes; drift from
 * those is detected on the next check, and detection never clears PENDING.
 *
 * Serialized API. No SDK admission/COMMIT/lease-pending-clear operations exist.
 * Returns 1 once a retained reader object is available, including REFUSED
 * evidence. Lease-namespace or exclusive-acquire failure returns 0 and NULL.
 * Always inspect classification. */
int lm_rr_open(const WCHAR *lease_dir,const char lease_identity[49],
 uint64_t expected_generation,const WCHAR *private_root,
 const WCHAR *source_leaf,const WCHAR *public_leaf,const lm_wr_record *expected,
 unsigned slots,lm_rr **out,lm_rr_result *result,wr_error *);
int lm_rr_check(lm_rr *,wr_error *);
void lm_rr_close(lm_rr *);
#endif
