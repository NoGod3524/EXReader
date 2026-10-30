/* SPDX-License-Identifier: MIT */
#ifndef LM_WIN_LEASE_H
#define LM_WIN_LEASE_H
#ifndef _WIN32
#error Windows-only admission lease
#endif
#ifndef _WIN32_WINNT
#define _WIN32_WINNT 0x0A00
#endif
#include <windows.h>
#include <stdint.h>
/* Cross-process shared-lifetime / admit-reopen lease keyed by a full49 native
 * identity text (48 lowercase hex + NUL; never truncated, never prefix-matched).
 *
 * Mechanism: one lease file "<identity>.lease" inside a caller-supplied private
 * lease directory. The kernel owns the lock state: a byte-range lock at offset
 * 4096 (shared or exclusive, per open handle) and an open file/directory handle
 * without FILE_SHARE_DELETE, so the lease file and its directory cannot be
 * renamed, deleted or replaced while any holder lives. Process death, including
 * TerminateProcess, releases the lock; nothing is inferred from file presence.
 * Shared and exclusive are mutually exclusive across processes AND across
 * handles of one process. There is no atomic upgrade/downgrade: release, then
 * acquire the other mode; contention is LM_WL_BUSY, never a silent retry.
 * Lease state never grants migration admission, SDK open, or commit
 * acknowledgement; it only reports whether the caller holds custody.
 * A lease object is not thread-safe. */
typedef enum { LM_WL_OK=0, LM_WL_INVALID=1, LM_WL_BUSY=2, LM_WL_STALE=3,
               LM_WL_REFUSED=4, LM_WL_NATIVE=5, LM_WL_LOST=6 } lm_wl_status;
typedef enum { LM_WL_SHARED=1, LM_WL_EXCLUSIVE=2 } lm_wl_mode;
typedef struct { DWORD native; const char *reason; } lm_wl_error;
typedef struct lm_wl_lease lm_wl_lease;
/* timeout_ms 0 = one attempt. Only lock contention yields BUSY after timeout. */
lm_wl_status lm_wl_acquire(const WCHAR *lease_dir, const char identity[49],
                           lm_wl_mode mode, DWORD timeout_ms,
                           lm_wl_lease **out, lm_wl_error *error);
/* Re-verifies handle identity, link count, header binding. LOST/REFUSED => stop. */
lm_wl_status lm_wl_check(lm_wl_lease *lease, lm_wl_error *error);
/* Generation observed at acquire; changes only through lm_wl_exclusive_bump. */
uint64_t lm_wl_generation(const lm_wl_lease *lease);
/* Admit-reopen gate: STALE when the publisher bumped since the admitted value. */
lm_wl_status lm_wl_require_generation(const lm_wl_lease *lease, uint64_t admitted);
/* Exclusive holders only; persisted before return. Publisher calls this after
 * its own publication is verified, so shared admissions made earlier go STALE. */
lm_wl_status lm_wl_exclusive_bump(lm_wl_lease *lease, uint64_t *generation,
                                  lm_wl_error *error);
void lm_wl_release(lm_wl_lease *lease);
#endif
