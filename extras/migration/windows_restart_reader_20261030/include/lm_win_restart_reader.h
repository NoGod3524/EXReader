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
 int pending,published,lease_restored;uint64_t generation;
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
 * disjoint from the provider's own 4096/4097 admission locks, and requires it to
 * be byte-identical to the snapshot taken before the acquire, refusing on any
 * drift between disk, the retained value and the provider cache.
 * The acquire window itself is not closable: the provider must open the file for
 * write, so in-place truncation cannot be denied, and its OPEN_ALWAYS branch would
 * re-initialise a zero-length file, clearing PENDING. The reader therefore settles
 * the snapshot again immediately after acquiring, under its own window. When the
 * settled bytes are a fresh initialisation (generation zero, PENDING cleared) the
 * exact pre-acquire 80 bytes are written back through the pinned handle, because a
 * legitimate commit from generation zero would have left generation one and cannot
 * produce that shape; the reader then refuses custody with
 * restart-lease-window-restored but leaves the domain's PENDING isolation intact.
 * Any other movement refuses with restart-lease-window-race. Both retentions keep
 * the exclusive lease held, so shared admission stays closed until the caller
 * closes the object; the object is only released early when no lease was ever
 * acquired.
 * The pin therefore carries write access, used only for that proven repair: a
 * shared byte-range lock over [0,80) blocks every other handle, so a repair from a
 * second handle cannot work. No other path in this adapter writes the lease.
 * Residual: a re-initialisation that cannot be proven from the bytes, or the
 * window before this adapter ever saw the file, cannot be repaired here, and the
 * provider still owns that defect.
 * Distinct refusal reasons: restart-lease-dir, restart-lease-dir-kind,
 * restart-lease-missing, restart-lease-empty, restart-lease-size,
 * restart-lease-kind, restart-lease-header, restart-lease-identity,
 * restart-lease-generation, restart-lease-pending, restart-lease-window,
 * restart-lease-window-restored, restart-lease-window-race,
 * restart-lease-restore, restart-lease-disk-drift,
 * restart-lease-cache-drift, restart-lease-state.
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
/* Test seam only, for deterministic reproduction of the acquire window. The hook
 * runs exactly between the lease pre-validation and the provider acquire and
 * receives the pinned lease path; production callers leave it NULL, and with no
 * hook installed the sequence is byte-for-byte the shipped one. It exists so the
 * interleaving can be injected instead of being argued about. */
void lm_rr_set_window_probe(void (*fn)(const WCHAR *lease_path));
#endif
