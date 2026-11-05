/* Experimental opt-in adapter; no changes to the frozen SDK ABI. */
#ifndef BOUNDED_TXT_H
#define BOUNDED_TXT_H
#include "exreader.h"
/* Cursor is a source byte offset, committed only on success. The source must be
   immutable across calls. Only UTF-8 with LF line endings is currently handled.
   A line longer than the 64 KiB window, CR, UTF-16, or a BOM at a noninitial
   window boundary returns an error. At EOF returns OK with *out == NULL. */
exr_status bounded_txt_next(const exr_source *source, uint64_t *cursor,
                            exr_document **out, exr_error *error);
#endif
