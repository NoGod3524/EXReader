/* SPDX-License-Identifier: MIT */
#ifndef EXR_WEBDAV_MANAGED_H
#define EXR_WEBDAV_MANAGED_H
#include "exr_webdav.h"
#ifdef __cplusplus
extern "C" {
#endif
#define EXR_WEBDAV_MANAGED_VERSION "0.1.0"
#define EXR_WEBDAV_MANAGED_ROOT_LIMIT 16
/* Explicit Linux capability. A profile owns a permanent 16-root registry.
 * Each root has 64 lifetime slots; no slot/root retirement or legacy adoption.
 * All client calls, including observe/free, belong to its enabling worker.
 * Snapshot values are copies, contain no handles or credentials, and retain
 * warnings for every root. status uses exr_wc_status numeric values (0..7).
 * published describes the latest attempted download, independently of cleanup.
 * cleanup_pending is the aggregate number of retained unfinished/unbound slots.
 */
typedef struct {
  char leaf[38], uuid[33];
  unsigned slots, pending, refused;
  int status, receipt_uncertain, unbound;
} exr_webdav_managed_root_snapshot;
typedef struct {
  int enabled, status, published, receipt_uncertain, native_error, capacity_exhausted, recovery_running;
  unsigned roots, cleanup_pending, cleaned;
  exr_webdav_managed_root_snapshot root[EXR_WEBDAV_MANAGED_ROOT_LIMIT];
} exr_webdav_managed_snapshot;
/* A failed enable remains managed and cannot silently use legacy staging.
 * profile must already be a private, absolute, canonical local directory.
 * Registry mutations use exclusive next + file fsync + rename + directory
 * fsync; any residual registry.next refuses further writes without deleting it.
 * ALLOCATING without an expected UUID is retained, never adopted.
 */
exr_webdav_status exr_webdav_managed_enable(exr_webdav_client *,const char *profile,exr_webdav_error *);
int exr_webdav_managed_enabled(const exr_webdav_client *);
exr_webdav_status exr_webdav_managed_observe(const exr_webdav_client *,exr_webdav_managed_snapshot *);
/* Offline, bounded recovery: <=16 registered roots, <=64 slots each.
 * All handles are created and closed within this call on the calling worker.
 * Does not access the SDK or network. Return value is the snapshot status.
 */
int exr_webdav_managed_recover_profile(const char *profile,exr_webdav_managed_snapshot *);
/* Linux owned upload snapshots. The client and snapshot stay on the enabling
 * worker; only one snapshot may be active. begin is the explicit opt-in that
 * atomically upgrades a v1 registry to v2 purpose records when it first needs
 * an S root. Download D roots retain their UUID and recovery semantics.
 * Total capacity remains 16 roots x 64 lifetime slots across both purposes.
 * Old binaries refuse v2. No downgrade or restoration of old registry is safe.
 * Borrowed write fd expires at seal; borrowed O_RDONLY fd expires at close.
 * Use pread; do not close/dup/fork borrowed descriptors or reenter the client.
 * Close attempts cleanup and always releases the handle; non-OK means retained
 * registered cleanup work, not rollback of a remotely committed PUT.
 * Freeing the client while a snapshot is active is refused.
 */
typedef struct exr_webdav_owned_snapshot exr_webdav_owned_snapshot;
exr_webdav_status exr_webdav_snapshot_begin(exr_webdav_client *,
  exr_webdav_owned_snapshot **,int *borrowed_write_fd,exr_webdav_error *);
exr_webdav_status exr_webdav_snapshot_seal(exr_webdav_owned_snapshot *,
  uint64_t expected_bytes,int *borrowed_read_fd,exr_webdav_error *);
exr_webdav_status exr_webdav_snapshot_close(exr_webdav_owned_snapshot **,exr_webdav_error *);
#ifdef __cplusplus
}
#endif
#endif
