/* SPDX-License-Identifier: MIT */
#ifndef READER_CLOUD_IMPORT_H
#define READER_CLOUD_IMPORT_H
#include <stddef.h>
#include <stdint.h>
#include <exr/library.h>
#include <exr_sideload.h>
#include <exr_webdav.h>
#ifdef __cplusplus
extern "C" {
#endif

#define READER_CLOUD_IMPORT_VERSION "0.1.0"
/* Same ceilings as EXReaderSideload: streaming formats (EPUB, CBZ, PDF) and
   32 MiB bounded-memory reflow formats. A request may lower, never raise. */
#define READER_CLOUD_STREAM_LIMIT EXR_SIDELOAD_STREAM_LIMIT
#define READER_CLOUD_MEMORY_LIMIT EXR_SIDELOAD_MEMORY_LIMIT
#define READER_CLOUD_MAX_RESOURCE_BYTES 4096u
#define READER_CLOUD_MAX_NAME_BYTES 1024u

/* Two independently callable synchronous phases; the package creates no
   thread, timer or resident task.
     1. reader_cloud_download: network worker only. Uses a borrowed
        exr_webdav_client, never an exr_library or any SDK pointer, and writes
        one new private staging file. No product directory, no catalog row.
     2. reader_cloud_import: the borrowed library's SDK owner only. Uses no
        WebDAV client or network. Serialize it with all other use of the library.
   The opaque reader_cloud_staged value is plain data and may be handed from the
   network worker to the SDK owner; one thread uses it at a time. */
typedef enum {
  READER_CLOUD_OK = 0,
  READER_CLOUD_ARGUMENT,
  READER_CLOUD_MEMORY,
  READER_CLOUD_IO,        /* staging file unreadable, missing or unwritable */
  READER_CLOUD_CANCELLED, /* stopped before any SDK commit */
  READER_CLOUD_REMOTE,    /* WebDAV failure: see webdav_code / http_status */
  READER_CLOUD_LENGTH,    /* bytes differ from the length the host expected */
  READER_CLOUD_LIMIT,     /* above the format ceiling or the request limit */
  READER_CLOUD_CORRUPT,   /* staged bytes changed between the two phases */
  READER_CLOUD_IMPORT     /* the SDK rejected the book: see sdk_code */
} reader_cloud_status;

typedef struct {
  reader_cloud_status code;
  exr_webdav_status webdav_code; /* meaningful for READER_CLOUD_REMOTE */
  int http_status;               /* HTTP status when the server supplied one */
  exr_status sdk_code;           /* meaningful for READER_CLOUD_IMPORT */
  char message[192];             /* diagnostic only; never contains credentials */
} reader_cloud_error;

/* Synchronous callbacks on the calling thread. cancelled is polled at I/O
   boundaries and every 64 KiB of staged-file verification; progress receives
   bytes received so far. Neither callback may call back into this package, the
   client or the library. */
typedef struct {
  int (*cancelled)(void *context);
  void (*progress)(void *context, uint64_t received_bytes);
  void *context;
} reader_cloud_control;

typedef struct {
  size_t struct_size;
  /* Root-relative resource exactly as returned in exr_webdav_entry.resource.
     Borrowed for the call; 1..READER_CLOUD_MAX_RESOURCE_BYTES. */
  const char *resource;
  /* Remote display name, UTF-8. Borrowed for the call, copied into the staged
     value. It names the book for the user and supplies the extension hint when
     format is EXR_CUSTOM. It is never a local path component. */
  const char *display_name;
  /* EXR_CUSTOM derives the format from display_name's extension (epub pdf cbz
     txt html htm fb2 docx rtf mobi azw azw3). Anything else must be one of the
     nine importable formats. The SDK still validates the bytes at import. */
  exr_format format;
  /* 0 = unknown. Otherwise the length the listing reported: a larger value is
     refused before any network request, and any other received length fails
     with READER_CLOUD_LENGTH after the staging file is removed. */
  uint64_t expected_bytes;
  /* 0 selects the format ceiling. A nonzero value may only lower it. The
     client's own max_download_bytes still applies. */
  uint64_t max_bytes;
  /* Existing app-private directory, stable for the call and controlled by the
     host. Required. The file name is generated here ("cloud-<hex>.<ext>"). */
  const char *staging_dir;
  reader_cloud_control control;
} reader_cloud_request;

/* Opaque. Owns the staging file until imported or discarded. */
typedef struct reader_cloud_staged reader_cloud_staged;

void reader_cloud_request_init(reader_cloud_request *request);

/* Phase 1. client is borrowed and must not be used concurrently by the caller;
   this call performs one exr_webdav_download_file. On OK *staged is a new
   value owning a published, complete, SHA-256-recorded regular file; free it
   with reader_cloud_import or reader_cloud_staged_discard. On any other
   status *staged is NULL, the temporary and any partial staging file are
   removed, and the client remains usable for a retry. Redirects, TLS, 401 and
   same-origin credential rules are exr_webdav's; a blocking native HTTPS call
   is bounded by the client's timeout, not interrupted instantly. Once the
   file is published the call returns OK even if cancellation arrives later;
   the host then imports or discards it.
   Memory: no whole-book allocation; 64 KiB buffers. */
reader_cloud_status reader_cloud_download(exr_webdav_client *client,
  const reader_cloud_request *request, reader_cloud_staged **staged,
  reader_cloud_error *error);

/* Read-only accessors. path is UTF-8 and valid until the staged value is
   consumed; sha256 is 64 lowercase hex digits. name is the remote display
   name, for display only. */
const char *reader_cloud_staged_path(const reader_cloud_staged *staged);
const char *reader_cloud_staged_name(const reader_cloud_staged *staged);
uint64_t reader_cloud_staged_bytes(const reader_cloud_staged *staged);
exr_format reader_cloud_staged_format(const reader_cloud_staged *staged);
const char *reader_cloud_staged_sha256(const reader_cloud_staged *staged);

/* Removes the staging file and frees the value; *staged becomes NULL. Safe for
   NULL. Use it after a cancellation between the phases. Never touches the SDK. */
void reader_cloud_staged_discard(reader_cloud_staged **staged);

typedef struct {
  size_t struct_size;
  /* Optional UTF-8 title. NULL/empty derives the title from the staged display
     name without its extension; if that is empty the SDK uses embedded
     metadata. Must be valid UTF-8 without control characters. */
  const char *title;
  /* 0 = the format ceiling; nonzero may only lower it. */
  uint64_t max_input_bytes;
  reader_cloud_control control;
} reader_cloud_import_options;

typedef struct {
  size_t struct_size;
  int committed;   /* 1 only after exr_sideload_import_file succeeded */
  int created;     /* 1 for a new SDK row; 0 for an exact duplicate */
  int64_t book_id; /* durable when committed */
  /* 1 when the staging copy was removed (always, once the call got as far as
     consuming the staged value). */
  int staging_removed;
} reader_cloud_import_result;

void reader_cloud_import_options_init(reader_cloud_import_options *options);

/* Phase 2, on the SDK owner. Consumes *staged: whatever the outcome (other
   than READER_CLOUD_ARGUMENT, which leaves it untouched) the staging file is
   removed, the value freed and *staged set to NULL. Only the staging copy is
   ever deleted; a committed or deduplicated SDK book is never removed on any
   failure path. Steps: cancellation check; re-read the staged file and verify
   length and SHA-256 (cancellable per 64 KiB; mismatch is READER_CLOUD_CORRUPT
   and the SDK is not entered); exr_sideload_import_file. The commit boundary is
   that SDK call: committed=1 wins over a later cancellation request and is
   reported with READER_CLOUD_OK; the SDK's own cancellation or rollback is
   READER_CLOUD_CANCELLED / READER_CLOUD_IMPORT with committed=0. created=0 is an
   exact duplicate whose existing title, progress and notes are preserved.
   On failure committed, created and book_id are zero; staging_removed still reports the cleanup. */
reader_cloud_status reader_cloud_import(exr_library *library,
  reader_cloud_staged **staged, const reader_cloud_import_options *options,
  reader_cloud_import_result *result, reader_cloud_error *error);

/* Derives a format from a display name extension (case-insensitive); returns
   EXR_CUSTOM when the extension is not one of the nine importable formats. */
exr_format reader_cloud_format_from_name(const char *display_name);
const char *reader_cloud_status_name(reader_cloud_status status);
#ifdef __cplusplus
}
#endif
#endif
