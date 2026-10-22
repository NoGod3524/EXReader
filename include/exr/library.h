/* SPDX-License-Identifier: MIT */
#ifndef EXR_LIBRARY_H
#define EXR_LIBRARY_H
#include "pdf.h"
#include "formats.h"
#define EXR_LIBRARY_VERSION "3.34.0"
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

/* Whole-book offsets and chapter-local offsets are different storage modes.
   Set struct_size before info_get. Valid-size payload fields are cleared on
   failure; records declaring a shorter prefix are rejected without tail writes. */
typedef struct {
  size_t struct_size;
  int bounded_storage, global_extent_known;
} exr_library_epub_info;
typedef struct {
  size_t part;
  char *path;
  exr_anchor selector; /* Normalized UTF-8 offsets within this part, not the book. */
} exr_epub_location;
typedef struct {
  int64_t id,book_id;
  exr_epub_location location;
  char *text;
} exr_epub_note;
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
/* Seekable original bytes, without parsing or a whole-book heap copy. On success
   the caller owns source.context: call source.release(source.context), or pass
   the source to a reader that takes ownership on successful open. The source
   keeps the database alive after library_close, including :memory: libraries.
   Metadata/progress writes through this owner remain readable. Deleting the
   book through this owner permanently invalidates its existing sources, even
   if a later insert reuses the ID. Any commit through another database
   connection conservatively invalidates these sources; reopen the source and
   reader to continue. Reads outside the advertised size return zero. A storage
   failure permanently invalidates the source; reader APIs report EXR_IO. Outputs are cleared
   on failure. Serialize use/release of each source; callbacks must not reenter
   the owner. Existing blob/snapshot APIs keep their original semantics. */
EXR_API exr_status exr_library_source(exr_library *library,int64_t id,exr_source *source,
                                      exr_error *error);
/* EPUB-only mode query. Source/file imports have unknown global text extent;
   existing memory imports retain their original whole-book extent. */
EXR_API exr_status exr_library_epub_info_get(exr_library *library,int64_t id,
  exr_library_epub_info *info,exr_error *error);
EXR_API void exr_epub_location_free(exr_epub_location *location);
/* Stores a caller-captured chapter-local point. part/path must describe the
   current package directory; selector.chapter, if present, must equal path.
   No chapter body is parsed and no text match is claimed. Capture/resolve with
   the bounded pager; only its FOUND result authorizes precise navigation.
   An empty exact string and start==end are required. */
EXR_API exr_status exr_library_epub_progress(exr_library *library,int64_t id,
  const exr_epub_location *location,exr_error *error);
/* Owned output strings; release with location_free. present denotes a stored
   record, not a resolved match. Missing records return OK with present=0.
   Failure clears the location/present; old global progress is never converted. */
EXR_API exr_status exr_library_epub_progress_get(exr_library *library,int64_t id,
  exr_epub_location *location,int *present,exr_error *error);
/* EPUB-only, single-part notes. New/reranged notes require an explicit nonempty
   quote selector captured by the bounded pager. Updating id>0 with exact=NULL
   changes only the comment: part/path/range inputs are ignored and the existing
   selector is retained. Updates check both note id and book id. No body is read.
   Stored selectors are not resolved matches; resolve before navigating. */
EXR_API exr_status exr_library_epub_note(exr_library *library,const exr_epub_note *note,
  int64_t *id,exr_error *error);
EXR_API exr_status exr_library_epub_notes(exr_library *library,int64_t book_id,
  exr_epub_note **notes,size_t *count,exr_error *error);
EXR_API void exr_epub_notes_free(exr_epub_note *notes,size_t count);
/* Note IDs belong to this API's own namespace, not exr_library_remove_note. */
EXR_API exr_status exr_library_remove_epub_note(exr_library *library,int64_t id,exr_error *error);
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
/* Streaming counterparts for large originals. The seekable source is borrowed
   only for the call; bytes are copied into SQLite in 64 KiB chunks, so the
   host never needs a contiguous copy. Source import supports EPUB/CBZ; file import
   additionally supports PDF, whose metadata is read through a read-only file
   mapping. EPUB imports read package metadata without loading XHTML; the ZIP
   source limit remains 128 MiB. Author/cover stay empty in this bounded mode,
   global extent is unknown, and legacy global progress/notes APIs return
   EXR_UNSUPPORTED. Use epub_info_get/epub_progress instead. Memory imports keep
   their snapshot behavior. Exact duplicates reuse the existing storage mode.
   Other formats return EXR_UNSUPPORTED. The source control callback is
   honored between chunks and beside archive/PDF header reads. A failed or
   cancelled write rolls back the book row and its blob; unique imports compare
   same-size stored sources byte-for-byte before reusing the oldest ID. */
EXR_API exr_status exr_library_import_source(exr_library *library,exr_format format,const exr_source *source,
                                             const char *title,int64_t *id,exr_error *error);
EXR_API exr_status exr_library_import_source_unique(exr_library *library,exr_format format,const exr_source *source,
                                                    const char *title,int64_t *id,int *created,exr_error *error);
/* Opens the path as a bounded source; no whole-file allocation is performed. */
EXR_API exr_status exr_library_import_file(exr_library *library,exr_format format,const char *path,
                                           const char *title,int64_t *id,exr_error *error);
EXR_API exr_status exr_library_import_file_unique(exr_library *library,exr_format format,const char *path,
                                                  const char *title,int64_t *id,int *created,exr_error *error);
/* Fixed reader over the stored original. CBZ pages are read on demand through
   exr_library_source and retain its library owner after exr_library_close.
   Metadata/progress writes through that owner preserve the open reader;
   deleting its book or a commit through another connection invalidates the
   source and requires reopening the reader. PDF bytes are paged into an anonymous mapping and parsed
   there, so the book is not materialized as one heap buffer. Falls back to
   EXR_UNSUPPORTED for formats without a streaming fixed reader. */
EXR_API exr_status exr_library_fixed_source(exr_library *library,int64_t id,const exr_fixed_open_options *options,
                                            exr_fixed_document **out,exr_error *error);
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
