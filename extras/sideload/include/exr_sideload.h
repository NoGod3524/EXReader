/* SPDX-License-Identifier: MIT */
#ifndef EXR_SIDELOAD_H
#define EXR_SIDELOAD_H
#include <exr/library.h>

#ifdef __cplusplus
extern "C" {
#endif

#define EXR_SIDELOAD_STREAM_LIMIT (UINT64_C(128) * 1024 * 1024)
#define EXR_SIDELOAD_MEMORY_LIMIT (UINT64_C(32) * 1024 * 1024)

typedef struct {
  size_t struct_size;
  /* Zero selects the format limit. Nonzero values can lower, never raise it. */
  uint64_t max_input_bytes;
  /* Supplied callbacks replace source.control; otherwise it is inherited. */
  exr_control control;
} exr_sideload_options;

typedef struct {
  size_t struct_size;
  int64_t book_id;
  int created;
} exr_sideload_result;

/* Synchronous imports into a borrowed library; serialize its use externally.
   Titles and paths are UTF-8 strings.
   Set struct_size on options/results. NULL options selects the defaults.
   EPUB/CBZ use the borrowed immutable random-read source without a whole-file
   allocation (128 MiB ceiling). Other reflow formats use at most 32 MiB of
   temporary input memory. PDF requires the stable-file entry below.
   Neither the source nor its context is retained or released by this module.
   Source reads and copying honor cancellation. Snapshot SDK import has no
   control argument: cancellation is checked before entering it, and a committed
   result wins. There is no implicit deletion, including on duplicate imports. */
exr_status exr_sideload_import_source(exr_library *library, exr_format format,
    const exr_source *source, const char *title, const exr_sideload_options *options,
    exr_sideload_result *result, exr_error *error);

/* UTF-8 path to an app-owned file that remains immutable at this path until
   return. PDF metadata and original bytes may be opened separately by the SDK.
   EPUB/CBZ follow the source route; PDF uses the public streaming file import.
   The PDF SDK call has no control argument and cannot be interrupted here.
   Cancellation is checked before it; its committed result is returned intact.
   No spool, path ownership transfer, background task or automatic deletion. */
exr_status exr_sideload_import_file(exr_library *library, exr_format format,
    const char *path, const char *title, const exr_sideload_options *options,
    exr_sideload_result *result, exr_error *error);

/* Export the exact original through public library_source, using at most 64KiB
   of copy memory and a 128MiB ceiling (options may lower it). Run on the SDK
   owner, without callback reentry. destination is a new UTF-8 filename in an
   existing app-private directory. The host keeps this directory stable.
   Publish is atomic and never replaces an existing destination, even on retry.
   On failure bytes_written remains zero; only this call's temporary file is
   removed. After success the source is released and no SDK handle is retained.
   Only then may the host pass the immutable file to a network worker; existing
   sync length/SHA-256 verification still establishes its global book identity.
   Options use the same struct_size/control/max_input_bytes rules as imports.
   Cancellation before publish removes the temporary; a published result wins.
   A process killed before publish may leave an unreferenced .exr-export temp. */
exr_status exr_sideload_export_original(exr_library *,int64_t book_id,
    const char *destination,const exr_sideload_options *,uint64_t *bytes_written,
    exr_error *);

#ifdef __cplusplus
}
#endif
#endif
