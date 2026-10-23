/* SPDX-License-Identifier: MIT */
#ifndef READER_SYNC_H
#define READER_SYNC_H
#include <reader_revisions.h>
#include <exr_webdav.h>
#ifdef __cplusplus
extern "C" {
#endif
typedef enum {READER_SYNC_OK=0,READER_SYNC_ARGUMENT,READER_SYNC_IO,READER_SYNC_DAV,
  READER_SYNC_REVISION,READER_SYNC_HASH,READER_SYNC_CANCELLED,READER_SYNC_LIMIT} reader_sync_status;
typedef struct {reader_sync_status code;int dav_code,revision_code,http_status;char message[160];} reader_sync_error;
/* Called on the host worker for pending book references. Supply a private
   original path matching the already-verified book history, or return nonzero
   when local bytes are unavailable. The module then verifies the existing
   remote original, or keeps the entry pending if absent. No credentials or
   SDK handles enter the module. */
typedef int (*reader_sync_original_fn)(void *,const char *book_key,char *utf8_path,size_t capacity);
typedef struct {
  exr_webdav_client *dav;reader_revisions *revisions;const char *private_directory;
  reader_sync_original_fn original;void *context;
} reader_sync_config;
typedef struct reader_sync reader_sync;
typedef struct {
  unsigned shard,next_shard,shard_count;
  char after[104]; /* Last processed leaf in this shard; empty when complete. */
  size_t pushed,pulled,originals_verified,pending_metadata,pending_local_original;
  size_t remaining_in_shard;int shard_complete;
  int full_library_complete; /* Always zero: host tracks full 256-shard sweeps. */
} reader_sync_report;
reader_sync_status reader_sync_create(const reader_sync_config *,reader_sync **,reader_sync_error *);
void reader_sync_free(reader_sync *);
/* One owning worker, no reentry. A step pushes at most limit (1..100) pending
   entries and processes at most limit sorted leaves from one selected shard.
   after is empty or a prior report cursor. Missing directories are empty only
   for this scan; they never delete local history. Repeat all 256 shards, then
   restart to discover concurrent insertions preceding a cursor. Every shard
   is bounded to 2000 entries / 4 MiB; overflow rejects rather than truncates.
   Pending metadata is retained via revision_receive and retried next sweep.
   No projection/SDK/current-reading mutation or remote garbage collection. */
reader_sync_status reader_sync_step(reader_sync *,unsigned shard,const char *after,size_t limit,
  const exr_webdav_control *,reader_sync_report *,reader_sync_error *);
#ifdef __cplusplus
}
#endif
#endif
