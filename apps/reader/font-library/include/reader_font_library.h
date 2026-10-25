/* SPDX-License-Identifier: MIT */
#ifndef READER_FONT_LIBRARY_H
#define READER_FONT_LIBRARY_H
#include <exr/text.h>
#ifdef __cplusplus
extern "C" {
#endif
#define RFL_VERSION 1u
#define RFL_HASH_BYTES 65u
#define RFL_NAME_BYTES 256u
typedef enum {
  RFL_OK=0, RFL_ARGUMENT, RFL_ENCODING, RFL_LIMIT, RFL_IO, RFL_FONT,
  RFL_CANCELLED, RFL_CHANGED, RFL_BUSY, RFL_THREAD, RFL_NOT_FOUND,
  RFL_MANIFEST_VERSION, RFL_CORRUPT, RFL_MISSING, RFL_UNSUPPORTED,
  RFL_COMMIT_UNCERTAIN, RFL_MEMORY
} rfl_status;
typedef struct rfl_library rfl_library;
typedef struct rfl_lease rfl_lease;
typedef struct { rfl_status code; char message[192]; } rfl_error;
typedef struct { uint64_t font_bytes, directory_bytes; uint32_t entries; } rfl_limits;
typedef struct { char hash[RFL_HASH_BYTES]; char display_name[RFL_NAME_BYTES]; uint64_t bytes; } rfl_record;
/* Host source is borrowed only during import. Immutable seekable reads: offset
   == declared size must return zero; offset beyond it is never requested. Short
   reads are retried. A second full pass detects changing bytes. No callback may
   throw, destroy, or reenter this library (reentry is rejected BUSY). */
typedef rfl_status (*rfl_read_fn)(void *context, uint64_t offset, void *buffer,
                                size_t capacity, size_t *read_bytes);
typedef struct { uint64_t bytes; rfl_read_fn read; void *context; } rfl_source;
/* Synchronous observation/cancellation on the owner thread. Stage names:
   copy, verify, validated, file-published, committed. Return nonzero to cancel
   before commit; committed is notification only and cannot cancel publication.
   The callbacks are host observability, not test-only hooks. */
typedef int (*rfl_progress_fn)(void *context, const char *stage, uint64_t done, uint64_t total);
typedef struct { rfl_progress_fn progress; void *context; } rfl_control;
rfl_limits rfl_limits_default(void);
/* Existing absolute private directory; host owns access control and must not
   mutate it outside this API. All path components reject symlinks/reparse points.
   Cross-process exclusive lock lasts until close. Thread-affine: calls from
   another thread return THREAD. No product schema or system font registration.
   Failure clears *out; null limits selects defaults. */
rfl_status rfl_open(const char *directory_utf8, const rfl_limits *limits, rfl_library **out, rfl_error *error);
/* BUSY while any lease exists; the caller must free SDK layouts/pagers using
   borrowed fonts before releasing the lease. Close and release return errors
   rather than silently destroying a handle on a wrong thread or in reentry. */
rfl_status rfl_close(rfl_library *library, rfl_error *error);
/* Names are display-only, 1..255 bytes strict UTF-8, no controls, slash/backslash.
   Files are streamed <=64 KiB, checked after open, copied privately then SDK
   validated before publication. Same hash returns created=0, preserves name.
   Import validates face 0; it does not enumerate or claim every TTC face.
   On any failure record and created are zero. Cancellation before the manifest
   commit leaves the previous set. COMMIT_UNCERTAIN requires close/reopen. */
rfl_status rfl_import_file(rfl_library *, const char *selected_path_utf8, const char *display_name,
                           const rfl_control *, rfl_record *out, int *created, rfl_error *);
rfl_status rfl_import_source(rfl_library *, const rfl_source *, const char *display_name,
                             const rfl_control *, rfl_record *out, int *created, rfl_error *);
/* Caller-owned fixed records; sorted by hash. Out-of-range index is NOT_FOUND. */
rfl_status rfl_count(rfl_library *, size_t *out, rfl_error *);
rfl_status rfl_get(rfl_library *, size_t index, rfl_record *out, rfl_error *);
rfl_status rfl_find(rfl_library *, const char *hash, rfl_record *out, rfl_error *);
/* Explicit face selection is delegated to the frozen SDK; no second parser or
   face enumeration. face_index <=65535 (named-instance encoding unsupported).
   The borrowed SDK pointer is owned by lease: never exr_font_free it. Font use
   follows SDK serialization. At most 32 leases / 128 MiB encoded bytes may
   be live; SDK-owned copied bytes and decoded caches are additional memory.
   Lease is owner-thread bound and retains library.
   SDK copies mapped bytes, so no dangling mapped file after this call. */
rfl_status rfl_font_open(rfl_library *, const char *hash, unsigned face_index,
                         rfl_lease **out, rfl_error *);
rfl_status rfl_lease_font(rfl_lease *, exr_font **out, rfl_error *);
rfl_status rfl_lease_release(rfl_lease *, rfl_error *);
/* Active leases make remove BUSY. Atomic manifest removal precedes unlink;
   unlink failure yields COMMIT_UNCERTAIN (the font may be logically removed).
   Recovery reopens the authoritative manifest and cleans unreferenced managed
   files, never selected source files. No rollback is claimed after commit. */
rfl_status rfl_remove(rfl_library *, const char *hash, rfl_error *);
#ifdef __cplusplus
}
#endif
#endif
