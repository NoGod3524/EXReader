/* SPDX-License-Identifier: MIT */
#ifndef READER_SESSION_H
#define READER_SESSION_H
#include <reader_sync.h>
#ifdef __cplusplus
extern "C" {
#endif
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
#define READER_SESSION_VERSION "0.2.0"
#else
#define READER_SESSION_VERSION "0.1.0"
#endif
typedef enum {READER_SESSION_OK=0,READER_SESSION_ARGUMENT,READER_SESSION_BUSY,
  READER_SESSION_IO,READER_SESSION_ACCOUNT,READER_SESSION_SYNC} reader_session_status;
typedef enum {READER_SESSION_IDLE=0,READER_SESSION_RUNNING,READER_SESSION_CANCELLING,
  READER_SESSION_CANCELLED,READER_SESSION_FINISHED,READER_SESSION_FAILED,
  READER_SESSION_CLOSING,READER_SESSION_CLOSED} reader_session_state;
typedef struct reader_session reader_session;
typedef struct {
  const char *product_path,*private_directory,*original_directory,*account_id;
  exr_webdav_config dav;
} reader_session_config;
typedef struct {
  reader_session_state state;
  reader_session_status status;
  uint64_t attempt,completed_sweeps,steps,pushed,pulled,originals_verified;
  uint64_t pending_metadata_observations,pending_original_observations,transfer_bytes;
  unsigned shard,completed_shards;
  char after[104];
  reader_sync_error error; /* Fixed module messages; no URL, secret or server body. */
  int full_library_complete; /* Always zero: later/earlier inserts need another sweep. */
} reader_session_snapshot;
/* Copies all strings, including session-only Authorization. No credentials
 * are persisted. One owned background worker opens/calls/closes DAV and the
 * independent product database; no SDK pointer or UI callback crosses it.
 * Directories must already exist and remain private/stable until CLOSED.
 * Staged originals use <sha256>.<format>; prepare immutable files on the SDK
 * owner before start, release its borrowed source, then start the network.
 * Existing reader_sync verifies length/hash and snapshots before publication. */
reader_session_status reader_session_create(const reader_session_config *,reader_session **);
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
/* Creates the same owner worker with explicit immutable raw store/sync
   capability. Existing catalog/schema and retained wire are not migrated. */
reader_session_status reader_session_create_raw_v3(const reader_session_config *,reader_session **);
#endif
/* Nonblocking: start/retry one 256-shard sweep. A failed/cancelled sweep
 * resumes its last successful cursor; FINISHED starts a fresh sweep at zero.
 * No overlapping requests or automatic retry loop. Counters count operations,
 * not distinct records; failed steps may have committed durable partial work. */
reader_session_status reader_session_start(reader_session *);
reader_session_status reader_session_cancel(reader_session *);
reader_session_status reader_session_observe(reader_session *,reader_session_snapshot *);
/* Nonblocking cancellation plus shutdown. Network timeouts bound in-flight
 * calls. Poll CLOSED, then destroy; destroy returns BUSY before CLOSED and
 * leaves the pointer intact. All callers must stop using it before destroy. */
reader_session_status reader_session_request_close(reader_session *);
reader_session_status reader_session_destroy(reader_session **);
/* A product-path-adjacent private binding locks the store to this UUID and
 * exact root URL across processes/restarts. A different account/root is
 * refused before any network traffic; never silently rebind a local library.
 * The module retains history/outbox, performs no metadata projection, SDK
 * import/navigation or remote GC. Host projection/resolve remains explicit. */
#ifdef __cplusplus
}
#endif
#endif
