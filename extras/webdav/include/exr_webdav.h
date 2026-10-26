/* SPDX-License-Identifier: MIT */
#ifndef EXR_WEBDAV_H
#define EXR_WEBDAV_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
#define EXR_WEBDAV_VERSION "0.2.0"
typedef enum {
  EXR_DAV_OK=0, EXR_DAV_ARGUMENT, EXR_DAV_MEMORY, EXR_DAV_IO,
  EXR_DAV_TLS, EXR_DAV_HTTP, EXR_DAV_AUTH, EXR_DAV_CANCELLED,
  EXR_DAV_LIMIT, EXR_DAV_FORMAT, EXR_DAV_REDIRECT, EXR_DAV_EXISTS
} exr_webdav_status;
typedef struct { exr_webdav_status code; int http_status; char message[160]; } exr_webdav_error;
typedef struct {
  /* An HTTPS collection URL ending in '/'. DNS/IPv4 hosts only in v0.1.
     Query, fragment, userinfo and ambiguous path encodings are refused. */
  const char *root_url;
  /* Optional complete Authorization value. Bound to this client's origin.
     Borrowed only during create; never logged, persisted or sent elsewhere.
     Host obtains it from platform secure storage or the current session. */
  const char *authorization;
  uint64_t max_download_bytes; /* 0 = 128 MiB; may only lower that ceiling. */
  size_t max_listing_bytes;    /* 0 = 4 MiB; may only lower that ceiling. */
  size_t max_entries;          /* 0 = 2000; may only lower that ceiling. */
  unsigned timeout_ms;         /* 0 = 30000; max 120000; deadline checked at I/O boundaries. */
} exr_webdav_config;
typedef struct {
  int (*cancelled)(void *context);
  void (*progress)(void *context, uint64_t received_bytes);
  void *context;
} exr_webdav_control;
typedef struct exr_webdav_client exr_webdav_client;
typedef struct {
  char *resource; /* Root-relative, encoded path; folders end in '/'. */
  char *display_name, *etag;
  uint64_t bytes;
  int has_size, collection;
} exr_webdav_entry;
typedef struct { exr_webdav_entry *entries; size_t count; } exr_webdav_listing;
typedef struct { uint64_t bytes; int published; } exr_webdav_download;
exr_webdav_status exr_webdav_create(const exr_webdav_config *, exr_webdav_client **, exr_webdav_error *);
void exr_webdav_free(exr_webdav_client *);
void exr_webdav_listing_free(exr_webdav_listing *);
/* Synchronous, one host worker at a time. collection is "" for the root or a
   prior entry's resource. Depth:1 only; no recursion and no remote mutation.
   Fresh/zero output required. Failure returns an empty listing. */
exr_webdav_status exr_webdav_list(exr_webdav_client *, const char *collection,
  const exr_webdav_control *, exr_webdav_listing *, exr_webdav_error *);
/* Stream into a new same-directory temporary file, then publish without
   replacing any existing destination. Host supplies a stable private directory
   and plain UTF-8 filename; a remote title is never a local path. No whole-book
   allocation. Failed/cancelled transfers remove their temporary file.
   Once publication commits, OK/published wins over later cancellation.
   Pass the published file to the existing exr_sideload_import_file on its owner
   queue; this source module does not open SDK handles or write catalog rows.
   Cancellation is observed at I/O boundaries; a blocking native HTTPS call is
   bounded by the remaining transfer timeout, not an immediate interrupt. */
exr_webdav_status exr_webdav_download_file(exr_webdav_client *, const char *resource,
  const char *private_directory, const char *filename, const exr_webdav_control *,
  exr_webdav_download *, exr_webdav_error *);
/* As above, additionally observes each successfully written body chunk in
   order on the caller's thread. The borrowed bytes are valid only during the
   callback. The observer must not reenter the client, retain the buffer, or
   fail; its partial state must be discarded unless the call returns OK. */
typedef void (*exr_webdav_write_observer)(void *context, const void *bytes, size_t size);
exr_webdav_status exr_webdav_download_observed(exr_webdav_client *, const char *resource,
  const char *private_directory, const char *filename, const exr_webdav_control *,
  exr_webdav_write_observer, void *observer_context, exr_webdav_download *, exr_webdav_error *);
/* Optional immutable-sync primitives. No write follows a redirect, even within
   the configured root. MKCOL accepts 201 or pre-existing 405; callers must
   subsequently prove the collection when using it. PUT streams a regular
   private file with its exact expected length and If-None-Match: *. A 412
   returns EXISTS and never authorizes ack: caller must GET/verify bytes/hash.
   Successful creation still requires caller identity verification before ack. */
exr_webdav_status exr_webdav_make_collection(exr_webdav_client *,const char *collection,
  const exr_webdav_control *,exr_webdav_error *);
exr_webdav_status exr_webdav_publish_file(exr_webdav_client *,const char *resource,
  const char *private_file,uint64_t expected_bytes,const exr_webdav_control *,exr_webdav_error *);
#ifdef __cplusplus
}
#endif
#endif
