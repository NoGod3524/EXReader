/* SPDX-License-Identifier: MIT */
#include "windows_migration_host.h"
#include <windows.h>
#include <stdlib.h>
struct reader_migration_host {
  rmh_provider provider;
  DWORD owner;
  rmh_state state;
  uint64_t epoch;
  void *lease;
  int host_open;
  int worker_live;
  int callback;
};
static int owner(const reader_migration_host *h) {
  return h && h->owner == GetCurrentThreadId() && !h->callback;
}
reader_migration_host *rmh_create(const rmh_provider *p) {
  reader_migration_host *h;
  if (!p || p->version != 1 || !p->acquire_admission || !p->begin_exclusive ||
      !p->start_worker || !p->observe_worker || !p->cancel_worker ||
      !p->admit_reopen || !p->release_lease) return NULL;
  h = (reader_migration_host *)calloc(1, sizeof(*h));
  if (!h) return NULL;
  h->provider = *p;
  h->owner = GetCurrentThreadId();
  h->state = RMH_CLOSED;
  return h;
}
rmh_result rmh_acquire(reader_migration_host *h) {
  int ok;
  if (!owner(h) || h->state != RMH_CLOSED || h->lease) return RMH_REFUSED;
  h->callback = 1;
  ok = h->provider.acquire_admission(h->provider.context, &h->lease);
  h->callback = 0;
  if (!ok || !h->lease) {
    h->state = RMH_RECOVERY_REQUIRED;
    return RMH_REFUSED;
  }
  h->state = RMH_ADMITTED;
  return RMH_OK;
}
rmh_result rmh_opened(reader_migration_host *h, int success) {
  if (!owner(h) ||
      (h->state != RMH_ADMITTED && h->state != RMH_REOPEN_READY))
    return RMH_REFUSED;
  h->host_open = success != 0;
  h->state = success ? RMH_RUNNING : RMH_RECOVERY_REQUIRED;
  return success ? RMH_OK : RMH_REFUSED;
}
rmh_result rmh_request(reader_migration_host *h, uint64_t *epoch) {
  if (!owner(h) || !epoch || h->state != RMH_RUNNING ||
      h->epoch == UINT64_MAX) return RMH_REFUSED;
  ++h->epoch;
  *epoch = h->epoch;
  h->state = RMH_DRAINING;
  return RMH_OK;
}
rmh_result rmh_drained(reader_migration_host *h, uint64_t epoch, int all_closed) {
  int ok;
  if (!owner(h) || h->state != RMH_DRAINING || epoch != h->epoch)
    return RMH_REFUSED;
  if (!all_closed) return RMH_PENDING;
  h->host_open = 0;
  h->callback = 1;
  ok = h->provider.begin_exclusive(h->provider.context, h->lease);
  h->callback = 0;
  if (!ok) {
    h->state = RMH_RECOVERY_REQUIRED;
    return RMH_REFUSED;
  }
  /* A failed start may have created a worker: containment is uncertain until
   * observe confirms terminal, so it must never unlock by treating false as
   * "nothing started". */
  h->worker_live = 1;
  h->state = RMH_MIGRATING;
  h->callback = 1;
  ok = h->provider.start_worker(h->provider.context, h->lease, epoch);
  h->callback = 0;
  if (!ok) {
    h->state = RMH_RECOVERY_REQUIRED;
    return RMH_REFUSED;
  }
  return RMH_OK;
}
rmh_result rmh_observe(reader_migration_host *h, uint64_t epoch) {
  rmh_worker_outcome outcome;
  int terminal = 0, ok;
  if (!owner(h) || epoch != h->epoch || !h->worker_live ||
      (h->state != RMH_MIGRATING && h->state != RMH_RECOVERY_REQUIRED))
    return RMH_REFUSED;
  h->callback = 1;
  outcome = h->provider.observe_worker(h->provider.context, h->lease,
                                       epoch, &terminal);
  h->callback = 0;
  if (outcome == RMH_WORKER_RECOVERY_REQUIRED ||
      (outcome != RMH_WORKER_PENDING &&
       outcome != RMH_WORKER_ABORTED_CLEAN &&
       outcome != RMH_WORKER_COMMITTED_ACKNOWLEDGED))
    h->state = RMH_RECOVERY_REQUIRED;
  if (!terminal) return RMH_PENDING;
  h->worker_live = 0;
  /* Once uncertainty is latched (e.g. failed spawn), observing terminal only
   * permits safe shutdown, not in-process recovery or normal reopen. */
  if (h->state == RMH_RECOVERY_REQUIRED ||
      (outcome != RMH_WORKER_ABORTED_CLEAN &&
       outcome != RMH_WORKER_COMMITTED_ACKNOWLEDGED)) {
    h->state = RMH_RECOVERY_REQUIRED;
    return RMH_REFUSED;
  }
  h->callback = 1;
  ok = h->provider.admit_reopen(h->provider.context, h->lease, outcome);
  h->callback = 0;
  h->state = ok ? RMH_REOPEN_READY : RMH_RECOVERY_REQUIRED;
  return ok ? RMH_OK : RMH_REFUSED;
}
rmh_result rmh_cancel(reader_migration_host *h, uint64_t epoch) {
  int ok;
  if (!owner(h) || epoch != h->epoch || h->state != RMH_MIGRATING ||
      !h->worker_live) return RMH_REFUSED;
  h->callback = 1;
  ok = h->provider.cancel_worker(h->provider.context, h->lease, epoch);
  h->callback = 0;
  /* Provider may refuse cancellation at its commit barrier. Neither result
   * proves rollback, terminal containment, or permission to reopen. */
  return ok ? RMH_OK : RMH_REFUSED;
}
rmh_result rmh_host_closed(reader_migration_host *h) {
  if (!owner(h) || h->worker_live || h->state == RMH_MIGRATING)
    return RMH_REFUSED;
  h->host_open = 0;
  h->state = RMH_CLOSED;
  return RMH_OK;
}
rmh_result rmh_destroy(reader_migration_host *h) {
  if (!owner(h) || h->host_open || h->worker_live ||
      h->state == RMH_ADMITTED || h->state == RMH_REOPEN_READY)
    return RMH_REFUSED;
  if (h->lease) {
    h->callback = 1;
    h->provider.release_lease(h->provider.context, h->lease);
    h->callback = 0;
  }
  free(h);
  return RMH_OK;
}
rmh_state rmh_get_state(const reader_migration_host *h) {
  return owner(h) ? h->state : RMH_RECOVERY_REQUIRED;
}
int rmh_commands_allowed(const reader_migration_host *h) {
  return owner(h) && h->state == RMH_RUNNING && h->host_open;
}
uint64_t rmh_epoch(const reader_migration_host *h) {
  return owner(h) ? h->epoch : 0;
}
