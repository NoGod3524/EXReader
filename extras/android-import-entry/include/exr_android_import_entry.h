/* SPDX-License-Identifier: MIT */
#ifndef EXR_ANDROID_IMPORT_ENTRY_H
#define EXR_ANDROID_IMPORT_ENTRY_H
#include <exr_sideload.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Input: one ready request produced by the Java org.exreader.importentry.ImportEntry.
   All strings are borrowed UTF-8 and only read during the call. */
typedef struct {
  size_t struct_size;       /* set to sizeof(exr_android_import_request) */
  const char *path;         /* absolute path of the staged, immutable private file */
  exr_format format;        /* ImportFormat.exrCode(); EXR_CUSTOM is refused */
  const char *title;        /* display-name hint, may be NULL or empty */
  uint64_t size;            /* ReadyRequest.size(): must equal the file's size */
  exr_control control;      /* optional cancellation/progress, borrowed for the call */
} exr_android_import_request;

/* Imports the staged file through exr_sideload_import_file after verifying it is a regular,
   non-symlink file of exactly request->size bytes within the format ceiling (32 MiB reflow,
   128 MiB EPUB/CBZ/PDF). Synchronous; run it on the one thread that owns `library`. It reads the
   file only, does not delete or move it, retains nothing and spawns no thread. After EXR_OK,
   result->book_id is durable and created=0 means an exact duplicate kept the existing book; the
   host may then call ImportEntry.release. On any other status the file is untouched and the
   host decides whether to retry or release. Cancellation after the SDK commit returns the
   committed result. result is cleared on entry. */
exr_status exr_android_import_commit(exr_library *library, const exr_android_import_request *request,
    exr_sideload_result *result, exr_error *error);

#ifdef __cplusplus
}
#endif
#endif
