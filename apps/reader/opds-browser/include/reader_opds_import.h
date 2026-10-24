/* SPDX-License-Identifier: MIT */
#ifndef READER_OPDS_IMPORT_H
#define READER_OPDS_IMPORT_H
#include <exr/library.h>
#include <exr_sideload.h>
#include "reader_opds_browser.h"

#ifdef __cplusplus
extern "C" {
#endif

/* SDK-owner phase. Runs on the thread that owns `library`, serialized with every other use of
   it, and never overlaps a network call that uses the same staged file. It creates no thread
   and keeps no state.

   Inputs: the result of reader_opds_acquire (struct_size, path, media_type, bytes, sha256).
   The staged file is re-read in 64 KiB steps and must still match the recorded byte count and
   SHA-256; a short, longer, replaced or unreadable file returns EXR_IO and imports nothing.
   bytes==0, an unknown media type or a broken descriptor returns EXR_ARGUMENT/EXR_UNSUPPORTED
   before any SDK import. A reparse point or a path that stopped being a plain file is not
   followed specially: it is opened as given and fails the size/digest check when it matters.

   The file is then handed to the public exr_sideload_import_file route, so the SDK is the only
   judge of whether the book is readable: a container that passed the network phase's structural
   check but is not a book returns the SDK's own status and leaves the library unchanged. The
   import is one commit: before it returns, either a new book row exists (result->created) or
   nothing changed. A committed result wins over a late cancellation, exactly as sideload
   documents.

   title is UTF-8; NULL or empty falls back to a fixed text. control is optional; it replaces
   nothing of the SDK's own limits (the sideload 128 MiB ceiling applies) and is copied for the
   call only. Neither the staged file nor the library is released or deleted here: call
   reader_opds_staged_discard when done, on the same owner thread. */
exr_status reader_opds_import_staged(exr_library *library, const reader_opds_acquired *staged,
                                     const char *title, const exr_control *control,
                                     exr_sideload_result *result, exr_error *error);

#ifdef __cplusplus
}
#endif
#endif
