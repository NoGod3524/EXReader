/* SPDX-License-Identifier: MIT
 * Private, opt-in host lifecycle controller. NOT a migration provider.
 * All calls and provider callbacks run on the creating UI thread. Callbacks
 * must return promptly; start/observe supervise a separate owned worker.
 * No callback may reenter this controller. Worker messages carry epoch only;
 * only the owner calls observe. Never pass this object to a worker thread.
 */
#ifndef READER_WINDOWS_MIGRATION_HOST_H
#define READER_WINDOWS_MIGRATION_HOST_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
typedef struct reader_migration_host reader_migration_host;
typedef enum {
  RMH_CLOSED, RMH_ADMITTED, RMH_RUNNING, RMH_DRAINING,
  RMH_MIGRATING, RMH_REOPEN_READY, RMH_RECOVERY_REQUIRED
} rmh_state;
typedef enum {
  RMH_ERROR = -1, RMH_REFUSED = 0, RMH_OK = 1, RMH_PENDING = 2
} rmh_result;
typedef enum {
  RMH_WORKER_PENDING,
  RMH_WORKER_ABORTED_CLEAN,
  RMH_WORKER_COMMITTED_ACKNOWLEDGED,
  RMH_WORKER_RECOVERY_REQUIRED
} rmh_worker_outcome;
/* The provider owns the opaque lease and all filesystem protocol decisions.
 * acquired lease is shared admission tied to exact target identity, namespace,
 * and compatible SDK; retained until no host/worker handle can use the target.
 * begin_exclusive is legal only with every host owner drained and closed.
 * terminal must prove the real worker and contained descendants stopped.
 * ABORTED_CLEAN/COMMITTED_ACKNOWLEDGED are claims requiring fresh admit_reopen;
 * exit status, cancellation request, hash equality or marker absence are NOT
 * independent admission evidence. Uncertain files/leases are never deleted.
 * admit_reopen independently verifies target+namespace+SDK and converts to
 * shared admission with no unlocked gap. A false result stays closed.
 * No implementation of this facade ships in this slice.
 */
typedef struct {
  unsigned version; /* exactly 1 */
  void *context;
  int (*acquire_admission)(void *, void **lease);
  int (*begin_exclusive)(void *, void *lease);
  int (*start_worker)(void *, void *lease, uint64_t epoch);
  rmh_worker_outcome (*observe_worker)(void *, void *lease,
                                      uint64_t epoch, int *terminal);
  int (*cancel_worker)(void *, void *lease, uint64_t epoch);
  int (*admit_reopen)(void *, void *lease, rmh_worker_outcome);
  void (*release_lease)(void *, void *lease);
} rmh_provider;
/* creation returns CLOSED; missing/incomplete providers are refused.
 * The initial host open must happen only after acquire and before opened.
 * A failed open is reported by opened(..., 0), retaining fail-closed state.
 */
reader_migration_host *rmh_create(const rmh_provider *);
rmh_result rmh_acquire(reader_migration_host *);
rmh_result rmh_opened(reader_migration_host *, int success);
rmh_result rmh_request(reader_migration_host *, uint64_t *epoch);
/* Caller must freeze all enqueue/timer/receive paths, respect existing commit
 * barriers, join jobs, release pending/discard/candidate/session/module owners
 * and close SDK handles. A cancel flag is not this proof. False stays DRAINING.
 * drained(...,1) records that no host handles remain and starts the worker.
 */
rmh_result rmh_drained(reader_migration_host *, uint64_t epoch, int all_closed);
rmh_result rmh_observe(reader_migration_host *, uint64_t epoch);
rmh_result rmh_cancel(reader_migration_host *, uint64_t epoch);
/* Explicit host shutdown acknowledgement. Cannot release while worker
 * containment is unconfirmed. It does not cancel, kill, unlink or recover.
 */
rmh_result rmh_host_closed(reader_migration_host *);
rmh_result rmh_destroy(reader_migration_host *);
rmh_state rmh_get_state(const reader_migration_host *);
int rmh_commands_allowed(const reader_migration_host *);
uint64_t rmh_epoch(const reader_migration_host *);
#ifdef __cplusplus
}
#endif
#endif
