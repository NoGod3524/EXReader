/* SPDX-License-Identifier: MIT */
#ifndef EXR_WEBDAV_CLEANUP_H
#define EXR_WEBDAV_CLEANUP_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/*
 * EXReaderWebDAVCleanup 0.1.0, API v1 (POSIX only).
 *
 * A dedicated namespace (root directory) owned by geteuid() with no group or
 * other permission bits.  The root keeps a 4160-byte receipt (.receipt) that
 * records up to 64 lifetime transaction slots; slots are never reused.  An
 * open root holds a non-blocking exclusive flock on .lock for its whole
 * lifetime; process death releases it.  Cooperative processes only: handles
 * must not be shared, forked or used concurrently, and no other writer may
 * modify the namespace.  Local filesystems only (flock and link semantics).
 *
 * States: RESERVED is committed before the transaction directory is created;
 * OWNED records the directory and payload inodes; SEALED means the payload was
 * flushed and its write handle closed; PUBLISH_INTENT is committed before the
 * no-replace link; PUBLISHED after the destination directory was flushed;
 * CLEANED after the alias and the transaction directory were removed.
 *
 * v1 amendments to the 2026-10-31 handoff contract:
 *  1. A publish whose link fails definitely (EEXIST, EXDEV, ENOENT, ...)
 *     rewrites the slot back to SEALED and returns EXISTS or IO with
 *     published=0.  Only an unknown link outcome stays in PUBLISH_INTENT.
 *  2. open_at discards a residual .receipt.next only when .receipt is valid
 *     and .receipt.next is a valid receipt of the same root whose generation
 *     is exactly one more; any other residue fails closed with REFUSED.
 *  3. Inodes are compared across opens; device numbers only against the
 *     root's current st_dev (same filesystem), never against a stored value.
 *  4. Receipt layout is fixed little-endian: 64-byte header, 64 slots of 64
 *     bytes, CRC-32 (IEEE) over the whole image with the CRC field zeroed.
 *
 * Non-goals of v1: RESERVED and PUBLISH_INTENT slots are never reclaimed and
 * the 64-slot lifetime is finite, so product wiring needs a root rotation
 * protocol.  Residue that was never recorded in a receipt is never adopted.
 */

typedef struct exr_wc_root exr_wc_root;
typedef struct exr_wc_tx exr_wc_tx;

typedef enum {
  EXR_WC_OK = 0,
  EXR_WC_ARGUMENT = 1,
  EXR_WC_IO = 2,
  EXR_WC_BUSY = 3,
  EXR_WC_REFUSED = 4,
  EXR_WC_LIMIT = 5,
  EXR_WC_EXISTS = 6,
  EXR_WC_UNCERTAIN = 7
} exr_wc_status;

typedef enum {
  EXR_WC_RESERVED = 1,
  EXR_WC_OWNED = 2,
  EXR_WC_SEALED = 3,
  EXR_WC_PUBLISH_INTENT = 4,
  EXR_WC_PUBLISHED = 5,
  EXR_WC_CLEANED = 6
} exr_wc_state;

typedef struct {
  uint32_t slot, state;
  uint64_t bytes, directory_device, directory_inode;
  uint64_t payload_device, payload_inode;
  char transaction_id[33];
} exr_wc_info;

/* cleanup_pending=1: the slot needs recovery instead of a normal cleanup. */
typedef struct {
  int published, cleanup_pending, receipt_uncertain, native_error;
} exr_wc_publish_result;

typedef struct {
  int removed, pending, receipt_uncertain, native_error;
} exr_wc_cleanup_result;

typedef struct {
  uint32_t inspected, cleaned, pending, refused, next_slot, total_slots;
  int receipt_uncertain, native_error;
} exr_wc_recovery_report;

/* Leaves are 1-120 ASCII bytes: [A-Za-z0-9_-] then also '.'.  UUIDs and
 * transaction ids are 32 lowercase hex characters. */
exr_wc_status exr_wc_create_at(int parent_fd, const char *leaf,
                               exr_wc_root **out, char root_uuid[33]);
exr_wc_status exr_wc_open_at(int parent_fd, const char *leaf,
                             const char *expected_uuid, exr_wc_root **out);

/* At most one active transaction per root.  The borrowed fd belongs to the
 * component: write the payload through it, never close, dup or fork it.  It
 * is closed by seal, abandon cleanup or tx_close.  A failed begin returns
 * out=NULL, borrowed_fd=-1 and may leave a RESERVED slot behind. */
exr_wc_status exr_wc_begin(exr_wc_root *root, exr_wc_tx **out,
                           int *borrowed_fd);
exr_wc_status exr_wc_seal(exr_wc_tx *tx);
/* After a successful link the result is OK/published=1 even if a later
 * flush or receipt write fails; that is reported by receipt_uncertain and
 * cleanup_pending and stops further mutation of the root. */
exr_wc_status exr_wc_publish_at(exr_wc_tx *tx, int destination_fd,
                                const char *leaf,
                                exr_wc_publish_result *result);
/* PUBLISHED only, or OWNED/SEALED with abandon_unpublished=1.  RESERVED and
 * PUBLISH_INTENT are always REFUSED.  CLEANED is an idempotent OK. */
exr_wc_status exr_wc_cleanup(exr_wc_tx *tx, int abandon_unpublished,
                             exr_wc_cleanup_result *result);
exr_wc_status exr_wc_inspect(exr_wc_root *root, uint32_t slot,
                             exr_wc_info *info);
/* Requires no active transaction, 1 <= maximum <= 64, start <= slot count.
 * Only PUBLISHED slots are cleaned; every other unfinished state counts as
 * pending.  Per-slot pending/refused still return OK: check the counters. */
exr_wc_status exr_wc_recover(exr_wc_root *root, uint32_t start,
                             uint32_t maximum,
                             exr_wc_recovery_report *report);
/* Releases resources only: no cleanup, the root lock stays held. */
exr_wc_status exr_wc_tx_close(exr_wc_tx **tx);
/* BUSY while a transaction is open; NULL is an idempotent OK. */
exr_wc_status exr_wc_close(exr_wc_root **root);

#ifdef __cplusplus
}
#endif

#endif
