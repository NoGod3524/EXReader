/* SPDX-License-Identifier: MIT */
#ifndef READER_SYNC_VIEW_H
#define READER_SYNC_VIEW_H
#include <reader_revisions.h>
#include <reader_session.h>
#ifdef __cplusplus
extern "C" {
#endif
#define READER_SYNC_VIEW_VERSION "0.1.0"
/* Hard upper bound of one captured snapshot's pending list and of row_limit. */
#define READER_SYNC_VIEW_MAX_ROWS ((size_t)100)
#define READER_SYNC_VIEW_DEFAULT_ROWS ((size_t)100)
#define READER_SYNC_VIEW_SHARD_COUNT 256u

typedef enum {READER_SYNC_VIEW_OK=0,READER_SYNC_VIEW_ARGUMENT,READER_SYNC_VIEW_MEMORY,
  READER_SYNC_VIEW_SESSION,READER_SYNC_VIEW_REVISIONS} reader_sync_view_status;
/* Mirrors the observed reader_session_state one-to-one. SWEEP_COMPLETE is one
 * finished 256-shard sweep and never "the whole library is synchronized". */
typedef enum {READER_SYNC_VIEW_IDLE=0,READER_SYNC_VIEW_SYNCING,READER_SYNC_VIEW_CANCELLING,
  READER_SYNC_VIEW_CANCELLED,READER_SYNC_VIEW_SWEEP_COMPLETE,READER_SYNC_VIEW_FAILED,
  READER_SYNC_VIEW_CLOSING,READER_SYNC_VIEW_CLOSED,READER_SYNC_VIEW_UNKNOWN} reader_sync_view_phase;
/* Fixed safe causes. Derived only from module status codes, never from module
 * text, a URL, a credential, a path, a title or a server body. */
typedef enum {READER_SYNC_VIEW_REASON_NONE=0,READER_SYNC_VIEW_REASON_NEEDS_CREDENTIALS,
  READER_SYNC_VIEW_REASON_OFFLINE,READER_SYNC_VIEW_REASON_TLS,READER_SYNC_VIEW_REASON_SERVER,
  READER_SYNC_VIEW_REASON_ACCOUNT,READER_SYNC_VIEW_REASON_STORAGE,READER_SYNC_VIEW_REASON_CONFLICT,
  READER_SYNC_VIEW_REASON_INTEGRITY,READER_SYNC_VIEW_REASON_LIMIT,READER_SYNC_VIEW_REASON_INTERNAL} reader_sync_view_reason;

typedef struct {
  size_t row_limit;     /* 0 = READER_SYNC_VIEW_DEFAULT_ROWS; otherwise 1..100. */
  int detect_conflicts; /* Nonzero: one reader_revision_heads call per distinct listed entity. */
} reader_sync_view_options;
typedef struct {
  reader_sync_view_status status;int session_status,revision_code;
  char message[96]; /* Fixed module text; no URL, secret, path or server body. */
} reader_sync_view_error;
typedef struct {
  reader_sync_view_phase phase;reader_sync_view_reason reason;
  int session_status,http_status,dav_code,revision_code;
  /* Session counters count OPERATIONS and per-step OBSERVATIONS, not distinct
   * records: a retried or failed step may count the same record again. */
  uint64_t attempt,completed_sweeps,operations,pushed_operations,pulled_operations,originals_verified_operations;
  uint64_t metadata_wait_observations,original_wait_observations,transfer_bytes;
  unsigned shard,completed_shards,shard_count;char cursor[104];
  int sweep_complete;   /* The last sweep reached shard 255. */
  int library_complete; /* Always zero, copied from the session's own flag. */
  int resumable;        /* CANCELLED/FAILED: the next start resumes the retained cursor. */
  int outbox_included;  /* Nonzero when a revisions handle supplied the pending list. */
  /* DISTINCT pending records in the listed page (not operations, not remaining
   * history). The outbox has no total-count or cursor API; a full page only
   * says more may exist. */
  size_t pending_records,retried_records,conflict_records;
  int more_may_exist;   /* The page filled row_limit: later queue rows may follow. */
  int conflicts_checked;
} reader_sync_view_summary;
typedef struct {
  char revision_id[33],entity_kind[16],operation[8]; /* Closed module tokens; no key, title or quote. */
  uint64_t bytes;int64_t attempts;int last_revision_code; /* 0 = none/unrecognized. */
  reader_sync_view_reason last_reason;int conflict; /* Concurrent heads for this entity. */
} reader_sync_view_row;
typedef struct reader_sync_view_snapshot reader_sync_view_snapshot;

/* Captures one immutable, read-only snapshot of session status plus a bounded
 * pending page. No product write, no network, no thread, no start/cancel, no
 * automatic retry, no ack. The snapshot owns all its memory, borrows nothing and
 * stays valid after the session is destroyed or the revisions handle is closed;
 * the caller releases it exactly once with reader_sync_view_release.
 *
 * Inputs: session is required. revisions may be NULL (session-only snapshot).
 * options may be NULL (100 rows, no conflict detection). out must be non-NULL;
 * *out is set to NULL on every failure. error may be NULL.
 *
 * Reads, in this order: reader_session_observe (one mutex-guarded copy on any
 * thread), then, when revisions is non-NULL, exactly one reader_revision_outbox
 * page of at most row_limit rows copied before any further call, then at most
 * row_limit distinct reader_revision_heads calls (each bounded to 4096 retained
 * revisions). These are separate reads, not one transaction: each is internally
 * consistent, the background worker may advance between them. Never use the
 * result to ack, retry or publish anything.
 *
 * Threading: with revisions non-NULL call on the thread that opened it and never
 * from inside one of its callbacks (reader_revisions rejects that reentry; this
 * then fails with READER_SYNC_VIEW_REVISIONS and revision_code READER_REV_OWNER,
 * leaving *out NULL). With revisions NULL the call is nonblocking apart from the
 * session mutex and any SQLite busy wait, and any thread may make it.
 *
 * Cost: bounded by row_limit<=100 rows (a few KiB) and at most 100 heads calls.
 * There is no cancellation: the work is already bounded and finishes; cancelling
 * a running sweep stays reader_session_cancel's job.
 *
 * Failure: *out stays NULL and no snapshot memory is retained. A conflict probe
 * that cannot be read fails the whole capture instead of reporting "no
 * conflict". Commit boundary: none, this call performs no write. */
reader_sync_view_status reader_sync_view_capture(reader_session *,reader_revisions *,
  const reader_sync_view_options *,reader_sync_view_snapshot **out,reader_sync_view_error *);
/* Immutable reads, any thread, concurrently, until release. Copies the summary;
 * out must be non-NULL. */
reader_sync_view_status reader_sync_view_summary_get(const reader_sync_view_snapshot *,reader_sync_view_summary *);
/* Copies up to capacity rows from offset in queue order (the order
 * reader_revision_outbox returned them; no sort, no cursor across captures).
 * rows, copied and capacity are required and capacity must be at least 1; a
 * larger capacity copies only the rows that exist. offset > count is ARGUMENT;
 * offset == count copies zero rows. The pending list
 * is paged only over this snapshot: after ack/retry capture again. */
reader_sync_view_status reader_sync_view_rows(const reader_sync_view_snapshot *,size_t offset,
  reader_sync_view_row *rows,size_t capacity,size_t *copied);
/* Idempotent for a NULL pointer target: release(&NULL) and release of an
 * already released pointer both succeed. Not safe while another thread reads the
 * same snapshot. */
reader_sync_view_status reader_sync_view_release(reader_sync_view_snapshot **);
/* Static ASCII; never NULL, also for out-of-range enum values. */
const char *reader_sync_view_phase_text(reader_sync_view_phase);
const char *reader_sync_view_reason_text(reader_sync_view_reason);
#ifdef __cplusplus
}
#endif
#endif
