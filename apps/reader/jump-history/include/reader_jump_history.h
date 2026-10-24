/* SPDX-License-Identifier: MIT */
#ifndef READER_JUMP_HISTORY_H
#define READER_JUMP_HISTORY_H
#include <stddef.h>
#include <stdint.h>
#include <reader_reading_state.h>
#ifdef __cplusplus
extern "C" {
#endif
#define READER_JH_VERSION "0.1.0"
#define READER_JH_STRUCT_VERSION 1u
#define READER_JH_DEFAULT_ENTRIES 64u
#define READER_JH_MAX_ENTRIES 256u          /* hard cap, never clamped silently */
#define READER_JH_DEFAULT_BYTES 262144u
#define READER_JH_MIN_BYTES 4096u
#define READER_JH_MAX_BYTES 1048576u        /* hard cap on the accounted total */
#define READER_JH_MAX_ENTRY_BYTES 32768u    /* one accounted entry, wire + identity */

/* Bounded linear back/forward stack of reading positions, in memory only.
   One entry is the exact reading-state wire (progress put, anchor v1/v2) that
   the installed revision validator accepted, plus a private canonical location
   key derived from the decoded wire. An entry never holds an SDK handle, a
   reader_revisions pointer, an SDK note or a product revision row.

   The component never resolves and never navigates. reader_jh_commit encodes
   through reader_rs_encode_v2, which validates bytes and never inserts; the
   writer therefore creates no product revision, no SDK note, no SDK progress
   and no product catalog change. A landing only becomes a history entry when
   the caller says which landing it was (page, search, table of contents).
   A return target is a decoded copy: the host reloads the book named by
   book_key with the SDK owner it holds, calls reader_rs_resolve_* and moves
   the view only on FOUND. Not calling reader_jh_complete is the cancellation;
   the cursor stays where it was.

   Threads: a handle belongs to the thread that opened it. Every call from
   another thread fails with READER_JH_THREAD before any state is read or
   changed. reader_jh_adopt_thread hands ownership to the caller; the host must
   then guarantee that the previous thread no longer uses the handle. Handles
   are not synchronized. No call invokes a callback, so a call cannot reenter
   the handle. The reader_revisions pointer is borrowed for one call only and
   follows its own owner-thread rule.

   Errors: every call that returns an error leaves the history exactly as
   before (same count, cursor, accounted bytes and generation). The out
   structures are zeroed on entry, so a caller that reuses a reader_jh_item must
   call reader_jh_item_release first; reusing it without releasing loses the
   previous wire. reader_jh_item.wire is owned by the item and stays valid until
   reader_jh_item_release, independent of the history and of every SDK object
   that produced the capture.

   Accounting: an entry costs book_key + canonical location key + wire bytes.
   When a new entry does not fit, the oldest entries are dropped until both the
   entry count and the byte budget hold; the newest entry is never evicted. */
typedef struct reader_jh reader_jh;
typedef enum {
  READER_JH_OK=0, READER_JH_ARGUMENT, READER_JH_MEMORY,
  READER_JH_VERSION_UNSUPPORTED, /* unknown struct_version */
  READER_JH_LIMIT,               /* requested limit is above the hard cap or below the floor */
  READER_JH_THREAD,              /* called on a thread that does not own the handle */
  READER_JH_REVISION,            /* installed validator refused the wire; revision_code is set */
  READER_JH_NOT_REPRESENTABLE,   /* capture has no wire form; gap is set; nothing stored */
  READER_JH_TOO_LARGE,           /* one entry exceeds READER_JH_MAX_ENTRY_BYTES or the byte limit */
  READER_JH_EMPTY,               /* no entry in that direction */
  READER_JH_STALE                /* history changed since the item was read; nothing moved */
} reader_jh_status;
typedef struct {
  reader_jh_status code; reader_rs_status rs_code; reader_rs_gap gap;
  int revision_code; char message[160]; /* Fixed module text, never a supplied path or secret */
} reader_jh_error;

typedef struct {
  uint32_t struct_version;  /* READER_JH_STRUCT_VERSION */
  uint32_t max_entries;     /* 0 = 64; 1..256 */
  uint32_t max_bytes;       /* 0 = 262144; 4096..1048576 */
} reader_jh_limits;

/* The caller classifies how the position was reached. */
typedef enum { READER_JH_PAGE=1, READER_JH_SEARCH=2, READER_JH_TOC=3 } reader_jh_kind;
typedef enum { READER_JH_BACK=1, READER_JH_FORWARD=2 } reader_jh_direction;
typedef enum {
  READER_JH_ADDED=1,      /* new entry; forward entries were truncated */
  READER_JH_COALESCED=2,  /* PAGE after PAGE in the same book replaced the current entry */
  READER_JH_UNCHANGED=3   /* same book and location as the current entry; nothing changed */
} reader_jh_outcome;
typedef struct {
  reader_jh_outcome outcome;
  uint64_t entry_id;       /* id of the entry that is now current */
  size_t evicted;          /* oldest entries dropped by this call to honor the limits */
  size_t truncated;        /* forward entries dropped by this call */
  uint64_t generation;
} reader_jh_result;

/* One position handed to the history. capture and part are used exactly as
   reader_rs_encode_v2 documents them (part is the EPUB spine index, and it is
   what makes a repeated spine path addressable). */
typedef struct {
  const char *book_key;       /* global original identity, "format:sha256" */
  const char *parser_version; /* the SDK parser version of the capture */
  reader_jh_kind kind;
  const reader_rs_capture *capture;
  size_t part;
} reader_jh_position;

/* Opens an empty history. limits may be NULL. */
reader_jh_status reader_jh_open(const reader_jh_limits *limits,reader_jh **out,reader_jh_error *);
/* Frees the history on its owner thread; on error the handle stays valid. */
reader_jh_status reader_jh_close(reader_jh **,reader_jh_error *);
reader_jh_status reader_jh_adopt_thread(reader_jh *,reader_jh_error *);
/* Drops every entry and keeps the limits. A no-op on an empty history. */
reader_jh_status reader_jh_clear(reader_jh *,reader_jh_error *);

/* Encodes the capture with reader_rs_encode_v2 (which validates through the
   installed revision module and never inserts) and records it as the new
   current position. Call it after every landing, including ordinary page turns,
   so that the entry behind the cursor is the last position the user really
   read. Rules, in order: the same book and location as the current entry is
   UNCHANGED; a PAGE following a PAGE of the same book replaces the current
   entry (that is one landing, not two); any other landing is appended, even
   when the same place appears earlier in the history. A change drops all
   forward entries and then evicts the oldest entries until count and bytes fit
   the limits. NOT_REPRESENTABLE, REVISION and TOO_LARGE leave the history
   untouched. */
reader_jh_status reader_jh_commit(reader_jh *,reader_revisions *,const reader_jh_position *,
  reader_jh_result *,reader_jh_error *);
/* Same rules for a wire the host already encoded. Only an unchanged-format
   progress put with a location is accepted; annotations, deletes, unknown
   anchor versions and anything the validator refuses leave the history alone. */
reader_jh_status reader_jh_commit_wire(reader_jh *,reader_revisions *,reader_jh_kind kind,
  const void *wire,size_t bytes,reader_jh_result *,reader_jh_error *);

/* A copy of one entry. wire is owned by the item and valid until
   reader_jh_item_release, independent of the history and of every SDK object
   that produced the capture. */
typedef struct {
  uint32_t struct_version;
  reader_jh_direction direction;  /* 0 for reader_jh_item_at */
  reader_jh_kind kind;
  uint64_t entry_id, generation;
  size_t index, accounted_bytes;
  char book_key[73];
  char *wire; size_t wire_bytes;
} reader_jh_item;
/* Reads the neighbor in a direction without moving the cursor. EMPTY when
   there is none. The host decodes item.wire with reader_rs_decode, reloads the
   book named by book_key with its own SDK owner and resolves publicly. */
reader_jh_status reader_jh_peek(reader_jh *,reader_jh_direction,reader_jh_item *,reader_jh_error *);
reader_jh_status reader_jh_item_at(reader_jh *,size_t index,reader_jh_item *,reader_jh_error *);
/* Moves the cursor onto a peeked item, only after the host has actually
   navigated to a FOUND resolve. STALE if any change happened since the peek.
   Not calling it is the cancellation: an unresolved, ambiguous or cancelled
   target never moves the cursor. A zeroed item is ARGUMENT; any other unknown
   struct_version is VERSION_UNSUPPORTED. */
reader_jh_status reader_jh_complete(reader_jh *,const reader_jh_item *,reader_jh_error *);
/* Releases item.wire and zeroes the item. Safe on a zeroed item and on NULL. */
void reader_jh_item_release(reader_jh_item *);

typedef struct {
  uint32_t struct_version;
  size_t count, cursor, bytes, max_entries, max_bytes;
  int can_back, can_forward;
  uint64_t generation, evicted_total, truncated_total;
} reader_jh_state;
/* Zero-initialize *out; a non-zero struct_version must be the current one. */
reader_jh_status reader_jh_state_get(reader_jh *,reader_jh_state *,reader_jh_error *);
#ifdef __cplusplus
}
#endif
#endif
