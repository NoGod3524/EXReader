/* SPDX-License-Identifier: MIT */
#ifndef READER_READING_COMMANDS_H
#define READER_READING_COMMANDS_H
#include <reader_projection.h>
#include <reader_reading_state.h>
#define READER_READING_COMMANDS_VERSION "0.1.0"
#ifdef __cplusplus
extern "C" {
#endif
/* Product-typed reading commands over the unchanged wire v1 envelope with
   reading anchor v1/v2: save progress, point bookmark, range highlight, note
   body edit, and explicit delete/restore. One call encodes one new local
   revision with reader_rs_encode_v2 and commits history+outbox through
   reader_revision_local_reading. It never writes SDK notes or progress,
   never changes the current page, never guesses an anchor from percentages or
   page numbers, and adds no entity. Calls use the store's owner worker
   without reentry. Output and error text is fixed and bounded. A product
   revision is never copied into SDK notes; the host may navigate the current
   page only after the public resolve result FOUND and an explicit user accept. */
typedef enum {
  READER_RC_OK=0, READER_RC_ARGUMENT, READER_RC_MEMORY,
  READER_RC_ENCODE,      /* capture has no lossless wire form; encode.gap says why */
  READER_RC_UNSAFE,      /* observed heads are stale/incomplete or history is not safe; nothing committed */
  READER_RC_REVISION,    /* another revision-module refusal; revision.code is set */
  READER_RC_SOURCE       /* edit source head is missing, not safe, or a tombstone */
} reader_rc_status;
typedef enum { READER_RC_PROGRESS=1, READER_RC_BOOKMARK=2, READER_RC_HIGHLIGHT=3, READER_RC_NOTE_TEXT=4 } reader_rc_kind;
typedef enum { READER_RC_PUT=0, READER_RC_DELETE=1, READER_RC_RESTORE=2 } reader_rc_operation;

typedef struct {
  reader_revisions *store;
  /* Required stable 32-hex lowercase ID chosen by the caller. Reuse it with the
     same inputs after an uncertain response: the exact bytes are a no-op. */
  const char *revision_id;
  /* Complete head set observed by the caller (0..32 unique IDs). Never selected here. */
  const char *const *expected_heads; size_t expected_count;
  /* Required for progress/bookmark/highlight put/restore. Ignored for note edit
     (the original parser version is preserved) and delete. */
  const char *parser_version;
} reader_rc_context;

typedef struct {
  reader_rc_kind kind; reader_rc_operation operation;
  const char *book_key;
  /* Progress: NULL/empty. Others: 32-hex ID; empty only creates (put, no heads) and
     lets the module allocate it. A retry with the same revision_id and an empty ID
     re-derives the identity of the revision already retained under that ID, so a
     lost first response is an exact no-op instead of a second entity. */
  const char *annotation_id;
  /* Real public-SDK capture. Bookmark requires a point, highlight a nonempty
     range, progress either. Delete names only the mode. NOTE_TEXT ignores it
     and keeps the selected head's selector exactly. */
  const reader_rs_capture *capture;
  size_t part;            /* spine index for EPUB captures (anchor v2); other modes ignore */
  const char *text;       /* annotation body, UTF-8, at most 65536 bytes; NULL for progress/delete */
} reader_rc_command;

typedef struct {
  reader_rc_status code;
  reader_rs_error encode;
  reader_revision_error revision;
  char message[160];
} reader_rc_error;
typedef struct {
  /* Assigned before committing and retained on failure for exact retry. */
  char entity_key[257], annotation_id[33], revision_id[33], sha256[65];
  size_t bytes;
  reader_revision_info revision;
  int created;            /* 1 only for the call that committed; 0 for exact retry */
} reader_rc_result;

reader_rc_status reader_rc_apply(const reader_rc_context *, const reader_rc_command *,
  reader_rc_result *, reader_rc_error *);
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
/* Explicit candidate fixed_page writer. New captures use anchor3; NOTE_TEXT
   keeps the selected source's actual version and nullable selector tags. */
reader_rc_status reader_rc_apply_fixed_v3(const reader_rc_context *,const reader_rc_command *,
  reader_rc_result *,reader_rc_error *);
#endif
#ifdef __cplusplus
}
#endif
#endif
