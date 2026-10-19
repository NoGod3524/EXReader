/* SPDX-License-Identifier: MIT */
#ifndef EXR_LIBRARY_H
#define EXR_LIBRARY_H
#include "pdf.h"
#include "formats.h"
#define EXR_LIBRARY_VERSION "3.33.0"
#ifdef __cplusplus
extern "C" {
#endif
/* SQLite owns the original bytes and covers; there is no filesystem sidecar. */
typedef struct {
  int64_t id;
  exr_format format;
  char *title, *author, *tags;
  int favorite, status;
  size_t position;
} exr_book;
typedef struct {
  int64_t id, book_id;
  size_t start, end; /* SIZE_MAX when reanchoring could not locate the note. */
  char *text;
  exr_anchor anchor; /* Owned in query results; zero-initialize input notes. */
} exr_note;
typedef struct {
  int64_t id,book_id;
  size_t page,start,end; /* Zero-based page; UTF-8 range within that page. */
  char *text;
  exr_fixed_anchor anchor; /* Query output; writes capture the stored source. */
} exr_fixed_note;
/* Host-chosen audio_id keys are independent of source URIs and book row IDs. */
typedef struct { char *track_id; uint64_t offset_ms; double rate; } exr_audio_checkpoint;
typedef struct { int64_t id; char *label; exr_audio_checkpoint position; } exr_audio_bookmark;
EXR_API void exr_audio_checkpoint_free(exr_audio_checkpoint *position);
EXR_API exr_status exr_library_audio_resume(exr_library *library,const char *audio_id,const exr_audio_checkpoint *position,exr_error *error);
EXR_API exr_status exr_library_audio_resume_get(exr_library *library,const char *audio_id,exr_audio_checkpoint *position,int *found,exr_error *error);
EXR_API exr_status exr_library_audio_bookmark(exr_library *library,const char *audio_id,const exr_audio_bookmark *bookmark,int64_t *id,exr_error *error);
EXR_API exr_status exr_library_audio_bookmarks(exr_library *library,const char *audio_id,exr_audio_bookmark **bookmarks,size_t *count,exr_error *error);
EXR_API void exr_audio_bookmarks_free(exr_audio_bookmark *bookmarks,size_t count);
EXR_API exr_status exr_library_remove_audio_bookmark(exr_library *library,int64_t id,exr_error *error);
EXR_API exr_status exr_library_clear_audio(exr_library *library,const char *audio_id,exr_error *error);
EXR_API exr_status exr_library_open(const char *path, exr_library **out, exr_error *error);
EXR_API void exr_library_close(exr_library *library);
/* Imports original bytes (including PDF/CBZ) and the first declared reflow cover-image up to 8 MiB.
   Larger covers remain in the original source; failed cover reads abort the insert. */
EXR_API exr_status exr_library_import(exr_library *library, exr_format format, const void *data,
                                      size_t size, const char *title, int64_t *id,
                                      exr_error *error);
/* Opt-in exact deduplication: same format and original bytes reuse the oldest ID.
   Existing metadata, progress, cover and notes stay untouched. created is 1 only
   for an inserted row. Lookup/insert commit atomically across library handles;
   failure clears id/created. Ordinary import still permits duplicate records. */
EXR_API exr_status exr_library_import_unique(exr_library *library,exr_format format,const void *data,
                                             size_t size,const char *title,int64_t *id,int *created,exr_error *error);
EXR_API exr_status exr_library_books(exr_library *library, const char *query, exr_book **books,
                                     size_t *count, exr_error *error);
EXR_API void exr_books_free(exr_book *books, size_t count);
EXR_API exr_status exr_library_update(exr_library *library, const exr_book *book, exr_error *error);
EXR_API exr_status exr_library_document(exr_library *library, int64_t id, exr_document **doc,
                                        exr_error *error);
/* PDF/CBZ books keep page-count extent and zero-based page progress. */
EXR_API exr_status exr_library_fixed(exr_library *library,int64_t id,const exr_fixed_open_options *options,
                                      exr_fixed_document **out,exr_error *error);
EXR_API exr_status exr_library_fixed_note(exr_library *library,const exr_fixed_note *note,const exr_control *control,
                                           int64_t *id,exr_error *error);
EXR_API exr_status exr_library_fixed_notes(exr_library *library,int64_t book_id,exr_fixed_note **notes,
                                            size_t *count,exr_error *error);
EXR_API void exr_fixed_notes_free(exr_fixed_note *notes,size_t count);
EXR_API exr_status exr_library_remove_fixed_note(exr_library *library,int64_t id,exr_error *error);
EXR_API exr_status exr_library_cover(exr_library *library, int64_t id, const void *data,
                                     size_t size, exr_error *error);
/* New/reranged notes capture a selector from the stored book. Updating only text
   preserves the old selector (including legacy). A non-NULL anchor.exact explicitly
   supplies a replacement selector, whose start/end must equal the note range. */
EXR_API exr_status exr_library_note(exr_library *library, const exr_note *note, int64_t *id,
                                    exr_error *error);
EXR_API exr_status exr_library_notes(exr_library *library, int64_t book_id, exr_note **notes,
                                     size_t *count, exr_error *error);
/* Edits only the comment, including notes whose current range is unresolved. */
EXR_API exr_status exr_library_note_text(exr_library *library,int64_t note_id,const char *text,exr_error *error);
EXR_API void exr_notes_free(exr_note *notes, size_t count);
/* Fast reflow progress persistence: host captures a point with anchor_create()
   from its current document. The SDK validates it and updates position/selector
   atomically without reparsing source. Getter owns strings (anchor_free), or
   returns LEGACY and the numeric position when no selector has been saved. */
EXR_API exr_status exr_library_progress(exr_library *library,int64_t book_id,const exr_anchor *point,exr_error *error);
EXR_API exr_status exr_library_progress_get(exr_library *library,int64_t book_id,exr_anchor *point,exr_anchor_state *state,exr_error *error);
/* Removes the selector, retaining the numeric book position. */
EXR_API exr_status exr_library_clear_progress(exr_library *library,int64_t book_id,exr_error *error);
EXR_API exr_status exr_library_blob(exr_library *library, int64_t id, int cover, void **data,
                                    size_t *size, exr_error *error);
EXR_API exr_status exr_library_remove_note(exr_library *library, int64_t id, exr_error *error);
typedef struct { int64_t note_id; size_t previous_start,previous_end; exr_anchor_match match; } exr_note_relocation;
typedef struct {
  size_t previous_size,text_size,previous_position,position;
  exr_anchor_match progress; exr_note_relocation *notes; size_t note_count;
} exr_library_relocation;
/* Reparse stored reflow source and atomically refresh extent, progress and note
   positions. Unique matches move; unresolved notes retain comments/selectors,
   return SIZE_MAX ranges, and never become guessed highlights. Host supplies a
   valid UTF-8 fallback position for unresolved progress. Report is owned. */
EXR_API exr_status exr_library_reanchor(exr_library *library,int64_t book_id,size_t fallback_position,
                                         const exr_control *control,exr_library_relocation *report,exr_error *error);
EXR_API void exr_library_relocation_free(exr_library_relocation *report);
EXR_API exr_status exr_library_backup(exr_library *library, const char *path, exr_error *error);
EXR_API exr_status exr_library_delete(exr_library *library, int64_t id, exr_error *error);
#ifdef __cplusplus
}
#endif
#endif
