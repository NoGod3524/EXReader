/* SPDX-License-Identifier: MIT */
#ifndef READER_ANNOTATION_VIEW_H
#define READER_ANNOTATION_VIEW_H
#include <stddef.h>
#include <stdint.h>
#include <reader_revisions.h>
#ifdef __cplusplus
extern "C" {
#endif
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
#define READER_ANNOTATION_VIEW_VERSION "0.2.0"
#else
#define READER_ANNOTATION_VIEW_VERSION "0.1.0"
#endif
#define READER_AV_BATCH_MAX 100u
/* One SAFE item is built from one retained revision of at most 1 MiB, and every
   decoded string is a substring of it, so an item never exceeds this plus its
   fixed struct. */
#define READER_AV_ITEM_BYTES_MAX ((size_t)1048576)
#define READER_AV_PAGE_BYTES_MIN ((size_t)2097152)
#define READER_AV_PAGE_BYTES_DEFAULT ((size_t)16777216)
#define READER_AV_PAGE_BYTES_MAX ((size_t)67108864)

/* Per-book bookmark and annotation list snapshots over the unchanged product
   revision history. Strictly read-only: it never navigates, resolves against
   the SDK, writes product history, the outbox, SDK notes or reading progress.
   It calls only reader_revision_annotations_page and reader_rs_decode.

   Owner: the reader_revisions store passed to open is borrowed from the host
   owner and must outlive every reader_av_page/close call (not the pages it
   returned). The view, its calls and close run on the thread that opened it;
   another thread gets READER_AV_OWNER before touching the store. A call made
   from inside this view's cancel callback gets READER_AV_BUSY and changes
   nothing, and so does a refused close.

   Snapshot: a returned page owns every byte it exposes in one allocation. It is
   independent of the view, the store and the SDK, may be read after all of
   them were closed, and is released exactly once with reader_av_page_free.
   Each page is one read snapshot of the store; successive pages are keyset
   pages (no OFFSET) over the distinct global annotation IDs of one book, so a
   concurrent insert or delete never duplicates a row of an unchanged range.

   Content: only a SAFE state carries revision identity and body. Any other
   state (CONCURRENT, PENDING_PARENTS, BLOCKED_RESTORE, MISSING) shows the true
   graph counts and nothing else: this module never selects a head and never
   invents a quote, note or location. A SAFE tombstone is shown as a tombstone
   without a body. Whether a selector can be found is not decided here:
   resolution starts as NOT_ATTEMPTED and only the host, after its own public
   SDK resolve, may record FOUND/MISSING/AMBIGUOUS/LEGACY with
   reader_av_page_set_resolution. Anchor version 1 is shown as legacy_anchor,
   and an EPUB anchor v1 has no spine index (has_part == 0).

   Budgets: limit 1..100 rows. The sum of retained wire bytes plus 512 bytes
   per row never exceeds max_page_bytes (2 MiB..64 MiB, default 16 MiB); a page
   that would exceed it stops before that row and reports budget_stopped with
   an unfinished cursor, so no row is skipped. The output never exceeds the
   same budget. Cancellation: the cancel callback is polled at the entry, before
   the store call, for every row inside it, before and after every decode and
   before returning. Any non-OK status discards the page completely and leaves
   the caller's cursor valid for an exact retry. */
typedef enum {
  READER_AV_OK=0,
  READER_AV_ARGUMENT,   /* NULL, size, limit, option or book key error */
  READER_AV_MEMORY,
  READER_AV_REVISION,   /* the store refused; revision_code is set */
  READER_AV_DECODE,     /* a SAFE wire was refused by reader_rs_decode; decode_code is set */
  READER_AV_CONTRACT,   /* store output violated order, book or identity rules */
  READER_AV_CURSOR,     /* cursor of another view, book, direction or malformed */
  READER_AV_CANCELLED,
  READER_AV_BUSY,       /* reentrant use of a view inside one of its calls */
  READER_AV_OWNER,      /* another thread used the view */
  READER_AV_LIMIT       /* a single row cannot fit the page budget */
} reader_av_status;
typedef struct {
  reader_av_status code;
  int revision_code, decode_code;
  char message[160];
} reader_av_error;

typedef enum {
  READER_AV_STATE_MISSING=0, READER_AV_STATE_SAFE=1, READER_AV_STATE_CONCURRENT=2,
  READER_AV_STATE_PENDING_PARENTS=3, READER_AV_STATE_BLOCKED_RESTORE=4
} reader_av_state;
typedef enum {
  READER_AV_KIND_UNAVAILABLE=0, /* any non-SAFE state: nothing is claimed */
  READER_AV_KIND_BOOKMARK=1,    /* SAFE put/restore with an empty point selector */
  READER_AV_KIND_HIGHLIGHT=2,   /* SAFE range quote without a note */
  READER_AV_KIND_NOTE=3,        /* SAFE range quote with a nonempty note */
  READER_AV_KIND_TOMBSTONE=4    /* SAFE delete: no body */
} reader_av_kind;
typedef enum { READER_AV_MODE_NONE=0, READER_AV_MODE_REFLOW=1, READER_AV_MODE_EPUB=2, READER_AV_MODE_FIXED=3 } reader_av_mode;
typedef enum {
  READER_AV_RESOLUTION_NOT_ATTEMPTED=0, READER_AV_RESOLUTION_FOUND, READER_AV_RESOLUTION_MISSING,
  READER_AV_RESOLUTION_AMBIGUOUS, READER_AV_RESOLUTION_LEGACY
} reader_av_resolution;

typedef struct {
  char annotation_id[33];            /* lowercase 32-hex, unique within the book */
  reader_av_state state;
  reader_av_kind kind;
  size_t revisions, heads, missing_parents, foreign_parents; /* true graph counts, any state */
  int deleted, requires_restore;
  int content_available;             /* 1 only for SAFE bookmark/highlight/note */
  /* The fields below are zero/NULL unless state is SAFE. */
  char revision_id[33], operation[8], sha256[65];
  size_t wire_bytes;
  reader_av_mode mode;               /* retained even by a tombstone */
  int has_location, legacy_anchor;   /* legacy_anchor: anchor_version == 1 */
  uint64_t anchor_version;
  char parser_version[65];
  int has_part; uint64_t part;       /* EPUB anchor v2 spine index */
  int has_page; uint64_t page;       /* fixed page hint; page_id is the route */
  uint64_t start, end;               /* UTF-8 byte offset hints, never a fallback */
  char *part_path, *page_id;         /* NULL when the mode has none */
  char *exact, *prefix, *suffix;     /* non-NULL (possibly empty) when has_location */
  size_t exact_size, prefix_size, suffix_size;
  char *chapter;                     /* NULL: unscoped reflow capture */
  char *note_text;                   /* non-NULL when has_location; bookmark label or note */
  size_t note_size;
  reader_av_resolution resolution;   /* host-recorded only */
} reader_av_item;

/* Plain value bound to one view's book. direction is +1/-1 (bytewise ascending
   or descending annotation_id); after_id is the last ID already shown. */
typedef struct {
  uint32_t version; /* 1 */
  int32_t direction;
  uint64_t binding;
  uint32_t has_after, complete;
  char book_key[73];
  char after_id[33];
} reader_av_cursor;

/* Owned by the page; release with reader_av_page_free exactly once. */
typedef struct {
  reader_av_item *items;
  size_t count;
  reader_av_cursor next;    /* continues the same direction after the last item */
  reader_av_cursor reverse; /* opposite direction, strictly before the first item;
                               for an empty page the input cursor, direction flipped */
  int complete;             /* nothing remains in this direction (fewer rows than limit) */
  int budget_stopped;       /* the page ended early because of max_page_bytes */
  size_t output_bytes, wire_bytes;
  uint64_t revision_rows, polls;
} reader_av_page;

typedef struct reader_av_view reader_av_view;
/* Return nonzero to cancel. Runs on the owner thread; it must not use this view
   (BUSY) and may only use the store through calls the store itself allows. */
typedef int (*reader_av_cancel_fn)(void *context);
typedef struct {
  size_t struct_size;            /* sizeof this struct */
  reader_av_cancel_fn cancel;    /* NULL: never cancelled */
  void *cancel_context;          /* borrowed until close */
  size_t max_page_bytes;         /* 0: default; otherwise MIN..MAX */
} reader_av_options;

/* book_key is the global "format:sha256" original identity (copied). The store
   is borrowed. *out is NULL on failure. options may be NULL. */
reader_av_status reader_av_open(reader_revisions *store,const char *book_key,const reader_av_options *options,
  reader_av_view **out,reader_av_error *error);
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
reader_av_status reader_av_open_raw_v3(reader_revisions *,const char *,const reader_av_options *,
  reader_av_view **,reader_av_error *);
#endif
/* Start of the list in one direction; pure, always allowed. */
reader_av_status reader_av_cursor_start(const reader_av_view *view,int direction,reader_av_cursor *cursor,reader_av_error *error);
/* One snapshot page after `from`, limit 1..100. *page is zeroed first; on a
   non-OK status it stays empty and from is unchanged. */
reader_av_status reader_av_page_get(reader_av_view *view,const reader_av_cursor *from,size_t limit,
  reader_av_page *page,reader_av_error *error);
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
/* Nullable selector tags are copied exactly; NULL exact never grants content
   availability or FOUND. Resolution remains the host's explicit public SDK call. */
reader_av_status reader_av_page_get_raw_v3(reader_av_view *,const reader_av_cursor *,size_t,
  reader_av_page *,reader_av_error *);
#endif
/* Host bookkeeping after its own SDK resolve; never touches anything else. */
reader_av_status reader_av_page_set_resolution(reader_av_page *page,size_t index,reader_av_resolution resolution,
  reader_av_error *error);
void reader_av_page_free(reader_av_page *page);
/* Frees the view and sets *view to NULL. BUSY/OWNER keep the handle. It never
   touches the borrowed store. */
reader_av_status reader_av_close(reader_av_view **view,reader_av_error *error);
#ifdef __cplusplus
}
#endif
#endif
